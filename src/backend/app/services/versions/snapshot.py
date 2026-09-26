"""G01：发布快照的组装、规范化与摘要（specs/teacher-review-publish.md V3，ADR-012）。

纯函数，不连库。调用方（G04 发布 P4～P7）在持课程写锁时读出**可见**草稿（按 V 过滤的节点、关系、
章节与来源关联，同 F07）、V 内任务的全部资料修订与本课程文本块的 ``chunk_id → revision_id``，
组成 ``DraftGraph`` 交给 ``build_snapshot``：

1. **发布集合**：知识点与关系取 ``status ∈ {draft, approved}``，关系另要求两端都在集合内（端点被
   排除的关系连带排除）；章节取集合内知识点引用到的章节及其祖先。``excluded`` 计
   ``low_confidence`` 知识点、``low_confidence`` 关系与连带排除的关系；``rejected`` 不计。
2. **校验**（任一不通过 → ``SnapshotBlocked``，``reasons`` 按契约 ``PublishBlockedReason``）：
   发布集合的 ``PREREQUISITE`` 成环（F05 ``find_cycle``，闭合环路）、关系端点在草稿中不存在、
   来源块不属于本课程或其修订不在本版本修订内、集合为空、``merged_from`` 谱系违反不变式。
3. **快照**（``snapshot_format = 1``）只含学生可见的内容字段与 ``merged_from``；不含状态、置信度、
   锁、来源类别、修订号、时间戳、向量与可推导字段（``level``、统计）。
4. **规范化**：UTF-8；键按字典序；紧凑分隔符；不转义非 ASCII；空值写 ``null`` 不省略；
   ``revisions``/``chapters``/``nodes``/``edges`` 按各自 ID 升序；``aliases``、``source_refs``、
   ``merged_from`` 去重升序；数值原样输出（拒绝 NaN/∞）。摘要 = ``sha256:`` + 规范字节的 sha256。

``load_snapshot`` 读回存储的快照：结构逐键校验，且必须已是规范形态，读出即可复算摘要（P9、R4）。
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from app.services.graph.dag import find_cycle

__all__ = [
    "BlockReason",
    "DraftChapter",
    "DraftEdge",
    "DraftGraph",
    "DraftNode",
    "Excluded",
    "Revision",
    "Snapshot",
    "SnapshotBlocked",
    "SnapshotBuild",
    "SnapshotFormatError",
    "build_snapshot",
    "canonical_bytes",
    "digest_of",
    "load_snapshot",
]

SNAPSHOT_FORMAT: Final = 1
NODE_TYPES: Final = frozenset({"concept", "theorem", "formula", "method", "example"})
RELATION_TYPES: Final = frozenset({"CONTAINS", "PREREQUISITE", "RELATED_TO", "EXAMPLE_OF"})
STATUSES: Final = frozenset({"draft", "low_confidence", "approved", "rejected"})
PUBLISHABLE: Final = frozenset({"draft", "approved"})

_TOP_KEYS: Final = ("chapters", "course_id", "edges", "nodes", "revisions", "snapshot_format")
_REVISION_KEYS: Final = ("content_hash", "material_id", "parser_version", "revision_id")
_CHAPTER_KEYS: Final = ("chapter_id", "order", "parent_id", "title")
_NODE_KEYS: Final = ("aliases", "chapter_id", "definition", "difficulty", "importance", "kp_id", "merged_from",
                     "name", "source_refs", "type")
_EDGE_KEYS: Final = ("from_id", "rel_id", "source_refs", "to_id", "type")


class SnapshotFormatError(ValueError):
    """输入草稿或存储快照不合结构（实现缺陷或数据损坏），不是可向教师展示的发布阻断原因。"""


# ---------------------------------------------------------------- 输入


@dataclass(frozen=True)
class Revision:
    revision_id: str
    material_id: str
    content_hash: str
    parser_version: str


@dataclass(frozen=True)
class DraftChapter:
    chapter_id: str
    title: str
    order: int
    parent_id: str | None = None


@dataclass(frozen=True)
class DraftNode:
    kp_id: str
    name: str
    type: str
    definition: str
    status: str
    aliases: Sequence[str] = ()
    chapter_id: str | None = None
    difficulty: float | None = None
    importance: float | None = None
    source_refs: Sequence[str] = ()  # chunk_id
    merged_from: Sequence[str] = ()


@dataclass(frozen=True)
class DraftEdge:
    rel_id: str
    type: str
    from_id: str
    to_id: str
    status: str
    source_refs: Sequence[str] = ()  # chunk_id


@dataclass(frozen=True)
class DraftGraph:
    """可见草稿；``chunk_revisions`` 为本课程文本块 ``chunk_id → revision_id``（D10 按课程读出）。"""

    course_id: str
    revisions: Sequence[Revision]
    chapters: Sequence[DraftChapter]
    nodes: Sequence[DraftNode]
    edges: Sequence[DraftEdge]
    chunk_revisions: Mapping[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------- 输出


@dataclass(frozen=True)
class Excluded:
    low_confidence_nodes: int = 0
    low_confidence_edges: int = 0
    cascaded_edges: int = 0

    def to_dict(self) -> dict[str, int]:
        return {"low_confidence_nodes": self.low_confidence_nodes,
                "low_confidence_edges": self.low_confidence_edges, "cascaded_edges": self.cascaded_edges}


@dataclass(frozen=True)
class BlockReason:
    """契约 ``PublishBlockedReason`` 的一项。"""

    kind: str
    cycle: tuple[str, ...] | None = None
    relation_id: str | None = None
    kp_id: str | None = None
    chunk_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind}
        if self.cycle is not None:
            out["cycle"] = list(self.cycle)
        for name in ("relation_id", "kp_id", "chunk_id"):
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        return out


class SnapshotBlocked(Exception):
    """发布集合校验不通过；``reasons`` 非空，顺序确定。"""

    code = "PUBLISH_BLOCKED"

    def __init__(self, reasons: Sequence[BlockReason]) -> None:
        super().__init__(self.code)
        self.reasons = tuple(reasons)

    def details(self) -> dict[str, Any]:
        return {"reasons": [r.to_dict() for r in self.reasons]}


@dataclass(frozen=True)
class Snapshot:
    """规范化快照。``canonical`` 为存储字节，``data`` 为其解析结果，``digest`` 为摘要。"""

    data: Mapping[str, Any]
    canonical: bytes
    digest: str


@dataclass(frozen=True)
class SnapshotBuild:
    snapshot: Snapshot
    excluded: Excluded


# ---------------------------------------------------------------- 规范化


def canonical_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except ValueError as error:
        raise SnapshotFormatError("snapshot numbers must be finite") from error
    return text.encode("utf-8")


def digest_of(canonical: bytes) -> str:
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _snapshot(data: dict[str, Any]) -> Snapshot:
    canonical = canonical_bytes(data)
    return Snapshot(data=json.loads(canonical), canonical=canonical, digest=digest_of(canonical))


# ---------------------------------------------------------------- 输入校验


def _text(value: object, name: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise SnapshotFormatError(f"{name} must be a{'' if empty else ' non-empty'} string")
    return value


def _opt_text(value: object, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _id_set(values: object, name: str) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise SnapshotFormatError(f"{name} must be a sequence of strings")
    return sorted({_text(v, name) for v in values})


def _unit(value: object, name: str) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or not 0 <= value <= 1:
        raise SnapshotFormatError(f"{name} must be a number in [0, 1] or null")
    return value


def _order(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SnapshotFormatError("chapter order must be a non-negative integer")
    return value


def _enum(value: object, allowed: frozenset[str], name: str) -> str:
    if value not in allowed:
        raise SnapshotFormatError(f"{name} must be one of {sorted(allowed)}")
    return value  # type: ignore[return-value]


def _unique(ids: Iterable[str], name: str) -> None:
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            raise SnapshotFormatError(f"duplicate {name}")
        seen.add(i)


def _revision_dict(r: Revision) -> dict[str, Any]:
    return {"revision_id": _text(r.revision_id, "revision_id"), "material_id": _text(r.material_id, "material_id"),
            "content_hash": _text(r.content_hash, "content_hash"),
            "parser_version": _text(r.parser_version, "parser_version")}


def _chapter_dict(c: DraftChapter) -> dict[str, Any]:
    return {"chapter_id": _text(c.chapter_id, "chapter_id"), "title": _text(c.title, "chapter title", empty=True),
            "order": _order(c.order), "parent_id": _opt_text(c.parent_id, "parent_id")}


def _node_dict(n: DraftNode) -> dict[str, Any]:
    return {"kp_id": _text(n.kp_id, "kp_id"), "name": _text(n.name, "name"),
            "aliases": _id_set(n.aliases, "aliases"), "type": _enum(n.type, NODE_TYPES, "knowledge point type"),
            "definition": _text(n.definition, "definition", empty=True),
            "difficulty": _unit(n.difficulty, "difficulty"), "importance": _unit(n.importance, "importance"),
            "chapter_id": _opt_text(n.chapter_id, "chapter_id"),
            "source_refs": _id_set(n.source_refs, "source_refs"), "merged_from": _id_set(n.merged_from, "merged_from")}


def _edge_dict(e: DraftEdge) -> dict[str, Any]:
    return {"rel_id": _text(e.rel_id, "rel_id"), "type": _enum(e.type, RELATION_TYPES, "relation type"),
            "from_id": _text(e.from_id, "from_id"), "to_id": _text(e.to_id, "to_id"),
            "source_refs": _id_set(e.source_refs, "source_refs")}


# ---------------------------------------------------------------- 组装


def build_snapshot(draft: DraftGraph) -> SnapshotBuild:
    """按 V3 组装发布集合、校验并生成规范化快照；校验不通过抛 ``SnapshotBlocked``。"""
    course_id = _text(draft.course_id, "course_id")
    for node in draft.nodes:
        _enum(node.status, STATUSES, "knowledge point status")
    for edge in draft.edges:
        _enum(edge.status, STATUSES, "relation status")
    _unique((n.kp_id for n in draft.nodes), "kp_id")
    _unique((e.rel_id for e in draft.edges), "rel_id")
    _unique((c.chapter_id for c in draft.chapters), "chapter_id")
    _unique((r.revision_id for r in draft.revisions), "revision_id")

    revisions = sorted((_revision_dict(r) for r in draft.revisions), key=lambda r: r["revision_id"])
    revision_ids = {r["revision_id"] for r in revisions}
    all_node_ids = {n.kp_id for n in draft.nodes}

    nodes = sorted((_node_dict(n) for n in draft.nodes if n.status in PUBLISHABLE), key=lambda n: n["kp_id"])
    # 章节引用悬空（草稿里没有这个可见章节）时按「未归章」发布，快照里不留断开的引用（ADR-036）。
    chapter_ids = {c.chapter_id for c in draft.chapters}
    for node in nodes:
        if node["chapter_id"] is not None and node["chapter_id"] not in chapter_ids:
            node["chapter_id"] = None
    kept = {n["kp_id"] for n in nodes}
    low_nodes = sum(1 for n in draft.nodes if n.status == "low_confidence")

    reasons: list[BlockReason] = []
    edges: list[dict[str, Any]] = []
    low_edges = cascaded = 0
    for edge in sorted(draft.edges, key=lambda e: e.rel_id):
        if edge.status == "rejected":
            continue
        if edge.from_id not in all_node_ids or edge.to_id not in all_node_ids:
            reasons.append(BlockReason("dangling_endpoint", relation_id=edge.rel_id))
            continue
        if edge.status == "low_confidence":
            low_edges += 1
        elif edge.from_id not in kept or edge.to_id not in kept:
            cascaded += 1
        else:
            edges.append(_edge_dict(edge))

    cycle = find_cycle(kept, ((e["from_id"], e["to_id"]) for e in edges if e["type"] == "PREREQUISITE"))
    if cycle is not None:
        reasons.insert(0, BlockReason("cycle", cycle=tuple(cycle)))

    def check_refs(refs: Iterable[str], **where: str) -> None:
        for chunk_id in refs:
            if draft.chunk_revisions.get(chunk_id) not in revision_ids:
                reasons.append(BlockReason("invalid_source_ref", chunk_id=chunk_id, **where))

    for node in nodes:
        check_refs(node["source_refs"], kp_id=node["kp_id"])
    for edge_dict in edges:
        check_refs(edge_dict["source_refs"], relation_id=edge_dict["rel_id"])

    if not nodes:
        reasons.append(BlockReason("empty_graph"))
    reasons.extend(_lineage(nodes, kept))
    if reasons:
        raise SnapshotBlocked(reasons)

    chapters = _chapters(draft.chapters, {n["chapter_id"] for n in nodes if n["chapter_id"] is not None})
    data = {"snapshot_format": SNAPSHOT_FORMAT, "course_id": course_id, "revisions": revisions,
            "chapters": chapters, "nodes": nodes, "edges": edges}
    return SnapshotBuild(_snapshot(data), Excluded(low_nodes, low_edges, cascaded))


def _lineage(nodes: Sequence[Mapping[str, Any]], kept: set[str]) -> list[BlockReason]:
    """ADR-012 修订 3：来源不能是本快照的节点（含自身），同一来源不能归属两个节点。"""
    owners: dict[str, list[str]] = {}
    bad: set[str] = set()
    for node in nodes:
        for source in node["merged_from"]:
            owners.setdefault(source, []).append(node["kp_id"])
            if source in kept:
                bad.add(node["kp_id"])
    for holders in owners.values():
        if len(holders) > 1:
            bad.update(holders)
    return [BlockReason("invalid_lineage", kp_id=kp_id) for kp_id in sorted(bad)]


def _chapters(chapters: Sequence[DraftChapter], wanted: set[str]) -> list[dict[str, Any]]:
    """被引用的章节及其在草稿中的祖先，按 ``chapter_id`` 升序。"""
    by_id = {c.chapter_id: c for c in chapters}
    chosen: set[str] = set()
    for chapter_id in wanted:
        current: str | None = chapter_id
        while current is not None and current in by_id and current not in chosen:
            chosen.add(current)
            current = by_id[current].parent_id
    out = [_chapter_dict(by_id[c]) for c in sorted(chosen)]
    for chapter in out:
        if chapter["parent_id"] is not None and chapter["parent_id"] not in chosen:
            chapter["parent_id"] = None  # 父章节不在草稿中：按顶层章节发布
    return out


# ---------------------------------------------------------------- 读回


def _keys(obj: object, keys: tuple[str, ...], where: str) -> Mapping[str, Any]:
    if not isinstance(obj, dict) or tuple(sorted(obj)) != keys:
        raise SnapshotFormatError(f"{where} must have exactly the keys {list(keys)}")
    return obj


def _list(value: object, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise SnapshotFormatError(f"{where} must be an array")
    return value


def load_snapshot(raw: bytes | str) -> Snapshot:
    """解析存储的快照：结构逐键校验，且字节必须已是规范形态（否则摘要不可复算）。"""
    canonical = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
    try:
        data = json.loads(canonical.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError) as error:
        raise SnapshotFormatError("snapshot is not valid UTF-8 JSON") from error

    top = _keys(data, _TOP_KEYS, "snapshot")
    if top["snapshot_format"] != SNAPSHOT_FORMAT or isinstance(top["snapshot_format"], bool):
        raise SnapshotFormatError(f"unsupported snapshot_format {top['snapshot_format']!r}")
    _text(top["course_id"], "course_id")
    rebuilt = {
        "snapshot_format": SNAPSHOT_FORMAT,
        "course_id": top["course_id"],
        "revisions": [_revision_dict(Revision(**_keys(r, _REVISION_KEYS, "revision")))
                      for r in _list(top["revisions"], "revisions")],
        "chapters": [_chapter_dict(DraftChapter(**_keys(c, _CHAPTER_KEYS, "chapter")))
                     for c in _list(top["chapters"], "chapters")],
        "nodes": [_node_dict(DraftNode(status="draft", **_keys(n, _NODE_KEYS, "node")))
                  for n in _list(top["nodes"], "nodes")],
        "edges": [_edge_dict(DraftEdge(status="draft", **_keys(e, _EDGE_KEYS, "edge")))
                  for e in _list(top["edges"], "edges")],
    }
    for name, key in (("revisions", "revision_id"), ("chapters", "chapter_id"), ("nodes", "kp_id"),
                      ("edges", "rel_id")):
        ids = [item[key] for item in rebuilt[name]]
        if ids != sorted(set(ids)):
            raise SnapshotFormatError(f"{name} must be unique and sorted by {key}")
    snapshot = _snapshot(rebuilt)
    if snapshot.canonical != canonical:
        raise SnapshotFormatError("snapshot bytes are not in canonical form")
    return snapshot


def _reject_constant(name: str) -> None:
    raise ValueError(f"non-finite number {name}")
