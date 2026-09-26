"""J04：检索合并与上下文预算——J01 向量候选 + J02 图证据 → 候选集合 H → 允许引用集合 A。

依据：``specs/grounded-qa.md`` Q1（H、A）、Q2 P5、Q3.1、Q11 J04 行、QA-6、QA-7、QA-17，主验收第 1、5、8、
9、13 条；ADR-065。

流程：

1. **合并去重**：向量命中（``ChunkHit``）与子图证据（``GraphEvidence``）按 ``chunk_id`` 合并为一个候选，
   保留全部出处：``origins`` 记录来自哪一路，``kp_ids`` 记录经 ``EVIDENCED_BY`` 关联到它的知识点，
   ``score`` 取该块向量相似度的最大值（只来自图证据的块没有相似度，为 ``None``）。
2. **Q3.1 过滤**：一次读取全部候选的文本块（``load_chunks``，调用方按 ``course_id`` 绑定 SQLite）。
   以库中的块为准复核三项条件——课程相同、``revision_id`` 在绑定版本修订列表内、可定位（首个能给出
   ``page`` 或 ``section_path`` 的出处，与 H06 取定位的方式一致）；读不到的块同样剔除。通过者构成 H。
   H 为空 → ``no_retrieval_hit``。
3. **阈值**（措施③）：阈值由调用方传入（真实值待 K01 调参，测试用 fake 值），``score ≥ threshold``
   为达标。**只有向量相似度能打开闸门**：H 中没有达标的向量候选 → ``below_similarity_threshold``，
   即使图证据很多，也不调用生成。闸门打开后，没有相似度的图证据块作为补充进入排序；有相似度但未达标的
   块（不论是否也来自图）一律不进 A。
4. **排序与编号**：达标的向量候选按相似度降序、``chunk_id`` 升序；其后是只来自图的证据块，按子图给出的
   顺序。依次放入，**整块放入或整块跳过**：块的文本与定位从不截断（主验收第 8 条、「token 预算不截断
   定位」），放不下的块跳过、继续尝试后面较小的块，直到 ``max_chunks``。放入者按顺序编号 ``1..k``。
   闸门已开但没有任何块放得下 → 同样按 ``below_similarity_threshold`` 拒答（wire 原因是闭集），并记一条
   WARNING，``stats.over_budget`` 可区分。
5. **图谱结构上下文**：子图节点（种子在前）与关系渲染成**无编号**的行，按行计入独立的 ``graph_tokens``
   预算，整行放入或停止；关系排在全部节点之后，节点放不下时不渲染任何关系。行内容剔除类标记与哨兵（与 J03 同一函数），因此结构
   上下文里不会出现可被误认为引用的编号。``kp_ids`` 是全部命中知识点（供 Q4 ``related_kp_ids`` 导航），
   不受预算影响。

token 估算缺省按 UTF-8 字节数（与 E03 ``estimate_input_tokens`` 同一口径，只会高估）；块的开销按渲染后的
整块（编号、定位行、原文与分隔）计算，因此各块 ``tokens`` 之和等于 ``render_evidence()`` 的估算。

本模块不调用模型、不访问数据库；日志只含计数，原文不进入日志或 ``repr``。
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, Literal

from app.repositories.chunks import StoredChunk
from app.repositories.graph_search import GraphSubgraph
from app.repositories.vector_search import ChunkHit
from app.services.qa.rewrite import strip_citation_markers

__all__ = [
    "ContextBudget",
    "ContextReason",
    "ContextStats",
    "ContextStatus",
    "EvidenceChunk",
    "EvidenceContext",
    "GraphContext",
    "build_context",
    "utf8_token_estimate",
]

logger = logging.getLogger(__name__)

Origin = Literal["vector", "graph"]
BLOCK_SEPARATOR: Final = "\n\n"
LINE_SEPARATOR: Final = "\n"

_RELATION_TEMPLATES: Final = {
    "PREREQUISITE": "关系：{a} 是 {b} 的前置",
    "CONTAINS": "关系：{a} 包含 {b}",
    "RELATED_TO": "关系：{a} 与 {b} 相关",
    "EXAMPLE_OF": "关系：{a} 是 {b} 的例子",
}


class ContextStatus(StrEnum):
    READY = "ready"
    NOT_COVERED = "not_covered"


class ContextReason(StrEnum):
    """P5 拒答原因，取值与契约 ``NotCoveredReason`` 的前两项相同。"""

    NO_RETRIEVAL_HIT = "no_retrieval_hit"
    BELOW_SIMILARITY_THRESHOLD = "below_similarity_threshold"


def utf8_token_estimate(text: str) -> int:
    """按 UTF-8 字节数估算 token（只会高估，E03 口径）。"""
    return len(text.encode("utf-8"))


def _count(name: str, value: object, *, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True)
class ContextBudget:
    """上下文预算：编号证据与图谱结构上下文各自的 token 上限，以及编号块数上限。"""

    chunk_tokens: int
    graph_tokens: int
    max_chunks: int

    def __post_init__(self) -> None:
        _count("chunk_tokens", self.chunk_tokens, minimum=1)
        _count("graph_tokens", self.graph_tokens, minimum=0)
        _count("max_chunks", self.max_chunks, minimum=1)


@dataclass(frozen=True)
class EvidenceChunk:
    """A 中的一个编号文本块。定位与原文取自 SQLite 中的块，不取自检索结果。"""

    index: int
    chunk_id: str
    revision_id: str
    document_id: str
    page: int | None
    section_path: str | None
    text: str = field(repr=False)
    score: float | None
    origins: tuple[Origin, ...]
    kp_ids: tuple[str, ...]
    tokens: int

    @property
    def locator(self) -> str:
        parts = []
        if self.page is not None:
            parts.append(f"第{self.page}页")
        if self.section_path:
            parts.append(self.section_path)
        return "；".join(parts)

    def render(self) -> str:
        return f"[{self.index}]（{self.locator}）\n{self.text}{BLOCK_SEPARATOR}"


@dataclass(frozen=True)
class GraphContext:
    """无编号的图谱结构上下文。``kp_ids`` 为全部命中知识点，不受预算影响。"""

    lines: tuple[str, ...] = field(default=(), repr=False)
    kp_ids: tuple[str, ...] = ()
    truncated: bool = False

    @property
    def text(self) -> str:
        return "".join(line + LINE_SEPARATOR for line in self.lines)


@dataclass(frozen=True)
class ContextStats:
    """未进入 H 或 A 的候选计数，供 J10 日志与排障；不含原文。"""

    foreign_course: int = 0
    outside_version: int = 0
    unlocatable: int = 0
    missing: int = 0
    below_threshold: int = 0
    over_budget: int = 0


@dataclass(frozen=True)
class EvidenceContext:
    status: ContextStatus
    reason: ContextReason | None
    chunks: tuple[EvidenceChunk, ...]
    graph: GraphContext
    candidates: int
    stats: ContextStats

    @property
    def covered(self) -> bool:
        return self.status is ContextStatus.READY

    @property
    def retrieved(self) -> int:
        """``meta.retrieved``（= |A|）。"""
        return len(self.chunks)

    def by_index(self, index: int) -> EvidenceChunk | None:
        if type(index) is int and 1 <= index <= len(self.chunks):
            return self.chunks[index - 1]
        return None

    def render_evidence(self) -> str:
        return "".join(chunk.render() for chunk in self.chunks)


@dataclass
class _Candidate:
    chunk_id: str
    order: int
    score: float | None = None
    origins: list[Origin] = field(default_factory=list)
    kp_ids: list[str] = field(default_factory=list)

    def add_origin(self, origin: Origin) -> None:
        if origin not in self.origins:
            self.origins.append(origin)


def _threshold(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("threshold must be a finite number in [0, 1]")
    if not 0.0 <= value <= 1.0:
        raise ValueError("threshold must be a finite number in [0, 1]")
    return float(value)


def _merge(vector_hits: Iterable[ChunkHit], subgraph: GraphSubgraph | None) -> dict[str, _Candidate]:
    merged: dict[str, _Candidate] = {}

    def candidate(chunk_id: str) -> _Candidate:
        if chunk_id not in merged:
            merged[chunk_id] = _Candidate(chunk_id, len(merged))
        return merged[chunk_id]

    for hit in vector_hits:
        item = candidate(hit.chunk_id)
        item.add_origin("vector")
        score = float(hit.score)
        if item.score is None or score > item.score:
            item.score = score
    if subgraph is not None:
        for evidence in subgraph.evidence:
            item = candidate(evidence.chunk_id)
            item.add_origin("graph")
            if evidence.kp_id not in item.kp_ids:
                item.kp_ids.append(evidence.kp_id)
    for item in merged.values():
        item.origins.sort(key=("vector", "graph").index)
    return merged


def _locate(chunk: StoredChunk) -> tuple[int | None, str | None] | None:
    for source in chunk.sources:
        fields = source.locator.to_source_fields()
        if fields:
            page = fields.get("page")
            path = fields.get("section_path")
            return (page if isinstance(page, int) else None, path if isinstance(path, str) else None)
    return None


def _graph_context(subgraph: GraphSubgraph | None, budget: int,
                   estimate: Callable[[str], int]) -> GraphContext:
    if subgraph is None or subgraph.empty:
        return GraphContext()
    names = {n.kp_id: strip_citation_markers(n.name).strip() for n in subgraph.nodes}
    node_lines: list[str] = []
    for n in subgraph.nodes:
        definition = strip_citation_markers(n.definition).strip()
        line = f"知识点：{names[n.kp_id]}（{n.type}）"
        node_lines.append(f"{line}：{definition}" if definition else line)
    lines: list[str] = []
    used = 0
    truncated = subgraph.truncated
    for line in node_lines:
        cost = estimate(line + LINE_SEPARATOR)
        if used + cost > budget:
            truncated = True
            break
        lines.append(line)
        used += cost
    else:  # 关系只在全部节点放入后渲染，因此端点总已出现
        for edge in subgraph.edges:
            template = _RELATION_TEMPLATES.get(edge.type)
            if template is None or edge.from_id not in names or edge.to_id not in names:
                continue
            line = template.format(a=names[edge.from_id], b=names[edge.to_id])
            cost = estimate(line + LINE_SEPARATOR)
            if used + cost > budget:
                truncated = True
                break
            lines.append(line)
            used += cost
    return GraphContext(tuple(lines), subgraph.kp_ids, truncated)


def build_context(
    *,
    course_id: str,
    revision_ids: Collection[str],
    vector_hits: Iterable[ChunkHit],
    subgraph: GraphSubgraph | None,
    load_chunks: Callable[[Sequence[str]], Iterable[StoredChunk]],
    threshold: float,
    budget: ContextBudget,
    estimate_tokens: Callable[[str], int] = utf8_token_estimate,
) -> EvidenceContext:
    """把两路检索结果组装为编号证据上下文，或判定 P5 拒答。

    ``revision_ids`` 为 G07 绑定版本的修订列表；``load_chunks`` 按请求课程读取文本块，未知 ID 省略。
    它按**位置参数**接收 ID 序列，而 ``get_chunks`` 的 ``chunk_ids`` 是 keyword-only，故不能直接
    ``functools.partial`` 绑定，必须包一层：``lambda ids: get_chunks(sqlite_url, course_id=course_id,
    chunk_ids=ids)``。
    """
    if not isinstance(course_id, str) or not course_id.strip():
        raise ValueError("course_id must be a non-empty string")
    threshold = _threshold(threshold)
    if not isinstance(budget, ContextBudget):
        raise ValueError("budget must be a ContextBudget")
    revisions = {r for r in revision_ids if isinstance(r, str) and r}

    merged = _merge(vector_hits, subgraph)
    graph = _graph_context(subgraph, budget.graph_tokens, estimate_tokens)
    foreign = outside = unlocatable = missing = below = over = 0
    if not merged:
        return EvidenceContext(ContextStatus.NOT_COVERED, ContextReason.NO_RETRIEVAL_HIT, (), graph, 0,
                               ContextStats())

    stored = {c.chunk_id: c for c in load_chunks(list(merged))}
    admitted: list[tuple[_Candidate, StoredChunk, int | None, str | None]] = []
    for item in merged.values():
        chunk = stored.get(item.chunk_id)
        if chunk is None:
            missing += 1
            continue
        if chunk.course_id != course_id:
            foreign += 1
            continue
        if chunk.revision_id not in revisions:
            outside += 1
            continue
        located = _locate(chunk)
        if located is None:
            unlocatable += 1
            continue
        admitted.append((item, chunk, *located))

    def stats() -> ContextStats:
        return ContextStats(foreign, outside, unlocatable, missing, below, over)

    if not admitted:
        return EvidenceContext(ContextStatus.NOT_COVERED, ContextReason.NO_RETRIEVAL_HIT, (), graph, 0, stats())

    scored = [entry for entry in admitted if entry[0].score is not None and entry[0].score >= threshold]
    below = sum(1 for entry in admitted if entry[0].score is not None and entry[0].score < threshold)
    if not scored:
        return EvidenceContext(ContextStatus.NOT_COVERED, ContextReason.BELOW_SIMILARITY_THRESHOLD, (), graph,
                               len(admitted), stats())
    scored.sort(key=lambda entry: (-entry[0].score, entry[0].chunk_id))  # type: ignore[operator]
    graph_only = sorted((entry for entry in admitted if entry[0].score is None), key=lambda entry: entry[0].order)

    chunks: list[EvidenceChunk] = []
    used = 0
    for item, chunk, page, section_path in (*scored, *graph_only):
        if len(chunks) >= budget.max_chunks:
            over += 1
            continue
        block = EvidenceChunk(index=len(chunks) + 1, chunk_id=chunk.chunk_id, revision_id=chunk.revision_id,
                              document_id=chunk.material_id, page=page, section_path=section_path,
                              text=chunk.text, score=item.score, origins=tuple(item.origins),
                              kp_ids=tuple(item.kp_ids), tokens=0)
        cost = estimate_tokens(block.render())
        if used + cost > budget.chunk_tokens:
            over += 1
            continue
        used += cost
        chunks.append(EvidenceChunk(**{**block.__dict__, "tokens": cost}))

    if not chunks:
        logger.warning("context budget admits no evidence chunk for course %s: %d over budget", course_id, over)
        return EvidenceContext(ContextStatus.NOT_COVERED, ContextReason.BELOW_SIMILARITY_THRESHOLD, (), graph,
                               len(admitted), stats())
    return EvidenceContext(ContextStatus.READY, None, tuple(chunks), graph, len(admitted), stats())
