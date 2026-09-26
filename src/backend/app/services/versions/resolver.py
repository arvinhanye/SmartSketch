"""G07：统一发布版本解析器（specs/teacher-review-publish.md V8，ADR-037）。

学生请求（图谱、推荐、问答）与带 ``?version=n`` 的读取在**请求开始时调用一次**
``resolve_published``，得到不可变的 ``PublishedVersion``。此后该请求内所有 Neo4j 查询、引用解析、
缓存键都用它的 ``version_id``，不再读发布指针；请求途中提交的新版本不会混入，下一次请求才读到。

- 从未发布（指针为 NULL）→ 404 ``GRAPH_NOT_PUBLISHED``，先于 ``version`` 的判断；
- ``version`` 不是本课程已提交版本号 → 404 ``NOT_FOUND``（含他课、未提交、失败的尝试）；
- 指针与版本行在同一条 SQL 中读出，二者一致；
- 已提交版本损坏（指针指向非提交行或他课行、版本号不符、快照不可解析、摘要或课程不符）→
  ``VersionIntegrityError``，按 5xx 处理，**不回退到草稿或其他版本**（V9 第 5 条）。

修订列表取自该版本的快照。已提交版本不可变（G02 触发器），因此按 ``version_id`` 缓存；
指针每次调用都重读，不缓存。
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Final

from app.repositories.neo4j import GraphScope
from app.repositories.sqlite import connect
from app.services.access import graph_not_published, not_found
from app.services.versions.snapshot import SnapshotFormatError, digest_of, load_snapshot

__all__ = ["PublishedVersion", "VersionIntegrityError", "clear_cache", "resolve_published"]

_CACHE_SIZE: Final = 256


class VersionIntegrityError(RuntimeError):
    """已提交版本或发布指针的数据损坏；对外只报 ``INTERNAL_ERROR``，细节只进日志。"""

    code = "INTERNAL_ERROR"


@dataclass(frozen=True)
class PublishedVersion:
    """一次请求绑定的已提交版本。"""

    course_id: str
    version_id: str
    version: int
    revision_ids: frozenset[str]

    @property
    def graph_version(self) -> int:
        """响应中的 ``graph_version``。"""
        return self.version

    def graph_scope(self) -> GraphScope:
        """读该版本 Neo4j 副本的作用域；副本即发布集合，不带 V。"""
        return GraphScope(self.course_id, self.version_id)

    def covers_revision(self, revision_id: str) -> bool:
        """文本块是否属于该版本：按 ``revision_id`` 判断，不按 ``material_id``（Codex A04-R01）。"""
        return revision_id in self.revision_ids


_lock = threading.Lock()
_revisions: OrderedDict[tuple[str, str], frozenset[str]] = OrderedDict()


def clear_cache() -> None:
    with _lock:
        _revisions.clear()


_BY_POINTER: Final = """
    SELECT c.published_version_id, c.published_version,
           v.version_id, v.course_id, v.version, v.state
    FROM courses c LEFT JOIN graph_versions v ON v.version_id = c.published_version_id
    WHERE c.id = ?"""

_BY_NUMBER: Final = """
    SELECT c.published_version_id, c.published_version,
           v.version_id, v.course_id, v.version, v.state
    FROM courses c LEFT JOIN graph_versions v
         ON v.course_id = c.id AND v.version = ? AND v.state = 'committed'
    WHERE c.id = ?"""


def resolve_published(sqlite_url: str, course_id: str, *, version: int | None = None) -> PublishedVersion:
    """解析本课程当前发布版本（``version`` 省略）或指定的已提交版本。"""
    if version is not None and type(version) is not int:
        raise TypeError("version must be an int")
    with connect(sqlite_url) as database:
        if version is None:
            row = database.execute(_BY_POINTER, (course_id,)).fetchone()
        else:
            row = database.execute(_BY_NUMBER, (version, course_id)).fetchone()
    if row is None:
        raise not_found()
    pointer_id, pointer_number, version_id, row_course, number, state = row
    if pointer_id is None:
        raise graph_not_published()
    if version is None:
        if version_id is None or state != "committed" or row_course != course_id:
            raise VersionIntegrityError(f"publish pointer of course {course_id} is not a committed version")
        if number != pointer_number:
            raise VersionIntegrityError(f"publish pointer number of course {course_id} disagrees with its version")
    elif version_id is None:
        raise not_found()
    return PublishedVersion(course_id, version_id, number, _revision_ids(sqlite_url, course_id, version_id))


def _revision_ids(sqlite_url: str, course_id: str, version_id: str) -> frozenset[str]:
    key = (sqlite_url, version_id)
    with _lock:
        cached = _revisions.get(key)
        if cached is not None:
            _revisions.move_to_end(key)
            return cached
    with connect(sqlite_url) as database:
        row = database.execute(
            "SELECT snapshot_json, digest FROM graph_versions WHERE version_id = ? AND state = 'committed'",
            (version_id,),
        ).fetchone()
    if row is None or row[0] is None:
        raise VersionIntegrityError(f"committed version {version_id} has no snapshot")
    raw = row[0].encode("utf-8")
    if digest_of(raw) != row[1]:
        raise VersionIntegrityError(f"snapshot digest mismatch for version {version_id}")
    try:
        snapshot = load_snapshot(raw)
    except SnapshotFormatError as error:
        raise VersionIntegrityError(f"snapshot of version {version_id} is malformed") from error
    if snapshot.data["course_id"] != course_id:
        raise VersionIntegrityError(f"snapshot of version {version_id} belongs to another course")
    revisions = frozenset(r["revision_id"] for r in snapshot.data["revisions"])
    with _lock:
        _revisions[key] = revisions
        while len(_revisions) > _CACHE_SIZE:
            _revisions.popitem(last=False)
    return revisions
