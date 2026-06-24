"""Application configuration.

All settings come from environment variables (optionally loaded from a .env
file) so the same code runs locally with SQLite + filesystem storage, or in a
fuller deployment with Postgres + S3 + an LLM key.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv is optional
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Storage ---------------------------------------------------------------
# Where raw uploaded datasets live. Local filesystem for the MVP; swap for S3.
DATA_DIR = Path(os.getenv("CONTEXTRA_DATA_DIR", BASE_DIR / "data" / "raw"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Database --------------------------------------------------------------
# SQLite by default (zero-config). Point at Postgres with e.g.
#   DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/contextra
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'contextra.db'}")

# --- AI / Semantic layer ---------------------------------------------------
# If set, the semantic service may call an LLM. If unset, it falls back to the
# fully-offline heuristic engine (no network, no key required).
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Number of sample values inspected per column during profiling/semantics.
SAMPLE_SIZE = int(os.getenv("CONTEXTRA_SAMPLE_SIZE", "50"))
