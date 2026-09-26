"""E10 同课证据对裁决：只用 fake 模型，不访问外部服务。"""

from __future__ import annotations

from dataclasses import replace
import json

import pytest

from app.services.ai.fake import FakeModelClient
from app.services.ai.policy import BudgetExceededError, ModelUnavailableError
from app.services.fusion.judge import FusionEntity, FusionEvidence, FusionJudge, FusionReviewReason, validate_pair


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


def _judgment(same: object = True, reason: str = "含义相同", refs: list[str] | None = None) -> str:
    return json.dumps({"same": same, "reason": reason, "source_ids": refs or ["s1", "s2"]}, ensure_ascii=False)


def _judge(*replies: str) -> tuple[FakeModelClient, object]:
    client = FakeModelClient()
    client.script(*replies)
    left, right = _pair()
    return client, FusionJudge(client, model="fake-model", max_output_tokens=4096).judge_duplicate(left, right)


def test_judge_same_has_reason_and_known_sources() -> None:
    client, result = _judge(_judgment())
    assert result.same is True and result.reason == "含义相同"
    assert result.source_ids == ("s1", "s2")
    assert result.model_calls == len(client.calls) == 1
    assert result.provenance.version == 2
    assert client.calls[0].request.response_format == "json"


def test_judge_false_skips_summary() -> None:
    client, result = _judge(_judgment(False, "概念不同"))
    assert result.same is False and result.review_reason is FusionReviewReason.NOT_SAME
    assert len(client.calls) == 1


def test_judge_rejects_integer_same_and_repairs_once() -> None:
    client, result = _judge(_judgment(1), _judgment())
    assert result.same is True and result.model_calls == 2
    assert [call.request.purpose for call in client.calls] == ["judge_duplicate", "repair"]


def test_judge_bad_json_twice_goes_review() -> None:
    client, result = _judge("{bad", "{still bad")
    assert result.same is None and result.review_reason is FusionReviewReason.INVALID_JUDGMENT
    assert result.model_calls == len(client.calls) == 2


def test_judge_truncated_then_bad_goes_review() -> None:
    client, result = _judge("x" * 5000, "{bad")
    assert result.review_reason is FusionReviewReason.INVALID_JUDGMENT
    assert result.model_calls == len(client.calls) == 2


@pytest.mark.parametrize("reason", [" ", "x" * 501])
def test_judge_blank_or_overlong_reason_reviews(reason: str) -> None:
    _, result = _judge(_judgment(reason=reason), _judgment(reason=reason))
    assert result.same is None and result.review_reason is FusionReviewReason.INVALID_JUDGMENT


def test_judge_budget_exceeded_goes_review() -> None:
    client = FakeModelClient(responder=lambda _request: (_ for _ in ()).throw(BudgetExceededError("task")))
    left, right = _pair()
    result = FusionJudge(client, model="fake-model", max_output_tokens=4096).judge_duplicate(left, right)
    assert result.same is None and result.review_reason is FusionReviewReason.BUDGET_EXCEEDED


def test_judge_budget_on_repair_preserves_first_call_count() -> None:
    attempts = 0
    def responder(_request: object) -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return "{bad"
        raise BudgetExceededError("task")
    client = FakeModelClient(responder=responder)
    left, right = _pair()
    result = FusionJudge(client, model="fake-model", max_output_tokens=4096).judge_duplicate(left, right)
    assert result.review_reason is FusionReviewReason.BUDGET_EXCEEDED
    assert result.model_calls == 1


def test_judge_unavailable_propagates() -> None:
    client = FakeModelClient(responder=lambda _request: (_ for _ in ()).throw(ModelUnavailableError()))
    left, right = _pair()
    with pytest.raises(ModelUnavailableError):
        FusionJudge(client, model="fake-model", max_output_tokens=4096).judge_duplicate(left, right)
