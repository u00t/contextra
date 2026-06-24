"""Data Profiler Service — the "data truth engine".

Computes per-column statistics, basic outlier counts, and PII detection. No
LLM involved; this is pure pandas/regex so results are deterministic.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..config import SAMPLE_SIZE

# --- PII detection ---------------------------------------------------------
_PII_VALUE_PATTERNS = {
    "email": re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    # Require >=10 digits and reject ISO date shapes (YYYY-MM-DD).
    "phone": re.compile(r"^(?!\d{4}-\d{2}-\d{2}$)[+(]?\d[\d\s().-]{8,}\d$"),
    "ssn": re.compile(r"^\d{3}-\d{2}-\d{4}$"),
    "credit_card": re.compile(r"^\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}$"),
    "ip_address": re.compile(r"^\d{1,3}(\.\d{1,3}){3}$"),
}

_PII_NAME_HINTS = {
    "email": ["email", "e_mail", "mail"],
    "phone": ["phone", "mobile", "cell", "tel"],
    "ssn": ["ssn", "social_security", "national_id"],
    "credit_card": ["card", "creditcard", "cc_number"],
    "name": ["first_name", "last_name", "full_name", "fname", "lname", "surname"],
    "address": ["address", "street", "zipcode", "postal", "city"],
    "dob": ["dob", "birth", "birthday"],
}


def _detect_pii(col_name: str, sample: pd.Series) -> str | None:
    """Return a PII category for the column, or None."""
    lname = col_name.lower()
    for category, hints in _PII_NAME_HINTS.items():
        if any(h in lname for h in hints):
            return category

    # Value-pattern matching only makes sense on free-form text columns.
    # Numeric/datetime columns would produce false positives (e.g. a date
    # like "2023-01-15" superficially matches a phone-number pattern).
    if not pd.api.types.is_object_dtype(sample) and not pd.api.types.is_string_dtype(sample):
        return None

    str_sample = sample.dropna().astype(str)
    if str_sample.empty:
        return None
    for category, pattern in _PII_VALUE_PATTERNS.items():
        match_rate = str_sample.apply(lambda v: bool(pattern.match(v.strip()))).mean()
        if match_rate > 0.7:
            return category
    return None


def _count_outliers(series: pd.Series) -> int:
    """IQR-based outlier count for numeric columns."""
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < 4:
        return 0
    q1, q3 = np.percentile(values, [25, 75])
    iqr = q3 - q1
    if iqr == 0:
        return 0
    low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return int(((values < low) | (values > high)).sum())


def _sample_values(series: pd.Series, n: int = 5) -> list:
    vals = series.dropna().unique()[:n]
    return [str(v) for v in vals]


def profile_dataframe(df: pd.DataFrame) -> dict:
    """Return the full profile envelope: {columns: {...}}"""
    n = len(df)
    columns: dict[str, dict] = {}

    for col in df.columns:
        series = df[col]
        non_null = series.dropna()
        null_rate = float(series.isna().mean()) if n else 0.0
        distinct = int(non_null.nunique())
        uniqueness = float(distinct / len(non_null)) if len(non_null) else 0.0
        is_numeric = pd.api.types.is_numeric_dtype(series)

        sample = non_null.sample(min(SAMPLE_SIZE, len(non_null)), random_state=0) if len(non_null) else non_null

        col_profile: dict = {
            "dtype": str(series.dtype),
            "null_rate": round(null_rate, 4),
            "uniqueness": round(uniqueness, 4),
            "cardinality": distinct,
            "outliers": _count_outliers(series) if is_numeric else 0,
            "pii": _detect_pii(str(col), sample),
            "sample_values": _sample_values(non_null),
        }

        if is_numeric and len(non_null):
            numeric = pd.to_numeric(non_null, errors="coerce").dropna()
            if len(numeric):
                col_profile["min"] = float(numeric.min())
                col_profile["max"] = float(numeric.max())
                col_profile["mean"] = round(float(numeric.mean()), 4)

        columns[str(col)] = col_profile

    return {"row_count": int(n), "columns": columns}
