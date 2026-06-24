"""Raw dataset storage. Local filesystem for the MVP — swap for S3 later."""

from pathlib import Path

from .config import DATA_DIR


def save_upload(dataset_id: str, filename: str, content: bytes) -> str:
    """Persist raw bytes and return the stored path."""
    safe_name = Path(filename).name or "dataset.csv"
    dest = DATA_DIR / f"{dataset_id}__{safe_name}"
    dest.write_bytes(content)
    return str(dest)
