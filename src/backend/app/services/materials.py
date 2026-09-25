"""C07 资料上传与列表的业务规则。

上传只做三件事：经 C05 ``FileStorage`` 校验并落盘，经 C06 在一个事务里建资料与 queued
任务，然后返回；解析由 worker 异步进行，请求里不解析。落盘之后的任何失败都删除新落盘的
文件（补偿）；C06 幂等重放（``created=False``）时新落盘的文件未被引用，同样删除。
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import uuid4

from app.config import Settings
from app.repositories.materials import MaterialRecord, list_materials
from app.repositories.tasks import create_material_task
from app.services.file_storage import FileStorage, FileStorageError, StorageWriteError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadResult:
    task_id: str
    document_id: str


def open_storage(settings: Settings) -> FileStorage:
    """D-11：存储根目录与单文件上限都取自设置。"""
    return FileStorage(settings.STORAGE_DIR, max_bytes=settings.UPLOAD_MAX_BYTES)


def _discard(storage: FileStorage, storage_name: str) -> None:
    """补偿删除；删除本身失败只记日志，不掩盖原始错误。"""
    try:
        storage.delete(storage_name)
    except (FileStorageError, ValueError):
        logger.error("failed to delete unreferenced upload %s", storage_name)


def upload_material(
    settings: Settings,
    *,
    course_id: str,
    filename: object,
    content_type: str | None,
    chunks: Iterable[bytes],
    idempotency_key: str | None = None,
) -> UploadResult:
    """落盘并建资料与 queued 任务；失败抛 ``FileStorageError`` 子类或原异常。

    契约没有幂等键，HTTP 路由不传 ``idempotency_key``，每次请求用新的随机键；
    参数留给将来契约补上幂等键时使用。
    """
    storage = open_storage(settings)
    stored = storage.save(filename, content_type, chunks)
    try:
        result = create_material_task(
            settings.SQLITE_URL,
            course_id=course_id,
            stored_file=stored,
            idempotency_key=idempotency_key or uuid4().hex,
        )
    except sqlite3.Error:
        _discard(storage, stored.storage_name)
        raise StorageWriteError("资料记录暂不可写") from None
    except BaseException:
        _discard(storage, stored.storage_name)
        raise
    if not result.created:
        _discard(storage, stored.storage_name)
    return UploadResult(task_id=result.task.id, document_id=result.material.id)


def list_course_materials(settings: Settings, course_id: str) -> list[MaterialRecord]:
    """本课程资料，``parse_status`` 按 D-16 取最新创建任务的 stage。"""
    return list_materials(settings.SQLITE_URL, course_id=course_id)
