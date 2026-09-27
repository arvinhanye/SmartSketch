"""J02 against a real Neo4j: bounded structural retrieval over one published version copy.

Acceptance: hops and node count are capped; only the same course's published version comes back
(never the draft, other versions or other courses); no match returns an empty subgraph
(specs/grounded-qa.md 处理链路「图谱结构检索」、Q1 候选集合 H、Q8 H4, ADR-050).
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

import pytest

from app.repositories.graph_migrations import apply_migrations
from app.repositories.graph_search import (
    DEFAULT_MAX_HOPS,
    DEFAULT_MAX_NODES,
    MAX_HOPS_LIMIT,
    MAX_NODES_LIMIT,
    GraphEvidence,
    GraphSubgraph,
    SubgraphEdge,
    SubgraphNode,
    search_subgraph,
)
from app.repositories.neo4j import GraphScope, GraphScopeError, Neo4jRepository
from app.services.versions.materialize import materialize
from app.services.versions.resolver import PublishedVersion
from app.services.versions.snapshot import DraftChapter, DraftEdge, DraftGraph, DraftNode, Revision, build_snapshot

_ENV = ("SMARTSKETCH_TEST_NEO4J_URI", "SMARTSKETCH_TEST_NEO4J_USER", "SMARTSKETCH_TEST_NEO4J_PASSWORD")
pytestmark = pytest.mark.skipif(not all(os.environ.get(n) for n in _ENV),
                                reason="isolated Neo4j fixture not configured")

SPACE = "fake/4"
REV1, REV2 = "rev_" + "1" * 64, "rev_" + "2" * 64
V1, V2 = "01VERSION1", "01VERSION2"


@dataclass(frozen=True)
class Vec:
    values: tuple[float, ...] = (1.0, 0.0, 0.0, 0.0)
    space: str = SPACE


def node(kp_id, name, *, aliases=(), refs=(), kind="concept", chapter="ch1"):
    return DraftNode(kp_id, name, kind, f"{name}的定义", "approved", aliases=tuple(aliases), chapter_id=chapter,
                     source_refs=tuple(refs))


# 线性结构课程（v1）：
#   线性表 -CONTAINS-> 栈 -PREREQUISITE-> 表达式求值 -RELATED_TO-> 逆波兰式
#   线性表 -CONTAINS-> 队列 ;  括号匹配 -EXAMPLE_OF-> 栈 ;  孤立点 无边
V1_NODES = [
    node("list", "线性表", refs=("c_list",)),
    node("stack", "栈", aliases=("LIFO", "堆栈"), refs=("c_stack", "c_stack2")),
    node("queue", "队列", aliases=("FIFO",), refs=("c_queue",)),
    node("expr", "表达式求值", kind="method", refs=("c_expr",)),
    node("rpn", "逆波兰式", aliases=("后缀表达式",)),
    node("paren", "括号匹配", kind="example", refs=("c_paren",)),
    node("lonely", "孤立知识点"),
]
V1_EDGES = [
    DraftEdge("r1", "CONTAINS", "list", "stack", "approved"),
    DraftEdge("r2", "CONTAINS", "list", "queue", "approved"),
    DraftEdge("r3", "PREREQUISITE", "stack", "expr", "approved"),
    DraftEdge("r4", "RELATED_TO", "expr", "rpn", "approved"),
    DraftEdge("r5", "EXAMPLE_OF", "paren", "stack", "approved"),
]
V1_CHUNKS = {"c_list": REV1, "c_stack": REV1, "c_stack2": REV1, "c_queue": REV1, "c_expr": REV1, "c_paren": REV1}


def snapshot_for(course, nodes, edges, chunks, revisions=(REV1,)):
    draft = DraftGraph(course, [Revision(r, "m1", "sha256:" + "a" * 64, "p") for r in revisions],
                       [DraftChapter("ch1", "第一章", 1)], nodes, edges, dict(chunks))
    return build_snapshot(draft).snapshot


class Env:
    def __init__(self, driver):
        self.driver = driver
        self.repo = Neo4jRepository(driver)
        self.course = "j02-" + uuid.uuid4().hex
        self.other = "j02-" + uuid.uuid4().hex

    def q(self, query, **params):
        return [dict(r) for r in self.driver.execute_query(query, parameters_=params, routing_="w",
                                                           database_="neo4j").records]

    def chunks(self, course, mapping):
        self.q("UNWIND $rows AS row CREATE (:Chunk {course_id: $c, chunk_id: row.id, revision_id: row.rev, "
               "document_id: 'm1'})", c=course, rows=[{"id": k, "rev": v} for k, v in mapping.items()])

    def publish(self, course, version_id, nodes, edges, chunks, revisions=(REV1,)):
        snapshot = snapshot_for(course, nodes, edges, chunks, revisions)
        vectors = {n.kp_id: Vec() for n in nodes}
        materialize(self.repo, snapshot, version_id, vectors, lambda: SPACE)

    def draft_node(self, course, kp_id, name):
        """草稿副本（version_id = draft），带贡献记录；检索绝不能读到它。"""
        self.q("CREATE (:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: $id, name: $n, "
               "definition: 'd', type: 'concept', contrib_manual: true})", c=course, id=kp_id, n=name)

    def search(self, terms=(), *, course=None, version=V1, revisions=(REV1, REV2), **kwargs):
        scope = GraphScope(course or self.course, version)
        return search_subgraph(self.repo, scope, frozenset(revisions), terms, **kwargs)


@pytest.fixture
def env():
    neo4j = pytest.importorskip("neo4j")
    driver = neo4j.GraphDatabase.driver(os.environ[_ENV[0]], auth=(os.environ[_ENV[1]], os.environ[_ENV[2]]))
    apply_migrations(driver)
    state = Env(driver)
    state.chunks(state.course, V1_CHUNKS)
    state.publish(state.course, V1, V1_NODES, V1_EDGES, V1_CHUNKS)
    try:
        yield state
    finally:
        state.q("MATCH (n) WHERE n.course_id IN $ids DETACH DELETE n", ids=[state.course, state.other])
        driver.close()


def kp_ids(graph):
    return [n.kp_id for n in graph.nodes]


def hops(graph):
    return {n.kp_id: n.hops for n in graph.nodes}


def edges(graph):
    return {(e.type, e.from_id, e.to_id) for e in graph.edges}


# ---------------------------------------------------------------- matching and shape


def test_term_in_question_seeds_and_expands_within_two_hops(env):
    graph = env.search(["栈为什么适合做表达式求值？"])
    assert isinstance(graph, GraphSubgraph)
    assert all(isinstance(n, SubgraphNode) for n in graph.nodes)
    assert all(isinstance(e, SubgraphEdge) for e in graph.edges)
    # 种子在前（长名称优先），再按跳数、kp_id
    assert kp_ids(graph)[:2] == ["expr", "stack"]
    # 括号匹配只经 EXAMPLE_OF 相连，默认不沿它扩展
    assert hops(graph) == {"expr": 0, "stack": 0, "list": 1, "rpn": 1, "queue": 2}
    assert graph.seed_kp_ids == ("expr", "stack")
    assert not graph.truncated
    stack = next(n for n in graph.nodes if n.kp_id == "stack")
    assert (stack.name, stack.type, stack.definition, stack.chapter_id) == ("栈", "concept", "栈的定义", "ch1")
    assert stack.aliases == ("LIFO", "堆栈")
    assert stack.matched == "栈"
    assert next(n for n in graph.nodes if n.kp_id == "list").matched is None


def test_edges_are_the_induced_edges_of_the_returned_nodes(env):
    graph = env.search(["栈"], max_hops=1)
    assert set(kp_ids(graph)) == {"stack", "list", "expr"}
    # r2（线性表→队列）端点不全在结果中，不返回
    assert edges(graph) == {("CONTAINS", "list", "stack"), ("PREREQUISITE", "stack", "expr")}
    assert {e.rel_id for e in graph.edges} == {"r1", "r3"}
    # EXAMPLE_OF 虽不用于扩展，两端都在结果中时照常返回
    graph = env.search(["括号匹配要用栈"], max_hops=0)
    assert kp_ids(graph) == ["paren", "stack"]
    assert edges(graph) == {("EXAMPLE_OF", "paren", "stack")}


def test_example_of_is_not_expanded_by_default_but_can_be_requested(env):
    graph = env.search(["括号匹配"], max_hops=1)
    assert kp_ids(graph) == ["paren"]
    graph = env.search(["括号匹配"], max_hops=1,
                       relation_types=("CONTAINS", "PREREQUISITE", "RELATED_TO", "EXAMPLE_OF"))
    assert hops(graph) == {"paren": 0, "stack": 1}


def test_aliases_match_case_insensitively(env):
    graph = env.search(["什么是 lifo？"], max_hops=0)
    assert kp_ids(graph) == ["stack"]
    assert graph.nodes[0].matched == "LIFO"
    assert kp_ids(env.search(["后缀表达式怎么算"], max_hops=0)) == ["rpn"]


def test_exact_term_beats_containment_and_short_terms_match_inside_names(env):
    # 「队列」精确命中；「表达式」包含于「表达式求值」「后缀表达式」（关键词式输入）
    graph = env.search(["表达式", "队列"], max_hops=0)
    assert kp_ids(graph) == ["queue", "expr", "rpn"]  # 精确 > 名称包含术语；同为 5 字按 kp_id
    assert graph.seed_kp_ids == ("queue", "expr", "rpn")
    assert [n.matched for n in graph.nodes] == ["队列", "表达式求值", "后缀表达式"]


def test_shorter_names_rank_after_longer_ones(env):
    # 单字名称（栈、堆）在问题中出现也算命中，但排在更长的名称之后，种子封顶时先被舍弃
    env.publish(env.course, V2, [node("heap", "堆"), node("tree", "二叉树")], [], {})
    assert kp_ids(env.search(["堆排序和二叉树的关系"], version=V2, max_hops=0)) == ["tree", "heap"]
    graph = env.search(["堆排序和二叉树的关系"], version=V2, max_hops=0, max_seeds=1)
    assert kp_ids(graph) == ["tree"] and graph.truncated
    assert kp_ids(env.search(["堆"], version=V2, max_hops=0)) == ["heap"]


def test_single_character_terms_do_not_match_inside_names(env):
    assert kp_ids(env.search(["表"], max_hops=0)) == []


def test_evidence_is_filtered_by_the_version_revision_list(env):
    graph = env.search(["栈"], max_hops=0)
    assert all(isinstance(e, GraphEvidence) for e in graph.evidence)
    assert [(e.kp_id, e.chunk_id, e.revision_id, e.document_id) for e in graph.evidence] == [
        ("stack", "c_stack", REV1, "m1"), ("stack", "c_stack2", REV1, "m1")]
    # 修订不在绑定版本的修订列表内的文本块不进入结果（纵深防御，Q3.1 第 2 条）
    assert env.search(["栈"], max_hops=0, revisions=(REV2,)).evidence == ()
    assert kp_ids(env.search(["栈"], max_hops=0, revisions=())) == ["stack"]


def test_published_version_bound_by_g07_is_used_as_is(env):
    bound = PublishedVersion(env.course, V1, 1, frozenset({REV1}))
    graph = search_subgraph(env.repo, bound.graph_scope(), bound.revision_ids, ["队列"], max_hops=0)
    assert kp_ids(graph) == ["queue"]
    assert [e.chunk_id for e in graph.evidence] == ["c_queue"]


# ---------------------------------------------------------------- isolation


def test_draft_other_versions_and_other_courses_never_come_back(env):
    env.draft_node(env.course, "draft_only", "草稿里的栈变体")
    env.draft_node(env.course, "stack", "栈")  # 同 kp_id 的草稿节点
    env.publish(env.course, V2, [node("v2only", "双端队列")], [], {})
    env.chunks(env.other, {"o1": REV1})
    env.publish(env.other, V1, [node("foreign", "栈的应用", refs=("o1",)), node("stack", "栈")],
                [DraftEdge("x", "CONTAINS", "stack", "foreign", "approved")], {"o1": REV1})

    graph = env.search(["栈的应用与双端队列，草稿里的栈变体"])
    ids = kp_ids(graph)
    assert "foreign" not in ids and "v2only" not in ids and "draft_only" not in ids
    assert ids.count("stack") == 1
    # 他课与本课 V2 各自只看到自己的内容
    assert kp_ids(env.search(["栈的应用"], course=env.other, max_hops=0)) == ["foreign", "stack"]
    assert kp_ids(env.search(["双端队列"], version=V2)) == ["v2only"]
    assert kp_ids(env.search(["双端队列"], version=V1, max_hops=0)) == ["queue"]  # 「队列」包含于术语


def test_draft_scope_is_refused(env):
    with pytest.raises(GraphScopeError):
        search_subgraph(env.repo, GraphScope(env.course, "draft", effective_task_ids=()), {REV1}, ["栈"])


def test_seed_kp_ids_outside_the_version_are_ignored(env, caplog):
    env.publish(env.other, V1, [node("foreign", "外课")], [], {})
    with caplog.at_level("INFO", logger="app.repositories.graph_search"):
        graph = env.search(seed_kp_ids=("foreign", "nope", "queue"), max_hops=0)
    assert kp_ids(graph) == ["queue"]
    assert graph.nodes[0].matched is None and graph.seed_kp_ids == ("queue",)
    assert "2 seed" in caplog.text


# ---------------------------------------------------------------- bounds


def test_hop_limit_is_respected(env):
    assert hops(env.search(["逆波兰式"], max_hops=0)) == {"rpn": 0}
    assert hops(env.search(["逆波兰式"], max_hops=1)) == {"rpn": 0, "expr": 1}
    assert hops(env.search(["逆波兰式"], max_hops=2)) == {"rpn": 0, "expr": 1, "stack": 2}
    assert hops(env.search(["逆波兰式"], max_hops=3)) == {"rpn": 0, "expr": 1, "stack": 2, "list": 3}


def test_node_limit_truncates_deterministically(env):
    graph = env.search(["栈"], max_nodes=3)
    assert kp_ids(graph) == ["stack", "expr", "list"]  # 同一跳按 kp_id 取前者
    assert graph.truncated
    assert all(e.from_id in kp_ids(graph) and e.to_id in kp_ids(graph) for e in graph.edges)
    assert kp_ids(env.search(["栈"], max_nodes=5)) == ["stack", "expr", "list", "queue", "rpn"]
    assert not env.search(["栈"], max_nodes=5).truncated  # 恰好装下两跳内全部可达点


def test_seed_limit_truncates(env):
    graph = env.search(["线性表、栈、队列、表达式求值"], max_hops=0, max_seeds=2)
    assert kp_ids(graph) == ["expr", "list"]  # 同为「名称包含于问题」时名称长者优先，再按 kp_id
    assert graph.truncated


def test_evidence_limit_truncates(env):
    graph = env.search(["线性表"], max_hops=1, max_evidence=2)
    assert kp_ids(graph) == ["list", "queue", "stack"]
    assert [(e.kp_id, e.chunk_id) for e in graph.evidence] == [("list", "c_list"), ("queue", "c_queue")]
    assert graph.truncated


def test_hub_expansion_stays_within_the_node_limit(env):
    hub = [node("hub", "中心概念")] + [node(f"n{i:03d}", f"外围{i:03d}") for i in range(120)]
    spokes = [DraftEdge(f"e{i:03d}", "RELATED_TO", "hub", f"n{i:03d}", "approved") for i in range(120)]
    env.publish(env.course, V2, hub, spokes, {})
    graph = env.search(["中心概念"], version=V2)
    assert len(graph.nodes) == DEFAULT_MAX_NODES
    assert graph.truncated
    assert kp_ids(graph)[1:4] == ["n000", "n001", "n002"]


class CountingRepository(Neo4jRepository):
    """记录每次读取返回的行数：上限必须在 Cypher 里生效，不能先全取再在应用层截断。"""

    def __init__(self, driver):
        super().__init__(driver)
        self.sizes = []

    def read(self, query, scope, **kwargs):
        rows = super().read(query, scope, **kwargs)
        self.sizes.append(len(rows))
        return rows


def test_limits_are_applied_in_the_query_not_after_fetching(env):
    hub = [node("hub", "中心概念")] + [node(f"n{i:03d}", f"外围{i:03d}") for i in range(120)]
    spokes = [DraftEdge(f"e{i:03d}", "RELATED_TO", "hub", f"n{i:03d}", "approved") for i in range(120)]
    env.publish(env.course, V2, hub, spokes, {})
    repo = CountingRepository(env.driver)
    graph = search_subgraph(repo, GraphScope(env.course, V2), {REV1}, ["中心概念"], max_nodes=10)
    assert len(graph.nodes) == 10 and graph.truncated
    assert max(repo.sizes) <= 10
    repo.sizes.clear()
    graph = search_subgraph(repo, GraphScope(env.course, V2), {REV1}, ["外围"], max_hops=0, max_seeds=5)
    assert kp_ids(graph) == ["n000", "n001", "n002", "n003", "n004"] and graph.truncated
    assert max(repo.sizes) <= 6


def test_defaults_are_bounded():
    assert 1 <= DEFAULT_MAX_HOPS <= MAX_HOPS_LIMIT
    assert 1 <= DEFAULT_MAX_NODES <= MAX_NODES_LIMIT


@pytest.mark.parametrize("kwargs", [
    {"max_hops": -1}, {"max_hops": MAX_HOPS_LIMIT + 1}, {"max_hops": True}, {"max_hops": 1.0},
    {"max_nodes": 0}, {"max_nodes": MAX_NODES_LIMIT + 1},
    {"max_seeds": 0}, {"max_seeds": 11, "max_nodes": 10},
    {"max_evidence": -1},
    {"relation_types": ()}, {"relation_types": ("KNOWS",)}, {"relation_types": "CONTAINS"},
])
def test_bad_bounds_are_rejected(env, kwargs):
    with pytest.raises(ValueError):
        env.search(["栈"], **kwargs)


# ---------------------------------------------------------------- empty


@pytest.mark.parametrize("terms", [[], ["   "], ["红黑树的旋转"], ["", "\n"]])
def test_no_match_returns_an_empty_subgraph(env, terms):
    graph = env.search(terms)
    assert graph == GraphSubgraph((), (), (), (), False)
    assert graph.empty


def test_unpublished_version_id_returns_empty(env):
    assert env.search(["栈"], version="01NOSUCHVERSION").empty


def test_bad_terms_are_rejected(env):
    with pytest.raises(TypeError):
        env.search("栈")  # 单个字符串会被逐字拆开，拒绝
    with pytest.raises(TypeError):
        env.search([1])
    with pytest.raises(TypeError):
        env.search(seed_kp_ids="stack")


def test_isolation_holds_with_many_terms_matching_foreign_names(env):
    env.publish(env.other, V1, [node(f"f{i}", f"外课概念{i}") for i in range(20)], [], {})
    assert env.search([f"外课概念{i}" for i in range(20)]).empty
