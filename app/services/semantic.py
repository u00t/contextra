"""Semantic AI Service — the differentiation core.

For each column it infers a semantic type (e.g. "customer_identifier"),
classifies an entity ("customer" / "product" / "order" / "event"), and assigns
a confidence. Works fully offline via heuristics; if OPENAI_API_KEY is set it
will refine low-confidence columns with an LLM.
"""

from __future__ import annotations

import re

import pandas as pd

from ..config import OPENAI_API_KEY, OPENAI_MODEL

# (regex on normalized column name) -> (semantic_type, entity, confidence)
_HEURISTICS: list[tuple[re.Pattern, str, str, float]] = [
    (re.compile(r"(cust|customer|client|user|account).*id"), "customer_identifier", "customer", 0.9),
    (re.compile(r"(prod|product|item|sku).*id"), "product_identifier", "product", 0.9),
    (re.compile(r"(order|transaction|invoice|txn).*id"), "order_identifier", "order", 0.9),
    (re.compile(r"(event|session|click|log).*id"), "event_identifier", "event", 0.85),
    (re.compile(r"^id$|.*_id$"), "identifier", "entity", 0.6),
    (re.compile(r"email|e_mail"), "email_address", "customer", 0.9),
    (re.compile(r"phone|mobile|tel"), "phone_number", "customer", 0.85),
    (re.compile(r"(first|last|full)?_?name$|surname"), "person_name", "customer", 0.8),
    (re.compile(r"address|street|city|zip|postal"), "postal_address", "customer", 0.8),
    (re.compile(r"amount|price|cost|total|revenue|sales|payment"), "monetary_amount", "order", 0.85),
    (re.compile(r"qty|quantity|count|units"), "quantity", "order", 0.8),
    (re.compile(r"date|time|_at$|timestamp|created|updated"), "datetime", "event", 0.85),
    (re.compile(r"status|state|stage"), "status_category", "entity", 0.75),
    (re.compile(r"country|region|state|province|location"), "geo_region", "entity", 0.75),
    (re.compile(r"category|type|kind|class"), "category", "entity", 0.7),
]


def _heuristic_type(col_name: str, series: pd.Series) -> dict:
    normalized = re.sub(r"[\s\-]+", "_", str(col_name).strip().lower())
    for pattern, semantic_type, entity, confidence in _HEURISTICS:
        if pattern.search(normalized):
            return {"semantic_type": semantic_type, "entity": entity, "confidence": confidence}

    # Fall back to dtype-driven guesses.
    if pd.api.types.is_numeric_dtype(series):
        return {"semantic_type": "numeric_measure", "entity": "entity", "confidence": 0.45}
    if pd.api.types.is_datetime64_any_dtype(series):
        return {"semantic_type": "datetime", "entity": "event", "confidence": 0.6}
    return {"semantic_type": "free_text", "entity": "entity", "confidence": 0.35}


def _normalized_name(col_name: str) -> str:
    """snake_case, lower, stripped — the 'column naming normalization' step."""
    name = re.sub(r"[\s\-]+", "_", str(col_name).strip())
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)  # camelCase -> snake
    return re.sub(r"_+", "_", name).lower()


def _llm_refine(col_name: str, samples: list[str]) -> dict | None:
    """Optional LLM refinement. Returns None if unavailable or on any error."""
    if not OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)
        prompt = (
            "You classify a database column for AI-readiness. "
            f'Column name: "{col_name}". Sample values: {samples[:8]}. '
            "Reply with strict JSON: "
            '{"semantic_type": str, "entity": "customer|product|order|event|entity", '
            '"confidence": float between 0 and 1}.'
        )
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        import json

        return json.loads(resp.choices[0].message.content)
    except Exception:
        return None


def build_semantic_map(df: pd.DataFrame) -> dict:
    """Return {columns: {original_name: {...}}}"""
    columns: dict[str, dict] = {}
    for col in df.columns:
        series = df[col]
        guess = _heuristic_type(col, series)

        # Only spend an LLM call when heuristics are unsure.
        if guess["confidence"] < 0.6:
            samples = [str(v) for v in series.dropna().unique()[:8]]
            refined = _llm_refine(str(col), samples)
            if refined:
                guess = {
                    "semantic_type": refined.get("semantic_type", guess["semantic_type"]),
                    "entity": refined.get("entity", guess["entity"]),
                    "confidence": float(refined.get("confidence", guess["confidence"])),
                    "source": "llm",
                }
        guess.setdefault("source", "heuristic")

        columns[str(col)] = {
            "normalized_name": _normalized_name(col),
            **guess,
        }

    entities = sorted({c["entity"] for c in columns.values()})
    return {"columns": columns, "entities_detected": entities}
