"""E09：向量候选分层（``docs/atomic-tasks.json`` E09；``docs/tasks.md`` 第八批 E09 验收）。

输入：同一课程、同一向量空间的实体向量与两条阈值；输出：自动合并 / 需裁决 / 保留三组。
验收：课程隔离（跨课程、跨向量空间混传拒绝）；阈值顺序非法拒绝；边界等号规则明确：
``相似度 ≥ auto_merge`` → 自动合并；``review ≤ 相似度 < auto_merge`` → 需裁决；``相似度 < review`` → 保留。
"""

import ast
import dataclasses
import itertools
import math
import random
from pathlib import Path

import pytest

from app.services.ai.embeddings import EmbeddedVector
from app.services.fusion.candidates import (
    CandidateTier,
    TierThresholds,
    VectorCandidate,
    VectorEntry,
    VectorIsolationError,
    VectorTiers,
    classify_similarity,
    cosine_similarity,
    tier_vector_candidates,
)

MODULE = Path(__file__).resolve().parents[2] / "src/backend/app/services/fusion/candidates.py"

SPACE = "fake/2"
COURSE = "course_a"
T = TierThresholds(auto_merge=0.9, review=0.6)


def vec(values, *, space=SPACE, model="fake", dimensions=None, text_hash="h"):
    values = tuple(values)
    return EmbeddedVector(
        values=values,
        model=model,
        dimensions=len(values) if dimensions is None else dimensions,
        space=space,
        text_hash=text_hash,
    )


def entry(entity_id, values, *, course_id=COURSE, **kwargs):
    return VectorEntry(entity_id=entity_id, course_id=course_id, vector=vec(values, **kwargs))


def run(entries, *, thresholds=T, course_id=COURSE, space=SPACE):
    return tier_vector_candidates(entries, course_id=course_id, space=space, thresholds=thresholds)


# ---------------------------------------------------------------- 阈值


class TestThresholds:
    def test_valid(self):
        t = TierThresholds(auto_merge=0.95, review=0.8)
        assert (t.auto_merge, t.review) == (0.95, 0.8)

    def test_ints_accepted_as_bounds(self):
        TierThresholds(auto_merge=1, review=0)

    @pytest.mark.parametrize(
        ("auto_merge", "review"),
        [
            (0.8, 0.8),  # 相等：裁决组为空区间，拒绝
            (0.7, 0.8),  # 顺序颠倒
            (0.0, 0.0),
        ],
    )
    def test_order_must_be_strict(self, auto_merge, review):
        with pytest.raises(ValueError, match="auto_merge"):
            TierThresholds(auto_merge=auto_merge, review=review)

    @pytest.mark.parametrize(
        ("auto_merge", "review"),
        [
            (1.0000001, 0.5),
            (0.9, -0.1),
            (2, 0.5),
            (0.9, -1),
        ],
    )
    def test_out_of_range(self, auto_merge, review):
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            TierThresholds(auto_merge=auto_merge, review=review)

    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
    def test_non_finite(self, bad):
        with pytest.raises(ValueError, match="finite"):
            TierThresholds(auto_merge=bad, review=0.5)
        with pytest.raises(ValueError, match="finite"):
            TierThresholds(auto_merge=0.9, review=bad)

    @pytest.mark.parametrize("bad", [True, False, "0.9", None, 1j])
    def test_type(self, bad):
        with pytest.raises(TypeError):
            TierThresholds(auto_merge=bad, review=0.1)
        with pytest.raises(TypeError):
            TierThresholds(auto_merge=0.9, review=bad)

    def test_required_keyword_no_defaults(self):
        with pytest.raises(TypeError):
            TierThresholds()  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            TierThresholds(0.9, 0.6)  # type: ignore[misc]

    def test_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            T.auto_merge = 0.5  # type: ignore[misc]

    def test_run_requires_thresholds_instance(self):
        with pytest.raises(TypeError):
            run([], thresholds=(0.9, 0.6))  # type: ignore[arg-type]


# ---------------------------------------------------------------- 边界等号


class TestClassifySimilarity:
    @pytest.mark.parametrize(
        ("similarity", "tier"),
        [
            (1.0, CandidateTier.AUTO_MERGE),
            (0.9, CandidateTier.AUTO_MERGE),  # 等于自动阈值 → 自动合并
            (math.nextafter(0.9, 0), CandidateTier.REVIEW),  # 紧贴其下 → 裁决
            (0.75, CandidateTier.REVIEW),
            (0.6, CandidateTier.REVIEW),  # 等于裁决阈值 → 裁决
            (math.nextafter(0.6, 0), CandidateTier.KEEP),  # 紧贴其下 → 保留
            (0.0, CandidateTier.KEEP),
            (-1.0, CandidateTier.KEEP),
        ],
    )
    def test_boundaries(self, similarity, tier):
        assert classify_similarity(similarity, T) is tier

    def test_auto_threshold_one_only_exact_one(self):
        t = TierThresholds(auto_merge=1.0, review=0.5)
        assert classify_similarity(1.0, t) is CandidateTier.AUTO_MERGE
        assert classify_similarity(math.nextafter(1.0, 0), t) is CandidateTier.REVIEW

    def test_review_threshold_zero(self):
        t = TierThresholds(auto_merge=0.5, review=0.0)
        assert classify_similarity(0.0, t) is CandidateTier.REVIEW
        assert classify_similarity(-0.0, t) is CandidateTier.REVIEW
        assert classify_similarity(math.nextafter(0.0, -1), t) is CandidateTier.KEEP

    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, 1.0000001, -1.0000001])
    def test_rejects_bad_similarity(self, bad):
        with pytest.raises(ValueError):
            classify_similarity(bad, T)

    @pytest.mark.parametrize("bad", [True, "0.9", None])
    def test_rejects_bad_similarity_type(self, bad):
        with pytest.raises(TypeError):
            classify_similarity(bad, T)

    def test_rejects_bad_thresholds_type(self):
        with pytest.raises(TypeError):
            classify_similarity(0.5, (0.9, 0.6))  # type: ignore[arg-type]

    def test_wire_values(self):
        assert [t.value for t in CandidateTier] == ["auto_merge", "review", "keep"]


# ---------------------------------------------------------------- 余弦


class TestCosine:
    def test_identical_is_exactly_one(self):
        v = vec((0.1, 0.2, 0.3))
        assert cosine_similarity(v, v) == 1.0
        w = vec((0.1, 0.2, 0.3), text_hash="other")
        assert cosine_similarity(v, w) == 1.0

    def test_identical_is_one_even_when_naive_float_math_is_not(self):
        # 朴素计算 fsum(x*x)/(norm*norm) 对 (0.1, 0.1) 得 0.9999999999999998
        v = vec((0.1, 0.1))
        assert cosine_similarity(v, v) == 1.0
        t = TierThresholds(auto_merge=1, review=0.5)
        out = run([entry("a", (0.1, 0.1)), entry("b", (0.1, 0.1))], thresholds=t)
        assert [p.tier for p in out.all_pairs()] == [CandidateTier.AUTO_MERGE]

    def test_parallel_scaled_clamped(self):
        s = cosine_similarity(vec((1.0, 3.0)), vec((3.0, 9.0)))
        assert -1.0 <= s <= 1.0
        assert s == pytest.approx(1.0)

    def test_orthogonal_and_opposite(self):
        assert cosine_similarity(vec((1.0, 0.0)), vec((0.0, 2.0))) == 0.0
        assert cosine_similarity(vec((1.0, 0.0)), vec((-3.0, 0.0))) == -1.0

    def test_symmetric(self):
        rng = random.Random(9)
        for _ in range(50):
            a = vec(rng.uniform(-1, 1) for _ in range(5))
            b = vec(rng.uniform(-1, 1) for _ in range(5))
            assert cosine_similarity(a, b) == cosine_similarity(b, a)
            assert -1.0 <= cosine_similarity(a, b) <= 1.0

    def test_zero_vector_rejected(self):
        with pytest.raises(ValueError, match="zero"):
            cosine_similarity(vec((0.0, 0.0)), vec((1.0, 0.0)))

    def test_space_mismatch_rejected(self):
        with pytest.raises(VectorIsolationError):
            cosine_similarity(vec((1.0, 0.0)), vec((1.0, 0.0), space="real/m/2"))

    def test_dimension_mismatch_rejected(self):
        with pytest.raises(ValueError):
            cosine_similarity(vec((1.0, 0.0)), vec((1.0, 0.0, 0.0)))

    @pytest.mark.parametrize("bad", [math.nan, math.inf])
    def test_non_finite_values_rejected(self, bad):
        with pytest.raises(ValueError, match="finite"):
            cosine_similarity(vec((bad, 1.0)), vec((1.0, 0.0)))

    def test_declared_dimensions_must_match_length(self):
        with pytest.raises(ValueError, match="dimensions"):
            cosine_similarity(vec((1.0, 0.0), dimensions=3), vec((1.0, 0.0), dimensions=3))

    def test_empty_vector_rejected(self):
        with pytest.raises(ValueError):
            cosine_similarity(vec(()), vec(()))

    def test_rejects_non_embedded_vector(self):
        with pytest.raises(TypeError):
            cosine_similarity((1.0, 0.0), vec((1.0, 0.0)))  # type: ignore[arg-type]

    def test_rejects_bool_values(self):
        with pytest.raises(ValueError):
            cosine_similarity(vec((True, 0.0)), vec((1.0, 0.0)))


# ---------------------------------------------------------------- 条目


class TestVectorEntry:
    @pytest.mark.parametrize("field_name", ["entity_id", "course_id"])
    def test_blank_ids(self, field_name):
        kwargs = {"entity_id": "kp1", "course_id": COURSE, "vector": vec((1.0, 0.0))}
        kwargs[field_name] = "  "
        with pytest.raises(ValueError):
            VectorEntry(**kwargs)
        kwargs[field_name] = 3
        with pytest.raises(TypeError):
            VectorEntry(**kwargs)

    def test_vector_type(self):
        with pytest.raises(TypeError):
            VectorEntry(entity_id="kp1", course_id=COURSE, vector=(1.0, 0.0))  # type: ignore[arg-type]

    def test_repr_hides_vector_values(self):
        e = entry("kp1", (0.123456, 0.654321))
        assert "0.123456" not in repr(e)


# ---------------------------------------------------------------- 课程与空间隔离


class TestIsolation:
    def test_mixed_courses_rejected(self):
        with pytest.raises(VectorIsolationError, match="course"):
            run([entry("a", (1.0, 0.0)), entry("b", (1.0, 0.0), course_id="course_b")])

    def test_single_foreign_course_rejected(self):
        with pytest.raises(VectorIsolationError, match="course"):
            run([entry("a", (1.0, 0.0), course_id="course_b")])

    def test_mixed_spaces_rejected(self):
        with pytest.raises(VectorIsolationError, match="space"):
            run([entry("a", (1.0, 0.0)), entry("b", (1.0, 0.0), space="real/m/2", model="m")])

    def test_single_foreign_space_rejected(self):
        with pytest.raises(VectorIsolationError, match="space"):
            run([entry("a", (1.0, 0.0), space="fake/3", dimensions=2)])

    def test_mixed_dimensions_in_same_label_rejected(self):
        with pytest.raises(ValueError):
            run([entry("a", (1.0, 0.0)), entry("b", (1.0, 0.0, 0.0), dimensions=3)])

    def test_isolation_error_is_value_error(self):
        assert issubclass(VectorIsolationError, ValueError)

    def test_rejection_is_all_or_nothing_even_if_foreign_is_last(self):
        entries = [entry(f"k{i}", (1.0, 0.0)) for i in range(5)]
        entries.append(entry("x", (1.0, 0.0), course_id="course_b"))
        with pytest.raises(VectorIsolationError):
            run(entries)

    def test_course_and_space_must_be_given(self):
        with pytest.raises(TypeError):
            tier_vector_candidates([], thresholds=T)  # type: ignore[call-arg]
        for bad in ("", "  "):
            with pytest.raises(ValueError):
                tier_vector_candidates([], course_id=bad, space=SPACE, thresholds=T)
            with pytest.raises(ValueError):
                tier_vector_candidates([], course_id=COURSE, space=bad, thresholds=T)
        with pytest.raises(TypeError):
            tier_vector_candidates([], course_id=1, space=SPACE, thresholds=T)  # type: ignore[arg-type]

    def test_identical_vectors_across_courses_never_pair(self):
        a = run([entry("a", (1.0, 0.0))])
        b = run([entry("b", (1.0, 0.0), course_id="course_b")], course_id="course_b")
        assert a.all_pairs() == () and b.all_pairs() == ()


# ---------------------------------------------------------------- 分层


class TestTiering:
    def test_empty_and_single(self):
        for entries in ([], [entry("a", (1.0, 0.0))]):
            out = run(entries)
            assert out == VectorTiers(course_id=COURSE, space=SPACE, thresholds=T)
            assert out.auto_merge == out.review == out.keep == ()

    def test_three_groups(self):
        anchor = VectorEntry(entity_id="a", course_id=COURSE, vector=vec((1.0, 0.0)))
        entries = [
            anchor,
            VectorEntry(entity_id="b", course_id=COURSE, vector=vec((1.0, 0.0))),  # 1.0
            VectorEntry(entity_id="c", course_id=COURSE, vector=vec((0.0, 1.0))),  # 0.0
        ]
        out = run(entries)
        assert [(p.left_id, p.right_id) for p in out.auto_merge] == [("a", "b")]
        assert out.review == ()
        assert [(p.left_id, p.right_id) for p in out.keep] == [("a", "c"), ("b", "c")]
        for p in out.auto_merge:
            assert p.tier is CandidateTier.AUTO_MERGE and p.similarity == 1.0

    def test_exact_boundary_values_via_vectors(self):
        # (1,0) 与 (0.6, 0.8)：余弦恰为 0.6 → 裁决；阈值 auto=0.8 时 (1,0) 与 (0.8,0.6) 恰为 0.8 → 自动
        t = TierThresholds(auto_merge=0.8, review=0.6)
        out = run(
            [entry("a", (1.0, 0.0)), entry("b", (0.6, 0.8)), entry("c", (0.8, 0.6))],
            thresholds=t,
        )
        sims = {(p.left_id, p.right_id): (p.similarity, p.tier) for p in out.all_pairs()}
        assert sims[("a", "b")] == (0.6, CandidateTier.REVIEW)
        assert sims[("a", "c")] == (0.8, CandidateTier.AUTO_MERGE)
        # b·c = 0.96
        assert sims[("b", "c")][1] is CandidateTier.AUTO_MERGE

    def test_partition_complete_and_disjoint(self):
        rng = random.Random(42)
        entries = [
            entry(f"kp{i:02d}", [rng.uniform(-1, 1) for _ in range(4)], space="fake/4")
            for i in range(15)
        ]
        out = run(entries, space="fake/4", thresholds=TierThresholds(auto_merge=0.7, review=0.2))
        pairs = [(p.left_id, p.right_id) for p in out.all_pairs()]
        assert len(pairs) == len(set(pairs)) == 15 * 14 // 2
        ids = sorted(e.entity_id for e in entries)
        assert set(pairs) == set(itertools.combinations(ids, 2))
        for group, tier in ((out.auto_merge, CandidateTier.AUTO_MERGE),
                            (out.review, CandidateTier.REVIEW),
                            (out.keep, CandidateTier.KEEP)):
            for p in group:
                assert p.tier is tier
                assert classify_similarity(p.similarity, out.thresholds) is tier
            assert [(p.left_id, p.right_id) for p in group] == sorted((p.left_id, p.right_id) for p in group)

    def test_order_independent(self):
        rng = random.Random(7)
        entries = [entry(f"e{i}", (rng.uniform(-1, 1), rng.uniform(-1, 1))) for i in range(10)]
        base = run(entries)
        for seed in range(5):
            shuffled = entries[:]
            random.Random(seed).shuffle(shuffled)
            assert run(shuffled) == base

    def test_left_id_sorts_first(self):
        out = run([entry("z", (1.0, 0.0)), entry("a", (1.0, 0.0))])
        (p,) = out.auto_merge
        assert (p.left_id, p.right_id) == ("a", "z")

    def test_duplicate_entity_id_rejected(self):
        with pytest.raises(ValueError, match="duplicate"):
            run([entry("a", (1.0, 0.0)), entry("a", (0.0, 1.0))])

    def test_non_entry_rejected(self):
        with pytest.raises(TypeError):
            run([("a", (1.0, 0.0))])  # type: ignore[list-item]

    def test_zero_vector_entry_rejected(self):
        with pytest.raises(ValueError, match="zero"):
            run([entry("a", (1.0, 0.0)), entry("b", (0.0, 0.0))])

    def test_accepts_generator(self):
        out = run(entry(i, (1.0, 0.0)) for i in ("a", "b"))
        assert len(out.auto_merge) == 1

    def test_does_not_mutate_input(self):
        entries = [entry("b", (1.0, 0.0)), entry("a", (0.0, 1.0))]
        snapshot = list(entries)
        run(entries)
        assert entries == snapshot

    def test_result_echoes_context(self):
        out = run([entry("a", (1.0, 0.0)), entry("b", (1.0, 0.0))])
        assert (out.course_id, out.space, out.thresholds) == (COURSE, SPACE, T)


class TestVectorCandidate:
    def test_ordering_enforced(self):
        with pytest.raises(ValueError):
            VectorCandidate(left_id="b", right_id="a", similarity=0.5, tier=CandidateTier.KEEP)
        with pytest.raises(ValueError):
            VectorCandidate(left_id="a", right_id="a", similarity=0.5, tier=CandidateTier.KEEP)

    def test_tier_type(self):
        with pytest.raises(TypeError):
            VectorCandidate(left_id="a", right_id="b", similarity=0.5, tier="keep")  # type: ignore[arg-type]

    def test_frozen(self):
        p = VectorCandidate(left_id="a", right_id="b", similarity=0.5, tier=CandidateTier.KEEP)
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.similarity = 0.9  # type: ignore[misc]


# ---------------------------------------------------------------- 纯函数约束


class TestPurity:
    def test_no_io_logging_or_model_imports(self):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        forbidden = {"logging", "os", "io", "pathlib", "socket", "httpx", "requests", "sqlite3",
                     "neo4j", "app.services.ai.client", "app.config"}
        assert not imported & forbidden, imported & forbidden
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert not names & {"open", "print"}

    def test_docstring_states_boundary_rule(self):
        doc = ast.get_docstring(ast.parse(MODULE.read_text(encoding="utf-8")))
        assert doc and "≥ auto_merge" in doc and "review ≤" in doc and "< review" in doc
