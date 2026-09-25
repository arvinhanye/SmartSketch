"""C07 course material upload orchestration and file compensation."""

from __future__ import annotations

from typing import BinaryIO
from uuid import uuid4

from app.config import Settings
from app.repositories import materials, tasks
from app.repositories.materials import MaterialRecord
from app.repositories.tasks import MaterialTaskResult
from app.services.file_storage import FileStorage, iter_file


class MaterialCreationError(Exception):
    """A saved file could not be recorded as a material and queued task."""


def upload_material(
    settings: Settings, *, course_id: str, filename: str,
    content_type: str | None, stream: BinaryIO,
    idempotency_key: str | None = None,
) -> MaterialTaskResult:
    """Store validated bytes then atomically create material/task; undo new files on failure.

    The public v1 upload contract has no idempotency header. Each HTTP call creates a
    fresh key; callers that already hold one can reuse it for an internal replay.
    """
    storage = FileStorage(settings.STORAGE_DIR, max_bytes=settings.UPLOAD_MAX_BYTES)
    stored = storage.save(filename, content_type, iter_file(stream))
    try:
        result = tasks.create_material_task(
            settings.SQLITE_URL,
            course_id=course_id,
            stored_file=stored,
            idempotency_key=idempotency_key or uuid4().hex,
        )
    except Exception as error:
        storage.delete(stored.storage_name)
        raise MaterialCreationError("无法创建资料处理任务") from error
    if not result.created:
        storage.delete(stored.storage_name)
    return result


def list_course_materials(settings: Settings, *, course_id: str) -> list[MaterialRecord]:
    return materials.list_materials(settings.SQLITE_URL, course_id=course_id)
