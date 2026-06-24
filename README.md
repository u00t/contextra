# Contextra

> **Make your data AI-ready.** Ingest a dataset, profile it for truth, enrich it with semantic meaning, and get a single explainable **AI Readiness Score** that tells you whether the data is safe to feed an LLM or RAG pipeline.

Contextra is the layer between your raw data and your AI stack. It is **not** a warehouse, **not** an ETL tool, and **not** a data catalog. It's an **analysis + semantic enrichment + AI usability scoring** engine that answers one question every AI team asks:

> *"Is this dataset actually usable for AI — and if not, what's wrong with it?"*

This README documents the **working MVP** in this repository: ~1,160 lines across a FastAPI backend, a heuristic AI engine, and a single-page UI. It runs with **zero infrastructure** — no database server, no cloud, no API key.

---

## Table of contents

- [Status](#status)
- [Feature summary](#feature-summary)
- [Quickstart](#quickstart)
- [How it works (end-to-end flow)](#how-it-works-end-to-end-flow)
- [Architecture](#architecture)
- [Project layout](#project-layout)
- [The four core services (in depth)](#the-four-core-services-in-depth)
- [Scoring methodology](#scoring-methodology)
- [API reference](#api-reference)
- [Data model](#data-model)
- [The UI](#the-ui)
- [Configuration](#configuration)
- [Tech stack](#tech-stack)
- [Tested & verified](#tested--verified)
- [Known limitations](#known-limitations)
- [Roadmap](#roadmap)

---

## Status

✅ **Working MVP — verified end-to-end.** Upload a CSV through the UI or API and it is ingested, profiled, semantically mapped, scored, and rendered as an AI Readiness Report. All processing runs asynchronously in a background job.

| | |
|---|---|
| **Version** | 0.1.0 |
| **Runtime** | Python 3.14, FastAPI |
| **Default infra** | SQLite + local filesystem + offline heuristic AI engine (no key needed) |
| **Optional infra** | Postgres (`DATABASE_URL`), OpenAI (`OPENAI_API_KEY`) |

---

## Feature summary

The MVP does exactly four things — deliberately scoped, as a real MVP should be:

| # | Capability | What's implemented |
|---|---|---|
| **1** | **Data ingestion** | CSV upload + a single-table Postgres connector → normalized into one internal DataFrame format with type inference. |
| **2** | **Data profiling** | Per-column null rate, uniqueness, cardinality, IQR outlier counts, numeric min/max/mean, sample values, and **PII detection** (name- and value-pattern based). |
| **3** | **AI readiness scoring** | A weighted 0–100 score across five dimensions, a letter grade (A–F), and a human-readable list of concrete issues. |
| **4** | **Semantic enrichment** | Column-name normalization, semantic-type inference, entity detection (customer / product / order / event), and confidence scoring — heuristic by default, LLM-refined when a key is present. |

---

## Quickstart

Runs with **zero infrastructure**. No API key, no database server.

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server
python run.py
#    (equivalently: uvicorn app.main:app --reload)

# 3. Open the UI
#    http://127.0.0.1:8000
```

Then drag in `sample_data/customers.csv` (ships with the repo) and watch it get ingested, profiled, semantically mapped, and scored in real time.

**Drive it from the API directly:**

```bash
# Upload + analyze (returns a dataset_id; processing is async)
curl -X POST -F "file=@sample_data/customers.csv" \
  http://127.0.0.1:8000/api/datasets/upload

# Poll status / fetch the readiness report once status is "done"
curl http://127.0.0.1:8000/api/datasets/<id>/ai-score
```

Interactive, auto-generated API docs live at **`http://127.0.0.1:8000/docs`**.

---

## How it works (end-to-end flow)

```
1. User uploads a CSV (or connects a Postgres table)
        │
        ▼
2. Ingestion: raw bytes saved to disk, metadata row written, job enqueued
        │
        ▼
3. Async pipeline (FastAPI BackgroundTasks) runs:
        ├─ Profiler   → null/uniqueness/cardinality/outliers/PII   (the "data truth engine")
        ├─ Semantic   → column meaning + entity detection
        └─ Scoring    → 5-dimension weighted score + grade + issues
        │
        ▼
4. Results persisted to DB; dataset status flips pending → profiling → done
        │
        ▼
5. Results API exposes the combined "AI Readiness Report"; UI polls and renders it
```

The dataset status lifecycle is explicit: **`pending` → `profiling` → `done`** (or **`failed`**, with the error message stored for the UI).

---

## Architecture

```
              ┌──────────────────────────┐
              │   Single-page UI         │   (served by FastAPI, vanilla JS)
              └────────────┬─────────────┘
                           │ REST (JSON)
                           ▼
              ┌──────────────────────────┐
              │  API Gateway (FastAPI)    │   app/main.py
              └────────────┬─────────────┘
                           │ enqueue BackgroundTask
                           ▼
              ┌──────────────────────────┐
              │  Async Pipeline           │   app/tasks.py
              └────────────┬─────────────┘
            ┌──────────────┼───────────────┬───────────────┐
            ▼              ▼               ▼               ▼
     ┌───────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
     │ Ingestion │  │ Profiler   │  │ Semantic   │  │ Scoring    │
     │ Service   │  │ Service    │  │ AI Service │  │ Engine     │
     └─────┬─────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
           │              │               │               │
           ▼              ▼               ▼               ▼
        ┌──────────────────────────────────────────────────────┐
        │           Core Data Store                            │
        │   SQLAlchemy → SQLite (default) / Postgres            │
        │   + local filesystem for raw datasets (→ S3 later)   │
        └──────────────────────────────────────────────────────┘
```

Every component is **swappable behind an interface**: the storage layer, the database (any SQLAlchemy URL), and the semantic engine (heuristic ↔ LLM) can each be replaced without touching the rest of the pipeline.

---

## Project layout

```
contextra/
├── README.md
├── requirements.txt
├── run.py                      # `python run.py` → dev server
├── .env.example                # all optional config documented
├── .gitignore
├── sample_data/
│   └── customers.csv           # demo dataset (15 rows, mixed PII + numerics)
└── app/
    ├── __init__.py
    ├── config.py               # env-driven settings (DB, storage, AI, sample size)
    ├── database.py             # SQLAlchemy engine/session + init_db()
    ├── models.py               # ORM: Dataset, DatasetFile, Profile, SemanticMap, ReadinessScore
    ├── schemas.py              # Pydantic response models
    ├── storage.py              # raw-file persistence (local FS)
    ├── tasks.py                # async pipeline orchestration
    ├── main.py                 # FastAPI app: ingestion + Results API + static UI
    ├── services/
    │   ├── ingestion.py        # CSV + Postgres loaders → normalized DataFrame
    │   ├── profiler.py         # statistics + PII detection
    │   ├── semantic.py         # semantic typing + entity detection (heuristic/LLM)
    │   └── scoring.py          # 5-dimension weighted AI readiness score
    └── static/
        ├── index.html          # 3-section single-page app
        ├── styles.css          # dark theme
        └── app.js              # upload, polling, report rendering, JSON export
```

---

## The four core services (in depth)

### A. Ingestion Service — `app/services/ingestion.py`

Loads a source into a normalized pandas DataFrame; everything downstream operates on that DataFrame, so adding a new source means adding one loader.

- **`load_csv(path)`** — reads the CSV and opportunistically parses datetime columns (any text column whose values parse as dates >90% of the time is converted to `datetime64`). This is robust to both pandas `object` and the newer native `str` dtype.
- **`load_postgres(dsn, table)`** — reads an entire table via SQLAlchemy.
- **`describe_columns(df)`** — maps pandas dtypes to coarse, UI-friendly types: `integer`, `float`, `boolean`, `datetime`, `string`.
- **`normalize(df)`** — returns the metadata envelope `{columns: [{name, type}], row_count}`.

### B. Data Profiler Service — `app/services/profiler.py`

The deterministic "data truth engine" — pure pandas/regex, no LLM. For each column it computes:

| Field | Meaning |
|---|---|
| `dtype` | pandas dtype |
| `null_rate` | fraction of missing values |
| `uniqueness` | distinct ÷ non-null count |
| `cardinality` | number of distinct values |
| `outliers` | IQR-based outlier count (numeric columns) |
| `pii` | detected PII category, or `null` |
| `sample_values` | up to 5 example values |
| `min` / `max` / `mean` | numeric columns only |

**PII detection** works two ways:
- **Name hints** — `email`, `phone`, `ssn`, `credit_card`, `name`, `address`, `dob` matched against the column name.
- **Value patterns** — regexes for `email`, `phone`, `ssn`, `credit_card`, `ip_address`, applied **only to text columns** (numeric/datetime columns are skipped to avoid false positives such as a date matching a phone pattern).

### C. Semantic AI Service — `app/services/semantic.py`

The differentiation core. For each column it produces:

```json
{
  "normalized_name": "cust_id",
  "semantic_type": "customer_identifier",
  "entity": "customer",
  "confidence": 0.9,
  "source": "heuristic"
}
```

- **Name normalization** — trims, converts `camelCase`/spaces/hyphens to `snake_case`, lowercases.
- **Semantic typing** — an ordered heuristic table maps name patterns to ~17 semantic types: `customer_identifier`, `product_identifier`, `order_identifier`, `event_identifier`, `identifier`, `email_address`, `phone_number`, `person_name`, `postal_address`, `monetary_amount`, `quantity`, `datetime`, `status_category`, `geo_region`, `category`, plus dtype-based fallbacks (`numeric_measure`, `free_text`).
- **Entity detection** — each column is bucketed into `customer` / `product` / `order` / `event` / `entity`; the dataset's distinct entities are surfaced as `entities_detected`.
- **Optional LLM refinement** — when `OPENAI_API_KEY` is set, columns with confidence < 0.6 are sent to the LLM (strict-JSON response) for a better label; everything else stays heuristic. Any failure silently falls back to the heuristic guess, so the service never hard-depends on the network.

### D. AI Readiness Scoring Engine — `app/services/scoring.py`

Aggregates the profile + semantic map into a single explainable score. See [Scoring methodology](#scoring-methodology) below.

---

## Scoring methodology

The final score is a weighted sum of five dimensions, each normalized to 0–100:

| Dimension | Weight | How it's computed |
|---|---:|---|
| **Completeness** | 25% | Average of `(1 − null_rate)` across columns. |
| **Consistency** | 20% | Average of `max(0, 1 − outlier_rate × 5)`, where `outlier_rate = outliers ÷ row_count`. |
| **Structure quality** | 20% | Per column starts at 1.0; −0.2 for untyped (`object`) columns; −0.2 for a near-unique free-text column that isn't an identifier. |
| **PII risk** | 20% | `max(0, 1 − pii_fraction × 1.5)` — more exposed PII ⇒ higher risk ⇒ lower score. |
| **Semantic clarity** | 15% | Average semantic-inference confidence across columns. |

```
final_score = Σ (dimension_score × weight)
```

**Grade bands:** `A ≥ 90`, `B ≥ 80`, `C ≥ 70`, `D ≥ 60`, `F < 60`.

**Issues** are generated from thresholds — high null rates (>20%), frequent outliers (>5% of rows), each detected PII column, and ambiguous-meaning columns (confidence < 0.5).

Example output:

```json
{
  "ai_readiness_score": 84.3,
  "grade": "B",
  "dimensions": {
    "completeness": 96.3, "consistency": 88.9, "structure": 100.0,
    "pii_risk": 50.0, "semantic_clarity": 83.3
  },
  "weights": { "completeness": 25, "consistency": 20, "structure": 20, "pii_risk": 20, "semantic_clarity": 15 },
  "issues": [
    "Frequent outliers (2) in column 'order_amount'.",
    "PII risk: 'email' looks like email data.",
    "PII risk: 'phone' looks like phone data."
  ]
}
```

---

## API reference

Base URL: `http://127.0.0.1:8000`

### Ingestion

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/api/datasets/upload` | multipart `file` (.csv) | `{ dataset_id, status: "pending" }` |
| `POST` | `/api/datasets/connect` | `{ name, dsn, table }` | `{ dataset_id, status: "pending" }` |

### Results

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/datasets` | list of dataset summaries (with score/grade when ready) |
| `GET` | `/api/datasets/{id}` | one dataset summary + status |
| `GET` | `/api/datasets/{id}/profile` | full column profile |
| `GET` | `/api/datasets/{id}/semantic-map` | semantic types + entities |
| `GET` | `/api/datasets/{id}/ai-score` | score, grade, dimensions, issues |
| `GET` | `/api/datasets/{id}/report` | **combined** report (dataset + profile + semantic + score) — one call for the UI |

Result endpoints return **HTTP 409** if the analysis is still running, and **404** for unknown IDs.

### UI / docs

| Path | Purpose |
|---|---|
| `/` | single-page UI |
| `/docs` | auto-generated interactive OpenAPI docs |

---

## Data model

SQLAlchemy ORM (`app/models.py`), mirroring the minimal design from the architecture spec:

| Table | Key columns |
|---|---|
| **datasets** | `id`, `name`, `source_type` (`csv`/`postgres`), `row_count`, `status`, `error`, `created_at` |
| **dataset_files** | `id`, `dataset_id` → datasets, `file_path` |
| **profiles** | `dataset_id` → datasets, `json_profile` |
| **semantic_maps** | `dataset_id` → datasets, `json_semantics` |
| **readiness_scores** | `dataset_id` → datasets, `score`, `grade`, `json_details` |

Tables are auto-created on startup via `init_db()`. JSON payloads are stored in `JSON` columns so the schema stays stable as the profiler/semantic outputs evolve.

---

## The UI

A dependency-free single-page app served directly by FastAPI (`app/static/`). Three sections:

1. **Upload** — drag-and-drop or click-to-pick a CSV; submits and kicks off analysis.
2. **Datasets** — a live table of every dataset with source, row count, status badge, and score; auto-polls until processing finishes.
3. **AI Readiness Report** — a circular score gauge (color-coded by grade), per-dimension bars, the issues list, a combined semantic-map + profile table (showing semantic type, confidence, null %, uniqueness, cardinality, and PII flags), and an **Export JSON** button.

No build step, no Node — migrating to Next.js later is a drop-in replacement of this folder since the API is already clean REST.

---

## Configuration

All settings are environment variables (optionally via a `.env` file — copy `.env.example`). Everything has a sensible default.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./contextra.db` | Any SQLAlchemy URL; point at Postgres to scale up. |
| `CONTEXTRA_DATA_DIR` | `./data/raw` | Where raw uploads are stored. |
| `OPENAI_API_KEY` | *(unset)* | Enables LLM refinement of low-confidence columns. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model used for refinement. |
| `CONTEXTRA_SAMPLE_SIZE` | `50` | Values sampled per column during profiling/semantics. |

**Optional dependencies** (commented in `requirements.txt`): `psycopg2-binary` for Postgres, `openai` for LLM semantics.

---

## Tech stack

| Layer | Choice |
|---|---|
| **API** | FastAPI + Uvicorn |
| **Data** | pandas, numpy |
| **Persistence** | SQLAlchemy 2.x → SQLite (default) / Postgres |
| **Uploads** | python-multipart |
| **Config** | python-dotenv |
| **Async** | FastAPI `BackgroundTasks` (swap for Celery when you need durability) |
| **Frontend** | Vanilla HTML/CSS/JS (no build step) |
| **AI** | Offline heuristic engine; optional OpenAI for refinement |

---

## Tested & verified

The full pipeline was exercised end-to-end over real HTTP against `sample_data/customers.csv`:

- Upload → async processing → status `done`, with results persisted and served.
- **Result: score `84.3`, grade `B`**, dimensions `completeness 96.3 / consistency 88.9 / structure 100 / pii_risk 50 / semantic_clarity 83.3`.
- Correct PII detection on `first_name`, `email`, `phone`; correct entity detection (`customer`, `order`, `event`, `entity`).
- Two real bugs were found and fixed during verification: a pandas 3.x native-`str` dtype that broke datetime detection, and a phone-number regex that falsely matched ISO date strings.

---

## Known limitations

These are intentional MVP boundaries:

- **CSV + single-table Postgres only** — no other warehouses/formats yet.
- **In-process background jobs** — `BackgroundTasks` doesn't survive a restart; use Celery for durability.
- **Heuristic semantics** by default — strong for common business columns, less so for exotic ones (the optional LLM path closes this gap).
- **No auth / multi-tenancy** — single-user local tool for now.
- **No embeddings persisted** — the semantic layer ships meaning + confidence; vector embeddings are a roadmap item.

Deliberately **out of scope** for the MVP (would kill velocity): full data-catalog UI, lineage graphs, enterprise RBAC, multi-cloud, streaming pipelines, real-time sync.

---

## Roadmap

- Additional connectors (MySQL, Snowflake, BigQuery, Parquet)
- Persisted embeddings + semantic similarity search
- Celery-backed durable job queue
- Schema-drift detection and dataset versioning
- Configurable scoring weights and custom rules
- Next.js frontend, auth, and team accounts
- Dockerfile + pytest suite

---

## The moat

Contextra isn't a warehouse, an ETL tool, or a catalog. It's the **AI usability layer** that scores, explains, and semantically enriches data before it ever reaches a model. That focus — analysis + semantics + an explainable readiness score — is the differentiation.
