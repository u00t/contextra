"""Pydantic response models for the Results API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class DatasetSummary(BaseModel):
    id: str
    name: str
    source_type: str
    row_count: int
    status: str
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    ai_readiness_score: Optional[float] = None
    grade: Optional[str] = None

    class Config:
        from_attributes = True


class ConnectRequest(BaseModel):
    name: str
    dsn: str
    table: str


class UploadResponse(BaseModel):
    dataset_id: str
    status: str


class JsonResponse(BaseModel):
    dataset_id: str
    data: dict[str, Any]
