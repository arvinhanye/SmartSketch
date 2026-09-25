"""I03：可学集合纯函数（``specs/learning-path.md`` §1、§2，LP-1/2/3/7/11/12）。

Eligible(V, E, M) = { k ∈ V \\ M | Pred(k) ⊆ M }，只看直接前置。
"""

import ast
import itertools
import random
from pathlib import Path
from types import MappingProxyType

import pytest

from app.services.graph.dag import find_cycle
from app.services.learning.eligible import (
    GraphIntegrityError,
    PrerequisiteGraph,
    ProgressOutsideGraphError,
    build_prerequisite_graph,
    eligible_set,
)


def eligible(nodes, edges, mastered):
    return eligible_set(build_prerequisite_graph(nodes, edges), mastered)


# ---------------------------------------------------------------- 成功路径


def test_empty_mastered_only_roots_are_eligible():
    # LP-1：M=∅，A 无前置、B 依赖 A → 仅 A 可学
    assert eligible(["A", "B"], [("A", "B")], set()) == ("A",)


def test_empty_mastered_all_roots_in_forest():
    nodes = ["A", "B", "C", "D", "E"]
    edges = [("A", "B"), ("B", "C"), ("D", "E")]
    assert eligible(nodes, edges, frozenset()) == ("A", "D")


def test_all_mastered_returns_empty_tuple():
    nodes = ["A", "B", "C"]
    edges = [("A", "B"), ("B", "C")]
    assert eligible(nodes, edges, {"A", "B", "C"}) == ()


def test_isolated_node_is_eligible_until_mastered():
    # LP-3：孤立点仍在候选中
    nodes = ["A", "B", "ISO"]
    edges = [("A", "B")]
    assert eligible(nodes, edges, set()) == ("A", "ISO")
    assert eligible(nodes, edges, {"A"}) == ("B", "ISO")
    assert eligible(nodes, edges, {"ISO"}) == ("A",)


def test_single_node_graph():
    assert eligible(["A"], [], set()) == ("A",)
    assert eligible(["A"], [], {"A"}) == ()


def test_multiple_prerequisites_must_all_be_mastered():
    # LP-2：C 依赖 A、B
    nodes = ["A", "B", "C"]
    edges = [("A", "C"), ("B", "C")]
    assert eligible(nodes, edges, set()) == ("A", "B")
    assert eligible(nodes, edges, {"B"}) == ("A",)
    assert eligible(nodes, edges, {"A"}) == ("B",)
    assert eligible(nodes, edges, {"A", "B"}) == ("C",)


def test_only_direct_prerequisites_are_checked():
    # A→B→C：C 只看直接前置 B；A 未掌握不阻挡 C
    nodes = ["A", "B", "C"]
    edges = [("A", "B"), ("B", "C")]
    assert eligible(nodes, edges, {"A"}) == ("B",)
    assert eligible(nodes, edges, {"B"}) == ("A", "C")


def test_out_of_order_mastery_grants_no_exemption():
    # LP-7：越序把 C 标 mastered，A/B 仍未掌握
    nodes = ["A", "B", "C", "D"]
    edges = [("A", "C"), ("B", "C"), ("C", "D"), ("A", "D")]
    result = eligible(nodes, edges, {"C"})
    assert result == ("A", "B")  # A/B 仍可学，C 自身不在候选
    # D 的直接前置 C 已掌握但 A 未掌握 → 仍被阻挡
    assert "D" not in result
    assert eligible(nodes, edges, {"C", "A"}) == ("B", "D")


def test_mastered_node_is_never_a_candidate_even_with_unmet_prerequisites():
    nodes = ["A", "B"]
    edges = [("A", "B")]
    assert eligible(nodes, edges, {"B"}) == ("A",)


def test_duplicate_edges_are_deduplicated():
    nodes = ["A", "B", "C"]
    edges = [("A", "C"), ("A", "C"), ["B", "C"], ("B", "C")]
    graph = build_prerequisite_graph(nodes, edges)
    assert graph.edges == frozenset({("A", "C"), ("B", "C")})
    assert eligible_set(graph, {"A", "B"}) == ("C",)


def test_duplicate_mastered_entries_are_a_set():
    assert eligible(["A", "B"], [("A", "B")], ["A", "A"]) == ("B",)


# ---------------------------------------------------------------- 排序与确定性


def test_result_is_sorted_by_utf8_byte_order():
    nodes = ["b", "a", "B", "知识点", "Z1", "_x", "é", "\U0001F600", "～"]
    result = eligible(nodes, [], set())
    assert list(result) == sorted(nodes, key=lambda s: s.encode("utf-8"))
    assert result[0] == "B"  # 大写 ASCII 在小写之前
    assert result[-1] == "\U0001F600"  # 4 字节 UTF-8 排在 3 字节之后


def test_result_independent_of_input_order_and_duplicates():
    nodes = ["A", "B", "C", "D", "E", "F"]
    edges = [("A", "C"), ("B", "C"), ("C", "E"), ("D", "E"), ("A", "F")]
    mastered = ["A", "D"]
    expected = eligible(nodes, edges, set(mastered))
    assert expected == ("B", "F")
    rng = random.Random(3)
    for _ in range(30):
        n = nodes[:]
        e = edges + edges[: rng.randrange(len(edges))]
        m = mastered + mastered[: rng.randrange(len(mastered) + 1)]
        rng.shuffle(n)
        rng.shuffle(e)
        rng.shuffle(m)
        assert eligible(n, e, m) == expected
        assert eligible(iter(n), iter(e), iter(m)) == expected


def _brute_force(nodes, edges, mastered):
    preds = {k: {a for a, b in edges if b == k} for k in nodes}
    return sorted(
        (k for k in nodes if k not in mastered and preds[k] <= mastered),
        key=lambda s: s.encode("utf-8"),
    )


@pytest.mark.parametrize("seed", range(40))
def test_random_dags_match_definition(seed):
    rng = random.Random(seed)
    size = rng.randrange(1, 12)
    nodes = [f"k{i:02d}" for i in range(size)]
    # 只加 i<j 的边保证无环
    edges = [(nodes[i], nodes[j]) for i, j in itertools.combinations(range(size), 2) if rng.random() < 0.3]
    mastered = {k for k in nodes if rng.random() < 0.4}
    result = eligible(nodes, edges, mastered)
    assert list(result) == _brute_force(nodes, edges, mastered)
    # §4：DAG 且 M≠V 时至少一个候选；M=V 时为空
    assert bool(result) == (mastered != set(nodes))
    # 候选之间不可能有先修边（§3 末）
    assert not any((a, b) in set(edges) for a in result for b in result)


# ---------------------------------------------------------------- 不可变输入


def test_mastered_set_is_not_modified():
    nodes = ["A", "B", "C"]
    edges = [("A", "B")]
    mastered = {"A"}
    snapshot = set(mastered)
    eligible(nodes, edges, mastered)
    assert mastered == snapshot


def test_graph_inputs_are_not_modified():
    nodes = ["B", "A", "C"]
    edges = [("A", "B"), ("A", "B")]
    nodes_copy, edges_copy = list(nodes), list(edges)
    eligible(nodes, edges, ["A"])
    assert nodes == nodes_copy
    assert edges == edges_copy


def test_mastered_not_modified_on_error():
    mastered = {"A", "OTHER-COURSE"}
    snapshot = set(mastered)
    with pytest.raises(ProgressOutsideGraphError):
        eligible(["A", "B"], [("A", "B")], mastered)
    assert mastered == snapshot


def test_prerequisite_graph_is_immutable():
    graph = build_prerequisite_graph(["A", "B", "C"], [("A", "C"), ("B", "C")])
    assert isinstance(graph, PrerequisiteGraph)
    assert graph.nodes == frozenset({"A", "B", "C"})
    assert isinstance(graph.predecessors, MappingProxyType)
    assert graph.predecessors["C"] == frozenset({"A", "B"})
    assert graph.predecessors["A"] == frozenset()
    with pytest.raises(TypeError):
        graph.predecessors["A"] = frozenset({"B"})  # type: ignore[index]
    with pytest.raises(AttributeError):
        graph.nodes = frozenset()  # type: ignore[misc]


def test_graph_can_be_reused_across_mastered_sets():
    graph = build_prerequisite_graph(["A", "B"], [("A", "B")])
    assert eligible_set(graph, set()) == ("A",)
    assert eligible_set(graph, {"A"}) == ("B",)
    assert eligible_set(graph, set()) == ("A",)


# ---------------------------------------------------------------- 外课 / 历史 ID


def test_foreign_mastered_id_is_rejected_not_ignored():
    # §1：纯函数只接受 projected_status 的键集 ⊆ V；外课/历史 ID 应在调用前由仓储边界处理
    with pytest.raises(ProgressOutsideGraphError) as info:
        eligible(["A", "B"], [("A", "B")], {"A", "zz-other", "aa-other"})
    assert info.value.ids == ("aa-other", "zz-other")


def test_foreign_mastered_id_rejected_even_when_graph_would_be_all_mastered():
    with pytest.raises(ProgressOutsideGraphError):
        eligible(["A"], [], {"A", "ghost"})


def test_foreign_edge_endpoint_is_integrity_error():
    # 他课节点出现在边上 = 悬空端点 = 已提交版完整性故障
    with pytest.raises(GraphIntegrityError) as info:
        build_prerequisite_graph(["A", "B"], [("A", "B"), ("other:X", "B"), ("A", "other:Y")])
    assert info.value.kind == "dangling_edge"
    assert info.value.ids == ("other:X", "other:Y")


# ---------------------------------------------------------------- 图完整性故障


def test_cycle_is_integrity_error_with_closed_path():
    nodes = ["A", "B", "C", "D"]
    edges = [("B", "C"), ("C", "D"), ("D", "B"), ("A", "B")]
    with pytest.raises(GraphIntegrityError) as info:
        build_prerequisite_graph(nodes, edges)
    assert info.value.kind == "cycle"
    assert info.value.ids == ("B", "C", "D", "B")
    # 复用 F05 的环检测结果与旋转规则
    assert info.value.ids == find_cycle(nodes, edges)


def test_cycle_in_unrelated_component_still_fails_regardless_of_mastery():
    # 不输出部分推荐：即使候选 A 与环无关
    nodes = ["A", "X", "Y"]
    edges = [("X", "Y"), ("Y", "X")]
    with pytest.raises(GraphIntegrityError) as info:
        build_prerequisite_graph(nodes, edges)
    assert info.value.kind == "cycle"
    assert info.value.ids == ("X", "Y", "X")


def test_self_loop_is_integrity_error():
    with pytest.raises(GraphIntegrityError) as info:
        build_prerequisite_graph(["A", "B"], [("A", "B"), ("B", "B")])
    assert info.value.kind == "self_loop"
    assert info.value.ids == ("B",)


def test_duplicate_node_id_is_integrity_error():
    with pytest.raises(GraphIntegrityError) as info:
        build_prerequisite_graph(["A", "B", "A", "C", "C"], [])
    assert info.value.kind == "duplicate_node"
    assert info.value.ids == ("A", "C")


def test_empty_graph_is_integrity_error():
    # LP-11：已提交 V=∅ 是完整性错误，不是正常空态
    with pytest.raises(GraphIntegrityError) as info:
        build_prerequisite_graph([], [])
    assert info.value.kind == "empty_graph"
    assert info.value.ids == ()


@pytest.mark.parametrize(
    "nodes, edges",
    [
        (["A", 1], []),
        (["A", ""], []),
        (["A", None], []),
        (["A", "\ud800"], []),  # 无法编码为 UTF-8 的孤立代理
        (["A", "B"], [("A",)]),
        (["A", "B"], [("A", "B", "C")]),
        (["A", "B"], ["AB"]),
        (["A", "B"], [("A", 2)]),
    ],
)
def test_malformed_graph_input_is_integrity_error(nodes, edges):
    with pytest.raises(GraphIntegrityError) as info:
        build_prerequisite_graph(nodes, edges)
    assert info.value.kind == "malformed"


def test_integrity_error_is_value_error_with_kind_in_message():
    with pytest.raises(ValueError, match="cycle"):
        build_prerequisite_graph(["A", "B"], [("A", "B"), ("B", "A")])


def test_integrity_errors_have_fixed_precedence():
    # malformed > empty > duplicate_node > dangling_edge > self_loop > cycle
    with pytest.raises(GraphIntegrityError) as info:
        build_prerequisite_graph(["A", "A", "B"], [("A", "X"), ("B", "B"), ("A", "B"), ("B", "A")])
    assert info.value.kind == "duplicate_node"
    with pytest.raises(GraphIntegrityError) as info:
        build_prerequisite_graph(["A", "B"], [("A", "X"), ("B", "B"), ("A", "B"), ("B", "A")])
    assert info.value.kind == "dangling_edge"
    with pytest.raises(GraphIntegrityError) as info:
        build_prerequisite_graph(["A", "B"], [("B", "B"), ("A", "B"), ("B", "A")])
    assert info.value.kind == "self_loop"


def test_non_string_mastered_id_is_type_error():
    graph = build_prerequisite_graph(["A"], [])
    with pytest.raises(TypeError):
        eligible_set(graph, {1})


def test_eligible_set_requires_validated_graph():
    with pytest.raises(TypeError):
        eligible_set((["A"], []), set())  # type: ignore[arg-type]


# ---------------------------------------------------------------- 纯函数与规模


def test_module_has_no_io_or_database_imports():
    source = Path(__file__).resolve().parents[2] / "src/backend/app/services/learning/eligible.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    forbidden = ("sqlite3", "neo4j", "app.repositories", "app.api", "fastapi", "os", "time", "datetime")
    assert not [m for m in imported if any(m == f or m.startswith(f + ".") for f in forbidden)]


def test_long_chain_is_linear_and_non_recursive():
    size = 100_000
    nodes = [f"k{i:06d}" for i in range(size)]
    edges = list(zip(nodes, nodes[1:]))
    mastered = frozenset(nodes[: size // 2])
    assert eligible(nodes, edges, mastered) == (nodes[size // 2],)
