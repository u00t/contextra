"""Async pipeline — runs profiler -> semantic -> scoring and persists results.

Invoked via FastAPI BackgroundTasks (the spec's recommended v1 approach). Swap
for a Celery task with the same body when you need durability/concurrency.
"""

from __future__ import annotations

from .database import SessionLocal
from .models import Dataset, Profile, ReadinessScore, SemanticMap
from .services import ingestion, profiler, scoring, semantic


def run_pipeline(dataset_id: str, source_type: str, *, file_path: str | None = None,
                 dsn: str | None = None, table: str | None = None) -> None:
    db = SessionLocal()
    try:
        ds = db.get(Dataset, dataset_id)
        if ds is None:
            return
        ds.status = "profiling"
        db.commit()

        # 1. Load source into a DataFrame
        if source_type == "csv":
            df = ingestion.load_csv(file_path)
        elif source_type == "postgres":
            df = ingestion.load_postgres(dsn, table)
        else:
            raise ValueError(f"Unknown source_type: {source_type}")

        meta = ingestion.normalize(df)

        # 2. Profile -> 3. Semantic -> 4. Score
        prof = profiler.profile_dataframe(df)
        sem = semantic.build_semantic_map(df)
        result = scoring.score_dataset(prof, sem)

        # Persist (upsert-style replace)
        db.merge(Profile(dataset_id=dataset_id, json_profile=prof))
        db.merge(SemanticMap(dataset_id=dataset_id, json_semantics=sem))
        db.merge(ReadinessScore(
            dataset_id=dataset_id,
            score=result["ai_readiness_score"],
            grade=result["grade"],
            json_details=result,
        ))

        ds.row_count = meta["row_count"]
        ds.status = "done"
        ds.error = None
        db.commit()
    except Exception as exc:  # noqa: BLE001 — record any failure for the UI
        db.rollback()
        ds = db.get(Dataset, dataset_id)
        if ds is not None:
            ds.status = "failed"
            ds.error = str(exc)[:500]
            db.commit()
    finally:
        db.close()
