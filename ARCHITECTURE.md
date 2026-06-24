# Architecture

A contributor-focused tour of how Contextra is wired. For product framing and
the API reference, see [README.md](README.md).

---

## Mental model

Contextra is a **linear pipeline behind a thin API**. Everything an analysis
needs is derived from one object — a pandas `DataFrame` produced by ingestion —
and each later stage only reads that DataFrame plus the previous stage's JSON.

```
HTTP ──► main.py ──► tasks.run_pipeline ──► [ingest ─► profile ─► semantic ─► score] ──► DB ──► HTTP
```

There is no shared mutable state between stages, no hidden globals. A stage is a
pure-ish function: `DataFrame (+ prior JSON) → JSON`. That's what makes the
services independently testable and swappable.

---

## Request lifecycle

### 1. Ingestion (synchronous part)
`POST /api/datasets/upload` (`app/main.py`):
1. Validates the file is a `.csv`.
2. Generates a 12-char hex `dataset_id`.
3. Persists raw bytes via `storage.save_upload` → `data/raw/<id>__<name>.csv`.
4. Writes a `Dataset` row (`status="pending"`) and a `DatasetFile` row.
5. Enqueues `run_pipeline` as a FastAPI **BackgroundTask** and returns immediately.

The Postgres path (`/api/datasets/connect`) skips file storage and passes a DSN
+ table name into the same pipeline.

### 2. The pipeline (asynchronous part)
`app/tasks.py::run_pipeline` owns its own DB session and a single transaction
boundary per outcome:

```
status = "profiling"
df    = ingestion.load_csv | load_postgres
prof  = profiler.profile_dataframe(df)
sem   = semantic.build_semantic_map(df)
score = scoring.score_dataset(prof, sem)
merge Profile / SemanticMap / ReadinessScore
status = "done"          # or "failed" + error on any exception
```

Any exception is caught, the transaction rolled back, and the dataset marked
`failed` with a truncated error string — so the UI always has something to show.

### 3. Results
The Results API reads the persisted JSON straight off the ORM relationships.
`/report` joins all three result tables into one response so the UI needs a
single round-trip.

---

## Status lifecycle

```
pending ──► profiling ──► done
                      └──► failed (error stored)
```

The UI polls `GET /api/datasets/{id}` every ~1.2s until the status is terminal.

---

## Module responsibilities

| Module | Responsibility | Depends on |
|---|---|---|
| `config.py` | Env-driven settings; creates the data dir | — |
| `database.py` | Engine, `SessionLocal`, `Base`, `init_db()` | `config` |
| `models.py` | ORM tables + relationships | `database` |
| `schemas.py` | Pydantic response shapes | — |
| `storage.py` | Raw-file persistence (local FS) | `config` |
| `services/ingestion.py` | Source → normalized `DataFrame` | pandas |
| `services/profiler.py` | Stats + PII detection | pandas, numpy, `config` |
| `services/semantic.py` | Semantic typing + entities (heuristic/LLM) | pandas, `config` |
| `services/scoring.py` | 5-dimension weighted score | — (pure dict math) |
| `tasks.py` | Orchestrates the pipeline, owns persistence | all services, `models` |
| `main.py` | Routes, DI, static UI | `tasks`, `models`, `schemas` |

**Dependency direction is one-way:** services know nothing about the web layer,
the database, or each other. `tasks.py` is the only place that wires services to
persistence; `main.py` is the only place that wires HTTP to `tasks`.

---

## Key design decisions

- **DataFrame as the universal interchange.** Adding a source = adding one
  loader in `ingestion.py`; nothing downstream changes.
- **JSON columns for results.** Profiler/semantic/scoring outputs evolve fast;
  storing them as `JSON` keeps the schema stable and migrations rare.
- **Heuristic-first AI.** The semantic engine is fully offline by default and
  only calls an LLM for low-confidence columns, with a silent fallback — so the
  product never hard-depends on a network or key.
- **BackgroundTasks over Celery (for now).** Zero-infra is the MVP's headline
  feature. `run_pipeline` is already a self-contained function with its own
  session, so promoting it to a Celery task is a near-mechanical change.
- **SQLAlchemy over raw SQL.** One code path serves SQLite and Postgres.

---

## Extension points

| You want to… | Touch only… |
|---|---|
| Support a new file format / warehouse | `services/ingestion.py` (add a loader) + a route in `main.py` |
| Add a profiling metric | `services/profiler.py` (`profile_dataframe`) |
| Improve column meaning | `services/semantic.py` (`_HEURISTICS` table or the LLM prompt) |
| Re-weight or add a score dimension | `services/scoring.py` (`WEIGHTS` + `score_dataset`) |
| Swap storage to S3 | `storage.py` (keep the `save_upload` signature) |
| Make jobs durable | `tasks.py` (wrap `run_pipeline` as a Celery task) |
| Replace the UI | `app/static/` (the REST API is already the contract) |

---

## Data flow types (at a glance)

```
ingestion.normalize(df)        → { columns: [{name, type}], row_count }
profiler.profile_dataframe(df) → { row_count, columns: { <col>: {null_rate, uniqueness,
                                    cardinality, outliers, pii, sample_values, ...} } }
semantic.build_semantic_map(df)→ { columns: { <col>: {normalized_name, semantic_type,
                                    entity, confidence, source} }, entities_detected: [...] }
scoring.score_dataset(p, s)    → { ai_readiness_score, grade, dimensions, weights, issues }
```

Each arrow is a stable contract — keep these shapes when you extend a stage and
the rest of the system keeps working.
