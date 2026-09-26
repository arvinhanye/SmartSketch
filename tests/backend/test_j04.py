"""J04：检索合并与上下文预算——两路候选 → 候选集合 H → 允许引用集合 A（编号证据上下文）。

依据：``specs/grounded-qa.md`` Q1（H、A 的定义）、Q2 P5（``no_retrieval_hit`` /
``below_similarity_threshold``）、Q3.1（A 的三项条件、图谱上下文无编号）、Q11 J04 行、QA-6、QA-7、
QA-17，主验收第 1、5、8、9、13 条；ADR-065。

J01 / J02 的结果与 SQLite 文本块全部用 fake 构造，阈值与预算都是 fake 值；不连数据库、不调模型。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import pytest

from app.repositories.chunks import StoredChunk
from app.repositories.graph_search import GraphEvidence, GraphSubgraph, SubgraphEdge, SubgraphNode
from app.repositories.vector_search import ChunkHit
from app.services.chunking import ChunkSource
from app.services.parsers.models import SourceLocator
from app.services.qa import context as context_module
from app.services.qa.context import (
    ContextBudget,
    ContextReason,
    ContextStatus,
    EvidenceContext,
    build_context,
    utf8_token_estimate,
)

COURSE = "course-a"
OTHER_COURSE = "course-b"
REV = "rev_1"
REV2 = "rev_2"
OLD_REV = "rev_old"
REVISIONS = (REV, REV2)
THRESHOLD = 0.6  # fake 值；真实阈值待 K01 标注集调参
BIG = ContextBudget(chunk_tokens=100_000, graph_tokens=100_000, max_chunks=50)


def chunk(chunk_id: str, text: str = "", *, course: str = COURSE, revision: str = REV,
          material: str = "mat-1", page: int | None = 3, titles: tuple[str, ...] = ("第3章", "3.1 栈"),
          paragraph: int | None = None) -> StoredChunk:
    text = text or f"{chunk_id} 的原文。"
    if page is None and not titles and paragraph is None:
        sources: tuple[ChunkSource, ...] = ()
    else:
        sources = (ChunkSource(0, 0, len(text), SourceLocator(page=page, section_titles=titles, paragraph=paragraph)),)
    return StoredChunk(chunk_id=chunk_id, course_id=course, material_id=material, revision_id=revision,
                       ordinal=0, text=text, text_sha256="0" * 64, section_titles=titles, sources=sources)


def hit(chunk_id: str, score: float, revision: str = REV) -> ChunkHit:
    return ChunkHit(chunk_id=chunk_id, revision_id=revision, document_id="mat-1", score=score)


def node(kp_id: str, name: str, *, definition: str = "", hops: int = 0) -> SubgraphNode:
    return SubgraphNode(kp_id=kp_id, name=name, aliases=(), type="concept", definition=definition,
                        chapter_id=None, hops=hops, matched=name if hops == 0 else None)


def subgraph(nodes: Sequence[SubgraphNode] = (), edges: Sequence[SubgraphEdge] = (),
             evidence: Sequence[GraphEvidence] = (), truncated: bool = False) -> GraphSubgraph:
    seeds = tuple(n.kp_id for n in nodes if n.hops == 0)
    return GraphSubgraph(tuple(nodes), tuple(edges), tuple(evidence), seeds, truncated)


def evidence(kp_id: str, chunk_id: str, revision: str = REV) -> GraphEvidence:
    return GraphEvidence(kp_id=kp_id, chunk_id=chunk_id, revision_id=revision, document_id="mat-1")


class Loader:
    """fake 文本块读取：记录每次请求的 ID，只返回已登记的块（模拟按课程读取 SQLite）。"""

    def __init__(self, *chunks: StoredChunk) -> None:
        self.chunks = {c.chunk_id: c for c in chunks}
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, chunk_ids: Sequence[str]) -> tuple[StoredChunk, ...]:
        self.calls.append(tuple(chunk_ids))
        return tuple(self.chunks[i] for i in chunk_ids if i in self.chunks)


def build(vector: Sequence[ChunkHit] = (), graph: GraphSubgraph | None = None, loader: Loader | None = None,
          *, threshold: float = THRESHOLD, budget: ContextBudget = BIG,
          revisions: Sequence[str] = REVISIONS, **kwargs) -> EvidenceContext:
    return build_context(course_id=COURSE, revision_ids=revisions, vector_hits=vector, subgraph=graph,
                         load_chunks=loader or Loader(), threshold=threshold, budget=budget, **kwargs)


# ------------------------------------------------------------------ P5：两种拒答


def test_no_candidates_is_no_retrieval_hit_without_reading_chunks():
    loader = Loader()
    ctx = build((), subgraph(), loader)
    assert ctx.status is ContextStatus.NOT_COVERED
    assert ctx.reason is ContextReason.NO_RETRIEVAL_HIT
    assert ctx.chunks == () and ctx.retrieved == 0 and ctx.candidates == 0
    assert not ctx.covered
    assert loader.calls == []
    assert build((), None, loader).reason is ContextReason.NO_RETRIEVAL_HIT


def test_candidates_that_fail_q31_leave_h_empty_so_the_reason_is_no_retrieval_hit():
    loader = Loader(chunk("c-foreign", course=OTHER_COURSE), chunk("c-old", revision=OLD_REV),
                    chunk("c-noloc", page=None, titles=()))
    ctx = build([hit("c-foreign", 0.99), hit("c-old", 0.98), hit("c-noloc", 0.97), hit("c-missing", 0.96)],
                None, loader)
    assert ctx.reason is ContextReason.NO_RETRIEVAL_HIT
    assert ctx.candidates == 0
    assert ctx.stats.foreign_course == 1
    assert ctx.stats.outside_version == 1
    assert ctx.stats.unlocatable == 1
    assert ctx.stats.missing == 1


def test_all_below_the_fake_threshold_is_below_similarity_threshold():
    loader = Loader(chunk("c1"), chunk("c2"))
    ctx = build([hit("c1", 0.59), hit("c2", 0.2)], None, loader)
    assert ctx.status is ContextStatus.NOT_COVERED
    assert ctx.reason is ContextReason.BELOW_SIMILARITY_THRESHOLD
    assert ctx.reason is not ContextReason.NO_RETRIEVAL_HIT
    assert ctx.candidates == 2 and ctx.chunks == ()
    assert ctx.stats.below_threshold == 2


def test_threshold_is_inclusive_and_comes_from_the_caller():
    loader = Loader(chunk("c1"))
    assert build([hit("c1", 0.6)], None, loader).covered
    assert not build([hit("c1", 0.6)], None, loader, threshold=0.61).covered
    assert build([hit("c1", 0.3)], None, loader, threshold=0.3).covered


def test_graph_evidence_alone_cannot_pass_the_relevance_gate():
    loader = Loader(chunk("g1"))
    graph = subgraph([node("kp1", "栈")], evidence=[evidence("kp1", "g1")])
    ctx = build((), graph, loader)
    assert ctx.reason is ContextReason.BELOW_SIMILARITY_THRESHOLD
    assert ctx.candidates == 1
    assert ctx.graph.kp_ids == ("kp1",)  # 拒答时图谱命中仍可作导航提示（Q4）


def test_graph_evidence_joins_once_a_vector_candidate_passes():
    loader = Loader(chunk("v1"), chunk("g1"))
    graph = subgraph([node("kp1", "栈")], evidence=[evidence("kp1", "g1")])
    ctx = build([hit("v1", 0.9)], graph, loader)
    assert ctx.status is ContextStatus.READY and ctx.reason is None
    assert [c.chunk_id for c in ctx.chunks] == ["v1", "g1"]
    assert ctx.chunks[1].score is None and ctx.chunks[1].origins == ("graph",)


def test_graph_evidence_with_a_low_vector_score_stays_out():
    loader = Loader(chunk("v1"), chunk("g1"))
    graph = subgraph([node("kp1", "栈")], evidence=[evidence("kp1", "g1")])
    ctx = build([hit("v1", 0.9), hit("g1", 0.1)], graph, loader)
    assert [c.chunk_id for c in ctx.chunks] == ["v1"]
    assert ctx.stats.below_threshold == 1


# ------------------------------------------------------------------ 合并去重与编号


def test_duplicates_merge_into_one_numbered_block_keeping_every_origin():
    loader = Loader(chunk("c1"), chunk("c2"))
    graph = subgraph([node("kp1", "栈"), node("kp2", "队列")],
                     evidence=[evidence("kp1", "c1"), evidence("kp2", "c1"), evidence("kp1", "c1"),
                               evidence("kp2", "c2")])
    ctx = build([hit("c1", 0.8), hit("c1", 0.7), hit("c2", 0.9)], graph, loader)
    assert [c.chunk_id for c in ctx.chunks] == ["c2", "c1"]
    c1 = ctx.chunks[1]
    assert c1.score == 0.8
    assert c1.origins == ("vector", "graph")
    assert c1.kp_ids == ("kp1", "kp2")
    assert ctx.candidates == 2
    assert loader.calls == [("c1", "c2")]


def test_numbering_is_contiguous_from_one_in_context_order():
    loader = Loader(*(chunk(f"c{i}") for i in range(5)), chunk("bad", course=OTHER_COURSE))
    hits = [hit("c3", 0.95), hit("bad", 0.94), hit("c1", 0.9), hit("c4", 0.9), hit("c0", 0.61), hit("c2", 0.5)]
    ctx = build(hits, None, loader)
    assert [(c.index, c.chunk_id) for c in ctx.chunks] == [(1, "c3"), (2, "c1"), (3, "c4"), (4, "c0")]
    assert ctx.by_index(2).chunk_id == "c1"
    assert ctx.by_index(0) is None and ctx.by_index(5) is None
    assert ctx.retrieved == 4


def test_ties_are_broken_by_chunk_id_and_graph_evidence_keeps_subgraph_order():
    loader = Loader(chunk("b"), chunk("a"), chunk("g2"), chunk("g1"))
    graph = subgraph([node("kp1", "栈")], evidence=[evidence("kp1", "g2"), evidence("kp1", "g1")])
    ctx = build([hit("b", 0.7), hit("a", 0.7)], graph, loader)
    assert [c.chunk_id for c in ctx.chunks] == ["a", "b", "g2", "g1"]


# ------------------------------------------------------------------ Q3.1 三项条件（QA-17）


def test_q31_uses_the_stored_chunk_not_the_hit():
    # 命中声称修订在列表内，但库中块的修订不在：以库为准。
    loader = Loader(chunk("c1", revision=OLD_REV), chunk("c2"))
    ctx = build([hit("c1", 0.9, revision=REV), hit("c2", 0.8)], None, loader)
    assert [c.chunk_id for c in ctx.chunks] == ["c2"]
    assert ctx.stats.outside_version == 1


def test_foreign_outside_and_unlocatable_chunks_never_get_a_number():
    loader = Loader(chunk("ok1"), chunk("foreign", course=OTHER_COURSE), chunk("old", revision=OLD_REV),
                    chunk("noloc", page=None, titles=()), chunk("ok2", revision=REV2))
    hits = [hit(i, 0.9) for i in ("ok1", "foreign", "old", "noloc", "ok2")]
    ctx = build(hits, None, loader)
    assert [c.chunk_id for c in ctx.chunks] == ["ok1", "ok2"]
    assert all(c.revision_id in REVISIONS for c in ctx.chunks)


def test_an_empty_revision_list_admits_nothing():
    loader = Loader(chunk("c1"))
    assert build([hit("c1", 0.9)], None, loader, revisions=()).reason is ContextReason.NO_RETRIEVAL_HIT


@pytest.mark.parametrize(
    ("kwargs", "page", "section_path"),
    [
        ({"page": 7, "titles": ("第3章", "3.1 栈")}, 7, "第3章 > 3.1 栈"),
        ({"page": 7, "titles": ()}, 7, None),
        ({"page": None, "titles": ("第2章",), "paragraph": 4}, None, "第2章 > 第4段"),
        ({"page": None, "titles": (), "paragraph": 2}, None, "第2段"),
    ],
)
def test_locator_comes_from_the_first_locatable_source(kwargs, page, section_path):
    loader = Loader(chunk("c1", **kwargs))
    [c] = build([hit("c1", 0.9)], None, loader).chunks
    assert (c.page, c.section_path) == (page, section_path)
    assert c.document_id == "mat-1"


def test_locator_skips_a_source_that_cannot_be_located():
    text = "前一段\n\n后一段"
    blank = SourceLocator(page=None, section_titles=(), paragraph=1)
    stored = StoredChunk(chunk_id="c1", course_id=COURSE, material_id="mat-9", revision_id=REV, ordinal=0,
                         text=text, text_sha256="0" * 64, section_titles=(),
                         sources=(ChunkSource(0, 0, 3, blank), ChunkSource(1, 0, 3, SourceLocator(page=5))))
    [c] = build([hit("c1", 0.9)], None, Loader(stored)).chunks
    assert (c.page, c.section_path, c.document_id) == (None, "第1段", "mat-9")


# ------------------------------------------------------------------ token 预算（主验收第 8 条）


def _tokens(ctx: EvidenceContext) -> int:
    return sum(c.tokens for c in ctx.chunks)


def test_budget_drops_whole_blocks_and_never_cuts_text_or_locator():
    long_text = "栈" * 200
    loader = Loader(chunk("c1", "短文一。"), chunk("c2", long_text), chunk("c3", "短文三。"))
    probe = build([hit("c1", 0.9), hit("c2", 0.8), hit("c3", 0.7)], None, loader)
    [t1, t2, t3] = (c.tokens for c in probe.chunks)
    assert t2 > t3 + 10
    budget = ContextBudget(chunk_tokens=t1 + t3 + 10, graph_tokens=0, max_chunks=10)
    ctx = build([hit("c1", 0.9), hit("c2", 0.8), hit("c3", 0.7)], None, loader, budget=budget)
    assert [c.chunk_id for c in ctx.chunks] == ["c1", "c3"]
    assert [c.index for c in ctx.chunks] == [1, 2]
    assert _tokens(ctx) <= budget.chunk_tokens
    assert ctx.stats.over_budget == 1
    assert ctx.chunks[1].text == "短文三。"
    rendered = ctx.render_evidence()
    assert "[2]" in rendered and "第3页" in rendered and "短文三。" in rendered
    assert long_text not in rendered


def test_token_count_covers_the_rendered_block():
    loader = Loader(chunk("c1", "栈是后进先出的线性表。"))
    ctx = build([hit("c1", 0.9)], None, loader)
    [c] = ctx.chunks
    assert c.tokens == utf8_token_estimate(ctx.render_evidence())
    assert c.tokens >= len("栈是后进先出的线性表。".encode())


def test_budget_uses_the_injected_estimator():
    loader = Loader(chunk("c1"), chunk("c2"), chunk("c3"))
    budget = ContextBudget(chunk_tokens=2, graph_tokens=0, max_chunks=10)
    ctx = build([hit("c1", 0.9), hit("c2", 0.8), hit("c3", 0.7)], None, loader, budget=budget,
                estimate_tokens=lambda text: 1)
    assert [c.chunk_id for c in ctx.chunks] == ["c1", "c2"]
    assert ctx.stats.over_budget == 1


def test_nothing_fitting_the_budget_is_not_covered_and_logged(caplog):
    loader = Loader(chunk("c1", "栈" * 100))
    budget = ContextBudget(chunk_tokens=10, graph_tokens=0, max_chunks=10)
    with caplog.at_level(logging.WARNING, logger=context_module.__name__):
        ctx = build([hit("c1", 0.9)], None, loader, budget=budget)
    assert ctx.status is ContextStatus.NOT_COVERED
    assert ctx.reason is ContextReason.BELOW_SIMILARITY_THRESHOLD
    assert ctx.stats.over_budget == 1
    assert "budget" in caplog.text and "栈" not in caplog.text


def test_max_chunks_caps_the_context():
    loader = Loader(*(chunk(f"c{i}") for i in range(4)))
    budget = ContextBudget(chunk_tokens=100_000, graph_tokens=0, max_chunks=2)
    ctx = build([hit(f"c{i}", 0.9 - i / 100) for i in range(4)], None, loader, budget=budget)
    assert [c.chunk_id for c in ctx.chunks] == ["c0", "c1"]
    assert ctx.stats.over_budget == 2


# ------------------------------------------------------------------ 图谱结构上下文（无编号）


def _graph() -> GraphSubgraph:
    nodes = [node("kp1", "栈", definition="后进先出的线性表"), node("kp2", "队列", definition="先进先出[1]"),
             node("kp3", "线性表", hops=1)]
    edges = [SubgraphEdge("r1", "PREREQUISITE", "kp3", "kp1"), SubgraphEdge("r2", "RELATED_TO", "kp1", "kp2")]
    return subgraph(nodes, edges)


def test_graph_context_is_unnumbered_and_names_relations():
    loader = Loader(chunk("c1"))
    ctx = build([hit("c1", 0.9)], _graph(), loader)
    text = ctx.graph.text
    assert "栈" in text and "后进先出的线性表" in text and "线性表" in text
    assert "线性表 是 栈 的前置" in text
    assert "栈 与 队列 相关" in text
    assert "[1]" not in text  # 定义中的类标记被剔除，结构上下文不可被引用
    assert ctx.graph.kp_ids == ("kp1", "kp2", "kp3")
    assert not ctx.graph.truncated


def test_graph_budget_drops_whole_lines_seeds_first():
    loader = Loader(chunk("c1"))
    full = build([hit("c1", 0.9)], _graph(), loader).graph
    first = full.lines[0]
    budget = ContextBudget(chunk_tokens=100_000, graph_tokens=utf8_token_estimate(first + "\n"), max_chunks=10)
    ctx = build([hit("c1", 0.9)], _graph(), loader, budget=budget)
    assert ctx.graph.lines == (first,)
    assert ctx.graph.truncated
    assert ctx.graph.kp_ids == ("kp1", "kp2", "kp3")  # 导航用的命中知识点不受预算影响


def test_edges_with_an_unknown_endpoint_are_skipped():
    loader = Loader(chunk("c1"))
    graph = subgraph([node("kp1", "栈")], [SubgraphEdge("r1", "CONTAINS", "kp1", "kp-gone"),
                                            SubgraphEdge("r2", "UNKNOWN", "kp1", "kp1")])
    assert build([hit("c1", 0.9)], graph, loader).graph.lines == ("知识点：栈（concept）",)


def test_edges_to_dropped_nodes_are_not_rendered():
    loader = Loader(chunk("c1"))
    nodes = [node("kp1", "栈"), node("kp2", "队列"), node("kp3", "线性表", definition="很长的定义" * 20, hops=1)]
    graph = subgraph(nodes, [SubgraphEdge("r1", "PREREQUISITE", "kp3", "kp1")])
    full = build([hit("c1", 0.9)], graph, loader).graph
    slack = 60  # 放得下一条关系行，放不下第三个节点
    budget = ContextBudget(chunk_tokens=100_000, max_chunks=10,
                           graph_tokens=sum(utf8_token_estimate(line + "\n") for line in full.lines[:2]) + slack)
    ctx = build([hit("c1", 0.9)], graph, loader, budget=budget)
    assert len(ctx.graph.lines) == 2 and ctx.graph.truncated
    assert all(not line.startswith("关系") for line in ctx.graph.lines)


def test_zero_graph_budget_or_no_subgraph_gives_empty_graph_context():
    loader = Loader(chunk("c1"))
    budget = ContextBudget(chunk_tokens=100_000, graph_tokens=0, max_chunks=10)
    assert build([hit("c1", 0.9)], _graph(), loader, budget=budget).graph.text == ""
    assert build([hit("c1", 0.9)], None, loader).graph.lines == ()


def test_subgraph_truncation_is_carried_over():
    loader = Loader(chunk("c1"))
    graph = subgraph([node("kp1", "栈")], truncated=True)
    assert build([hit("c1", 0.9)], graph, loader).graph.truncated


# ------------------------------------------------------------------ 渲染与隐私


def test_render_numbers_every_block_with_its_locator():
    loader = Loader(chunk("c1", "甲。", page=2, titles=()), chunk("c2", "乙。", page=None, titles=("第1章",),
                                                                  paragraph=3))
    ctx = build([hit("c1", 0.9), hit("c2", 0.8)], None, loader)
    rendered = ctx.render_evidence()
    assert rendered.index("[1]") < rendered.index("甲。") < rendered.index("[2]") < rendered.index("乙。")
    assert "第2页" in rendered and "第1章 > 第3段" in rendered


def test_not_covered_context_renders_nothing():
    ctx = build((), None, Loader())
    assert ctx.render_evidence() == ""


def test_chunk_text_stays_out_of_repr():
    loader = Loader(chunk("c1", "机密原文内容"))
    ctx = build([hit("c1", 0.9)], None, loader)
    assert "机密原文内容" not in repr(ctx)


# ------------------------------------------------------------------ 参数校验


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan"), True, "0.5"])
def test_bad_threshold_is_rejected(threshold):
    with pytest.raises(ValueError):
        build((), None, threshold=threshold)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"chunk_tokens": 0, "graph_tokens": 0, "max_chunks": 1},
        {"chunk_tokens": 10, "graph_tokens": -1, "max_chunks": 1},
        {"chunk_tokens": 10, "graph_tokens": 0, "max_chunks": 0},
        {"chunk_tokens": 1.5, "graph_tokens": 0, "max_chunks": 1},
        {"chunk_tokens": 10, "graph_tokens": 0, "max_chunks": True},
    ],
)
def test_bad_budget_is_rejected(kwargs):
    with pytest.raises(ValueError):
        ContextBudget(**kwargs)


def test_blank_course_is_rejected():
    with pytest.raises(ValueError):
        build_context(course_id=" ", revision_ids=REVISIONS, vector_hits=(), subgraph=None,
                      load_chunks=Loader(), threshold=THRESHOLD, budget=BIG)


def test_utf8_estimate_is_an_upper_bound_by_bytes():
    assert utf8_token_estimate("") == 0
    assert utf8_token_estimate("ab") == 2
    assert utf8_token_estimate("栈") == 3
