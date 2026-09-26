"""F12：教师图编辑审计（ADR-061；specs/teacher-review-publish.md「图编辑审计」）。

记录 F08 新建/修改/解锁、F09 删除、F10 合并这五种教师写入：**谁**（``actor_id``）、**何时**（``created_at`` /
``resolved_at``）、**何版本**（写入后的课程 ``draft_revision`` 与节点修订号前后值）、**变更摘要**（白名单字段、
脱敏）。只读、校验失败、冲突、未加锁节点的解锁等没有写入的请求不记录。

跨库顺序（Neo4j 与 SQLite 之间没有分布式事务）：

1. ``begin``：持课程写锁、校验通过后，在一个 SQLite 事务里 ``draft_revision + 1`` 并插入 ``pending`` 行
   （取代原来单独的 ``bump_draft_revision``）。失败则什么都没写，编辑按原样报错。
2. Neo4j 写事务。
3. ``commit`` / ``abort``：把行置为 ``committed`` / ``aborted``。SQLite 暂时失败时按 ``RETRY_DELAYS`` 退避重试；
   仍失败则只记日志、**不**让已提交的编辑报错（否则客户端重试会得到 ``REVISION_CONFLICT``），行留在 ``pending``。
4. ``reconcile``：每次教师写入取得课程写锁后、做任何事之前，先把本课程遗留的 ``pending`` 行对照 Neo4j
   判定为已提交或未生效。持锁时不会有其他教师写入插进来，自动流程又不改加锁节点，所以判定是确定的
   （规则见 ``_applied``）。

``ctx.actor_id is None``（不经 API 的内部调用）时不记审计，只加草稿修订号，与 F08～F10 原行为相同。
"""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from app.repositories import edit_logs
from app.repositories.edit_logs import EditLog
from app.repositories.graph_edit import bump_draft_revision
from app.repositories.neo4j import GraphScope

__all__ = [
    "RETRY_DELAYS",
    "Pending",
    "abort",
    "begin",
    "commit",
    "create_summary",
    "delete_summary",
    "merge_summary",
    "reconcile",
    "redact",
    "unlock_summary",
    "update_summary",
]

log = logging.getLogger(__name__)

#: ``commit``/``abort`` 遇到 SQLite 错误时的退避（秒）；次数 = 长度 + 1。
RETRY_DELAYS: Final = (0.05, 0.2, 0.5)
#: 摘要中单个字符串的上限（字符），超出截断并以 ``…`` 结尾。
MAX_TEXT: Final = 500
MAX_ITEMS: Final = 50
#: 审计里保留的知识点字段（学生可见内容与锁状态）；其余属性（贡献、向量、谱系等）不进摘要。
FIELDS: Final = ("name", "aliases", "type", "definition", "importance", "difficulty", "status", "chapter_id")
REDACTED: Final = "[REDACTED]"

_SECRETS: Final = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.DOTALL),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),       # JWT
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),                                           # 模型服务密钥
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\$argon2(?:id|i|d)\$[^\s]+"),                                         # 口令散列
)
_ASSIGNMENT: Final = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|token|authorization)(\s*[:=]\s*)\S+")


class _Store(Protocol):
    def node(self, scope: GraphScope, kp_id: str) -> dict[str, Any] | None: ...


class _Context(Protocol):
    sqlite_url: str
    store: _Store
    actor_id: str | None


# ---------------------------------------------------------------- 脱敏与摘要


def redact(text: str) -> str:
    """去掉看起来像密钥、令牌、口令的片段，并截断到 ``MAX_TEXT``。"""
    for pattern in _SECRETS:
        text = pattern.sub(REDACTED, text)
    text = _ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, bool) or value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in list(value)[:MAX_ITEMS]]
    return redact(str(getattr(value, "value", value)))


def _fields(props: Mapping[str, Any]) -> dict[str, Any]:
    return {k: _clean(props[k]) for k in FIELDS if props.get(k) is not None}


def update_summary(before: Mapping[str, Any], changes: Mapping[str, Any]) -> dict[str, Any]:
    """修改：每个提交字段的前后值（含未变的，教师确认过），以及锁状态。"""
    diff = {k: {"before": _clean(before.get(k)), "after": _clean(changes[k])} for k in FIELDS if k in changes}
    return {"changes": diff, "locked": {"before": bool(before.get("locked")), "after": True}}


def unlock_summary() -> dict[str, Any]:
    return {"locked": {"before": True, "after": False}}


def create_summary(props: Mapping[str, Any], sources: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"fields": _fields(props),
            "sources": [{k: _clean(s.get(k)) for k in ("chunk_id", "evidence_start", "evidence_end")}
                        for s in sources[:MAX_ITEMS]]}


def delete_summary(node: Mapping[str, Any], relations: int | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"fields": _fields(node), "locked": bool(node.get("locked"))}
    if relations is not None:
        out["relations_deleted"] = relations
    return out


def merge_summary(primary: Mapping[str, Any], merged: Sequence[Mapping[str, Any]], *,
                  lineage: Sequence[str] = (), relations_removed: int | None = None,
                  relations_created: int | None = None, evidence_moved: int | None = None) -> dict[str, Any]:
    """合并：主节点、**直接**被合并的节点（ADR-012 修订 3：直接父子关系只记在这里）与展平后的谱系。"""
    out: dict[str, Any] = {
        "primary": {"kp_id": _clean(primary.get("kp_id")), "name": _clean(primary.get("name"))},
        "merged": [{"kp_id": _clean(m.get("kp_id")), "name": _clean(m.get("name")),
                    "revision": m.get("revision")} for m in merged],
        "merged_from": _clean(list(lineage)),
    }
    for key, value in (("relations_removed", relations_removed), ("relations_created", relations_created),
                       ("evidence_moved", evidence_moved)):
        if value is not None:
            out[key] = value
    return out


# ---------------------------------------------------------------- 写入路径


@dataclass(frozen=True)
class Pending:
    """一次已加过草稿修订号的写入；``event_id is None`` 表示不记审计。"""

    event_id: str | None
    draft_revision: int
    action: str = ""
    kp_id: str = ""


def begin(ctx: _Context, course_id: str, action: str, kp_id: str, *, revision_before: int | None,
          summary: Mapping[str, Any]) -> Pending:
    """持锁、校验通过后调用：草稿修订号加 1 并记 ``pending`` 审计行（同一 SQLite 事务）。"""
    if ctx.actor_id is None:
        return Pending(None, bump_draft_revision(ctx.sqlite_url, course_id), action, kp_id)
    event_id, revision = edit_logs.begin(ctx.sqlite_url, course_id=course_id, actor_id=ctx.actor_id, action=action,
                                         kp_id=kp_id, kp_revision_before=revision_before, summary=summary)
    return Pending(event_id, revision, action, kp_id)


def _retry(what: str, event_id: str, operation: Callable[[], bool]) -> bool:
    for delay in (*RETRY_DELAYS, None):
        try:
            operation()
            return True
        except (sqlite3.Error, OSError) as exc:
            if delay is None:
                log.warning("graph edit audit %s for %s failed after retries (%s); left pending for reconcile",
                            what, event_id, type(exc).__name__)
                return False
            _sleep(delay)
    return False  # pragma: no cover - loop always returns


def _sleep(seconds: float) -> None:  # 测试替换
    time.sleep(seconds)


def commit(ctx: _Context, pending: Pending, *, revision_after: int | None,
           summary: Mapping[str, Any] | None = None) -> bool:
    """Neo4j 已提交：置 ``committed``。从不抛错；最终失败时行留在 ``pending``，由 ``reconcile`` 补齐。"""
    if pending.event_id is None:
        return True
    event_id = pending.event_id
    return _retry("commit", event_id, lambda: edit_logs.resolve(
        ctx.sqlite_url, event_id, state="committed", resolved_by="writer", kp_revision_after=revision_after,
        summary=summary))


def abort(ctx: _Context, pending: Pending, error: BaseException) -> bool:
    """Neo4j 写入没有生效：置 ``aborted``，原因只记错误码或异常类名（不含消息，避免带出数据）。从不抛错。"""
    if pending.event_id is None:
        return True
    event_id = pending.event_id
    reason = str(getattr(error, "code", None) or type(error).__name__)[:255]
    return _retry("abort", event_id, lambda: edit_logs.resolve(
        ctx.sqlite_url, event_id, state="aborted", resolved_by="writer", failure_reason=reason))


# ---------------------------------------------------------------- 对账


def _applied(entry: EditLog, node: Mapping[str, Any] | None) -> tuple[bool, int | None]:
    """持课程写锁时判定遗留的 ``pending`` 写入是否已在 Neo4j 生效，返回 ``(已生效, 写入后节点修订号)``。

    - ``create``：节点存在（ID 由本次写入随机生成）。
    - ``update`` / ``merge``：主节点已加锁且修订号恰为写前 + 1。未生效时节点要么保持写前修订号，要么
      未加锁（自动流程只改未加锁节点），都不会同时满足这两条；生效后节点加锁，自动流程不再改它，
      而下一次教师写入会先来对账。
    - ``unlock``：节点未加锁（解锁只对加锁节点写入，未生效时仍加锁）。
    - ``delete``：节点对本课程草稿已不可见。
    """
    before = entry.kp_revision_before
    if entry.action == "create":
        return node is not None, 1 if node is not None else None
    if entry.action == "delete":
        return node is None, None
    if node is None or before is None:
        return False, None
    if entry.action == "unlock":
        return not node.get("locked"), before + 1
    revision = int(node.get("revision") or 0)
    return bool(node.get("locked")) and revision == before + 1, before + 1


def reconcile(ctx: _Context, scope: GraphScope) -> list[tuple[str, str]]:
    """把本课程遗留的 ``pending`` 行判定为 ``committed`` / ``aborted``；必须持课程写锁调用。

    返回 ``[(event_id, state)]``。读 Neo4j 失败时抛出 ``RepositoryError``（与随后的写入一样不可用）。
    """
    resolved: list[tuple[str, str]] = []
    for entry in edit_logs.pending(ctx.sqlite_url, scope.course_id):
        done, after = _applied(entry, ctx.store.node(scope, entry.kp_id))
        state = "committed" if done else "aborted"
        if edit_logs.resolve(ctx.sqlite_url, entry.event_id, state=state, resolved_by="reconcile",
                             kp_revision_after=after if done else None,
                             failure_reason=None if done else "not_applied"):
            resolved.append((entry.event_id, state))
    return resolved
