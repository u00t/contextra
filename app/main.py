"""Contextra API Gateway + Results API + static UI."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import __version__
from .database import get_db, init_db
from .models import Dataset, DatasetFile
from .schemas import ConnectRequest, DatasetSummary, UploadResponse
from .storage import save_upload
from .tasks import run_pipeline

app = FastAPI(title="Contextra", version=__version__,
              description="AI Data Readiness Platform")

STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.on_event("startup")
def _startup():
    init_db()


# --------------------------------------------------------------------------
# Ingestion
# --------------------------------------------------------------------------
@app.post("/api/datasets/upload", response_model=UploadResponse, tags=["ingestion"])
async def upload_csv(background: BackgroundTasks, file: UploadFile = File(...),
                     db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Only .csv files are supported in the MVP.")

    dataset_id = uuid.uuid4().hex[:12]
    content = await file.read()
    path = save_upload(dataset_id, file.filename, content)

    ds = Dataset(id=dataset_id, name=file.filename, source_type="csv", status="pending")
    db.add(ds)
    db.add(DatasetFile(dataset_id=dataset_id, file_path=path))
    db.commit()

    background.add_task(run_pipeline, dataset_id, "csv", file_path=path)
    return UploadResponse(dataset_id=dataset_id, status="pending")


@app.post("/api/datasets/connect", response_model=UploadResponse, tags=["ingestion"])
def connect_postgres(req: ConnectRequest, background: BackgroundTasks,
                     db: Session = Depends(get_db)):
    dataset_id = uuid.uuid4().hex[:12]
    ds = Dataset(id=dataset_id, name=req.name, source_type="postgres", status="pending")
    db.add(ds)
    db.commit()

    background.add_task(run_pipeline, dataset_id, "postgres", dsn=req.dsn, table=req.table)
    return UploadResponse(dataset_id=dataset_id, status="pending")


# --------------------------------------------------------------------------
# Results API
# --------------------------------------------------------------------------
@app.get("/api/datasets", response_model=list[DatasetSummary], tags=["results"])
def list_datasets(db: Session = Depends(get_db)):
    out = []
    for ds in db.query(Dataset).order_by(Dataset.created_at.desc()).all():
        summary = DatasetSummary.model_validate(ds)
        if ds.readiness_score:
            summary.ai_readiness_score = ds.readiness_score.score
            summary.grade = ds.readiness_score.grade
        out.append(summary)
    return out


def _get_or_404(db: Session, dataset_id: str) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise HTTPException(404, "Dataset not found.")
    return ds


@app.get("/api/datasets/{dataset_id}", response_model=DatasetSummary, tags=["results"])
def get_dataset(dataset_id: str, db: Session = Depends(get_db)):
    ds = _get_or_404(db, dataset_id)
    summary = DatasetSummary.model_validate(ds)
    if ds.readiness_score:
        summary.ai_readiness_score = ds.readiness_score.score
        summary.grade = ds.readiness_score.grade
    return summary


@app.get("/api/datasets/{dataset_id}/profile", tags=["results"])
def get_profile(dataset_id: str, db: Session = Depends(get_db)):
    ds = _get_or_404(db, dataset_id)
    if not ds.profile:
        raise HTTPException(409, f"Profile not ready (status: {ds.status}).")
    return ds.profile.json_profile


@app.get("/api/datasets/{dataset_id}/semantic-map", tags=["results"])
def get_semantic_map(dataset_id: str, db: Session = Depends(get_db)):
    ds = _get_or_404(db, dataset_id)
    if not ds.semantic_map:
        raise HTTPException(409, f"Semantic map not ready (status: {ds.status}).")
    return ds.semantic_map.json_semantics


@app.get("/api/datasets/{dataset_id}/ai-score", tags=["results"])
def get_ai_score(dataset_id: str, db: Session = Depends(get_db)):
    ds = _get_or_404(db, dataset_id)
    if not ds.readiness_score:
        raise HTTPException(409, f"Score not ready (status: {ds.status}).")
    return ds.readiness_score.json_details


@app.get("/api/datasets/{dataset_id}/report", tags=["results"])
def get_report(dataset_id: str, db: Session = Depends(get_db)):
    """Combined report — everything the UI needs in one call."""
    ds = _get_or_404(db, dataset_id)
    return {
        "dataset": {
            "id": ds.id,
            "name": ds.name,
            "source_type": ds.source_type,
            "row_count": ds.row_count,
            "status": ds.status,
            "error": ds.error,
        },
        "profile": ds.profile.json_profile if ds.profile else None,
        "semantic_map": ds.semantic_map.json_semantics if ds.semantic_map else None,
        "ai_score": ds.readiness_score.json_details if ds.readiness_score else None,
    }


# --------------------------------------------------------------------------
# Static UI
# --------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
