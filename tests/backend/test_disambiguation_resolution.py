"""DISAMBIG-BE-01: semantic decisions are not graph writes or calibrated probabilities."""
from dataclasses import replace
import json

import pytest

from app.services.ai.client import ModelServerError
from app.services.ai.fake import FakeModelClient
from app.services.ai.policy import BudgetExceededError
from app.services.fusion.judge import FusionEntity, FusionEvidence


def pair():
    a = FusionEvidence("s1", "c", "d1", "r1", "ch1", "散列表支持按键查询。")
    b = FusionEvidence("s2", "c", "d2", "r2", "ch2", "哈希表用于存储键值对。")
    return (FusionEntity("a", "c", "散列表", "concept", "按键查询的结构", (a,)),
            FusionEntity("b", "c", "哈希表", "concept", "存储键值对的结构", (b,)))


def reply(verdict="SAME", **changes):
    value = dict(verdict=verdict, basis="model_knowledge", reason="两个名称表示同一结构",
                 left_source_ids=["s1"], right_source_ids=["s2"],
                 differences=["对象不同"] if verdict == "DIFFERENT" else [])
    value.update(changes)
    return json.dumps(value, ensure_ascii=False)


def resolver(*replies, **kwargs):
    from app.services.fusion.resolution import SemanticResolver
    client = FakeModelClient()
    client.script(*replies)
    return client, SemanticResolver(client, model="test-model", **kwargs)


def test_domain_synonyms_require_blind_verification():
    client, service = resolver(reply(), reply())
    decision = service.resolve(*pair())
    assert (decision.status, decision.verdict, decision.basis) == ("complete", "SAME", "model_knowledge")
    assert decision.left_source_ids == ("s1",) and decision.right_source_ids == ("s2",)
    assert decision.model_calls == len(client.calls) == 2
    prompts = [c.request.messages[0].content for c in client.calls]
    assert "两个名称表示同一结构" not in prompts[1]  # the first model conclusion is not leaked
    assert "资料中" in prompts[0] and "领域知识" in prompts[0]
    assert decision.prompt_sha256 and decision.model_ids == ("test-model",)
    assert "按键查询的结构" not in repr(decision)


def test_different_does_not_request_definition_or_second_vote():
    client, service = resolver(reply("DIFFERENT"))
    result = service.resolve(*pair())
    assert result.verdict == "DIFFERENT" and result.status == "complete"
    assert len(client.calls) == 1


def test_conflicting_verifier_is_uncertain_not_majority_vote():
    client, service = resolver(reply(), reply("DIFFERENT"))
    result = service.resolve(*pair())
    assert result.verdict == "UNCERTAIN" and result.status == "complete"
    assert result.code == "verification_disagreed" and len(client.calls) == 2


@pytest.mark.parametrize("bad", ["{bad", reply(left_source_ids=["s2"]),
    reply(right_source_ids=[]), reply(right_source_ids=["invented"]),
    reply(differences=["适用条件不同"]), reply(basis="authoritative_dictionary"),
    reply(reason=""), reply("DIFFERENT", differences=[])])
def test_invalid_output_is_technical_failure_not_semantic_review(bad):
    client, service = resolver(bad, bad)
    result = service.resolve(*pair())
    assert result.status == "failed" and result.verdict is None
    assert result.code == "invalid_output" and len(client.calls) == 2


def test_single_shared_repair_budget_bounds_whole_pair():
    client, service = resolver("{bad", reply(), "{bad")
    result = service.resolve(*pair())
    assert len(client.calls) == result.model_calls == 3
    assert result.status == "failed" and result.verdict is None


def test_truncated_valid_json_is_not_a_decision():
    cut = reply() + " " * 10000  # fake truncates after complete JSON and reports length
    client, service = resolver(cut, cut)
    assert service.resolve(*pair()).status == "failed"
    assert len(client.calls) == 2


def test_long_input_is_deferred_without_silent_truncation_or_calls():
    client, service = resolver(max_input_bytes=7000)
    a, b = pair()
    a = replace(a, definition="独立性前提" * 2000)
    result = service.resolve(a, b)
    assert result.status == "deferred" and result.code == "input_budget"
    assert result.verdict is None and len(client.calls) == 0


def test_output_reservation_is_part_of_budget():
    client, service = resolver(max_output_tokens=2000, max_input_bytes=7000)
    assert service.resolve(*pair()).code == "input_budget"
    assert not client.calls


def test_course_isolation_rejects_before_model_call():
    client, service = resolver()
    a, b = pair()
    with pytest.raises(ValueError):
        service.resolve(a, replace(b, course_id="other"))
    assert not client.calls


def test_provider_failure_is_not_a_negative_semantic_result():
    client, service = resolver(ModelServerError("provider unavailable"))
    result = service.resolve(*pair())
    assert result.status == "failed" and result.verdict is None
    assert result.code == "model_error" and result.model_calls == 1
    assert result.prompt_sha256 == service.template.sha256


def test_budget_rejection_is_deferred_without_retry():
    from app.services.fusion.resolution import SemanticResolver
    def rejected(_request):
        raise BudgetExceededError("task")
    client = FakeModelClient(responder=rejected)
    service = SemanticResolver(client, model="test-model")
    result = service.resolve(*pair())
    assert result.status == "deferred" and result.code == "budget_exceeded"
    assert result.verdict is None and len(client.calls) == 1


@pytest.mark.parametrize("field,value", [("max_input_bytes", True), ("max_input_bytes", 0),
                                        ("max_output_tokens", -1), ("max_output_tokens", True)])
def test_invalid_limits_rejected(field, value):
    with pytest.raises(ValueError):
        resolver(**{field: value})
