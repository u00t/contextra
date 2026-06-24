"""AI Readiness Scoring Engine — the monetizable 'wow feature'.

Aggregates the profile + semantic map into a single 0-100 score across five
weighted dimensions, assigns a letter grade, and emits a human-readable list
of issues.
"""

from __future__ import annotations

WEIGHTS = {
    "completeness": 0.25,
    "consistency": 0.20,
    "structure": 0.20,
    "pii_risk": 0.20,
    "semantic_clarity": 0.15,
}


def _grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _avg(values: list[float], default: float = 1.0) -> float:
    return sum(values) / len(values) if values else default


def score_dataset(profile: dict, semantic: dict) -> dict:
    """Return {ai_readiness_score, grade, dimensions, issues}."""
    cols = profile.get("columns", {})
    sem_cols = semantic.get("columns", {})
    issues: list[str] = []

    if not cols:
        return {
            "ai_readiness_score": 0,
            "grade": "F",
            "dimensions": {k: 0 for k in WEIGHTS},
            "issues": ["No columns could be profiled."],
        }

    # --- Completeness: how non-null the dataset is -------------------------
    completeness = _avg([1 - c["null_rate"] for c in cols.values()])
    for name, c in cols.items():
        if c["null_rate"] > 0.2:
            issues.append(f"High null rate ({c['null_rate']:.0%}) in column '{name}'.")

    # --- Consistency: penalize heavy outliers --------------------------------
    consistency_parts = []
    row_count = profile.get("row_count", 0) or 1
    for name, c in cols.items():
        outlier_rate = c.get("outliers", 0) / row_count
        consistency_parts.append(max(0.0, 1 - outlier_rate * 5))
        if outlier_rate > 0.05:
            issues.append(f"Frequent outliers ({c['outliers']}) in column '{name}'.")
    consistency = _avg(consistency_parts)

    # --- Structure quality: typed columns, sane cardinality ------------------
    structure_parts = []
    for name, c in cols.items():
        s = 1.0
        if c["dtype"] == "object":
            s -= 0.2  # untyped / free-form string
        # A near-unique non-identifier text column hints at messy structure.
        if c["uniqueness"] > 0.99 and c["cardinality"] > 1 and c["dtype"] == "object":
            sem = sem_cols.get(name, {})
            if "identifier" not in sem.get("semantic_type", ""):
                s -= 0.2
        structure_parts.append(max(0.0, s))
    structure = _avg(structure_parts)

    # --- PII risk: more exposed PII => higher risk => lower readiness --------
    pii_cols = [name for name, c in cols.items() if c.get("pii")]
    pii_fraction = len(pii_cols) / len(cols)
    pii_risk = max(0.0, 1 - pii_fraction * 1.5)
    for name in pii_cols:
        issues.append(f"PII risk: '{name}' looks like {cols[name]['pii']} data.")

    # --- Semantic clarity: avg confidence of inferred meaning ----------------
    semantic_clarity = _avg([s.get("confidence", 0.0) for s in sem_cols.values()], default=0.0)
    unclear = [n for n, s in sem_cols.items() if s.get("confidence", 0) < 0.5]
    if unclear:
        issues.append(f"Ambiguous meaning for column(s): {', '.join(unclear[:5])}.")

    dimensions = {
        "completeness": round(completeness * 100, 1),
        "consistency": round(consistency * 100, 1),
        "structure": round(structure * 100, 1),
        "pii_risk": round(pii_risk * 100, 1),
        "semantic_clarity": round(semantic_clarity * 100, 1),
    }

    score = sum(dimensions[k] * w for k, w in WEIGHTS.items())
    score = round(score, 1)

    return {
        "ai_readiness_score": score,
        "grade": _grade(score),
        "dimensions": dimensions,
        "weights": {k: int(v * 100) for k, v in WEIGHTS.items()},
        "issues": issues or ["No significant issues detected."],
    }
