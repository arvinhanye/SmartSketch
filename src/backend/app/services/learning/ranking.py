"""Pure four-factor scoring, ordering and rule-based reasons for next-step recommendation (I04).

Implements ``specs/learning-path.md`` §3 and §4 (ADR-014 decision 1, revision 1
decisions 5 and 6). No I/O, no database, no model call, no clock.

``rank_candidates(graph, candidates, mastered, attributes, chapters, weights)`` takes

- ``graph``: the validated ``PrerequisiteGraph`` of the bound version (I03
  ``build_prerequisite_graph``);
- ``candidates``: the I03 ``eligible_set(graph, mastered)`` output. It must be *all*
  candidates (the unlock denominator is taken over every candidate, §3); any other
  set, or a duplicate, raises ``CandidateMismatchError``;
- ``mastered``: the projected mastered set ``M ⊆ V`` (same contract as I03;
  ``ProgressOutsideGraphError`` otherwise);
- ``attributes``: one ``KnowledgePointAttributes`` per node of ``V``, exactly;
- ``chapters``: every ``Chapter`` of the bound version (may be empty);
- ``weights``: a validated ``RecommendWeights`` (build it from
  ``Settings.recommend_weights``); used as-is, never re-normalised.

and returns every candidate as a ``RankedCandidate``, sorted by
``(-score, chapter_rank, kp_id)``: score descending on the *unrounded* double, then
chapter rank ascending with "no chapter" last, then ``kp_id`` UTF-8 bytes ascending.
Truncation to ``limit`` and ``total_eligible`` belong to the caller (I05); the result
is empty exactly when ``M = V``.

Factors (each in ``[0, 1]``):

- ``unlock_count(k) = |{v ∈ V \\ M : (k, v) ∈ E and Pred(v) \\ M = {k}}|`` — successors
  that become eligible immediately after ``k`` is learned (not out-degree);
  ``u = unlock_count / max over candidates``, ``0`` when that max is ``0``.
- ``i = 0.5 × importance + 0.5 × centrality``, ``centrality = (in + out) / (N − 1)``
  on the de-duplicated edges of the whole version, ``0`` when ``N ≤ 1``.
- ``c = 1 − r / (C − 1)`` with ``r`` the pre-order rank of the node's chapter
  (roots, then children recursively, siblings by ``(order, chapter_id)``); ``1`` when
  ``C = 1``; ``0`` without a chapter.
- ``e = 1 − difficulty``.

Missing ``importance`` / ``difficulty`` use the neutral 0.5. Weighted components are
``w × x`` and ``score = ((w_u·u + w_i·i) + w_c·c) + w_e·e`` in that fixed order, so the
four weighted values rebuild ``score`` bit for bit.

Data defects of the committed version (attributes not covering ``V`` exactly, invalid
numbers, unknown chapter references, broken chapter tree) raise
``RankingIntegrityError``; like I03's ``GraphIntegrityError`` its ``ids`` are for
server logs only, and I05 maps it to the 500 integrity response (ADR-017 decision 4).
"""

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from app.services.learning.eligible import PrerequisiteGraph, eligible_set

FactorName = Literal["unlock", "importance", "chapter_order", "ease"]
FACTOR_ORDER: tuple[FactorName, ...] = ("unlock", "importance", "chapter_order", "ease")

NEUTRAL_VALUE = 0.5
WEIGHT_SUM_TOLERANCE = 1e-9

RankingIntegrityKind = Literal[
    "malformed", "attributes_mismatch", "invalid_number", "unknown_chapter", "chapter_tree"
]


class RankingIntegrityError(ValueError):
    """Node attributes or chapters of the committed version are invalid; ``ids`` for logs only."""

    def __init__(self, kind: RankingIntegrityKind, ids: tuple[str, ...] = (), detail: str = "") -> None:
        self.kind = kind
        self.ids = ids
        message = f"committed graph ranking data integrity error: {kind}"
        if detail:
            message += f" ({detail})"
        if ids:
            message += f": {list(ids)!r}"
        super().__init__(message)


class CandidateMismatchError(ValueError):
    """``candidates`` is not exactly ``eligible_set(graph, mastered)``; a caller defect."""


class InvalidWeightsError(ValueError):
    """Weights violate §1: finite, non-negative, sum within ``1 ± 1e-9``, at least one positive."""


@dataclass(frozen=True)
class RecommendWeights:
    """Validated weights in the fixed order unlock, importance, chapter, ease."""

    unlock: float
    importance: float
    chapter: float
    ease: float

    def __post_init__(self) -> None:
        values = (self.unlock, self.importance, self.chapter, self.ease)
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise InvalidWeightsError("each weight must be a real number")
            if not math.isfinite(value) or value < 0:
                raise InvalidWeightsError("each weight must be finite and non-negative")
        if not any(value > 0 for value in values):
            raise InvalidWeightsError("at least one weight must be positive")
        # same test as app.config._check_rules, so startup and this guard agree bit for bit
        if not math.isclose(sum(values), 1, rel_tol=0, abs_tol=WEIGHT_SUM_TOLERANCE):
            raise InvalidWeightsError("weights must sum to 1 within 1e-9")
        for name, value in zip(("unlock", "importance", "chapter", "ease"), values):
            object.__setattr__(self, name, float(value))

    @classmethod
    def from_sequence(cls, values: Sequence[float]) -> "RecommendWeights":
        """Build from ``Settings.recommend_weights`` (unlock, importance, chapter, ease)."""
        if len(values) != 4:
            raise InvalidWeightsError("exactly four weights are required")
        return cls(*values)


@dataclass(frozen=True)
class KnowledgePointAttributes:
    """Scoring inputs of one node of the bound version; ``None`` means the attribute is absent."""

    kp_id: str
    name: str
    chapter_id: str | None = None
    importance: float | None = None
    difficulty: float | None = None


@dataclass(frozen=True)
class Chapter:
    """One chapter of the bound version; ``parent_id=None`` for a root."""

    chapter_id: str
    parent_id: str | None
    order: int
    name: str


@dataclass(frozen=True)
class Factors:
    """Four values in the fixed summation order u → i → c → e."""

    unlock: float
    importance: float
    chapter_order: float
    ease: float

    def as_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in FACTOR_ORDER}


@dataclass(frozen=True)
class ReasonFacts:
    """Structured facts behind ``reason`` (contract ``RecommendReasonFacts``)."""

    primary_factor: FactorName
    chapter_id: str | None
    chapter_name: str | None
    chapter_rank: int | None
    importance: float
    centrality: float
    difficulty: float


@dataclass(frozen=True)
class RankedCandidate:
    """One scored candidate; ``graph_version`` is added by the caller (I05)."""

    kp_id: str
    name: str
    unlock_count: int
    factors: Factors
    weighted: Factors
    score: float
    reason: str
    reason_facts: ReasonFacts


def chapter_ranks(chapters: Iterable[Chapter]) -> dict[str, int]:
    """Pre-order ranks ``0..C−1`` of the chapter forest; siblings by ``(order, chapter_id)``.

    Raises ``RankingIntegrityError(kind="chapter_tree")`` for malformed chapters,
    duplicate IDs, a missing parent or a cycle.
    """
    return {chapter_id: rank for chapter_id, (rank, _name) in _chapter_index(chapters).items()}


def rank_candidates(
    graph: PrerequisiteGraph,
    candidates: Iterable[str],
    mastered: Iterable[str],
    attributes: Iterable[KnowledgePointAttributes],
    chapters: Iterable[Chapter],
    weights: RecommendWeights,
) -> tuple[RankedCandidate, ...]:
    """Score and order every candidate (see module doc)."""
    if not isinstance(graph, PrerequisiteGraph):
        raise TypeError("graph must be a PrerequisiteGraph from build_prerequisite_graph")
    if not isinstance(weights, RecommendWeights):
        raise TypeError("weights must be a RecommendWeights")

    owned = frozenset(mastered)
    expected = eligible_set(graph, owned)  # also rejects mastered IDs outside V (I03)
    candidate_list = list(candidates)
    if len(candidate_list) != len(set(candidate_list)) or set(candidate_list) != set(expected):
        raise CandidateMismatchError("candidates must be exactly eligible_set(graph, mastered)")

    attrs = _checked_attributes(graph, attributes)
    index = _chapter_index(chapters)
    unknown = {a.kp_id for a in attrs.values() if a.chapter_id is not None and a.chapter_id not in index}
    if unknown:
        raise RankingIntegrityError("unknown_chapter", _utf8_sorted(unknown))
    chapter_count = len(index)

    successors: dict[str, list[str]] = {node: [] for node in graph.nodes}
    for source, target in graph.edges:
        successors[source].append(target)
    n = len(graph.nodes)

    unlock_counts = {k: _unlock_count(graph, successors, owned, k) for k in expected}
    max_unlock = max(unlock_counts.values(), default=0)

    ranked: list[RankedCandidate] = []
    for k in expected:
        attr = attrs[k]
        importance = NEUTRAL_VALUE if attr.importance is None else float(attr.importance)
        difficulty = NEUTRAL_VALUE if attr.difficulty is None else float(attr.difficulty)
        degree = len(graph.predecessors[k]) + len(successors[k])
        centrality = degree / (n - 1) if n > 1 else 0.0

        count = unlock_counts[k]
        u = count / max_unlock if max_unlock > 0 else 0.0
        i = 0.5 * importance + 0.5 * centrality
        if attr.chapter_id is None:
            rank, chapter_name = None, None
            c = 0.0
        else:
            rank, chapter_name = index[attr.chapter_id]
            c = 1.0 - rank / (chapter_count - 1) if chapter_count > 1 else 1.0
        e = 1.0 - difficulty

        factors = Factors(u, i, c, e)
        weighted = Factors(
            weights.unlock * u,
            weights.importance * i,
            weights.chapter * c,
            weights.ease * e,
        )
        score = ((weighted.unlock + weighted.importance) + weighted.chapter_order) + weighted.ease
        facts = ReasonFacts(
            primary_factor=_primary_factor(weighted),
            chapter_id=attr.chapter_id,
            chapter_name=chapter_name,
            chapter_rank=rank,
            importance=importance,
            centrality=centrality,
            difficulty=difficulty,
        )
        ranked.append(
            RankedCandidate(
                kp_id=k,
                name=attr.name,
                unlock_count=count,
                factors=factors,
                weighted=weighted,
                score=score,
                reason=_reason(facts, factors, weighted, count, chapter_count),
                reason_facts=facts,
            )
        )

    ranked.sort(key=_sort_key)
    return tuple(ranked)


def _unlock_count(
    graph: PrerequisiteGraph, successors: Mapping[str, list[str]], mastered: frozenset[str], k: str
) -> int:
    """Direct successors ``v ∉ M`` whose only unmastered prerequisite is ``k``."""
    count = 0
    for v in set(successors[k]):
        if v in mastered:
            continue
        if all(p == k or p in mastered for p in graph.predecessors[v]):
            count += 1
    return count


def _primary_factor(weighted: Factors) -> FactorName:
    """Largest weighted contribution; ties go to the earliest of ``FACTOR_ORDER``."""
    best: FactorName = FACTOR_ORDER[0]
    for name in FACTOR_ORDER[1:]:
        if getattr(weighted, name) > getattr(weighted, best):
            best = name
    return best


def _reason(
    facts: ReasonFacts, factors: Factors, weighted: Factors, unlock_count: int, chapter_count: int
) -> str:
    """One sentence from structured facts only (§4); never calls a model."""
    if all(value == 0 for value in weighted.as_dict().values()):
        return "当前无可直接解锁的后继；此点的直接前置均已掌握"
    primary = facts.primary_factor
    if primary == "unlock":
        # weighted.unlock > 0 here, hence unlock_count > 0
        return f"完成该点可立即解锁 {unlock_count} 个知识点（解锁度 {factors.unlock:.4f}）"
    if primary == "importance":
        return (
            f"该点的主要推荐依据是重要度（重要度 {facts.importance:.4f}，"
            f"中心度 {facts.centrality:.4f}）"
        )
    if primary == "chapter_order":
        # weighted.chapter_order > 0 here, hence the node has a chapter; the rank is the
        # pre-order position over all chapters (sub-chapters included), 1-based in the text
        position = (facts.chapter_rank or 0) + 1
        return (
            f"该点所在章节「{facts.chapter_name}」在课程章节顺序中排第 {position} 位"
            f"（共 {chapter_count} 个章节，章节顺序 {factors.chapter_order:.4f}）"
        )
    return f"该点的主要推荐依据是易学度（难度 {facts.difficulty:.4f}，易学度 {factors.ease:.4f}）"


def _sort_key(item: RankedCandidate) -> tuple[float, int, int, bytes]:
    rank = item.reason_facts.chapter_rank
    # no chapter sorts as rank +∞
    missing = rank is None
    return (-item.score, int(missing), 0 if rank is None else rank, item.kp_id.encode("utf-8"))


def _checked_attributes(
    graph: PrerequisiteGraph, attributes: Iterable[KnowledgePointAttributes]
) -> dict[str, KnowledgePointAttributes]:
    attrs: dict[str, KnowledgePointAttributes] = {}
    duplicates: set[str] = set()
    for attr in attributes:
        if not isinstance(attr, KnowledgePointAttributes):
            raise RankingIntegrityError(
                "attributes_mismatch", detail="attributes must be KnowledgePointAttributes"
            )
        if attr.kp_id in attrs:
            duplicates.add(attr.kp_id)
        attrs[attr.kp_id] = attr
    if duplicates:
        raise RankingIntegrityError("attributes_mismatch", _utf8_sorted(duplicates), "duplicate kp_id")
    if set(attrs) != graph.nodes:
        diff = set(attrs) ^ graph.nodes
        raise RankingIntegrityError(
            "attributes_mismatch", _utf8_sorted(str(x) for x in diff), "attributes must cover V exactly"
        )
    for attr in attrs.values():
        if not isinstance(attr.name, str):
            raise RankingIntegrityError("malformed", (attr.kp_id,), "name must be a string")
        if attr.chapter_id is not None and (not isinstance(attr.chapter_id, str) or not attr.chapter_id):
            raise RankingIntegrityError("malformed", (attr.kp_id,), "chapter_id must be a non-empty string")
        for label, value in (("importance", attr.importance), ("difficulty", attr.difficulty)):
            if value is None:
                continue
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise RankingIntegrityError("invalid_number", (attr.kp_id,), f"{label} must be in [0, 1]")
    return attrs


def _chapter_index(chapters: Iterable[Chapter]) -> dict[str, tuple[int, str]]:
    """``chapter_id → (pre-order rank, name)``; see ``chapter_ranks``."""
    by_id: dict[str, Chapter] = {}
    for chapter in chapters:
        if not isinstance(chapter, Chapter):
            raise RankingIntegrityError("chapter_tree", detail="chapters must be Chapter objects")
        _check_chapter(chapter)
        if chapter.chapter_id in by_id:
            raise RankingIntegrityError("chapter_tree", (chapter.chapter_id,), "duplicate chapter")
        by_id[chapter.chapter_id] = chapter

    children: dict[str | None, list[Chapter]] = {}
    missing: set[str] = set()
    for chapter in by_id.values():
        if chapter.parent_id is not None and chapter.parent_id not in by_id:
            missing.add(chapter.chapter_id)
        children.setdefault(chapter.parent_id, []).append(chapter)
    if missing:
        raise RankingIntegrityError("chapter_tree", _utf8_sorted(missing), "parent chapter not found")
    for siblings in children.values():
        siblings.sort(key=lambda c: (c.order, c.chapter_id.encode("utf-8")))

    index: dict[str, tuple[int, str]] = {}
    stack = list(reversed(children.get(None, [])))
    while stack:
        chapter = stack.pop()
        index[chapter.chapter_id] = (len(index), chapter.name)
        stack.extend(reversed(children.get(chapter.chapter_id, [])))
    unreachable = set(by_id) - set(index)
    if unreachable:  # every parent exists, so chapters not reached from a root lie on cycles
        raise RankingIntegrityError("chapter_tree", _utf8_sorted(unreachable), "chapter cycle")
    return index


def _check_chapter(chapter: Chapter) -> None:
    if not isinstance(chapter.chapter_id, str) or not chapter.chapter_id:
        raise RankingIntegrityError("chapter_tree", detail="chapter_id must be a non-empty string")
    if chapter.parent_id is not None and (
        not isinstance(chapter.parent_id, str) or not chapter.parent_id
    ):
        raise RankingIntegrityError("chapter_tree", (chapter.chapter_id,), "invalid parent_id")
    if isinstance(chapter.order, bool) or not isinstance(chapter.order, int) or chapter.order < 0:
        raise RankingIntegrityError("chapter_tree", (chapter.chapter_id,), "order must be an integer ≥ 0")
    if not isinstance(chapter.name, str):
        raise RankingIntegrityError("chapter_tree", (chapter.chapter_id,), "name must be a string")


def _utf8_sorted(ids: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(ids, key=lambda kp_id: kp_id.encode("utf-8")))
