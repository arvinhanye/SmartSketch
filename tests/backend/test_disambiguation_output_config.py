"""The semantic output limit reaches both worker factories and provider billing."""

import pytest

from app.config import SettingsError, load_settings
from app.repositories.courses import create_course
from app.repositories.model_calls import billed_for_task
from app.repositories.sqlite import connect
from app.services.ai import compatible_base
from app.services.ai.fake import FakeModelClient
from app.services.ai.policy import CallAttribution
from app.workers.runner import build_toolkit
from tests.backend.test_disambiguation_resolution import pair, reply
from tests.backend.test_l07 import _bound_task, _configure, _lease, _settings, _user
from test_e03 import ScriptedResponse, ScriptedTransport, completion_body


OVERRIDES = {
    "DISAMBIGUATION_ANALYSIS_ENABLED": "true",
    "DISAMBIGUATION_MAX_OUTPUT_TOKENS": "1024000",
}


def _live_settings(db_url, base_url, model):
    return load_settings({
        "SQLITE_URL": db_url,
        "LLM_MODE": "live",
        "LLM_BASE_URL": base_url,
        "LLM_API_KEY": "test-key",
        "LLM_EXTRACTION_MODEL": model,
        "LLM_CHAT_MODEL": model,
        **OVERRIDES,
    })


@pytest.mark.parametrize("mode", ["personal", "live", "fake"])
def test_worker_factory_sets_output_ceiling_for_judgment_repair_and_verification(db_url, mode):
    if mode == "personal":
        user = _user(db_url, "semantic-budget-teacher")
        course = create_course(db_url, name="Semantic budget", description=None, creator_id=user.id)
        _configure(db_url, user, base_url="https://model.example/v1", model="m", key="test-key")
        task = _bound_task(db_url, course.id, user)
        toolkit = build_toolkit(_settings(db_url, **OVERRIDES))(_lease(task))
    elif mode == "live":
        toolkit = build_toolkit(_live_settings(db_url, "https://model.example/v1", "m"))
    else:
        toolkit = build_toolkit(load_settings({"SQLITE_URL": db_url, "LLM_MODE": "fake", **OVERRIDES}))
    client = FakeModelClient()
    client.script("invalid JSON", reply(), reply())

    result = toolkit.resolver(client).resolve(*pair())

    assert (result.status, result.verdict) == ("complete", "SAME")
    assert [(call.request.purpose, call.request.max_output_tokens) for call in client.calls] == [
        ("resolve_duplicate", 1_024_000), ("repair", 1_024_000), ("resolve_duplicate", 1_024_000),
    ]


def test_deepseek_semantic_request_and_ledger_use_same_provider_limit(db_url, monkeypatch):
    model = "deepseek-flash"
    payload = completion_body(content=reply("DIFFERENT"), model=model, usage=None)
    transport = ScriptedTransport(ScriptedResponse(200, payload))
    monkeypatch.setattr(compatible_base, "StdlibTransport", lambda: transport)
    toolkit = build_toolkit(_live_settings(db_url, "https://api.deepseek.com/v1", model))
    bound = toolkit.policy.bind(CallAttribution(course_id="c", task_id="semantic-budget-task"))

    result = toolkit.resolver(bound).resolve(*pair())

    assert (result.status, result.verdict) == ("complete", "DIFFERENT")
    with connect(db_url) as db:
        [(purpose, limit, estimated_input)] = db.execute(
            "SELECT purpose, max_output_tokens, input_tokens_est FROM model_calls"
        ).fetchall()
    assert purpose == "resolve_duplicate"
    assert transport.payload["max_tokens"] == limit == 393_216
    assert billed_for_task(db_url, "semantic-budget-task") == estimated_input + 393_216


def test_semantic_output_limit_defaults_to_1024_tokens():
    assert load_settings({}).DISAMBIGUATION_MAX_OUTPUT_TOKENS == 1024


@pytest.mark.parametrize("value", ["0", "1024001", "1.5"])
def test_semantic_output_limit_rejects_out_of_range_or_fractional_values(value):
    with pytest.raises(SettingsError, match="DISAMBIGUATION_MAX_OUTPUT_TOKENS"):
        load_settings({"DISAMBIGUATION_MAX_OUTPUT_TOKENS": value})
