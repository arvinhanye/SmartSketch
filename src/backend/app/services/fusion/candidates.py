"""E09：向量候选分层——同一课程、同一向量空间的实体向量 + 两条阈值 → 自动合并 / 需裁决 / 保留三组。

纯函数：不调用模型、不做 I/O、不记录日志、不修改输入。E09 **只分层，不合并**：「自动合并」组是给
E10/E12 的结论输入，实际合并（含教师加锁节点不被覆盖）不在本模块。

阈值（``TierThresholds``，两项均为必填关键字参数，本模块**不给默认值**）：

- ``auto_merge`` 与 ``review`` 都必须是有限实数（``int``/``float``，``bool`` 不算），取值 ``[0, 1]``，且
  ``review < auto_merge``（严格小于；相等会使裁决组成为空区间，视为配置错误）。违反即 ``ValueError``，
  类型不符即 ``TypeError``。初始取值待 D-08 签收，由调用方传入；本模块不读环境变量。

边界等号规则（``classify_similarity``；相似度与阈值直接按浮点比较，不做舍入或容差）：

- ``相似度 ≥ auto_merge`` → ``auto_merge``（自动合并）；等于自动阈值**算自动合并**；
- ``review ≤ 相似度 < auto_merge`` → ``review``（需裁决）；等于裁决阈值**算需裁决**；
- ``相似度 < review`` → ``keep``（保留，不合并）。

即每组区间都含下界、不含上界（最高组含 1）。与 ADR-010 部分失败阈值「含等号」、E08 包含比例
「≥ 3/5」一致：达到阈值即进入该组。

相似度（``cosine_similarity``）为余弦相似度，取值 ``[-1, 1]``：

- 两个向量必须同属一个向量空间（``EmbeddedVector.space``，E07 的 ``fake/<维度>`` 或
  ``real/<模型>/<维度>``），否则 ``VectorIsolationError``；维度不同、``values`` 长度与 ``dimensions`` 不符、
  含非有限值或 ``bool``、全零向量（余弦无定义）一律 ``ValueError``；
- ``values`` 完全相同时结果**恰为 1.0**（不受浮点误差影响，保证 ``auto_merge = 1`` 时逐值相同的向量
  仍进入自动合并）；其余情况用 ``math.fsum`` 求点积与范数，结果截断到 ``[-1, 1]``，对称。

课程与向量空间隔离（``tier_vector_candidates``）：

- 调用方必须显式给出 ``course_id`` 与 ``space``；每个 ``VectorEntry`` 的 ``course_id`` 与向量的 ``space``
  都必须与之相等，**任何一项不符即整体拒绝**（``VectorIsolationError``，是 ``ValueError`` 的子类），
  不做部分分层、不静默丢弃。因此不同课程、不同向量空间的实体绝不会配对。
- 草稿可见性 V 过滤（ADR-011 修订 1，F02）仍由调用方先做；本模块只保证传入集合内部同课程同空间。

输出 ``VectorTiers``：回显 ``course_id``、``space``、``thresholds``，三组 ``VectorCandidate`` 元组互斥且
合起来覆盖全部 C(n, 2) 对（``keep`` 组即余下全部配对，复杂度 O(n²·d)，面向单课程规模）。每对
``left_id < right_id``（码点序），组内按 ``(left_id, right_id)`` 升序，与输入顺序无关；无自配对。
``entity_id`` 重复即 ``ValueError``。

与 E08 名称候选（``same_key``/``alias``/``containment``）的关系：规格未定如何合流，本模块只看向量、
不接收名称候选（待决，见 ``docs/handoffs/claude-e09.md``）。
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from app.services.ai.embeddings import EmbeddedVector

__all__ = [
    "CandidateTier",
    "TierThresholds",
    "VectorCandidate",
    "VectorEntry",
    "VectorIsolationError",
    "VectorTiers",
    "classify_similarity",
    "cosine_similarity",
    "tier_vector_candidates",
]


class VectorIsolationError(ValueError):
    """混入了其他课程或其他向量空间的实体/向量。"""


class CandidateTier(StrEnum):
    """分层结果，从高到低。"""

    AUTO_MERGE = "auto_merge"
    REVIEW = "review"
    KEEP = "keep"


def _require_real(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be int or float, got {type(value).__name__}")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _require_id(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be str, got {type(value).__name__}")
    if not value.strip():
        raise ValueError(f"{name} must be non-blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class TierThresholds:
    """两条阈值：``0 ≤ review < auto_merge ≤ 1``，必填、无默认值（D-08 待签收）。"""

    auto_merge: float
    review: float

    def __post_init__(self) -> None:
        auto_merge = _require_real(self.auto_merge, "auto_merge")
        review = _require_real(self.review, "review")
        for name, value in (("auto_merge", auto_merge), ("review", review)):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be within [0, 1]")
        if not review < auto_merge:
            raise ValueError("auto_merge must be strictly greater than review")


@dataclass(frozen=True, slots=True)
class VectorEntry:
    """一个待分层的实体：``entity_id`` 在一次调用内唯一；``course_id`` 用于隔离校验。"""

    entity_id: str
    course_id: str
    vector: EmbeddedVector = field(repr=False)

    def __post_init__(self) -> None:
        _require_id(self.entity_id, "entity_id")
        _require_id(self.course_id, "course_id")
        if not isinstance(self.vector, EmbeddedVector):
            raise TypeError(f"vector must be EmbeddedVector, got {type(self.vector).__name__}")


@dataclass(frozen=True, slots=True)
class VectorCandidate:
    """一对实体的相似度与分层。``left_id < right_id``。"""

    left_id: str
    right_id: str
    similarity: float
    tier: CandidateTier

    def __post_init__(self) -> None:
        if not isinstance(self.tier, CandidateTier):
            raise TypeError("tier must be CandidateTier")
        if not self.left_id < self.right_id:
            raise ValueError("left_id must sort strictly before right_id")


@dataclass(frozen=True, slots=True)
class VectorTiers:
    """三组分层结果；三组互斥，合起来覆盖全部配对。"""

    course_id: str
    space: str
    thresholds: TierThresholds
    auto_merge: tuple[VectorCandidate, ...] = ()
    review: tuple[VectorCandidate, ...] = ()
    keep: tuple[VectorCandidate, ...] = ()

    def all_pairs(self) -> tuple[VectorCandidate, ...]:
        """三组合并，按 ``(left_id, right_id)`` 升序。"""
        return tuple(
            sorted((*self.auto_merge, *self.review, *self.keep), key=lambda p: (p.left_id, p.right_id))
        )


def classify_similarity(similarity: float, thresholds: TierThresholds) -> CandidateTier:
    """按模块说明的边界等号规则把一个相似度归入三组之一。相似度须为 ``[-1, 1]`` 内的有限实数。"""
    if not isinstance(thresholds, TierThresholds):
        raise TypeError("thresholds must be TierThresholds")
    value = _require_real(similarity, "similarity")
    if not -1 <= value <= 1:
        raise ValueError("similarity must be within [-1, 1]")
    if value >= thresholds.auto_merge:
        return CandidateTier.AUTO_MERGE
    if value >= thresholds.review:
        return CandidateTier.REVIEW
    return CandidateTier.KEEP


def _checked(vector: EmbeddedVector) -> tuple[tuple[float, ...], float]:
    """校验向量并返回 ``(values, 范数)``。"""
    if not isinstance(vector, EmbeddedVector):
        raise TypeError(f"vector must be EmbeddedVector, got {type(vector).__name__}")
    values = tuple(vector.values)
    if not values:
        raise ValueError("vector must not be empty")
    if len(values) != vector.dimensions:
        raise ValueError("vector length does not match its declared dimensions")
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("vector values must be finite real numbers")
    norm = math.sqrt(math.fsum(v * v for v in values))
    if norm == 0:
        raise ValueError("zero vector has no cosine similarity")
    return values, norm


def _cosine(a: tuple[tuple[float, ...], float], b: tuple[tuple[float, ...], float]) -> float:
    (av, an), (bv, bn) = a, b
    if av == bv:
        return 1.0
    result = math.fsum(x * y for x, y in zip(av, bv, strict=True)) / (an * bn)
    return min(1.0, max(-1.0, result))


def cosine_similarity(a: EmbeddedVector, b: EmbeddedVector) -> float:
    """同一向量空间内两个向量的余弦相似度（规则见模块说明）。"""
    left, right = _checked(a), _checked(b)
    if a.space != b.space:
        raise VectorIsolationError("vectors belong to different vector spaces")
    if len(left[0]) != len(right[0]):
        raise ValueError("vectors have different dimensions")
    return _cosine(left, right)


def tier_vector_candidates(
    entries: Iterable[VectorEntry],
    *,
    course_id: str,
    space: str,
    thresholds: TierThresholds,
) -> VectorTiers:
    """把单课程、单向量空间的实体两两配对并分成自动合并 / 需裁决 / 保留三组（只分层，不合并）。"""
    if not isinstance(thresholds, TierThresholds):
        raise TypeError("thresholds must be TierThresholds")
    _require_id(course_id, "course_id")
    _require_id(space, "space")

    prepared: list[tuple[str, tuple[tuple[float, ...], float]]] = []
    seen: set[str] = set()
    dimensions: int | None = None
    for entry in entries:
        if not isinstance(entry, VectorEntry):
            raise TypeError(f"entries must contain VectorEntry, got {type(entry).__name__}")
        if entry.course_id != course_id:
            raise VectorIsolationError("entry belongs to a different course")
        if entry.vector.space != space:
            raise VectorIsolationError("entry vector belongs to a different vector space")
        if entry.entity_id in seen:
            raise ValueError("duplicate entity_id")
        seen.add(entry.entity_id)
        checked = _checked(entry.vector)
        if dimensions is None:
            dimensions = len(checked[0])
        elif len(checked[0]) != dimensions:
            raise ValueError("vectors have different dimensions")
        prepared.append((entry.entity_id, checked))
    prepared.sort(key=lambda item: item[0])

    groups: dict[CandidateTier, list[VectorCandidate]] = {tier: [] for tier in CandidateTier}
    for i, (left_id, left) in enumerate(prepared):
        for right_id, right in prepared[i + 1 :]:
            similarity = _cosine(left, right)
            tier = classify_similarity(similarity, thresholds)
            groups[tier].append(VectorCandidate(left_id, right_id, similarity, tier))
    return VectorTiers(
        course_id=course_id,
        space=space,
        thresholds=thresholds,
        auto_merge=tuple(groups[CandidateTier.AUTO_MERGE]),
        review=tuple(groups[CandidateTier.REVIEW]),
        keep=tuple(groups[CandidateTier.KEEP]),
    )
