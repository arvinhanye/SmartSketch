"""E02: model interface (request/result/error taxonomy) and deterministic fake adapters.

Rules checked here come from docs/integrations.md「模型接入规则（A07）」:
the declared output ceiling on every LLM request, the requested vs responded model ID,
the pre-generation rejection set (ADR-011 修订 3), fake usage that keeps budgets testable,
and no prompt/output text in reprs or error messages (E04 验收).
"""

import json
import math
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from app.services.ai.client import (
    REJECTED_BEFORE_GENERATION_STATUSES,
    EmbeddingClient,
    EmbeddingRequest,
    EmbeddingResult,
    ErrorClass,
    Message,
    ModelAuthError,
    ModelCallError,
    ModelClient,
    ModelConnectionError,
    ModelError,
    ModelInvalidRequestError,
    ModelMalformedResponseError,
    ModelOutputError,
    ModelRateLimitedError,
    ModelRequest,
    ModelResult,
    ModelServerError,
    ModelStreamInterruptedError,
    ModelTimeoutError,
    StreamDelta,
    StreamDone,
    Usage,
)
from app.services.ai.fake import (
    BAD_JSON_TEXT,
    FakeEmbedding,
    FakeEmbeddingClient,
    FakeModelClient,
    FakeReply,
)

SECRET_TEXT = "学生问题-不应出现在日志-7f3a"


def make_request(content: str = "栈是后进先出的线性表。", **overrides: object) -> ModelRequest:
    fields: dict[str, object] = {
        "purpose": "extract_entities",
        "model": "model-x-2026-01",
        "messages": [Message("system", "你是抽取助手。"), Message("user", content)],
        "max_output_tokens": 512,
    }
    fields.update(overrides)
    return ModelRequest(**fields)  # type: ignore[arg-type]


def collect(stream) -> tuple[list[str], ModelResult]:  # type: ignore[no-untyped-def]
    deltas: list[str] = []
    done: ModelResult | None = None
    for event in stream:
        if isinstance(event, StreamDelta):
            assert done is None, "delta after done"
            deltas.append(event.text)
        else:
            assert isinstance(event, StreamDone)
            done = event.result
    assert done is not None, "stream ended without StreamDone"
    return deltas, done


# ---------------------------------------------------------------- request validation


def test_request_normalizes_messages_to_tuple_and_is_frozen() -> None:
    request = make_request()
    assert isinstance(request.messages, tuple)
    assert request.response_format == "text"
    assert request.timeout_seconds is None
    with pytest.raises(AttributeError):
        request.model = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"messages": []}, "messages"),
        ({"messages": [("user", "hi")]}, "messages"),
        ({"model": ""}, "model"),
        ({"model": "   "}, "model"),
        ({"purpose": ""}, "purpose"),
        ({"purpose": "Extract Entities"}, "purpose"),
        ({"max_output_tokens": 0}, "max_output_tokens"),
        ({"max_output_tokens": True}, "max_output_tokens"),
        ({"max_output_tokens": 10.0}, "max_output_tokens"),
        ({"response_format": "xml"}, "response_format"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"timeout_seconds": float("nan")}, "timeout_seconds"),
        ({"timeout_seconds": float("inf")}, "timeout_seconds"),
    ],
)
def test_request_rejects_invalid_fields_by_name(overrides: dict[str, object], field: str) -> None:
    with pytest.raises(ValueError, match=field):
        make_request(**overrides)


def test_message_rejects_unknown_role_and_non_string_content() -> None:
    with pytest.raises(ValueError, match="role"):
        Message("tool", "x")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="content"):
        Message("user", 42)  # type: ignore[arg-type]


def test_reprs_never_show_prompt_or_output_text() -> None:
    request = make_request(SECRET_TEXT)
    result = FakeModelClient().complete(request)
    delta = StreamDelta(SECRET_TEXT)
    for obj in (request, request.messages[1], result, delta, StreamDone(result)):
        assert SECRET_TEXT not in repr(obj)
    scripted = FakeModelClient()
    scripted.script(SECRET_TEXT)
    assert SECRET_TEXT not in repr(scripted.complete(make_request()))
    assert SECRET_TEXT not in repr(FakeReply(SECRET_TEXT))


def test_usage_validation() -> None:
    assert Usage(3, 4).total == 7
    for bad in ((-1, 0), (0, -1), (True, 0), (1.0, 0)):
        with pytest.raises(ValueError):
            Usage(*bad)  # type: ignore[arg-type]


def test_result_rejects_unknown_finish_reason() -> None:
    with pytest.raises(ValueError, match="finish_reason"):
        ModelResult(text="", model_requested="m", model_responded="m", usage=None, finish_reason="eos")  # type: ignore[arg-type]


# ---------------------------------------------------------------- deterministic fake


def test_fake_is_reproducible_for_fixed_input() -> None:
    first = FakeModelClient().complete(make_request())
    second = FakeModelClient().complete(make_request())
    assert first == second
    assert first.text  # never empty
    other = FakeModelClient().complete(make_request("队列是先进先出的线性表。"))
    assert other.text != first.text
    assert FakeModelClient().complete(make_request(model="model-y")).text != first.text
    assert FakeModelClient().complete(make_request(purpose="judge_duplicate")).text != first.text


def test_fake_output_is_stable_across_processes() -> None:
    """sha256-based, not hash()-based: a different PYTHONHASHSEED gives the same bytes."""
    code = (
        "import json;"
        "from app.services.ai.client import Message, ModelRequest;"
        "from app.services.ai.fake import FakeModelClient;"
        "r = ModelRequest(purpose='extract_entities', model='model-x-2026-01',"
        " messages=[Message('user', '栈')], max_output_tokens=512, response_format='json');"
        "print(json.dumps(FakeModelClient().complete(r).text))"
    )
    outputs = set()
    for seed in ("1", "2"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            check=True,
            cwd=Path(__file__).parent,
        )
        outputs.add(proc.stdout)
    here = FakeModelClient().complete(
        ModelRequest(
            purpose="extract_entities",
            model="model-x-2026-01",
            messages=[Message("user", "栈")],
            max_output_tokens=512,
            response_format="json",
        )
    )
    assert outputs == {json.dumps(here.text) + "\n"}


def test_fake_json_mode_default_output_is_valid_json() -> None:
    result = FakeModelClient().complete(make_request(response_format="json"))
    parsed = result.json()
    assert isinstance(parsed, dict)
    assert parsed["purpose"] == "extract_entities"


def test_fake_reports_simulated_usage_and_requested_model() -> None:
    request = make_request()
    result = FakeModelClient().complete(request)
    chars_in = sum(len(message.content) for message in request.messages)
    assert result.usage == Usage(input_tokens=chars_in, output_tokens=len(result.text))
    assert result.model_requested == "model-x-2026-01"
    assert result.model_responded == "model-x-2026-01"
    assert result.finish_reason == "stop"


def test_fake_honours_declared_output_ceiling() -> None:
    client = FakeModelClient()
    client.script("一二三四五六七八九十")
    result = client.complete(make_request(max_output_tokens=4))
    assert result.text == "一二三四"
    assert result.finish_reason == "length"
    assert result.usage is not None and result.usage.output_tokens == 4


def test_script_is_fifo_then_falls_back_to_default() -> None:
    client = FakeModelClient()
    client.script("A", FakeReply("B"))
    default = FakeModelClient().complete(make_request()).text
    assert [client.complete(make_request()).text for _ in range(3)] == ["A", "B", default]
    assert client.pending == 0


def test_purpose_script_only_serves_that_purpose() -> None:
    client = FakeModelClient()
    client.script("judged", purpose="judge_duplicate")
    client.script("generic")
    assert client.complete(make_request()).text == "generic"
    assert client.complete(make_request(purpose="judge_duplicate")).text == "judged"
    assert client.pending == 0


def test_responder_supplies_input_dependent_output() -> None:
    client = FakeModelClient(responder=lambda request: request.messages[-1].content[::-1])
    assert client.complete(make_request("abc")).text == "cba"
    client2 = FakeModelClient(responder=lambda request: FakeReply("x", model_responded="alias-v2"))
    assert client2.complete(make_request()).model_responded == "alias-v2"


def test_responder_may_return_a_fault() -> None:
    client = FakeModelClient(responder=lambda request: ModelTimeoutError(request.model))
    with pytest.raises(ModelTimeoutError):
        client.complete(make_request())
    with pytest.raises(ModelTimeoutError):
        collect(client.stream(make_request()))
    assert [call.outcome for call in client.calls] == ["timeout", "timeout"]
    bad = FakeModelClient(responder=lambda request: 42)  # type: ignore[arg-type,return-value]
    with pytest.raises(TypeError):
        bad.complete(make_request())


def test_reply_without_usage_and_with_explicit_usage() -> None:
    client = FakeModelClient()
    client.script(FakeReply("ok", usage=None), FakeReply("ok", usage=Usage(100, 7)))
    assert client.complete(make_request()).usage is None
    assert client.complete(make_request()).usage == Usage(100, 7)


def test_script_rejects_untyped_steps() -> None:
    client = FakeModelClient()
    with pytest.raises(TypeError):
        client.script(RuntimeError("boom"))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        client.script(42)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        client.script(FakeEmbedding(vectors=((1.0,),)))  # type: ignore[arg-type]
    assert client.pending == 0


# ---------------------------------------------------------------- simulated faults


def test_timeout_is_a_typed_error_and_is_recorded() -> None:
    client = FakeModelClient()
    client.script(ModelTimeoutError("model-x-2026-01"))
    with pytest.raises(ModelTimeoutError) as info:
        client.complete(make_request())
    error = info.value
    assert isinstance(error, ModelCallError) and isinstance(error, ModelError)
    assert error.error_class is ErrorClass.TIMEOUT
    assert error.rejected_before_generation is False
    assert len(client.calls) == 1
    assert client.calls[0].outcome == "timeout"


def test_rate_limit_is_typed_and_rejected_before_generation() -> None:
    client = FakeModelClient()
    client.script(ModelRateLimitedError("model-x-2026-01", retry_after_seconds=2.5))
    with pytest.raises(ModelRateLimitedError) as info:
        client.complete(make_request())
    assert info.value.status_code == 429
    assert info.value.retry_after_seconds == 2.5
    assert info.value.error_class is ErrorClass.RATE_LIMITED
    assert info.value.rejected_before_generation is True
    assert client.calls[0].outcome == "rate_limited"


def test_bad_json_surfaces_as_output_error_with_result_attached() -> None:
    client = FakeModelClient()
    client.script(BAD_JSON_TEXT)
    result = client.complete(make_request(response_format="json"))
    assert client.calls[0].outcome == "ok"  # the call itself succeeded and is billable
    with pytest.raises(ModelOutputError) as info:
        result.json()
    assert info.value.reason == "invalid_json"
    assert info.value.result is result
    assert info.value.result.usage is not None
    assert BAD_JSON_TEXT not in str(info.value)


@pytest.mark.parametrize("text", ["NaN", '{"a": Infinity}', "[1, -Infinity]", ""])
def test_json_rejects_non_standard_json(text: str) -> None:
    result = ModelResult(text=text, model_requested="m", model_responded="m", usage=None, finish_reason="stop")
    with pytest.raises(ModelOutputError):
        result.json()


def test_error_messages_never_contain_prompt_text() -> None:
    client = FakeModelClient()
    client.script(ModelServerError("model-x-2026-01", status_code=503))
    with pytest.raises(ModelServerError) as info:
        client.complete(make_request(SECRET_TEXT))
    assert SECRET_TEXT not in str(info.value)
    assert SECRET_TEXT not in repr(info.value)
    assert "model-x-2026-01" in str(info.value)
    assert "503" in str(info.value)


def test_rejected_before_generation_set_matches_adr_011_revision_3() -> None:
    assert REJECTED_BEFORE_GENERATION_STATUSES == frozenset({400, 401, 403, 404, 413, 422, 429})
    cases = [
        (ModelTimeoutError("m"), ErrorClass.TIMEOUT, None, False),
        (ModelTimeoutError("m", status_code=408), ErrorClass.TIMEOUT, 408, False),
        (ModelConnectionError("m"), ErrorClass.CONNECTION, None, False),
        (ModelRateLimitedError("m"), ErrorClass.RATE_LIMITED, 429, True),
        (ModelServerError("m"), ErrorClass.SERVER, 500, False),
        (ModelServerError("m", status_code=502), ErrorClass.SERVER, 502, False),
        (ModelAuthError("m"), ErrorClass.AUTH, 401, True),
        (ModelAuthError("m", status_code=403), ErrorClass.AUTH, 403, True),
        (ModelInvalidRequestError("m"), ErrorClass.INVALID_REQUEST, 400, True),
        (ModelInvalidRequestError("m", status_code=404), ErrorClass.INVALID_REQUEST, 404, True),
        (ModelInvalidRequestError("m", status_code=413), ErrorClass.INVALID_REQUEST, 413, True),
        (ModelInvalidRequestError("m", status_code=422), ErrorClass.INVALID_REQUEST, 422, True),
        (ModelStreamInterruptedError("m"), ErrorClass.STREAM_INTERRUPTED, None, False),
        (ModelMalformedResponseError("m"), ErrorClass.MALFORMED_RESPONSE, None, False),
        (ModelMalformedResponseError("m", status_code=200), ErrorClass.MALFORMED_RESPONSE, 200, False),
    ]
    for error, error_class, status, rejected in cases:
        assert error.error_class is error_class, error
        assert error.status_code == status, error
        assert error.rejected_before_generation is rejected, error
        assert error.model == "m"
        assert error.usage is None


@pytest.mark.parametrize(
    ("factory", "status"),
    [
        (ModelAuthError, 400),
        (ModelAuthError, 429),
        (ModelServerError, 429),
        (ModelServerError, 600),
        (ModelInvalidRequestError, 401),
        (ModelInvalidRequestError, 429),
        (ModelInvalidRequestError, 408),
        (ModelInvalidRequestError, 500),
        (ModelTimeoutError, 504),
        (ModelRateLimitedError, 503),
    ],
)
def test_error_status_must_match_its_class(factory: type[ModelCallError], status: int) -> None:
    with pytest.raises(ValueError, match="status_code"):
        factory("m", status_code=status)


def test_error_may_carry_usage_from_the_error_response() -> None:
    error = ModelServerError("m", status_code=500, usage=Usage(10, 2))
    assert error.usage == Usage(10, 2)
    with pytest.raises(ValueError, match="model"):
        ModelServerError("")


# ---------------------------------------------------------------- streaming


def test_stream_deltas_concatenate_to_final_result_and_match_complete() -> None:
    request = make_request()
    deltas, result = collect(FakeModelClient(stream_chunk_chars=3).stream(request))
    assert len(deltas) > 1
    assert "".join(deltas) == result.text
    assert result == FakeModelClient().complete(request)


def test_stream_uses_scripted_chunks() -> None:
    client = FakeModelClient()
    client.script(FakeReply(chunks=("栈是", "线性表[1]。")))
    deltas, result = collect(client.stream(make_request()))
    assert deltas == ["栈是", "线性表[1]。"]
    assert result.text == "栈是线性表[1]。"


def test_reply_text_and_chunks_must_agree() -> None:
    with pytest.raises(ValueError):
        FakeReply("abc", chunks=("ab",))
    with pytest.raises(ValueError):
        FakeReply()
    assert FakeReply(chunks=("a", "b")).text == "ab"


def test_stream_failure_before_first_delta() -> None:
    client = FakeModelClient()
    client.script(ModelServerError("model-x-2026-01", status_code=502))
    stream = client.stream(make_request())
    with pytest.raises(ModelServerError):
        next(iter(stream))
    assert client.calls[0].kind == "stream"
    assert client.calls[0].chunks_delivered == 0
    assert client.calls[0].outcome == "server"


def test_stream_interrupted_after_some_deltas() -> None:
    client = FakeModelClient()
    client.script(
        FakeReply(chunks=("一", "二", "三"), error_after_chunks=(2, ModelStreamInterruptedError("model-x-2026-01")))
    )
    received: list[str] = []
    with pytest.raises(ModelStreamInterruptedError):
        for event in client.stream(make_request()):
            assert isinstance(event, StreamDelta)
            received.append(event.text)
    assert received == ["一", "二"]
    assert client.calls[0].chunks_delivered == 2
    assert client.calls[0].outcome == "stream_interrupted"


def test_error_after_chunks_bounds_are_checked() -> None:
    with pytest.raises(ValueError):
        FakeReply(chunks=("a",), error_after_chunks=(2, ModelStreamInterruptedError("m")))
    with pytest.raises(TypeError):
        FakeReply(chunks=("a",), error_after_chunks=(0, RuntimeError("x")))  # type: ignore[arg-type]


def test_error_after_chunks_raises_on_complete_too() -> None:
    client = FakeModelClient()
    client.script(FakeReply("abc", error_after_chunks=(0, ModelMalformedResponseError("model-x-2026-01"))))
    with pytest.raises(ModelMalformedResponseError):
        client.complete(make_request())
    assert client.calls[0].outcome == "malformed_response"


def test_early_close_is_recorded() -> None:
    client = FakeModelClient()
    client.script(FakeReply(chunks=("<<INSUFFICIENT_EVIDENCE>>", "资料里没有", "……")))
    stream = client.stream(make_request())
    first = next(iter(stream))
    assert isinstance(first, StreamDelta)
    stream.close()
    assert client.calls[0].closed_early is True
    assert client.calls[0].chunks_delivered == 1

    collect(client.stream(make_request()))
    assert client.calls[1].closed_early is False
    assert client.calls[1].outcome == "ok"


def test_stream_truncates_at_output_ceiling() -> None:
    client = FakeModelClient()
    client.script(FakeReply(chunks=("abc", "def", "ghi")))
    deltas, result = collect(client.stream(make_request(max_output_tokens=5)))
    assert "".join(deltas) == "abcde"
    assert result.finish_reason == "length"


# ---------------------------------------------------------------- recording, isolation, protocol


def test_calls_record_each_request() -> None:
    client = FakeModelClient()
    assert client.calls == ()
    request = make_request()
    client.complete(request)
    collect(client.stream(request))
    assert [call.kind for call in client.calls] == ["complete", "stream"]
    assert all(call.request is request for call in client.calls)
    assert all(call.outcome == "ok" for call in client.calls)


def test_fakes_need_no_network_keys_or_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("fake adapter touched the network")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    for name in list(os.environ):
        if name.startswith(("LLM_", "EMBEDDING_")):
            monkeypatch.delenv(name)
    client = FakeModelClient()
    client.complete(make_request())
    collect(client.stream(make_request()))
    FakeEmbeddingClient().embed(EmbeddingRequest(model="emb-1", texts=["栈"], dimensions=8))


def test_fakes_satisfy_the_protocols() -> None:
    assert isinstance(FakeModelClient(), ModelClient)
    assert isinstance(FakeEmbeddingClient(), EmbeddingClient)
    assert not isinstance(FakeEmbeddingClient(), ModelClient)


def test_fake_is_safe_under_concurrent_calls() -> None:
    client = FakeModelClient()
    client.script(*[str(i) for i in range(40)])
    outputs: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        for _ in range(10):
            text = client.complete(make_request()).text
            with lock:
                outputs.append(text)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outputs, key=int) == [str(i) for i in range(40)]
    assert len(client.calls) == 40


# ---------------------------------------------------------------- embeddings


def test_embedding_request_validation() -> None:
    with pytest.raises(ValueError, match="texts"):
        EmbeddingRequest(model="emb-1", texts=[], dimensions=8)
    with pytest.raises(ValueError, match="texts"):
        EmbeddingRequest(model="emb-1", texts=["a", 1], dimensions=8)  # type: ignore[list-item]
    with pytest.raises(ValueError, match="dimensions"):
        EmbeddingRequest(model="emb-1", texts=["a"], dimensions=0)
    with pytest.raises(ValueError, match="dimensions"):
        EmbeddingRequest(model="emb-1", texts=["a"], dimensions=True)
    with pytest.raises(ValueError, match="model"):
        EmbeddingRequest(model="", texts=["a"], dimensions=8)
    request = EmbeddingRequest(model="emb-1", texts=["a", "b"], dimensions=8)
    assert request.texts == ("a", "b")
    assert SECRET_TEXT not in repr(EmbeddingRequest(model="emb-1", texts=[SECRET_TEXT], dimensions=4))


def test_fake_embeddings_are_deterministic_unit_vectors() -> None:
    request = EmbeddingRequest(model="emb-1", texts=["栈", "队列", "栈"], dimensions=16)
    result = FakeEmbeddingClient().embed(request)
    assert isinstance(result, EmbeddingResult)
    assert result == FakeEmbeddingClient().embed(request)
    assert len(result.vectors) == 3
    for vector in result.vectors:
        assert len(vector) == 16
        assert math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0, rel_tol=1e-9)
    assert result.vectors[0] == result.vectors[2]
    assert result.vectors[0] != result.vectors[1]
    assert result.model_requested == result.model_responded == "emb-1"
    assert result.usage == Usage(input_tokens=len("栈队列栈"), output_tokens=0)
    other_model = FakeEmbeddingClient().embed(EmbeddingRequest(model="emb-2", texts=["栈"], dimensions=16))
    assert other_model.vectors[0] != result.vectors[0]
    assert repr(result.vectors[0][0]) not in repr(result)


def test_fake_embedding_script_can_return_wrong_dimensions_and_faults() -> None:
    client = FakeEmbeddingClient()
    client.script(
        FakeEmbedding(vectors=((0.1, 0.2),)),
        ModelRateLimitedError("emb-1"),
    )
    request = EmbeddingRequest(model="emb-1", texts=["栈"], dimensions=8)
    wrong = client.embed(request)
    assert len(wrong.vectors[0]) == 2  # the fake does not hide mismatches; E07 must detect them
    with pytest.raises(ModelRateLimitedError):
        client.embed(request)
    assert [call.outcome for call in client.calls] == ["ok", "rate_limited"]
    assert client.pending == 0
    default = client.embed(request)
    assert len(default.vectors[0]) == 8
    with pytest.raises(TypeError):
        client.script("text")  # type: ignore[arg-type]
