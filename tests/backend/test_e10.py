"""E10 同课证据对裁决：只用 fake 模型，不访问外部服务。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.services.fusion.judge import FusionEntity, FusionEvidence, validate_pair


def _pair() -> tuple[FusionEntity, FusionEntity]:
    left_source = FusionEvidence("s1", "course-1", "doc-1", "rev-1", "chunk-1", "栈是后进先出的线性表")
    right_source = FusionEvidence("s2", "course-1", "doc-2", "rev-2", "chunk-2", "堆栈遵循后进先出")
    left = FusionEntity("a", "course-1", "栈", "concept", "后进先出", (left_source,))
    right = FusionEntity("b", "course-1", "堆栈", "concept", "后进先出", (right_source,))
    return left, right


def test_validate_pair_rejects_cross_course_evidence() -> None:
    left, right = _pair()
    wrong = replace(right.evidence[0], course_id="course-2")
    with pytest.raises(ValueError):
        validate_pair(left, replace(right, evidence=(wrong,)))


def test_validate_pair_rejects_reused_source_id() -> None:
    left, right = _pair()
    repeated = replace(right.evidence[0], source_id="s1")
    with pytest.raises(ValueError):
        validate_pair(left, replace(right, evidence=(repeated,)))


@pytest.mark.parametrize("case", ["missing", "same_id", "reverse"])
def test_validate_pair_rejects_missing_evidence_and_equal_ids(case: str) -> None:
    left, right = _pair()
    if case == "missing":
        right = replace(right, evidence=())
    elif case == "same_id":
        right = replace(right, entity_id="a")
    else:
        right = replace(right, entity_id="0")
    with pytest.raises(ValueError):
        validate_pair(left, right)


@pytest.mark.parametrize("field", ["definition", "type", "quote"])
def test_validate_pair_rejects_blank_definition_type_or_quote(field: str) -> None:
    left, right = _pair()
    if field == "quote":
        left = replace(left, evidence=(replace(left.evidence[0], quote=" "),))
    else:
        left = replace(left, **{field: " "})
    with pytest.raises(ValueError):
        validate_pair(left, right)


def test_sensitive_fields_not_in_repr() -> None:
    left, right = _pair()
    assert "栈是后进先出的线性表" not in repr(left)
    assert "后进先出" not in repr(left)
    assert "堆栈遵循后进先出" not in repr(right.evidence[0])
