"""I04：四项评分与结构化理由（``specs/learning-path.md`` §1、§3、§4，LP-2/3/4/5/6/13/14/15）。

score(k) = w_u·u + w_i·i + w_c·c + w_e·e，按 u→i→c→e 依次求和；排序键 (-score, chapter_rank, kp_id)。
"""

import ast
import copy
import itertools
import math
import random
import re
from pathlib import Path

import pytest

from app.services.learning.eligible import (
    ProgressOutsideGraphError,
    build_prerequisite_graph,
    eligible_set,
)
from app.services.learning.ranking import (
    FACTOR_ORDER,
    CandidateMismatchError,
    Chapter,
    Factors,
    InvalidWeightsError,
    KnowledgePointAttributes,
    RankedCandidate,
    RankingIntegrityError,
    ReasonFacts,
    RecommendWeights,
    chapter_ranks,
    rank_candidates,
)

DEFAULT = RecommendWeights(0.35, 0.25, 0.20, 0.20)


def kp(kp_id, *, chapter=None, importance=None, difficulty=None, name=None):
    return KnowledgePointAttributes(
        kp_id=kp_id,
        name=name if name is not None else f"名称-{kp_id}",
        chapter_id=chapter,
        importance=importance,
        difficulty=difficulty,
    )


def rank(nodes, edges, mastered=(), *, attrs=None, chapters=(), weights=DEFAULT, candidates=None):
    graph = build_prerequisite_graph(nodes, edges)
    if candidates is None:
        candidates = eligible_set(graph, mastered)
    if attrs is None:
        attrs = [kp(n) for n in nodes]
    return rank_candidates(graph, candidates, mastered, attrs, chapters, weights)


def by_id(ranked):
    return {r.kp_id: r for r in ranked}


def brute_unlock_count(nodes, edges, mastered, k):
    """定义式：学完 k 后新增可学、且不是 k 本身的点数。"""
    graph = build_prerequisite_graph(nodes, edges)
    before = set(eligible_set(graph, mastered))
    after = set(eligible_set(graph, set(mastered) | {k}))
    return len(after - before - {k})


# ---------------------------------------------------------------- 解锁数（真实可解锁，不是出度）


def test_unlock_count_lp2_counts_only_immediately_unlocked():
    # LP-2：C 依赖 A、B；M={B} 时学完 A 解锁 C；M=∅ 时为 0
    nodes = ["A", "B", "C"]
    edges = [("A", "C"), ("B", "C")]
    assert by_id(rank(nodes, edges, {"B"}))["A"].unlock_count == 1
    ranked = by_id(rank(nodes, edges, set()))
    assert ranked["A"].unlock_count == 0
    assert ranked["B"].unlock_count == 0


def test_unlock_count_excludes_multi_hop_and_mastered_successors():
    # A→B→C、A→D(已越序掌握)：学完 A 只解锁 B；C 多跳不计；D 已掌握不计
    nodes = ["A", "B", "C", "D"]
    edges = [("A", "B"), ("B", "C"), ("A", "D")]
    ranked = by_id(rank(nodes, edges, {"D"}))
    assert ranked["A"].unlock_count == 1


def test_unlock_count_differs_from_out_degree():
    # A 出度 3，但 X、Y 还缺 P，只有 B 能被立即解锁
    nodes = ["A", "P", "B", "X", "Y"]
    edges = [("A", "B"), ("A", "X"), ("A", "Y"), ("P", "X"), ("P", "Y")]
    ranked = by_id(rank(nodes, edges, set()))
    assert ranked["A"].unlock_count == 1
    assert ranked["P"].unlock_count == 0
    assert ranked["A"].factors.unlock == 1.0


def test_unlock_count_with_out_of_order_mastery():
    # LP-7：C 越序掌握；学完 A 后 D（依赖 A、C）立即可学
    nodes = ["A", "B", "C", "D"]
    edges = [("A", "C"), ("B", "C"), ("A", "D"), ("C", "D")]
    ranked = by_id(rank(nodes, edges, {"C"}))
    assert set(ranked) == {"A", "B"}
    assert ranked["A"].unlock_count == 1  # D；C 已掌握不计
    assert ranked["B"].unlock_count == 0


@pytest.mark.parametrize("seed", range(30))
def test_unlock_count_matches_definition_on_random_dags(seed):
    rng = random.Random(seed)
    n = rng.randint(1, 12)
    nodes = [f"k{i:02d}" for i in range(n)]
    edges = [(nodes[a], nodes[b]) for a, b in itertools.combinations(range(n), 2) if rng.random() < 0.3]
    mastered = {x for x in nodes if rng.random() < 0.3}
    graph = build_prerequisite_graph(nodes, edges)
    candidates = eligible_set(graph, mastered)
    ranked = rank(nodes, edges, mastered)
    assert len(ranked) == len(candidates)
    top = max((brute_unlock_count(nodes, edges, mastered, k) for k in candidates), default=0)
    for r in ranked:
        expected = brute_unlock_count(nodes, edges, mastered, r.kp_id)
        assert r.unlock_count == expected
        assert r.factors.unlock == (expected / top if top else 0.0)
        for f in (r.factors.unlock, r.factors.importance, r.factors.chapter_order, r.factors.ease):
            assert 0.0 <= f <= 1.0
    # 返回列表中两个候选之间不可能有先修边（§3 末段）
    ids = {r.kp_id for r in ranked}
    assert not [e for e in edges if e[0] in ids and e[1] in ids]


# ---------------------------------------------------------------- 零分母


def test_all_unlock_zero_no_division_error_lp3():
    # LP-3：所有候选都不能立即解锁 → u=0；孤立点在候选中
    nodes = ["A", "B", "ISO", "C"]
    edges = [("A", "C"), ("B", "C")]
    ranked = rank(nodes, edges, set())
    assert {r.kp_id for r in ranked} == {"A", "B", "ISO"}
    for r in ranked:
        assert r.unlock_count == 0
        assert r.factors.unlock == 0.0


def test_single_node_graph_zero_centrality_lp4():
    ranked = rank(["A"], [], set())
    (r,) = ranked
    assert r.reason_facts.centrality == 0.0
    assert r.factors.unlock == 0.0
    assert r.factors.chapter_order == 0.0  # 无章节
    assert r.factors.importance == 0.5 * 0.5 + 0.5 * 0.0  # 缺 importance 取 0.5
    assert r.factors.ease == 0.5  # 缺 difficulty 取 0.5
    assert r.reason_facts.importance == 0.5
    assert r.reason_facts.difficulty == 0.5


def test_single_chapter_gives_chapter_order_one_lp4():
    chapters = [Chapter("ch1", None, 0, "第一章")]
    attrs = [kp("A", chapter="ch1"), kp("B")]
    ranked = by_id(rank(["A", "B"], [], set(), attrs=attrs, chapters=chapters))
    assert ranked["A"].factors.chapter_order == 1.0
    assert ranked["A"].reason_facts.chapter_rank == 0
    assert ranked["A"].reason_facts.chapter_name == "第一章"
    assert ranked["B"].factors.chapter_order == 0.0
    assert ranked["B"].reason_facts.chapter_id is None
    assert ranked["B"].reason_facts.chapter_rank is None
    assert ranked["B"].reason_facts.chapter_name is None


def test_no_chapters_at_all_gives_zero():
    ranked = rank(["A", "B"], [], set())
    assert all(r.factors.chapter_order == 0.0 for r in ranked)


def test_all_mastered_returns_empty():
    assert rank(["A", "B"], [("A", "B")], {"A", "B"}) == ()


# ---------------------------------------------------------------- 中心度（LP-14）


@pytest.mark.parametrize("n", [2, 3, 4, 5])
def test_star_centrality_lp14(n):
    nodes = ["hub"] + [f"leaf{i}" for i in range(n - 1)]
    edges = [("hub", leaf) for leaf in nodes[1:]]
    mastered = set()
    (hub,) = rank(nodes, edges, mastered)
    assert hub.reason_facts.centrality == 1.0
    # 叶子：掌握 hub 后成为候选
    ranked = rank(nodes, edges, {"hub"})
    for leaf in ranked:
        assert leaf.reason_facts.centrality == 1 / (n - 1)


def test_centrality_uses_whole_graph_not_mastered():
    nodes = ["A", "B", "C"]
    edges = [("A", "B"), ("A", "C")]
    (a,) = rank(nodes, edges, set())
    assert a.reason_facts.centrality == 1.0
    ranked = by_id(rank(nodes, edges, {"A"}))
    assert ranked["B"].reason_facts.centrality == 0.5


def test_duplicate_edges_do_not_inflate_centrality():
    ranked = rank(["A", "B"], [("A", "B"), ("A", "B")], set())
    assert ranked[0].reason_facts.centrality == 1.0


def test_importance_combines_attribute_and_centrality():
    attrs = [kp("A", importance=0.8), kp("B"), kp("C")]
    ranked = by_id(rank(["A", "B", "C"], [("A", "B")], set(), attrs=attrs))
    assert ranked["A"].factors.importance == 0.5 * 0.8 + 0.5 * (1 / 2)
    assert ranked["C"].factors.importance == 0.5 * 0.5 + 0.5 * 0.0


# ---------------------------------------------------------------- 章节顺序（LP-15）


def test_chapter_preorder_ranks_lp15():
    chapters = [
        Chapter("c2", None, 2, "第二章"),
        Chapter("c2.1", "c2", 1, "2.1"),
        Chapter("c1.1", "c1", 1, "1.1"),
        Chapter("c1", None, 1, "第一章"),
    ]
    assert chapter_ranks(chapters) == {"c1": 0, "c1.1": 1, "c2": 2, "c2.1": 3}
    attrs = [kp("A", chapter="c1"), kp("B", chapter="c1.1"), kp("C", chapter="c2"), kp("D", chapter="c2.1"), kp("E")]
    ranked = by_id(rank(list("ABCDE"), [], set(), attrs=attrs, chapters=chapters))
    assert ranked["A"].factors.chapter_order == 1.0
    assert ranked["B"].factors.chapter_order == 1 - 1 / 3
    assert ranked["C"].factors.chapter_order == 1 - 2 / 3
    assert ranked["D"].factors.chapter_order == 0.0
    assert ranked["E"].factors.chapter_order == 0.0


def test_chapter_siblings_tie_on_order_break_by_chapter_id():
    chapters = [Chapter("b", None, 0, "B"), Chapter("a", None, 0, "A"), Chapter("a0", "a", 0, "A0")]
    assert chapter_ranks(chapters) == {"a": 0, "a0": 1, "b": 2}


def test_chapter_count_includes_chapters_without_nodes():
    chapters = [Chapter("c1", None, 0, "一"), Chapter("c2", None, 1, "二"), Chapter("c3", None, 2, "三")]
    (a,) = rank(["A"], [], set(), attrs=[kp("A", chapter="c2")], chapters=chapters)
    assert a.factors.chapter_order == 0.5


# ---------------------------------------------------------------- 易学度


def test_ease_is_one_minus_difficulty():
    attrs = [kp("A", difficulty=0.25), kp("B", difficulty=0.0), kp("C", difficulty=1.0)]
    ranked = by_id(rank(list("ABC"), [], set(), attrs=attrs))
    assert ranked["A"].factors.ease == 0.75
    assert ranked["B"].factors.ease == 1.0
    assert ranked["C"].factors.ease == 0.0
    assert ranked["A"].reason_facts.difficulty == 0.25


# ---------------------------------------------------------------- 加权分量求和


@pytest.mark.parametrize(
    "weights",
    [DEFAULT, RecommendWeights(0.1, 0.2, 0.3, 0.4), RecommendWeights(0.7, 0.1, 0.1, 0.1), RecommendWeights(1, 0, 0, 0)],
)
def test_score_is_ordered_sum_of_weighted_components(weights):
    rng = random.Random(7)
    nodes = [f"k{i}" for i in range(10)]
    edges = [("k0", "k5"), ("k1", "k5"), ("k2", "k6"), ("k3", "k7"), ("k3", "k8")]
    chapters = [Chapter(f"ch{i}", None, i, f"章{i}") for i in range(3)]
    attrs = [
        kp(n, chapter=rng.choice([None, "ch0", "ch1", "ch2"]), importance=rng.random(), difficulty=rng.random())
        for n in nodes
    ]
    ranked = rank(nodes, edges, {"k1"}, attrs=attrs, chapters=chapters, weights=weights)
    assert ranked
    for r in ranked:
        f, w = r.factors, r.weighted
        assert w.unlock == weights.unlock * f.unlock
        assert w.importance == weights.importance * f.importance
        assert w.chapter_order == weights.chapter * f.chapter_order
        assert w.ease == weights.ease * f.ease
        assert r.score == ((w.unlock + w.importance) + w.chapter_order) + w.ease
        # 与 math.fsum 等其他求和方式不必相等，但必须逐位等于固定顺序
        assert r.score.hex() == (((w.unlock + w.importance) + w.chapter_order) + w.ease).hex()


def test_score_sum_uses_fixed_order_where_order_matters():
    # 0.1+0.2+0.3 与 0.3+0.2+0.1 在 double 下不同，确认实现按 u→i→c→e
    weights = RecommendWeights(0.1, 0.2, 0.3, 0.4)
    attrs = [kp("A", importance=1.0, difficulty=0.0), kp("B")]
    chapters = [Chapter("c", None, 0, "唯一章")]
    attrs[0] = kp("A", importance=1.0, difficulty=0.0, chapter="c")
    ranked = by_id(rank(["A", "B"], [("A", "B")], set(), attrs=attrs, chapters=chapters, weights=weights))
    a = ranked["A"]
    assert (a.factors.unlock, a.factors.importance, a.factors.chapter_order, a.factors.ease) == (1.0, 1.0, 1.0, 1.0)
    assert a.score == ((0.1 + 0.2) + 0.3) + 0.4
    assert a.score != 0.4 + 0.3 + 0.2 + 0.1


def test_factors_iterate_in_fixed_order():
    assert FACTOR_ORDER == ("unlock", "importance", "chapter_order", "ease")
    f = Factors(0.1, 0.2, 0.3, 0.4)
    assert tuple(f.as_dict()) == FACTOR_ORDER
    assert f.as_dict() == {"unlock": 0.1, "importance": 0.2, "chapter_order": 0.3, "ease": 0.4}


# ---------------------------------------------------------------- 权重


def test_weights_from_settings_sequence():
    assert RecommendWeights.from_sequence((0.35, 0.25, 0.20, 0.20)) == DEFAULT


@pytest.mark.parametrize(
    "values",
    [
        (0, 0, 0, 0),  # 全零
        (-0.1, 0.5, 0.3, 0.3),  # 负数
        (math.nan, 0.5, 0.25, 0.25),
        (math.inf, 0, 0, 0),
        (0.5, 0.5, 0.5, 0.5),  # 和偏离 1
        (0.25, 0.25, 0.25, 0.2499),
        (True, False, False, False),  # 布尔不是数值
        ("0.25", 0.25, 0.25, 0.25),
    ],
)
def test_invalid_weights_rejected_lp5(values):
    with pytest.raises(InvalidWeightsError):
        RecommendWeights(*values)


def test_weights_sequence_length_checked():
    with pytest.raises(InvalidWeightsError):
        RecommendWeights.from_sequence((0.5, 0.5, 0.0))


def test_weights_sum_tolerance_and_used_as_is():
    w = RecommendWeights(0.25, 0.25, 0.25, 0.25 + 5e-10)
    assert w.ease == 0.25 + 5e-10  # 原样使用，不再除以总和
    (a,) = rank(["A"], [], set(), attrs=[kp("A", difficulty=0.0)], weights=w)
    assert a.weighted.ease == 0.25 + 5e-10


def test_non_weights_object_rejected():
    graph = build_prerequisite_graph(["A"], [])
    with pytest.raises(TypeError):
        rank_candidates(graph, ("A",), set(), [kp("A")], [], (0.35, 0.25, 0.2, 0.2))


# ---------------------------------------------------------------- 排序与同分（LP-6）


def test_sorted_by_score_descending():
    attrs = [kp("A", importance=0.1), kp("B", importance=0.9), kp("C", importance=0.5)]
    ranked = rank(list("ABC"), [], set(), attrs=attrs)
    assert [r.kp_id for r in ranked] == ["B", "C", "A"]
    assert ranked[0].score > ranked[1].score > ranked[2].score


def test_tie_broken_by_chapter_rank_then_none_last():
    chapters = [Chapter("c1", None, 0, "一"), Chapter("c2", None, 1, "二")]
    # 用 chapter 权重 0，让章节不影响分数，只作平局键
    w = RecommendWeights(0.5, 0.5, 0, 0)
    attrs = [kp("A"), kp("B", chapter="c2"), kp("C", chapter="c1")]
    ranked = rank(list("ABC"), [], set(), attrs=attrs, chapters=chapters, weights=w)
    assert len({r.score for r in ranked}) == 1
    assert [r.kp_id for r in ranked] == ["C", "B", "A"]


def test_tie_same_chapter_broken_by_kp_id_utf8_bytes():
    ids = ["中", "b", "B", "a", "é"]
    ranked = rank(ids, [], set())
    assert [r.kp_id for r in ranked] == sorted(ids, key=lambda s: s.encode("utf-8"))
    assert [r.kp_id for r in ranked] == ["B", "a", "b", "é", "中"]


def test_tiny_score_difference_is_not_a_tie():
    # A 的分数只比 C 大 1 ulp 级别，但章节更靠后；未舍入比较须让 A 在前
    chapters = [Chapter("c1", None, 0, "一"), Chapter("c2", None, 1, "二")]
    w = RecommendWeights(0, 1, 0, 0)
    imp_c = 0.5
    imp_a = math.nextafter(0.5, 1.0)  # 仅大一个 ulp
    attrs = [kp("A", chapter="c2", importance=imp_a), kp("C", chapter="c1", importance=imp_c)]
    ranked = rank(["A", "C"], [], set(), attrs=attrs, chapters=chapters, weights=w)
    assert ranked[0].score > ranked[1].score
    assert round(ranked[0].score, 12) == round(ranked[1].score, 12)
    assert [r.kp_id for r in ranked] == ["A", "C"]


def test_ranking_independent_of_input_order():
    nodes = [f"k{i}" for i in range(8)]
    edges = [("k0", "k4"), ("k1", "k4"), ("k2", "k5")]
    attrs = [kp(n) for n in nodes]
    base = rank(nodes, edges, set(), attrs=attrs)
    rng = random.Random(3)
    for _ in range(5):
        n2, e2, a2 = nodes[:], edges[:], attrs[:]
        rng.shuffle(n2), rng.shuffle(e2), rng.shuffle(a2)
        graph = build_prerequisite_graph(n2, e2)
        cands = list(eligible_set(graph, set()))
        rng.shuffle(cands)
        assert rank_candidates(graph, cands, set(), a2, (), DEFAULT) == base


def test_full_sort_before_truncation_lp6():
    # 截断归 I05；本函数返回全部候选，前 1 条即全量排序后的第一条
    attrs = [kp(n, importance=v) for n, v in zip("ABCD", [0.2, 0.9, 0.4, 0.9])]
    ranked = rank(list("ABCD"), [], set(), attrs=attrs)
    assert len(ranked) == 4
    assert [r.kp_id for r in ranked[:1]] == ["B"]
    assert [r.kp_id for r in ranked] == ["B", "D", "C", "A"]


def test_unlock_normalized_over_all_candidates():
    # u 的分母按全部候选算：A 解锁 2 个 → u=1；B 解锁 1 个 → u=0.5
    nodes = ["A", "B", "a1", "a2", "b1"]
    edges = [("A", "a1"), ("A", "a2"), ("B", "b1")]
    ranked = by_id(rank(nodes, edges, set()))
    assert ranked["A"].unlock_count == 2 and ranked["A"].factors.unlock == 1.0
    assert ranked["B"].unlock_count == 1 and ranked["B"].factors.unlock == 0.5


# ---------------------------------------------------------------- 理由（§4，LP-13）


def test_reason_unlock_two_lp13():
    nodes = ["A", "a1", "a2"]
    edges = [("A", "a1"), ("A", "a2")]
    w = RecommendWeights(1, 0, 0, 0)
    (a,) = rank(nodes, edges, set(), weights=w)
    assert a.unlock_count == 2 and a.factors.unlock == 1.0
    assert a.reason_facts.primary_factor == "unlock"
    assert a.reason == "完成该点可立即解锁 2 个知识点（解锁度 1.0000）"
    assert "解锁 1 个" not in a.reason


def test_reason_importance_primary():
    attrs = [kp("A", importance=1.0), kp("B")]
    (a,) = rank(["A", "B"], [("A", "B")], set(), attrs=attrs, weights=RecommendWeights(0, 1, 0, 0))
    assert a.reason_facts.primary_factor == "importance"
    assert a.reason == "该点的主要推荐依据是重要度（重要度 1.0000，中心度 1.0000）"


def test_reason_chapter_primary_states_actual_order():
    chapters = [Chapter("c1", None, 0, "绪论"), Chapter("c2", None, 1, "线性表"), Chapter("c3", None, 2, "树")]
    attrs = [kp("A", chapter="c2")]
    (a,) = rank(["A"], [], set(), attrs=attrs, chapters=chapters, weights=RecommendWeights(0, 0, 1, 0))
    assert a.reason_facts.primary_factor == "chapter_order"
    assert a.reason_facts.chapter_rank == 1
    assert a.reason == "该点所在章节「线性表」在课程章节顺序中排第 2 位（共 3 个章节，章节顺序 0.5000）"


def test_reason_ease_primary():
    attrs = [kp("A", difficulty=0.2)]
    (a,) = rank(["A"], [], set(), attrs=attrs, weights=RecommendWeights(0, 0, 0, 1))
    assert a.reason_facts.primary_factor == "ease"
    assert a.reason == "该点的主要推荐依据是易学度（难度 0.2000，易学度 0.8000）"


def test_reason_all_zero():
    # 只给解锁度权重且无可解锁后继 → 四个加权分量全 0
    (a,) = rank(["A"], [], set(), weights=RecommendWeights(1, 0, 0, 0))
    assert a.score == 0.0
    assert a.reason == "当前无可直接解锁的后继；此点的直接前置均已掌握"
    assert a.reason_facts.primary_factor == "unlock"  # 同贡献按 unlock→importance→chapter→ease


def test_reason_primary_tie_order():
    # importance 与 ease 加权贡献相等 → 取 importance
    # N=1：centrality 0，imp=1 → i=0.5；difficulty=0.5 → e=0.5
    attrs = [kp("A", importance=1.0, difficulty=0.5)]
    (a,) = rank(["A"], [], set(), attrs=attrs, weights=RecommendWeights(0, 0.5, 0, 0.5))
    assert a.weighted.importance == a.weighted.ease
    assert a.reason_facts.primary_factor == "importance"


@pytest.mark.parametrize("seed", range(15))
def test_reason_never_claims_unlock_when_count_zero(seed):
    rng = random.Random(100 + seed)
    n = rng.randint(1, 9)
    nodes = [f"n{i}" for i in range(n)]
    edges = [(nodes[a], nodes[b]) for a, b in itertools.combinations(range(n), 2) if rng.random() < 0.35]
    ws = [rng.random() for _ in range(4)]
    ws[3] = 1 - (ws[0] + ws[1] + ws[2]) if sum(ws[:3]) < 1 else 0.0
    if ws[3] == 0.0:
        ws = [0.35, 0.25, 0.2, 0.2]
    attrs = [kp(x, importance=rng.random(), difficulty=rng.random()) for x in nodes]
    for r in rank(nodes, edges, set(), attrs=attrs, weights=RecommendWeights(*ws)):
        if r.unlock_count == 0:
            assert not re.search(r"可立即解锁 \d+ 个", r.reason)
        else:
            m = re.search(r"可立即解锁 (\d+) 个", r.reason)
            if m:
                assert int(m.group(1)) == r.unlock_count
        # primary 是加权贡献最大者，同贡献取 FACTOR_ORDER 中最早者
        values = r.weighted.as_dict()
        best = max(values.values())
        assert r.reason_facts.primary_factor == next(k for k in FACTOR_ORDER if values[k] == best)


def test_reason_is_deterministic_and_facts_match_factors():
    attrs = [kp("A", importance=0.3, difficulty=0.6, chapter="c")]
    chapters = [Chapter("c", None, 0, "唯一")]
    r1 = rank(["A"], [], set(), attrs=attrs, chapters=chapters)
    r2 = rank(["A"], [], set(), attrs=attrs, chapters=chapters)
    assert r1 == r2
    (a,) = r1
    assert isinstance(a, RankedCandidate) and isinstance(a.reason_facts, ReasonFacts)
    assert a.name == "名称-A"
    assert a.reason_facts.importance == 0.3
    assert a.reason_facts.difficulty == 0.6
    assert a.factors.ease == 1 - 0.6


# ---------------------------------------------------------------- 失败路径：完整性与调用方错误


def test_invalid_number_attributes_are_integrity_errors():
    for bad in (1.5, -0.1, math.nan, math.inf, True, "0.5"):
        with pytest.raises(RankingIntegrityError) as err:
            rank(["A"], [], set(), attrs=[kp("A", importance=bad)])
        assert err.value.kind == "invalid_number"
        with pytest.raises(RankingIntegrityError):
            rank(["A"], [], set(), attrs=[kp("A", difficulty=bad)])


def test_attributes_must_cover_exactly_v():
    with pytest.raises(RankingIntegrityError) as err:
        rank(["A", "B"], [], set(), attrs=[kp("A")])
    assert err.value.kind == "attributes_mismatch"
    with pytest.raises(RankingIntegrityError) as err:
        rank(["A"], [], set(), attrs=[kp("A"), kp("X")])
    assert err.value.kind == "attributes_mismatch"
    with pytest.raises(RankingIntegrityError) as err:
        rank(["A"], [], set(), attrs=[kp("A"), kp("A")])
    assert err.value.kind == "attributes_mismatch"


def test_malformed_attribute_fields_are_integrity_errors():
    with pytest.raises(RankingIntegrityError) as err:
        rank(["A"], [], set(), attrs=[kp("A", chapter="")])
    assert err.value.kind == "malformed"
    with pytest.raises(RankingIntegrityError) as err:
        rank(["A"], [], set(), attrs=[KnowledgePointAttributes("A", None)])  # type: ignore[arg-type]
    assert err.value.kind == "malformed"


def test_unknown_chapter_reference_is_integrity_error():
    with pytest.raises(RankingIntegrityError) as err:
        rank(["A"], [], set(), attrs=[kp("A", chapter="missing")], chapters=[Chapter("c", None, 0, "c")])
    assert err.value.kind == "unknown_chapter"


@pytest.mark.parametrize(
    ("chapters", "kind"),
    [
        ([Chapter("c", "nope", 0, "c")], "chapter_tree"),  # 父章节不存在
        ([Chapter("c", "d", 0, "c"), Chapter("d", "c", 0, "d")], "chapter_tree"),  # 成环
        ([Chapter("c", "c", 0, "c")], "chapter_tree"),  # 自指
        ([Chapter("c", None, 0, "c"), Chapter("c", None, 1, "c2")], "chapter_tree"),  # 重复 ID
        ([Chapter("c", None, -1, "c")], "chapter_tree"),  # 非法 order
        ([Chapter("c", None, 1.5, "c")], "chapter_tree"),
        ([Chapter("", None, 0, "c")], "chapter_tree"),
    ],
)
def test_broken_chapter_tree_is_integrity_error(chapters, kind):
    with pytest.raises(RankingIntegrityError) as err:
        rank(["A"], [], set(), chapters=chapters)
    assert err.value.kind == kind


def test_candidates_must_equal_eligible_set():
    nodes = ["A", "B", "C"]
    edges = [("A", "B")]
    graph = build_prerequisite_graph(nodes, edges)
    attrs = [kp(n) for n in nodes]
    for bad in (("A",), ("A", "B", "C"), ("A", "C", "C"), ("A", "C", "Z")):
        with pytest.raises(CandidateMismatchError):
            rank_candidates(graph, bad, set(), attrs, (), DEFAULT)


def test_mastered_outside_graph_rejected():
    graph = build_prerequisite_graph(["A"], [])
    with pytest.raises(ProgressOutsideGraphError):
        rank_candidates(graph, ("A",), {"X"}, [kp("A")], (), DEFAULT)


def test_graph_must_be_prerequisite_graph():
    with pytest.raises(TypeError):
        rank_candidates(object(), (), set(), [], (), DEFAULT)


# ---------------------------------------------------------------- 不修改输入、无 I/O


def test_inputs_not_modified():
    nodes = ["A", "B", "C", "D"]
    edges = [("A", "C"), ("B", "C"), ("C", "D")]
    graph = build_prerequisite_graph(nodes, edges)
    mastered = {"B"}
    candidates = list(eligible_set(graph, mastered))
    attrs = [kp("A", chapter="c1", importance=0.4), kp("B"), kp("C", difficulty=0.1), kp("D")]
    chapters = [Chapter("c1", None, 0, "一")]
    snapshot = copy.deepcopy((mastered, candidates, attrs, chapters))
    preds = dict(graph.predecessors)
    rank_candidates(graph, candidates, mastered, attrs, chapters, DEFAULT)
    assert (mastered, candidates, attrs, chapters) == snapshot
    assert dict(graph.predecessors) == preds


def test_accepts_single_pass_iterables():
    graph = build_prerequisite_graph(["A", "B"], [("A", "B")])
    ranked = rank_candidates(
        graph, iter(["A"]), iter([]), iter([kp("A"), kp("B")]), iter([]), DEFAULT
    )
    assert [r.kp_id for r in ranked] == ["A"]


def test_results_are_immutable():
    (a,) = rank(["A"], [], set())
    with pytest.raises(AttributeError):
        a.score = 1.0  # type: ignore[misc]


def test_module_has_no_io_llm_or_database_imports():
    source = Path(__file__).resolve().parents[2] / "src/backend/app/services/learning/ranking.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    forbidden = (
        "sqlite3", "neo4j", "app.repositories", "app.api", "app.services.ai", "fastapi",
        "httpx", "os", "time", "datetime", "random", "app.config",
    )
    assert not [m for m in imported if any(m == f or m.startswith(f + ".") for f in forbidden)]
