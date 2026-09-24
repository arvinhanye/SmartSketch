"""B13: grounded Q&A response union, chat SSE events, and terminal-state wire fields."""

import copy
import importlib.util
import re
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SPEC = yaml.safe_load((ROOT / "src/contracts/api.v1.yaml").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]
CHAT = SPEC["paths"]["/api/v1/courses/{cid}/chat"]["post"]
EVENTS_DOC = (ROOT / "src/contracts/events.v1.md").read_text(encoding="utf-8")
ARCH = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")


def _rewrite(node):
    if isinstance(node, dict):
        return {
            key: (value.replace("#/components/schemas/", "#/$defs/")
                  if key == "$ref" and isinstance(value, str) else _rewrite(value))
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_rewrite(item) for item in node]
    return node


DEFS = _rewrite(copy.deepcopy(SCHEMAS))


def is_valid(name: str, instance) -> bool:
    schema = {"$defs": DEFS, "$ref": f"#/$defs/{name}"}
    return jsonschema.Draft202012Validator(schema).is_valid(instance)


def generated_models():
    """导入入库的 Pydantic 生成物，确认约束进入了生成类型（REVIEW-B13-R02）。"""
    path = ROOT / "src/contracts/v1/generated/python/models.py"
    spec = importlib.util.spec_from_file_location("b13_generated_models", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module   # Pydantic 按模块命名空间解析前向引用
    spec.loader.exec_module(module)
    return module


BOUND = {"graph_version": 3, "request_id": "01J8ZQ3N6T7W8X9Y0ZABCDEF12"}
CITATION = {"index": 1, "chunk_id": "c_77", "document_id": "d_03", "page": 52, "text": "栈是限定仅在表尾进行插入和删除操作的线性表。"}
ANSWERED = {"status": "answered", "answer": "栈是一种后进先出的线性表[1]。", "citations": [CITATION],
            "related_kp_ids": ["kp_12"], "latency_ms": 6200} | BOUND
NOT_COVERED = {"status": "not_covered", "answer": "检索到的课程资料不足以回答这个问题。", "citations": [],
               "reason": "insufficient_evidence", "latency_ms": 5400} | BOUND


# ── NotCoveredReason（ADR-015 决定 3）──────────────────────────────────────

def test_not_covered_reason_is_the_signed_closed_set():
    assert SCHEMAS["NotCoveredReason"]["enum"] == [
        "no_retrieval_hit", "below_similarity_threshold",
        "insufficient_evidence", "all_citations_invalidated",
    ]
    assert not is_valid("ChatResponse", NOT_COVERED | {"reason": "out_of_course_scope"})
    row = next(line for line in ARCH.splitlines() if line.startswith("| `NotCoveredReason`"))
    assert "insufficient_evidence" in row and "`out_of_course_scope`、" not in row


# ── 终态 ChatResponse（R03 + Q4 + Q9）──────────────────────────────────────

@pytest.mark.parametrize("payload", [ANSWERED, NOT_COVERED,
                                     NOT_COVERED | {"reason": "no_retrieval_hit", "related_kp_ids": []}])
def test_final_responses_carry_bound_version_and_request_id(payload):
    assert is_valid("ChatResponse", payload)


@pytest.mark.parametrize("field", ["graph_version", "request_id"])
@pytest.mark.parametrize("base", [ANSWERED, NOT_COVERED])
def test_final_without_version_binding_is_rejected(base, field):
    assert not is_valid("ChatResponse", {k: v for k, v in base.items() if k != field})


@pytest.mark.parametrize("payload", [
    ANSWERED | {"citations": []},                                             # answered 空引用
    ANSWERED | {"citations": [{k: v for k, v in CITATION.items() if k != "page"}]},  # 无定位
    ANSWERED | {"answer": ""},                                                # 替换正文为空
    {k: v for k, v in ANSWERED.items() if k != "answer"},                     # 替换正文缺失
    NOT_COVERED | {"citations": [CITATION]},                                   # 未覆盖却带引用
    NOT_COVERED | {"graph_version": 0},
    ANSWERED | {"request_id": ""},
])
def test_answered_and_not_covered_invariants(payload):
    assert not is_valid("ChatResponse", payload)


# ── 事件（Q2、Q5）─────────────────────────────────────────────────────────

META_ANSWERED = {"event": "meta", "status": "answered", "retrieved": 6} | BOUND
META_NOT_COVERED = {"event": "meta", "status": "not_covered", "retrieved": 0} | BOUND
LLM_ERROR = {"event": "error", "error": {"code": "LLM_UNAVAILABLE", "message": "模型暂不可用，请稍后重试",
                                         "details": {"reason": "stream_interrupted", "request_id": BOUND["request_id"]}}}


@pytest.mark.parametrize("payload", [
    META_ANSWERED, META_NOT_COVERED,
    {"event": "delta", "delta": "栈是一种"},
    {"event": "done", "final": ANSWERED},
    {"event": "done", "final": NOT_COVERED},
    LLM_ERROR,
    *[{"event": "error", "error": {"code": "LLM_UNAVAILABLE", "message": "m",
                                   "details": {"reason": reason, "request_id": "r1"}}}
      for reason in ("upstream", "timeout", "auth")],
    *[{"event": "error", "error": {"code": code, "message": "m", "details": {"request_id": "r1"}}}
      for code in ("BUDGET_EXCEEDED", "STORAGE_UNAVAILABLE", "INTERNAL_ERROR")],
])
def test_valid_chat_events(payload):
    assert is_valid("ChatEvent", payload)


@pytest.mark.parametrize("payload", [
    {},
    {"event": "meta"},
    {"event": "meta", "status": "answered", "retrieved": 6},                  # 缺版本绑定
    META_NOT_COVERED | {"retrieved": 2},                                      # not_covered 时 retrieved = 0
    {"event": "delta", "delta": ""},
    {"event": "done"},
    {"event": "done", "final": {k: v for k, v in ANSWERED.items() if k != "request_id"}},
    {"event": "error"},
    {"event": "error", "error": {"code": "LLM_UNAVAILABLE", "message": "m"}},                         # 缺 details
    {"event": "error", "error": {"code": "LLM_UNAVAILABLE", "message": "m", "details": {"request_id": "r1"}}},
    {"event": "error", "error": {"code": "LLM_UNAVAILABLE", "message": "m",
                                 "details": {"reason": "rate_limited", "request_id": "r1"}}},          # 闭集外
    {"event": "error", "error": {"code": "INTERNAL_ERROR", "message": "m", "details": {}}},           # 缺 request_id
])
def test_invalid_chat_events_are_rejected(payload):
    assert not is_valid("ChatEvent", payload)


def test_meta_fields_are_all_required():
    assert set(SCHEMAS["ChatMetaEvent"]["required"]) == {"event", "status", "retrieved", "graph_version", "request_id"}


# ── 接口响应（Q2 P1、Q7）──────────────────────────────────────────────────

def test_chat_operation_declares_pre_stream_and_json_mode_errors():
    responses = CHAT["responses"]
    assert {"401", "403", "404", "422", "429", "500", "503"} <= set(responses)
    assert "GRAPH_NOT_PUBLISHED" in responses["404"]["description"]
    assert "request_id" in CHAT["description"]
    for code in ("500", "503"):
        assert "details.request_id" in responses[code]["description"]
    assert "details.reason" in responses["503"]["description"]


# ── events.v1.md §3 改为指向规格（Q11 B13 行）───────────────────────────────

def test_events_doc_chat_section_follows_grounded_qa():
    section = EVENTS_DOC.split("## 3. 问答流式事件", 1)[1].split("## 4. 重连", 1)[0]
    assert "specs/grounded-qa.md" in section
    for anchor in ("Q2", "Q5", "Q6"):
        assert anchor in section
    assert "两者可能不同" not in section, "I1：answered 时 final.answer 等于 delta 拼接"
    assert "out_of_course_scope" not in EVENTS_DOC
    assert "insufficient_evidence" in section
    assert "O15" in section and "撤回" in section
    assert '"graph_version"' in section and '"request_id"' in section


def test_rate_limited_only_means_this_service():
    errors_doc = (ROOT / "src/contracts/errors.v1.md").read_text(encoding="utf-8")
    row = next(line for line in errors_doc.splitlines() if line.startswith("| `RATE_LIMITED`"))
    assert "模型 API" not in row and "本服务" in row


# ── REVIEW-B13（2026-09-24）─────────────────────────────────────────────────

def _error_event(code, details):
    return {"event": "error", "error": {"code": code, "message": "m", "details": details}}


@pytest.mark.parametrize("payload", [
    _error_event("CYCLE_DETECTED", {"request_id": "r1"}),                      # R01：Q5 之外的码
    _error_event("VALIDATION_ERROR", {"request_id": "r1"}),                    # R01：开流前的码
    _error_event("INTERNAL_ERROR", {"request_id": "r1", "reason": "timeout"}),  # R03：reason 只属于 LLM_UNAVAILABLE
    _error_event("BUDGET_EXCEEDED", {"request_id": "r1", "reason": "upstream"}),
    META_ANSWERED | {"retrieved": 0},                                          # R04：进入生成时 |A| ≥ 1
])
def test_review_b13_rejects(payload):
    assert not is_valid("ChatEvent", payload)


def test_chat_error_is_a_union_by_code_so_generators_keep_reason():
    error = SCHEMAS["ChatError"]
    assert "if" not in error and "if" not in str(error.get("allOf", "")), "if/then 会被生成器忽略"
    assert error["discriminator"]["propertyName"] == "code"
    assert set(error["discriminator"]["mapping"]) == {
        "LLM_UNAVAILABLE", "BUDGET_EXCEEDED", "STORAGE_UNAVAILABLE", "INTERNAL_ERROR"}

    event = generated_models().ChatErrorEvent
    event.model_validate(LLM_ERROR)
    event.model_validate(_error_event("INTERNAL_ERROR", {"request_id": "r1"}))
    for bad in (_error_event("LLM_UNAVAILABLE", {"request_id": "r1"}),          # 缺 reason
                _error_event("CYCLE_DETECTED", {"request_id": "r1"}),
                _error_event("INTERNAL_ERROR", {"request_id": "r1", "reason": "timeout"})):
        with pytest.raises(Exception):
            event.model_validate(bad)


def test_json_mode_503_constrains_reason_to_the_closed_set():
    schema = CHAT["responses"]["503"]["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/ChatUnavailableError"}
    ok = [{"code": "LLM_UNAVAILABLE", "message": "m", "details": {"reason": "timeout", "request_id": "r1"}},
          {"code": "LLM_UNAVAILABLE", "message": "m"},                            # P4 向量失败：规格未定 reason
          {"code": "STORAGE_UNAVAILABLE", "message": "m"},                          # P2 失败：尚无 request_id
          {"code": "STORAGE_UNAVAILABLE", "message": "m", "details": {"request_id": "r1"}}]
    bad = [{"code": "LLM_UNAVAILABLE", "message": "m", "details": {"reason": "provider_down"}},
           {"code": "STORAGE_UNAVAILABLE", "message": "m", "details": {"reason": "upstream"}},
           {"code": "INTERNAL_ERROR", "message": "m"}]
    for body in ok:
        assert is_valid("ChatUnavailableError", body), body
    for body in bad:
        assert not is_valid("ChatUnavailableError", body), body


def test_events_doc_records_the_b13_in_place_exception():
    section = EVENTS_DOC.split("## 6. 变更策略", 1)[1]
    assert re.search(r"例外记录：B13", section), "B13 原地改写 §3 须在 §6 登记（REVIEW-B13-R06）"


def test_generated_details_classes_have_stable_names():
    models = (ROOT / "src/contracts/v1/generated/python/models.py").read_text(encoding="utf-8")
    assert not re.findall(r"^class Details\d*\(", models, re.M), "内联 details 会按出现顺序编号（REVIEW-B13-R07）"
    for name in ("ChatErrorDetails", "ChatLlmUnavailableDetails", "TaskPersistingDetails",
                 "TaskProcessingFinishedDetails", "TaskAlreadyTerminalDetails"):
        assert re.search(rf"^class {name}\(", models, re.M), name
