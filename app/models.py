"""ORM models — mirrors the minimal DB design from the architecture spec."""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)  # "csv" | "postgres"
    row_count = Column(Integer, default=0)
    # pending -> profiling -> done | failed
    status = Column(String, default="pending", nullable=False)
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    files = relationship("DatasetFile", back_populates="dataset", cascade="all, delete-orphan")
    profile = relationship("Profile", back_populates="dataset", uselist=False, cascade="all, delete-orphan")
    semantic_map = relationship("SemanticMap", back_populates="dataset", uselist=False, cascade="all, delete-orphan")
    readiness_score = relationship("ReadinessScore", back_populates="dataset", uselist=False, cascade="all, delete-orphan")


class DatasetFile(Base):
    __tablename__ = "dataset_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    file_path = Column(String, nullable=False)

    dataset = relationship("Dataset", back_populates="files")


class Profile(Base):
    __tablename__ = "profiles"

    dataset_id = Column(String, ForeignKey("datasets.id"), primary_key=True)
    json_profile = Column(JSON, nullable=False)

    dataset = relationship("Dataset", back_populates="profile")


class SemanticMap(Base):
    __tablename__ = "semantic_maps"

    dataset_id = Column(String, ForeignKey("datasets.id"), primary_key=True)
    json_semantics = Column(JSON, nullable=False)

    dataset = relationship("Dataset", back_populates="semantic_map")


class ReadinessScore(Base):
    __tablename__ = "readiness_scores"

    dataset_id = Column(String, ForeignKey("datasets.id"), primary_key=True)
    score = Column(Float, nullable=False)
    grade = Column(String, nullable=False)
    json_details = Column(JSON, nullable=False)

    dataset = relationship("Dataset", back_populates="readiness_score")
