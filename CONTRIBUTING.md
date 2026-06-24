# Contributing to Contextra

Thanks for your interest! Contextra is a small, focused codebase — this guide
gets you productive fast. For the big picture, read [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Getting set up

```bash
# Clone, then from the repo root:
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -r requirements.txt
python run.py          # http://127.0.0.1:8000
```

That's the whole setup — SQLite and local file storage need no extra services.
Optional extras:

```bash
pip install psycopg2-binary   # Postgres connector
pip install openai            # LLM-backed semantic refinement
```

Configuration is environment-driven; copy `.env.example` to `.env` and edit.

---

## Project conventions

- **Python 3.11+** (developed on 3.14). Standard library + the deps in
  `requirements.txt` — keep new dependencies minimal and justify them in the PR.
- **One-way dependencies.** Services (`app/services/`) must not import the web
  layer, the database, or each other. Only `tasks.py` wires services to
  persistence; only `main.py` wires HTTP to `tasks`.
- **Stable stage contracts.** If you change a service's output shape, update the
  "Data flow types" section in `ARCHITECTURE.md` and any dependent stage.
- **Type hints** on public functions; **docstrings** that say *why*, not *what*.
- Match the surrounding style — short functions, descriptive names, no clever
  one-liners where a plain loop reads better.

---

## Where things live

| Change you're making | File(s) to touch |
|---|---|
| New data source / file format | `services/ingestion.py` + a route in `main.py` |
| New profiling metric | `services/profiler.py` |
| Better column-meaning detection | `services/semantic.py` |
| Scoring weights / new dimension | `services/scoring.py` |
| New API endpoint | `main.py` (+ `schemas.py` for response models) |
| New persisted field | `models.py` (+ a migration story) |
| UI | `app/static/` |

---

## Making a change

1. **Branch** off `main`: `git checkout -b feat/short-description`.
2. **Keep it scoped** — one concern per PR.
3. **Verify end-to-end** before pushing (see below).
4. **Update docs** — `README.md` for user-facing changes, `ARCHITECTURE.md` for
   structural ones.
5. Open a PR with a clear description of *what* and *why*, plus how you tested.

---

## Verifying your change

There is no test suite yet (adding `pytest` is a welcome contribution — see the
roadmap). Until then, verify manually:

```bash
# Quick pipeline smoke test — no server needed:
python -c "
from app.services import ingestion, profiler, semantic, scoring
df = ingestion.load_csv('sample_data/customers.csv')
prof = profiler.profile_dataframe(df)
sem  = semantic.build_semantic_map(df)
res  = scoring.score_dataset(prof, sem)
print('score', res['ai_readiness_score'], res['grade'])
print('PII', [n for n,c in prof['columns'].items() if c['pii']])
"

# Full HTTP test:
python run.py &
curl -X POST -F "file=@sample_data/customers.csv" http://127.0.0.1:8000/api/datasets/upload
# then GET /api/datasets/<id>/ai-score once status is "done"
```

A change is "done" when the sample dataset still ingests, profiles, scores, and
renders in the UI without errors — and your new behavior demonstrably works.

### Good first contributions
- A `pytest` suite around the four services (start with `scoring.py` — it's pure).
- A `Dockerfile` + `docker-compose.yml` (app + Postgres).
- More PII patterns or semantic heuristics (with sample data proving them).
- Additional ingestion loaders (Parquet, MySQL, JSON).

---

## Reporting bugs / proposing features

Open an issue with: what you expected, what happened, and a minimal dataset or
request that reproduces it. For features, describe the use case before the
solution — it helps keep Contextra focused on its core (analysis + semantics +
AI usability scoring) rather than drifting into catalog/ETL territory.

By contributing, you agree your contributions are licensed under the project's
[MIT License](LICENSE).
