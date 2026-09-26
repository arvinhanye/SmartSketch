"""F11：审核队列与单项处理（契约 ``getReviewQueue`` / ``resolveReviewItem``；specs/teacher-review-publish.md
「审核队列」；ADR-060）。

**队列按请求实时计算**，不另存一份：请求开始时读 V，从草稿读可见节点与关系（F07 的 ``GraphReader``），
再扣掉教师在 SQLite 里记下的「不是重复」「确认保留」。三栏定义：

- **低置信度关系**：状态为 ``low_confidence``、两端都未被拒绝的可见关系（含 ADR-009 降级而来的关系）。
  排序 ``(confidence 升序, rel_id 升序)``，附原文证据。
- **疑似重复**：未被拒绝的可见节点两两比对，用 E08 名称归一（``find_duplicate_candidates``）得到
  ``same_key`` / ``alias`` / ``containment``；另把节点已存的 ``aliases`` 逐个归一，名称或别名的归一键
  相交也算 ``alias``（原因取最强者）。``similarity``：前两者为 1，包含候选为有效字符比 较短/较长。
  排序 ``(similarity 降序, 小 ID, 大 ID)``。向量相似（E09）要等 D-08 阈值，暂不参与。
- **孤立知识点**：未被拒绝、且没有任何「关系未拒绝、另一端可见且未拒绝」的相连关系的可见节点，
  也就是发布后在图里没有一条边的节点。排序 ``(name, kp_id)``。

**分页**是键集分页：游标编码本栏最后一条的排序键，下一页取排序键严格大于它的条目。处理掉前面的
条目不会让后面的被跳过或重复，这是「分页稳定」的含义；新出现、排在游标之前的条目要到重新从第一页读
时才看到。

**单项处理**（图写入与 F08/F10 同一顺序：取课程写锁 → 读 V → 一个 Neo4j 写事务里先读、判断仍在
队列、再 ``draft_revision + 1`` 并写）：

- 低置信度关系 ``approve`` / ``reject``：改状态、登记人工贡献（此后自动流程不再降级或改写它）、修订号加 1。
  改的是已在环检测范围内的关系（``low_confidence`` 的 ``PREREQUISITE`` 本就参与验环），只会维持或删除
  前置边，不会成环，所以不再验环。
- 疑似重复 ``merge``：交给 F10 ``merge_nodes``（它自己取锁，规则与错误全部沿用）；``reject``：只记
  「不是重复」。
- 孤立知识点 ``approve``：只记「确认保留」；``reject``：节点置 ``rejected``，同 F08 教师修改一样加锁。

条目已不在队列中 → 404；同一动作已经生效（关系已是目标状态、节点已拒绝、这一对或这个节点已记过、
被合并节点已并入主节点）→ 200、``changed = false``，不写入。审计日志归 F12。
"""

from __future__ import annotations

import base64
import binascii
import json
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Final

from app.repositories import review as store
from app.repositories.graph_edit import bump_draft_revision
from app.repositories.neo4j import GraphScope, ScopedTransaction
from app.repositories.sqlite import connect
from app.repositories.tasks import read_effective_task_ids
from app.schemas.contracts import KnowledgePointRef, Relation
from app.services.access import not_found
from app.services.fusion.normalize import (
    CandidateReason,
    NameEntry,
    NormalizedName,
    find_duplicate_candidates,
    normalize_name,
)
from app.services.graph.edit_node import EditContext, InvalidEdit, _course_write
from app.services.graph.merge_nodes import merge_nodes
from app.services.graph.read import _chunks, _relation, _relation_chunk_ids, _source_ref

__all__ = [
    "DEFAULT_LIMIT",
    "KINDS",
    "MAX_LIMIT",
    "ActionResult",
    "Classified",
    "InvalidCursor",
    "classify",
    "decode_cursor",
    "encode_cursor",
    "page",
    "read_queue",
    "resolve_duplicate",
    "resolve_isolated",
    "resolve_relation",
]

DRAFT: Final = "draft"
RELATIONS: Final = "low_confidence_relation"
DUPLICATES: Final = store.DUPLICATE
ISOLATED: Final = store.ISOLATED
KINDS: Final = (RELATIONS, DUPLICATES, ISOLATED)
_COLUMN: Final = {RELATIONS: "low_confidence_relations", DUPLICATES: "suspected_duplicates",
                  ISOLATED: "isolated_nodes"}
DEFAULT_LIMIT: Final = 50
MAX_LIMIT: Final = 200


class InvalidCursor(ValueError):
    """游标无法解析、属于另一栏，或没有和 ``kind`` 一起给出。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------- 分类（纯函数）


@dataclass(frozen=True)
class DuplicatePair:
    left: Mapping[str, Any]
    right: Mapping[str, Any]
    similarity: float
    reason: str

    @property
    def key(self) -> tuple[Any, ...]:
        return (-self.similarity, str(self.left["kp_id"]), str(self.right["kp_id"]))


@dataclass(frozen=True)
class Classified:
    """三栏的完整条目（已排序）；关系条目是 ``GraphReader.edges`` 的原始行，节点条目是原始属性。"""

    relations: list[Mapping[str, Any]]
    duplicates: list[DuplicatePair]
    isolated: list[Mapping[str, Any]]

    def totals(self) -> dict[str, int]:
        return {"low_confidence_relations": len(self.relations), "suspected_duplicates": len(self.duplicates),
                "isolated_nodes": len(self.isolated)}


def _rejected(p: Mapping[str, Any] | None) -> bool:
    return p is None or p.get("status") == "rejected"


def _confidence(edge: Mapping[str, Any]) -> float:
    value = edge["p"].get("confidence", 1.0)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 1.0


def relation_key(edge: Mapping[str, Any]) -> tuple[Any, ...]:
    return (_confidence(edge), str(edge["p"].get("rel_id")))


def isolated_key(p: Mapping[str, Any]) -> tuple[Any, ...]:
    return (str(p.get("name") or ""), str(p["kp_id"]))


def _normalized(text: object) -> NormalizedName | None:
    if not isinstance(text, str):
        return None
    try:
        return normalize_name(text)
    except ValueError:
        return None


def _significant(key: str) -> int:
    return sum(1 for ch in key if unicodedata.category(ch)[0] in "LN")


def _pairs(nodes: Sequence[Mapping[str, Any]]) -> list[DuplicatePair]:
    by_id = {str(p["kp_id"]): p for p in nodes}
    names: dict[str, NormalizedName] = {}
    keys: dict[str, set[str]] = {}
    for kp_id, p in by_id.items():
        name = _normalized(p.get("name"))
        if name is None:  # 名称为空的节点无从比对
            continue
        names[kp_id] = name
        own = set(name.keys)
        for alias in p.get("aliases") or ():
            normalized = _normalized(alias)
            if normalized is not None:
                own.update(normalized.keys)
        keys[kp_id] = own

    found: dict[tuple[str, str], tuple[str, float]] = {}
    for c in find_duplicate_candidates(NameEntry(kp_id, by_id[kp_id]["name"]) for kp_id in names):
        if c.reason is CandidateReason.CONTAINMENT:
            a, b = names[c.left_id].key, names[c.right_id].key
            short, long = sorted((a, b), key=len)
            similarity = float(Fraction(_significant(short), _significant(long)))
        else:
            similarity = 1.0
        found[(c.left_id, c.right_id)] = (c.reason.value, similarity)
    ids = sorted(names)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            current = found.get((a, b))
            if (current is None or current[0] == CandidateReason.CONTAINMENT.value) and keys[a] & keys[b]:
                found[(a, b)] = (CandidateReason.ALIAS.value, 1.0)
    pairs = [DuplicatePair(by_id[a], by_id[b], similarity, reason) for (a, b), (reason, similarity) in found.items()]
    return sorted(pairs, key=lambda d: d.key)


def classify(nodes: Iterable[Mapping[str, Any]], edges: Iterable[Mapping[str, Any]], *,
             dismissed_pairs: Iterable[tuple[str, str]] = (), dismissed_isolated: Iterable[str] = ()) -> Classified:
    """把可见草稿分成三栏。``nodes`` 为节点属性，``edges`` 为 ``{type, from_id, to_id, p}``。"""
    by_id = {str(p["kp_id"]): p for p in nodes}
    edges = list(edges)
    relations = [e for e in edges if e["p"].get("status") == "low_confidence"
                 and not _rejected(by_id.get(e["from_id"])) and not _rejected(by_id.get(e["to_id"]))]
    relations.sort(key=relation_key)

    live = [p for p in by_id.values() if not _rejected(p)]
    skip = {tuple(sorted(pair)) for pair in dismissed_pairs}
    duplicates = [d for d in _pairs(live) if (str(d.left["kp_id"]), str(d.right["kp_id"])) not in skip]

    touched: set[str] = set()
    for e in edges:
        if e["p"].get("status") == "rejected":
            continue
        if _rejected(by_id.get(e["from_id"])) or _rejected(by_id.get(e["to_id"])):
            continue
        touched.update((e["from_id"], e["to_id"]))
    kept = set(dismissed_isolated)
    isolated = sorted((p for p in live if str(p["kp_id"]) not in touched and str(p["kp_id"]) not in kept),
                      key=isolated_key)
    return Classified(relations, duplicates, isolated)


# ---------------------------------------------------------------- 游标与分页


def encode_cursor(kind: str, key: Sequence[Any]) -> str:
    raw = json.dumps({"k": kind, "a": list(key)}, ensure_ascii=False, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _key_shape(kind: str, key: object) -> bool:
    if not isinstance(key, list) or len(key) != (3 if kind == DUPLICATES else 2):
        return False
    number, *texts = key if kind != ISOLATED else [0.0, *key]
    return (isinstance(number, (int, float)) and not isinstance(number, bool)
            and all(isinstance(t, str) for t in texts))


def decode_cursor(kind: str | None, cursor: str | None) -> tuple[Any, ...] | None:
    if cursor is None:
        return None
    if kind is None:
        raise InvalidCursor("kind_required")
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise InvalidCursor("invalid_cursor") from None
    if not isinstance(data, dict) or data.get("k") != kind or not _key_shape(kind, data.get("a")):
        raise InvalidCursor("invalid_cursor")
    return tuple(data["a"])


def page(items: Sequence[Any], key: Any, after: tuple[Any, ...] | None, limit: int) -> tuple[list[Any], tuple | None]:
    """取排序键严格大于 ``after`` 的前 ``limit`` 条；还有后续时返回最后一条的键。"""
    rest = [item for item in items if after is None or tuple(key(item)) > after]
    chosen = rest[:limit]
    return chosen, (tuple(key(chosen[-1])) if len(rest) > limit else None)


# ---------------------------------------------------------------- 读取


def _draft_scope(sqlite_url: str, course_id: str) -> GraphScope:
    with connect(sqlite_url) as database:
        v = read_effective_task_ids(database, course_id)
    return GraphScope(course_id, DRAFT, effective_task_ids=v)


def _classified(ctx: EditContext, course_id: str) -> tuple[GraphScope, Classified]:
    scope = _draft_scope(ctx.sqlite_url, course_id)
    nodes = ctx.reader.nodes(scope, "teacher")
    edges = ctx.reader.edges(scope, "teacher")
    pairs, kept = store.read_dismissals(ctx.sqlite_url, course_id)
    return scope, classify(nodes, edges, dismissed_pairs=pairs, dismissed_isolated=kept)


def _ref(p: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"id": p.get("kp_id"), "name": p.get("name"), "type": p.get("type")}
    return KnowledgePointRef.model_validate({k: v for k, v in fields.items() if v is not None}).model_dump(
        mode="json", exclude_none=True)


def _relations(ctx: EditContext, scope: GraphScope, edges: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    chunks = _chunks(ctx.sqlite_url, scope.course_id, {c for e in edges for c in _relation_chunk_ids(e, scope)})
    out = []
    for e in edges:
        refs = [ref for cid in _relation_chunk_ids(e, scope)
                if (ref := _source_ref(chunks.get(cid), None, None, None)) is not None]
        relation: Relation | None = _relation(scope.course_id, e, refs)
        if relation is not None:
            out.append(relation.model_dump(mode="json", exclude_none=True))
    return out


def read_queue(ctx: EditContext, course_id: str, *, kind: str | None = None, cursor: str | None = None,
               limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """契约 ``ReviewQueue``：不带 ``kind`` 时三栏各第一页，带 ``kind`` 时只填该栏。"""
    after = decode_cursor(kind, cursor)
    scope, c = _classified(ctx, course_id)
    body: dict[str, Any] = {"low_confidence_relations": [], "suspected_duplicates": [], "isolated_nodes": [],
                            "totals": c.totals(),
                            "next_cursors": {column: None for column in _COLUMN.values()}}
    wanted = KINDS if kind is None else (kind,)
    if RELATIONS in wanted:
        chosen, last = page(c.relations, relation_key, after if kind else None, limit)
        body["low_confidence_relations"] = _relations(ctx, scope, chosen)
        body["next_cursors"]["low_confidence_relations"] = last and encode_cursor(RELATIONS, last)
    if DUPLICATES in wanted:
        chosen, last = page(c.duplicates, lambda d: d.key, after if kind else None, limit)
        body["suspected_duplicates"] = [{"candidates": [_ref(d.left), _ref(d.right)], "similarity": d.similarity,
                                         "reason": d.reason} for d in chosen]
        body["next_cursors"]["suspected_duplicates"] = last and encode_cursor(DUPLICATES, last)
    if ISOLATED in wanted:
        chosen, last = page(c.isolated, isolated_key, after if kind else None, limit)
        body["isolated_nodes"] = [_ref(p) for p in chosen]
        body["next_cursors"]["isolated_nodes"] = last and encode_cursor(ISOLATED, last)
    return body


# ---------------------------------------------------------------- 单项处理


@dataclass(frozen=True)
class ActionResult:
    item: str
    action: str
    changed: bool
    totals: dict[str, int]

    def body(self) -> dict[str, Any]:
        return {"item": self.item, "action": self.action, "changed": self.changed, "totals": self.totals}


def _result(ctx: EditContext, course_id: str, item: str, action: str, changed: bool) -> ActionResult:
    return ActionResult(item, action, changed, _classified(ctx, course_id)[1].totals())


def _field(field: str, reason: str) -> dict[str, str]:
    return {"in": "body", "field": field, "reason": reason}


_TARGET: Final = {"approve": "approved", "reject": "rejected"}


def resolve_relation(ctx: EditContext, course_id: str, rel_id: str, action: str) -> ActionResult:
    target = _TARGET[action]

    with _course_write(ctx, course_id) as scope:
        bumped: list[int] = []

        def bump() -> None:  # 驱动重跑事务时不重复加
            if not bumped:
                bumped.append(bump_draft_revision(ctx.sqlite_url, course_id))

        def work(tx: ScopedTransaction) -> bool:
            state = store.read_relation(tx, rel_id)
            if state is None:
                raise not_found()
            if state.status == target:
                return False
            if state.status != "low_confidence" or "rejected" in (state.from_status, state.to_status):
                raise not_found()
            bump()
            if not store.set_relation_status(tx, rel_id, target):  # 持守卫锁读过，不应落空
                raise RuntimeError(f"relation {rel_id} changed inside the review transaction")
            return True

        changed = ctx.store.transaction(scope, work)
    return _result(ctx, course_id, RELATIONS, action, changed)


def resolve_isolated(ctx: EditContext, course_id: str, kp_id: str, action: str, user_id: str) -> ActionResult:
    if action == "approve":
        if store.is_dismissed(ctx.sqlite_url, course_id, ISOLATED, kp_id):
            return _result(ctx, course_id, ISOLATED, action, False)
        _, c = _classified(ctx, course_id)
        if kp_id not in {str(p["kp_id"]) for p in c.isolated}:
            raise not_found()
        changed = store.dismiss(ctx.sqlite_url, course_id, ISOLATED, kp_id, user_id)
        return _result(ctx, course_id, ISOLATED, action, changed)

    with _course_write(ctx, course_id) as scope:
        bumped: list[int] = []

        def bump() -> None:  # 驱动重跑事务时不重复加
            if not bumped:
                bumped.append(bump_draft_revision(ctx.sqlite_url, course_id))

        def work(tx: ScopedTransaction) -> bool:
            state = store.read_isolation(tx, kp_id)
            if state is None:
                raise not_found()
            if state.status == "rejected":
                return False
            if state.relations or store.is_dismissed(ctx.sqlite_url, course_id, ISOLATED, kp_id):
                raise not_found()
            bump()
            if not store.reject_node(tx, kp_id, state.revision):
                raise RuntimeError(f"knowledge point {kp_id} changed inside the review transaction")
            return True

        changed = ctx.store.transaction(scope, work)
    return _result(ctx, course_id, ISOLATED, action, changed)


def _duplicate_pairs(ctx: EditContext, course_id: str) -> set[tuple[str, str]]:
    """当前「疑似重复」栏里的节点对，键为 ``(小 ID, 大 ID)``（与 ``Classified.duplicates`` 同源）。"""
    _, c = _classified(ctx, course_id)
    return {(str(d.left["kp_id"]), str(d.right["kp_id"])) for d in c.duplicates}


def _require_duplicate(ctx: EditContext, course_id: str, a: str, b: str) -> None:
    """这一对是否真在当前「疑似重复」栏：不在就是 404；``merge`` 与 ``reject`` 共用同一条复核。"""
    if (a, b) not in _duplicate_pairs(ctx, course_id):
        raise not_found()


def resolve_duplicate(ctx: EditContext, course_id: str, kp_ids: Sequence[str], action: str,
                      primary_id: str | None, user_id: str) -> ActionResult:
    a, b = sorted(kp_ids)
    if action == "merge":
        if primary_id is None:
            raise InvalidEdit([_field("primary_id", "missing")])
        if primary_id not in (a, b):
            raise InvalidEdit([_field("primary_id", "not_in_pair")])
        other = b if primary_id == a else a
        scope = _draft_scope(ctx.sqlite_url, course_id)
        found = {str(p["kp_id"]): p for p in ctx.reader.nodes(scope, "teacher", [a, b])}
        if primary_id in found and other not in found and other in (found[primary_id].get("merged_from") or ()):
            return _result(ctx, course_id, DUPLICATES, action, False)
        if len(found) != 2:
            raise not_found()
        _require_duplicate(ctx, course_id, a, b)  # 不在疑似重复栏：与 reject 一样 404，且一个字也不写
        merge_nodes(ctx, course_id, primary_id, [other])
        return _result(ctx, course_id, DUPLICATES, action, True)

    if primary_id is not None:
        raise InvalidEdit([_field("primary_id", "extra_forbidden")])
    key = store.pair_key(a, b)
    if store.is_dismissed(ctx.sqlite_url, course_id, DUPLICATES, key):
        return _result(ctx, course_id, DUPLICATES, action, False)
    _require_duplicate(ctx, course_id, a, b)
    changed = store.dismiss(ctx.sqlite_url, course_id, DUPLICATES, key, user_id)
    return _result(ctx, course_id, DUPLICATES, action, changed)
