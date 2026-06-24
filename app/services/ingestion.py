"""Ingestion Service — load a source into a normalized pandas DataFrame.

Supports CSV files and a single-table Postgres read. Everything downstream
(profiler, semantic, scoring) operates on the DataFrame this returns, so adding
a new source only means adding a loader here.
"""

from __future__ import annotations

import pandas as pd


def _simple_type(dtype) -> str:
    """Map a pandas dtype to a coarse, UI-friendly type name."""
    name = str(dtype)
    if name.startswith("int"):
        return "integer"
    if name.startswith("float"):
        return "float"
    if name.startswith("bool"):
        return "boolean"
    if "datetime" in name:
        return "datetime"
    return "string"


def describe_columns(df: pd.DataFrame) -> list[dict]:
    """Return [{name, type}] for each column."""
    return [{"name": str(col), "type": _simple_type(df[col].dtype)} for col in df.columns]


def load_csv(path: str) -> pd.DataFrame:
    """Read a CSV and opportunistically parse obvious datetime columns."""
    df = pd.read_csv(path)
    for col in df.columns:
        # Works across pandas object dtype and the newer native string dtype.
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            # Try datetime parse; keep original if it doesn't cleanly convert.
            parsed = pd.to_datetime(df[col], errors="coerce", format="mixed")
            if parsed.notna().mean() > 0.9:
                df[col] = parsed
    return df


def load_postgres(dsn: str, table: str) -> pd.DataFrame:
    """Read an entire table from Postgres. Requires SQLAlchemy + a driver."""
    from sqlalchemy import create_engine

    engine = create_engine(dsn)
    # Identifier is caller-supplied; quote it to avoid breaking on mixed case.
    return pd.read_sql(f'SELECT * FROM "{table}"', engine)


def normalize(df: pd.DataFrame) -> dict:
    """Produce the internal metadata envelope for an ingested dataset."""
    return {
        "columns": describe_columns(df),
        "row_count": int(len(df)),
    }
