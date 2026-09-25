"""F05: DAG 环检测纯函数——节点/前置边 + 候选边 → 合法或闭合环路径。

依据 specs/course-knowledge-graph.md「前置关系成环处理」DAG-1/DAG-8/DAG-9/DAG-10，
环路径格式对齐 B11 契约 `x-closed-cycle: true`（首尾同 ID，至少两项）。
"""

import random
from collections import deque

import pytest

from app.services.graph.dag import CycleCheck, UnknownNodeError, check_candidates, find_cycle


def assert_closed_cycle_in(cycle: tuple[str, ...], edges: set[tuple[str, str]]) -> None:
    """闭合环不变量：首尾同 ID、至少两项、相邻两项都是图中的边、除首尾外无重复节点。"""
    assert isinstance(cycle, tuple)
    assert len(cycle) >= 2
    assert cycle[0] == cycle[-1]
    assert len(set(cycle[:-1])) == len(cycle) - 1
    for pair in zip(cycle, cycle[1:]):
        assert pair in edges


def is_acyclic(nodes: set[str], edges: set[tuple[str, str]]) -> bool:
    """测试侧参考实现（Kahn 拓扑排序），与被测 DFS/BFS 实现无共享代码。"""
    indegree = {n: 0 for n in nodes}
    out: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        out[a].append(b)
        indegree[b] += 1
    queue = deque(n for n, d in indegree.items() if d == 0)
    seen = 0
    while queue:
        n = queue.popleft()
        seen += 1
        for m in out[n]:
            indegree[m] -= 1
            if indegree[m] == 0:
                queue.append(m)
    return seen == len(nodes)


# ---------- 成功路径：合法 ----------


def test_empty_graph_and_no_candidates_are_legal():
    assert check_candidates([], [], []) == CycleCheck(ok=True, cycle=None, edge=None)
    assert find_cycle([], []) is None


def test_legal_candidate_on_dag():
    result = check_candidates(["A", "B", "C"], [("A", "B")], [("B", "C")])
    assert result.ok is True
    assert result.cycle is None and result.edge is None


def test_candidate_equal_to_existing_edge_is_legal():
    assert check_candidates(["A", "B"], [("A", "B")], [("A", "B")]).ok is True


def test_duplicate_edges_are_tolerated():
    assert find_cycle(["A", "B"], [("A", "B"), ("A", "B")]) is None
    assert check_candidates(["A", "B"], [("A", "B")], [("A", "B"), ("A", "B")]).ok


def test_diamond_is_not_a_cycle():
    # 多前置汇合（A→B→D、A→C→D）是 DAG，不能被误判为环
    nodes = ["A", "B", "C", "D"]
    edges = [("A", "B"), ("A", "C"), ("B", "D")]
    assert find_cycle(nodes, edges + [("C", "D")]) is None
    assert check_candidates(nodes, edges, [("C", "D")]).ok


# ---------- 自环 ----------


def test_self_loop_candidate_returns_two_item_cycle():
    # DAG-9：教师新建自环 A→A → details.cycle = [A, A]
    result = check_candidates(["A", "B"], [("A", "B")], [("A", "A")])
    assert result == CycleCheck(ok=False, cycle=("A", "A"), edge=("A", "A"))


def test_self_loop_in_existing_graph_is_found():
    assert find_cycle(["A"], [("A", "A")]) == ("A", "A")


# ---------- 三节点环 ----------


def test_three_node_cycle_dag_1():
    # DAG-1：已有 B→C、C→A，教师新建 A→B → [A, B, C, A]，从候选边起点开始
    result = check_candidates(["A", "B", "C"], [("B", "C"), ("C", "A")], [("A", "B")])
    assert result == CycleCheck(ok=False, cycle=("A", "B", "C", "A"), edge=("A", "B"))


def test_find_cycle_rotates_to_smallest_id():
    # 全图复检（G04 发布前）：环从环上字典序最小的 ID 开始
    assert find_cycle(["A", "B", "C"], [("B", "C"), ("C", "A"), ("A", "B")]) == ("A", "B", "C", "A")
    assert find_cycle(["x", "y", "z"], [("z", "y"), ("y", "x"), ("x", "z")]) == ("x", "z", "y", "x")


def test_find_cycle_rotates_when_dfs_enters_cycle_at_larger_id():
    # DFS 从 A 经 A→C 进入环 C→B→C，入环点 C 不是环上最小 ID，仍须旋转为从 B 开始
    edges = [("A", "C"), ("C", "B"), ("B", "C")]
    assert find_cycle(["A", "B", "C"], edges) == ("B", "C", "B")
    assert check_candidates(["A", "B", "C"], edges, []) == CycleCheck(ok=False, cycle=("B", "C", "B"), edge=None)


# ---------- 反转造环 ----------


def test_reversing_an_edge_without_removing_it_forms_two_node_cycle():
    result = check_candidates(["A", "B"], [("A", "B")], [("B", "A")])
    assert result == CycleCheck(ok=False, cycle=("B", "A", "B"), edge=("B", "A"))


def test_reversal_that_closes_a_longer_path():
    # A→B→C 且 A→C；调用方把 A→C 反转为 C→A（先从既有边移除 A→C）→ 经 A→B→C 成环
    result = check_candidates(["A", "B", "C"], [("A", "B"), ("B", "C")], [("C", "A")])
    assert result == CycleCheck(ok=False, cycle=("C", "A", "B", "C"), edge=("C", "A"))


def test_reversal_that_stays_acyclic():
    # 链 A→B→C，把 B→C 反转为 C→B（已移除 B→C）→ 仍合法
    assert check_candidates(["A", "B", "C"], [("A", "B")], [("C", "B")]).ok


# ---------- 断开图 ----------


def test_disconnected_components_legal_link():
    nodes = ["A", "B", "X", "Y", "lonely"]
    edges = [("A", "B"), ("X", "Y")]
    assert find_cycle(nodes, edges) is None
    assert check_candidates(nodes, edges, [("B", "X")]).ok
    assert check_candidates(nodes, edges, [("Y", "A")]).ok


def test_cycle_inside_one_component_of_disconnected_graph():
    nodes = ["A", "B", "X", "Y", "Z", "lonely"]
    edges = [("A", "B"), ("X", "Y"), ("Y", "Z")]
    result = check_candidates(nodes, edges, [("Z", "X")])
    assert result == CycleCheck(ok=False, cycle=("Z", "X", "Y", "Z"), edge=("Z", "X"))


def test_find_cycle_picks_component_with_smallest_root_first():
    # 两个互不相连的环：按 ID 升序选 DFS 起点，先找到含 A 的环
    edges = [("X", "Y"), ("Y", "X"), ("B", "A"), ("A", "B")]
    assert find_cycle(["Y", "X", "B", "A"], edges) == ("A", "B", "A")


def test_linking_two_components_both_ways_forms_cycle():
    nodes = ["A", "B", "C", "D"]
    result = check_candidates(nodes, [("A", "B"), ("C", "D")], [("B", "C"), ("D", "A")])
    assert result == CycleCheck(ok=False, cycle=("D", "A", "B", "C", "D"), edge=("D", "A"))
    assert check_candidates(nodes, [("A", "B"), ("C", "D")], [("B", "C")]).ok is True


# ---------- 大链条（不递归爆栈） ----------

CHAIN = 100_000  # 远超 CPython 默认递归上限 1000


def chain(n: int) -> tuple[list[str], list[tuple[str, str]]]:
    nodes = [f"k{i:06d}" for i in range(n)]
    return nodes, list(zip(nodes, nodes[1:]))


def test_long_chain_is_legal_and_find_cycle_does_not_recurse():
    nodes, edges = chain(CHAIN)
    assert find_cycle(nodes, edges) is None
    assert check_candidates(nodes, edges, [(nodes[0], nodes[-1])]).ok


def test_long_chain_back_edge_returns_full_cycle():
    nodes, edges = chain(CHAIN)
    result = check_candidates(nodes, edges, [(nodes[-1], nodes[0])])
    assert result.ok is False
    assert result.edge == (nodes[-1], nodes[0])
    assert result.cycle == (nodes[-1], *nodes)
    assert find_cycle(nodes, edges + [(nodes[-1], nodes[0])]) == (*nodes, nodes[0])


# ---------- 确定性 ----------


def test_candidate_cycle_is_shortest_through_candidate():
    # 从 B 回到 A 有长路 B→C→D→E→A 与短路 B→F→A：取经候选边的最短环
    nodes = ["A", "B", "C", "D", "E", "F"]
    edges = [("B", "C"), ("C", "D"), ("D", "E"), ("E", "A"), ("B", "F"), ("F", "A")]
    assert check_candidates(nodes, edges, [("A", "B")]).cycle == ("A", "B", "F", "A")


def test_tie_between_equal_length_paths_breaks_by_ascending_ids():
    nodes = ["A", "B", "C", "D"]
    edges = [("A", "C"), ("A", "B"), ("C", "D"), ("B", "D")]
    assert check_candidates(nodes, edges, [("D", "A")]).cycle == ("D", "A", "B", "D")


def test_result_independent_of_input_order():
    nodes = ["A", "B", "C", "D", "E", "M"]
    edges = [("A", "C"), ("A", "B"), ("C", "D"), ("B", "D"), ("D", "E"), ("E", "M")]
    candidates = [("M", "B"), ("E", "A"), ("C", "B"), ("M", "A")]
    baseline = check_candidates(nodes, edges, candidates)
    baseline_whole = find_cycle(nodes, edges + candidates)
    assert baseline.ok is False and baseline_whole is not None
    rng = random.Random(20260925)
    for _ in range(50):
        n, e, c = nodes[:], edges[:], candidates[:]
        rng.shuffle(n)
        rng.shuffle(e)
        rng.shuffle(c)
        assert check_candidates(n, e, c) == baseline
        assert find_cycle(n, e + c) == baseline_whole


def test_multiple_candidates_are_applied_in_ascending_order():
    # 单独都合法，合起来成环：按 (from_id, to_id) 升序逐条加入，报告第一条闭合环的候选边
    for candidates in ([("B", "C"), ("C", "A")], [("C", "A"), ("B", "C")]):
        result = check_candidates(["A", "B", "C"], [("A", "B")], candidates)
        assert result == CycleCheck(ok=False, cycle=("C", "A", "B", "C"), edge=("C", "A"))


def test_merge_rewire_forms_two_node_cycle_dag_8():
    # DAG-8：A→B、B→C，合并 A 与 C 为 M → 重接得到 M→B、B→M
    result = check_candidates(["M", "B"], [], [("M", "B"), ("B", "M")])
    assert result == CycleCheck(ok=False, cycle=("M", "B", "M"), edge=("M", "B"))


# ---------- 既有图已违反不变量 ----------


def test_existing_cycle_is_reported_without_blaming_a_candidate():
    # DAG-10：草稿已含环 → 如实报告该环，edge=None，调用方据此失败而不是静默降级
    result = check_candidates(["A", "B", "C", "D"], [("C", "B"), ("B", "C")], [("A", "D")])
    assert result == CycleCheck(ok=False, cycle=("B", "C", "B"), edge=None)


# ---------- 输入校验与纯函数性质 ----------


def test_unknown_node_in_edge_or_candidate_is_rejected():
    # 跨课程/未知 ID 不得被静默当作新节点
    with pytest.raises(UnknownNodeError, match="other-course-kp"):
        check_candidates(["A", "B"], [("A", "other-course-kp")], [])
    with pytest.raises(UnknownNodeError):
        check_candidates(["A", "B"], [], [("A", "ghost")])
    with pytest.raises(UnknownNodeError):
        find_cycle(["A"], [("ghost", "A")])
    assert issubclass(UnknownNodeError, ValueError)


@pytest.mark.parametrize(
    "nodes, edges",
    [
        ([""], []),
        (["A", 1], []),
        (["A"], [("A",)]),
        (["A", "B"], [("A", "B", "C")]),
        (["A", "B"], ["AB"]),
    ],
)
def test_malformed_input_is_rejected(nodes, edges):
    with pytest.raises((ValueError, TypeError)):
        find_cycle(nodes, edges)


def test_inputs_are_not_mutated_and_single_pass_iterables_work():
    nodes = ["A", "B", "C"]
    edges = [("A", "B"), ("B", "C")]
    candidates = [("C", "A")]
    snapshot = (list(nodes), list(edges), list(candidates))
    result = check_candidates(iter(nodes), (e for e in edges), iter(candidates))
    assert result.cycle == ("C", "A", "B", "C")
    assert (nodes, edges, candidates) == snapshot


def test_result_is_immutable():
    result = check_candidates(["A"], [], [("A", "A")])
    with pytest.raises(AttributeError):
        result.ok = True  # type: ignore[misc]


# ---------- 随机图：与参考实现对拍 ----------


@pytest.mark.parametrize("seed", range(40))
def test_random_graphs_agree_with_reference(seed):
    rng = random.Random(seed)
    size = rng.randint(1, 9)
    nodes = [f"n{i}" for i in range(size)]
    # 既有边只取某个随机拓扑序上的前向边，保证既有图无环
    order = nodes[:]
    rng.shuffle(order)
    existing = {
        (order[i], order[j]) for i in range(size) for j in range(i + 1, size) if rng.random() < 0.3
    }
    candidates = {(rng.choice(nodes), rng.choice(nodes)) for _ in range(rng.randint(0, 3))}
    union = existing | candidates

    result = check_candidates(nodes, sorted(existing), sorted(candidates))
    assert result.ok is is_acyclic(set(nodes), union)
    if not result.ok:
        assert result.edge in candidates
        assert result.cycle[:2] == result.edge
        assert_closed_cycle_in(result.cycle, union)

    whole = find_cycle(nodes, sorted(union))
    assert (whole is None) is is_acyclic(set(nodes), union)
    if whole is not None:
        assert_closed_cycle_in(whole, union)
        assert whole[0] == min(whole)
