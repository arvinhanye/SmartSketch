"""F08：教师编辑、新建与解锁知识点（契约 ``updateKnowledgePoint`` / ``createKnowledgePoint`` /
``unlockKnowledgePoint``；specs/teacher-review-publish.md「节点加锁」V4；ADR-035）。

每次写入的顺序固定（V4）：

1. 有界等待取课程写锁（持有方 ``edit``，租约与心跳同 ``course_locks``）；超时 → ``CourseBusy``（409
   ``COURSE_BUSY``，``holder`` 为当时的持有方）。
2. 持锁读一次 V，读目标节点并校验：不可见 → 404；``expected_revision`` 不等于当前修订号 →
   ``RevisionConflict``（409 ``REVISION_CONFLICT``，带当前内容，**不写入**）；输入不合法 → ``InvalidEdit``（422）。
   校验失败不改变任何数据，也不增加草稿修订号。
3. ``courses.draft_revision + 1``（在写 Neo4j 之前），然后一个 Neo4j 写事务，更新以修订号为条件。
4. 释放锁。

加锁语义（ADR-035）：锁是整个节点（全部字段与来源），不连带关系；任何成功的教师修改都置
``locked = true``。修改接口不能解锁；解锁是单独的接口与动作，节点本就未加锁时原样返回、不写入。
新建的知识点必须带至少一条来源，块须属于本课程且其修订关联到 V 中的任务。

审计（F12，ADR-061）：取锁后先对账本课程遗留的审计行（``audit.reconcile``）；第 3 步的草稿修订号加 1
改由 ``audit.begin`` 与 ``pending`` 审计行在同一 SQLite 事务里完成，Neo4j 写入返回后置 ``committed`` /
``aborted``。``EditContext.actor_id`` 为空时不记审计。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final, Protocol

from app.repositories import course_locks
from app.repositories.graph_edit import source_chunks
from app.repositories.neo4j import GraphScope
from app.repositories.sqlite import connect
from app.repositories.tasks import read_effective_task_ids
from app.schemas.contracts import KnowledgePoint
from app.services.access import not_found
from app.services.graph import audit
from app.services.graph.read import _levels, _node

__all__ = [
    "CourseBusy",
    "EditContext",
    "InvalidEdit",
    "RevisionConflict",
    "SourceInput",
    "create_node",
    "unlock_node",
    "update_node",
]

DRAFT: Final = "draft"
LOCK_HOLDER: Final = "edit"
#: 教师新建的知识点视为已确认（与 ``source = manual`` 的关系同口径）。
MANUAL_STATUS: Final = "approved"
MANUAL_CONFIDENCE: Final = 1.0
#: ``REVISION_CONFLICT`` 的 ``details.current`` 给出的字段（学生可见内容与锁状态）。
_CURRENT_FIELDS: Final = ("name", "aliases", "type", "definition", "importance", "difficulty", "status", "locked")


class NodeStore(Protocol):
    def node(self, scope: GraphScope, kp_id: str) -> dict[str, Any] | None: ...

    def chapter_visible(self, scope: GraphScope, chapter_id: str) -> bool: ...

    def update(self, scope: GraphScope, kp_id: str, expected_revision: int,
               changes: Mapping[str, Any]) -> dict[str, Any] | None: ...

    def unlock(self, scope: GraphScope, kp_id: str, expected_revision: int) -> dict[str, Any] | None: ...

    def create(self, scope: GraphScope, kp_id: str, props: Mapping[str, Any],
               sources: Sequence[Mapping[str, Any]]) -> dict[str, Any]: ...


class GraphView(Protocol):
    def nodes(self, scope: GraphScope, reader: Any, kp_ids: Sequence[str] | None = None) -> list[dict[str, Any]]: ...

    def edges(self, scope: GraphScope, reader: Any, kp_ids: Sequence[str] | None = None) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class EditContext:
    sqlite_url: str
    store: NodeStore
    reader: GraphView
    lock_seconds: int
    wait_seconds: float
    #: 发起写入的用户（审计的「谁」）；``None`` 时不记审计（内部调用）。
    actor_id: str | None = None


class CourseBusy(Exception):
    code = "COURSE_BUSY"

    def __init__(self, holder: str | None) -> None:
        super().__init__("course write lock is busy")
        self.holder = holder

    def details(self) -> dict[str, str]:
        return {} if self.holder is None else {"holder": self.holder}


class RevisionConflict(Exception):
    """``expected_revision`` 已过期：期间有他人写入。带当前内容，后写者据此知道自己会覆盖什么。"""

    code = "REVISION_CONFLICT"

    def __init__(self, kp_id: str, expected: int, current: Mapping[str, Any]) -> None:
        super().__init__("knowledge point revision changed")
        self.kp_id = kp_id
        self.expected = expected
        self.current = dict(current)

    def details(self) -> dict[str, Any]:
        current = {k: self.current.get(k) for k in _CURRENT_FIELDS if self.current.get(k) is not None}
        current["aliases"] = list(self.current.get("aliases") or [])
        current["locked"] = bool(self.current.get("locked", False))
        return {"kp_id": self.kp_id, "expected_revision": self.expected,
                "current_revision": int(self.current.get("revision") or 1), "current": current}


class InvalidEdit(Exception):
    """业务校验失败（422 ``VALIDATION_ERROR``）；``fields`` 为 ``details.fields`` 的各项。"""

    def __init__(self, fields: Sequence[Mapping[str, str]]) -> None:
        super().__init__("invalid knowledge point edit")
        self.fields = [dict(f) for f in fields]


@dataclass(frozen=True)
class SourceInput:
    chunk_id: str
    evidence_start: int | None = None
    evidence_end: int | None = None


def _field(field: str, reason: str) -> dict[str, str]:
    return {"in": "body", "field": field, "reason": reason}


# ---------------------------------------------------------------- 锁与作用域


@contextmanager
def _course_write(ctx: EditContext, course_id: str) -> Iterator[GraphScope]:
    lock = course_locks.acquire(ctx.sqlite_url, course_id, holder=LOCK_HOLDER, lease_seconds=ctx.lock_seconds,
                                wait_seconds=ctx.wait_seconds)
    if lock is None:
        raise CourseBusy(course_locks.current_holder(ctx.sqlite_url, course_id))
    with course_locks.held(ctx.sqlite_url, lock, lease_seconds=ctx.lock_seconds):
        with connect(ctx.sqlite_url) as database:
            effective = read_effective_task_ids(database, course_id)
        scope = GraphScope(course_id, DRAFT, effective_task_ids=effective)
        audit.reconcile(ctx, scope)
        yield scope


def _respond(ctx: EditContext, scope: GraphScope, p: Mapping[str, Any]) -> KnowledgePoint:
    kp_id = str(p["kp_id"])
    levels = _levels((n.get("kp_id") for n in ctx.reader.nodes(scope, "teacher")), ctx.reader.edges(scope, "teacher"))
    node = _node(scope.course_id, p, levels.get(kp_id, 0))
    if node is None:  # 存储里的节点不满足契约：不应出现
        raise RuntimeError(f"knowledge point {kp_id} does not satisfy the contract after the write")
    return node


def _current(ctx: EditContext, scope: GraphScope, kp_id: str, expected_revision: int) -> dict[str, Any]:
    node = ctx.store.node(scope, kp_id)
    if node is None:
        raise not_found()
    if int(node.get("revision") or 0) != expected_revision:
        raise RevisionConflict(kp_id, expected_revision, node)
    return node


def _lost_race(ctx: EditContext, scope: GraphScope, kp_id: str, expected_revision: int) -> Exception:
    """条件更新没有命中：持锁下不应出现（写锁被他人夺走时才可能），按冲突报告而不是静默成功。"""
    node = ctx.store.node(scope, kp_id)
    if node is None:
        return not_found()
    return RevisionConflict(kp_id, expected_revision, node)


def _write(ctx: EditContext, pending: audit.Pending, write: Callable[[], dict[str, Any] | None],
           lost: Callable[[], Exception] | None) -> dict[str, Any]:
    """执行一次 Neo4j 写入并结束审计行：成功 → ``committed``；抛错或条件未命中 → ``aborted`` 后原样抛出。"""
    try:
        written = write()
        if written is None:
            if lost is None:  # pragma: no cover - create 总是返回节点
                raise RuntimeError("draft write returned no node")
            raise lost()
    except BaseException as exc:
        audit.abort(ctx, pending, exc)
        raise
    audit.commit(ctx, pending, revision_after=int(written.get("revision") or 0) or None)
    return written


# ---------------------------------------------------------------- 输入规范化


def _text(field: str, value: object, errors: list[dict[str, str]]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(_field(field, "blank"))
        return None
    return value.strip()


def _aliases(values: Sequence[str], errors: list[dict[str, str]]) -> list[str]:
    out: list[str] = []
    for i, alias in enumerate(values):
        text = _text(f"aliases.{i}", alias, errors)
        if text is not None and text not in out:
            out.append(text)
    return out


def _changes(changes: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    out: dict[str, Any] = {}
    for key, value in changes.items():
        if key in ("name", "definition"):
            text = _text(key, value, errors)
            if text is not None:
                out[key] = text
        elif key == "aliases":
            out[key] = _aliases(value, errors)
        elif key in ("type", "status"):
            out[key] = getattr(value, "value", value)
        elif key in ("importance", "difficulty"):
            out[key] = float(value)
        else:
            errors.append(_field(key, "extra_forbidden"))
    if not changes:
        errors.append(_field("", "no_changes"))
    if errors:
        raise InvalidEdit(errors)
    return out


# ---------------------------------------------------------------- 操作


def update_node(ctx: EditContext, course_id: str, kp_id: str, expected_revision: int,
                changes: Mapping[str, Any]) -> KnowledgePoint:
    """教师修改：写入字段、加锁、修订号加 1。"""
    normalized = _changes(changes)
    with _course_write(ctx, course_id) as scope:
        node = _current(ctx, scope, kp_id, expected_revision)
        pending = audit.begin(ctx, course_id, "update", kp_id, revision_before=expected_revision,
                              summary=audit.update_summary(node, normalized))
        written = _write(ctx, pending, lambda: ctx.store.update(scope, kp_id, expected_revision, normalized),
                         lambda: _lost_race(ctx, scope, kp_id, expected_revision))
        return _respond(ctx, scope, written)


def unlock_node(ctx: EditContext, course_id: str, kp_id: str, expected_revision: int) -> KnowledgePoint:
    """显式解锁；节点本就未加锁时原样返回，不写入、不加修订号。"""
    with _course_write(ctx, course_id) as scope:
        node = _current(ctx, scope, kp_id, expected_revision)
        if not node.get("locked"):
            return _respond(ctx, scope, node)
        pending = audit.begin(ctx, course_id, "unlock", kp_id, revision_before=expected_revision,
                              summary=audit.unlock_summary())
        written = _write(ctx, pending, lambda: ctx.store.unlock(scope, kp_id, expected_revision),
                         lambda: _lost_race(ctx, scope, kp_id, expected_revision))
        return _respond(ctx, scope, written)


def _sources(ctx: EditContext, scope: GraphScope, sources: Sequence[SourceInput],
             errors: list[dict[str, str]]) -> list[dict[str, Any]]:
    chunks = source_chunks(ctx.sqlite_url, scope.course_id, (s.chunk_id for s in sources),
                           scope.effective_task_ids or ())
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for i, source in enumerate(sources):
        chunk = chunks.get(source.chunk_id)
        if chunk is None:
            errors.append(_field(f"sources.{i}.chunk_id", "source_not_available"))
            continue
        start, end = source.evidence_start, source.evidence_end
        if start is None and end is None:
            start, end = 0, len(chunk.text)
        elif start is None or end is None:
            errors.append(_field(f"sources.{i}.{'evidence_start' if start is None else 'evidence_end'}", "missing"))
            continue
        elif not 0 <= start < end <= len(chunk.text):
            errors.append(_field(f"sources.{i}.evidence_end", "evidence_out_of_range"))
            continue
        if (chunk.chunk_id, start, end) in seen:
            continue
        seen.add((chunk.chunk_id, start, end))
        rows.append({"chunk_id": chunk.chunk_id, "document_id": chunk.material_id,
                     "revision_id": chunk.revision_id, "evidence_start": start, "evidence_end": end})
    return rows


def create_node(ctx: EditContext, course_id: str, fields: Mapping[str, Any],
                sources: Sequence[SourceInput]) -> KnowledgePoint:
    """新建人工知识点：``source = manual``、``locked = true``、``status = approved``，至少一条来源。"""
    errors: list[dict[str, str]] = []
    name = _text("name", fields.get("name"), errors)
    definition = _text("definition", fields.get("definition"), errors)
    aliases = _aliases(fields.get("aliases") or [], errors)
    if not sources:
        errors.append(_field("sources", "too_short"))
    if errors:
        raise InvalidEdit(errors)
    with _course_write(ctx, course_id) as scope:
        chapter_id = fields.get("chapter_id")
        if chapter_id is not None and not ctx.store.chapter_visible(scope, chapter_id):
            errors.append(_field("chapter_id", "not_found"))
        rows = _sources(ctx, scope, sources, errors)
        if errors:
            raise InvalidEdit(errors)
        props: dict[str, Any] = {
            "name": name, "type": getattr(fields["type"], "value", fields["type"]), "definition": definition,
            "aliases": aliases, "confidence": MANUAL_CONFIDENCE, "status": MANUAL_STATUS,
        }
        for key in ("chapter_id", "importance", "difficulty"):
            if fields.get(key) is not None:
                props[key] = fields[key]
        kp_id = "kp_" + uuid.uuid4().hex
        pending = audit.begin(ctx, course_id, "create", kp_id, revision_before=None,
                              summary=audit.create_summary(props, rows))
        written = _write(ctx, pending, lambda: ctx.store.create(scope, kp_id, props, rows), None)
        return _respond(ctx, scope, written)
