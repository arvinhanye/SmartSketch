"""Provider output limits agree across the HTTP payload and SQLite billing."""

import pytest

from app.config import Settings
from app.repositories.model_calls import SqliteCallStore, billed_for_task
from app.repositories.sqlite import connect
from app.services.ai.compatible import CompatibleModelClient
from app.services.ai.policy import CallAttribution, ModelCallPolicy
from test_e03 import SSE_HEADERS, ScriptedResponse, ScriptedTransport, chunk, completion_body, make_request, sse


REQUESTED_TOKENS = 4_096_000


@pytest.mark.parametrize(
    ("base_url", "model", "requested", "expected"),
    [
        ("https://api.deepseek.com", "deepseek-flash", REQUESTED_TOKENS, 393_216),
        ("https://api.deepseek.com/v1", "deepseek-v4-pro", REQUESTED_TOKENS, 393_216),
        ("https://api.deepseek.com:443/v1", "deepseek-v4-flash", REQUESTED_TOKENS, 393_216),
        ("https://api.deepseek.com", "deepseek-v4-flash-vision-exp", REQUESTED_TOKENS, 393_216),
        ("https://api.deepseek.com", "deepseek-flash", 393_216, 393_216),
        ("https://api.deepseek.com", "deepseek-flash", 4096, 4096),
        ("https://api.deepseek.com", "deepseek-unknown", REQUESTED_TOKENS, REQUESTED_TOKENS),
        ("https://api.deepseek.com.example.test", "deepseek-flash", REQUESTED_TOKENS, REQUESTED_TOKENS),
        ("http://api.deepseek.com", "deepseek-flash", REQUESTED_TOKENS, REQUESTED_TOKENS),
        ("https://api.deepseek.com:444", "deepseek-flash", REQUESTED_TOKENS, REQUESTED_TOKENS),
    ],
)
def test_build_payload_limits_only_known_official_deepseek_models(base_url, model, requested, expected):
    client = CompatibleModelClient(base_url, "test-key")
    request = make_request(model=model, max_output_tokens=requested)

    assert client.build_payload(request, stream=False)["max_tokens"] == expected


@pytest.mark.parametrize("stream", [False, True], ids=["complete", "stream"])
@pytest.mark.parametrize("use_fallback", [False, True], ids=["primary", "fallback"])
def test_policy_writes_and_bills_the_limit_sent_to_selected_provider(db_url, stream, use_fallback):
    official_model = "deepseek-flash"
    response = (
        ScriptedResponse(200, sse(chunk("answer", finish_reason="stop"), "[DONE]"), headers=SSE_HEADERS)
        if stream
        else ScriptedResponse(200, completion_body(content="answer", model=official_model, usage=None))
    )
    transport = ScriptedTransport(response)
    official = CompatibleModelClient("https://api.deepseek.com/v1", "test-key", transport=transport)
    if use_fallback:
        primary_model = "gateway-model"
        primary_transport = ScriptedTransport(ScriptedResponse(503, b'{}'))
        primary = CompatibleModelClient("https://llm.example.test/v1", "test-key", transport=primary_transport)
        fallback = official
    else:
        primary_model, primary, fallback = official_model, official, None
    policy = ModelCallPolicy.from_settings(
        Settings(
            LLM_EXTRACTION_MODEL=primary_model,
            LLM_FALLBACK_EXTRACTION_MODEL=official_model,
            LLM_MAX_RETRIES=0,
            LLM_TASK_TOKEN_BUDGET=5_000_000,
        ),
        primary=primary,
        fallback=fallback,
        store=SqliteCallStore(db_url),
    )
    request = make_request(model=primary_model, max_output_tokens=REQUESTED_TOKENS)
    client = policy.bind(CallAttribution(course_id="course-1", task_id="task-1"))

    if stream:
        list(client.stream(request))
    else:
        client.complete(request)

    with connect(db_url) as db:
        rows = db.execute(
            "SELECT provider_role, model_requested, max_output_tokens, input_tokens_est, "
            "status, usage_output FROM model_calls ORDER BY call_seq"
        ).fetchall()
    assert len(rows) == (2 if use_fallback else 1)
    role, model, stored_ceiling, _, status, usage = rows[-1]
    assert (role, model, status, usage) == ("fallback" if use_fallback else "primary", official_model, "ok", None)
    assert stored_ceiling == transport.payload["max_tokens"] == 393_216
    budgeted_input = sum(row[3] for row in rows)
    if use_fallback:
        assert primary_transport.payload["max_tokens"] == rows[0][2] == REQUESTED_TOKENS
        budgeted_input += REQUESTED_TOKENS  # The 503 supplied no usage; it is billed by estimate too.
    assert billed_for_task(db_url, "task-1") == budgeted_input + 393_216
