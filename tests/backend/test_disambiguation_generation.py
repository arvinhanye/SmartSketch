"""Bounded generation analysis, truthful coverage and per-call credentials."""
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from app.services.ai.client import ModelAuthError, ModelServerError
from app.services.ai.entities import EntityCandidate, EntitySource
from app.services.ai.fake import FakeModelClient
from app.services.credentials import CredentialUnavailable
from app.services.fusion.resolution import SemanticResolver
from app.workers.extraction.types import TaskEntity


def entities(count=3):
    result = []
    for i in range(count):
        source = EntitySource("c", "d", "r", f"ch{i}", 0, 2, ())
        c = EntityCandidate(f"概念{i}", "concept", f"定义{i}", "原文", 0.8, source)
        result.append(TaskEntity(f"e{i}", c.name, c.type, (c,)))
    return tuple(result), {f"ch{i}": SimpleNamespace(text="原文及上下文") for i in range(count)}


def different(request):
    payload = json.loads(request.messages[0].content.splitlines()[-1])
    return json.dumps(dict(verdict="DIFFERENT", basis="mixed", reason="限定条件不同", differences=["对象不同"],
        left_source_ids=[payload["left"]["sources"][0]["source_id"]],
        right_source_ids=[payload["right"]["sources"][0]["source_id"]]), ensure_ascii=False)


def test_candidate_cap_reports_unprocessed_pairs_without_materializing_all_pairs():
    from app.workers.extraction.analysis import analyze_section
    nodes, chunks = entities(4)
    client = FakeModelClient(responder=different)
    report = analyze_section(nodes, chunks, resolver=SemanticResolver(client, model="m"), max_pairs=2)
    assert report["total_pairs"] == 6 and report["unprocessed_pairs"] == 4
    assert report["completion"] == "partial" and len(client.calls) == 2
    assert all(d["verdict"] == "DIFFERENT" for d in report["decisions"])
    assert len(report["input_digest"]) == 64


def test_analysis_digest_changes_when_evidence_or_definition_changes():
    from app.workers.extraction.analysis import analyze_section
    nodes, chunks = entities(2)
    service = SemanticResolver(FakeModelClient(responder=different), model="m")
    a = analyze_section(nodes, chunks, resolver=service, max_pairs=1)
    nodes = (replace(nodes[0], candidates=(replace(nodes[0].candidates[0], definition="不同假设"),)), nodes[1])
    b = analyze_section(nodes, chunks, resolver=service, max_pairs=1)
    assert a["input_digest"] != b["input_digest"]


def test_bad_analysis_does_not_become_uncertain_or_hide_missing_coverage():
    from app.workers.extraction.analysis import analyze_section
    nodes, chunks = entities(2)
    client = FakeModelClient(responder=lambda _: "bad JSON")
    report = analyze_section(nodes, chunks, resolver=SemanticResolver(client, model="m"), max_pairs=1)
    assert report["completion"] == "partial" and report["unprocessed_pairs"] == 1
    assert report["decisions"][0]["verdict"] is None
    assert report["decisions"][0]["status"] == "failed"


def test_unavailable_resolver_preserves_mentions_and_reports_deferred():
    from app.workers.extraction.analysis import analyze_section
    nodes, chunks = entities(2)
    report = analyze_section(nodes, chunks, resolver=None, max_pairs=1)
    assert report["completion"] == "partial" and report["unprocessed_pairs"] == 1
    assert report["reason"] == "analysis_disabled"


def test_server_fault_is_technical_but_auth_fault_aborts_stage():
    from app.workers.extraction.analysis import analyze_section
    nodes, chunks = entities(2)
    client = FakeModelClient(); client.script(ModelServerError("m"))
    report = analyze_section(nodes, chunks, resolver=SemanticResolver(client, model="m"), max_pairs=1)
    assert report["decisions"][0]["code"] == "model_error"
    client.script(ModelAuthError("m"))
    with pytest.raises(ModelAuthError):
        analyze_section(nodes, chunks, resolver=SemanticResolver(client, model="m"), max_pairs=1)


def test_source_offset_mismatch_never_reaches_model():
    from app.workers.extraction.analysis import analyze_section
    nodes, chunks = entities(2)
    chunks["ch0"].text = "不是引用"
    client = FakeModelClient(responder=different)
    report = analyze_section(nodes, chunks, resolver=SemanticResolver(client, model="m"), max_pairs=1)
    assert report["unprocessed_pairs"] == 1 and not client.calls
    assert report["decisions"][0]["code"] == "invalid_evidence"


def test_credentials_checked_again_before_verification_call():
    from app.workers.extraction.units import _AttemptClient
    from app.services.ai.policy import CallAttribution, ModelCallPolicy
    count = 0
    def guard():
        nonlocal count
        count += 1
        if count == 2:
            raise CredentialUnavailable("credential_revoked")
    client = FakeModelClient(responder=lambda r: different(r).replace('"DIFFERENT"', '"SAME"').replace('["对象不同"]', '[]'))
    policy = ModelCallPolicy(primary=client,
        store=SimpleNamespace(prewrite=lambda *a, **kw: None, finish=lambda *a, **kw: None),
        max_retries=0, failure_threshold=5, open_seconds=30,
        task_token_budget=1_000_000, daily_token_budget=1_000_000)
    wrapped = _AttemptClient(policy, CallAttribution(course_id="c", task_id="t"), guard=guard)
    nodes, chunks = entities(2)
    from app.workers.extraction.analysis import analyze_section
    with pytest.raises(CredentialUnavailable):
        analyze_section(nodes, chunks, resolver=SemanticResolver(wrapped, model="m"), max_pairs=1)
    assert count == 2 and len(client.calls) == 1


def test_worker_analysis_factory_is_opt_in():
    from app.config import load_settings
    from app.workers.runner import build_toolkit
    off = build_toolkit(load_settings({}))
    on = build_toolkit(load_settings({"DISAMBIGUATION_ANALYSIS_ENABLED": "true"}))
    assert off.resolver is None and not off.preserve_mentions
    assert on.resolver is not None and on.preserve_mentions


def test_output_budget_is_part_of_analysis_input_digest():
    from app.workers.extraction.analysis import analyze_section
    nodes, chunks = entities(2)
    a = analyze_section(nodes, chunks, resolver=SemanticResolver(
        FakeModelClient(responder=different), model="m", max_output_tokens=1024), max_pairs=1)
    b = analyze_section(nodes, chunks, resolver=SemanticResolver(
        FakeModelClient(responder=different), model="m", max_output_tokens=6000), max_pairs=1)
    assert a["input_digest"] != b["input_digest"]


def test_verifier_model_failure_preserves_prior_response_and_logical_call_audit():
    from app.workers.extraction.analysis import analyze_section
    def respond(request):
        if len(client.calls) == 2:
            raise ModelServerError("m")
        return different(request).replace('"DIFFERENT"', '"SAME"').replace('["对象不同"]', '[]')
    client = FakeModelClient(responder=respond)
    service = SemanticResolver(client, model="m")
    nodes, chunks = entities(2)
    result = analyze_section(nodes, chunks, resolver=service, max_pairs=1)["decisions"][0]
    assert result["status"] == "failed" and result["verdict"] is None
    assert result["model_calls"] == 2
    assert result["model_ids"] and result["prompt_sha256"] == service.template.sha256


def test_section_analysis_uses_recall_instead_of_sending_every_pair():
    from app.workers.extraction.analysis import analyze_section
    nodes, chunks = entities(2)
    nodes = tuple(replace(n, name=name, candidates=(replace(n.candidates[0], name=name, definition=definition),))
                  for n, name, definition in zip(nodes, ("alpha", "beta"), ("one", "two")))
    client = FakeModelClient(responder=different)
    result = analyze_section(nodes, chunks, resolver=SemanticResolver(client, model="m"), max_pairs=10)
    assert not client.calls and result["unprocessed_pairs"] == 1
    assert result["recall"]["missing_channels"] == ("vector",)
