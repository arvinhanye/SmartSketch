"""Settings shared only by the parse/extract worker tests (15-second lease)."""

from app.config import load_settings
from app.services.file_storage import FileStorage


def worker_settings(db_url: str, storage: FileStorage):
    return load_settings(
        {"SQLITE_URL": db_url, "STORAGE_DIR": str(storage.root), "TASK_LEASE_SECONDS": "15"}
    )
