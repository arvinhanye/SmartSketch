"""B10: task snapshot, task SSE events, cancel semantics, and event tickets."""

import copy
from pathlib import Path

import jsonschema
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SPEC = yaml.safe_load((ROOT / "src/contracts/api.v1.yaml").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]
PATHS = SPEC["paths"]
EVENTS_DOC = (ROOT / "src/contracts/events.v1.md").read_text(encoding="utf-8")


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


def operation(path: str, method: str):
    return PATHS[f"/api/v1{path}"][method]


ERROR = {"code": "LLM_UNAVAILABLE", "message": "主备模型均不可用"}
BASE_TASK = {
    "id": "t_01", "course_id": "c_01", "document_id": "d_01", "progress": 0.34,
    "cancel_requested": False,
    "created_at": "2026-09-24T08:00:00Z", "updated_at": "2026-09-24T08:01:00Z",
}


# ── TaskEvent：每种事件一个独立 schema（A03 §7、events.v1.md §2）────────────

STAGE_EVENT = {"task_id": "t_01", "stage": "extracting", "progress": 0.34, "cancel_requested": False}
DONE_EVENT = {"task_id": "t_01", "stage": "completed", "progress": 1}
ERROR_EVENT = {"task_id": "t_01", "stage": "failed", "progress": 0.42, "error": ERROR}
CANCELLED_EVENT = {"task_id": "t_01", "stage": "cancelled", "progress": 0.2, "cancel_requested": True}


def test_task_event_is_a_union_of_one_schema_per_event():
    event = SCHEMAS["TaskEvent"]
    refs = [item["$ref"].rsplit("/", 1)[-1] for item in event["oneOf"]]
    assert refs == ["TaskStageEvent", "TaskDoneEvent", "TaskErrorEvent", "TaskCancelledEvent"]
    mapping = event["discriminator"]["mapping"]
    assert event["discriminator"]["propertyName"] == "stage"
    assert set(mapping) == set(SCHEMAS["TaskStage"]["enum"])
    for name in refs:
        assert SCHEMAS[name]["required"], f"{name} 必须有必填字段"


@pytest.mark.parametrize("payload", [STAGE_EVENT, DONE_EVENT, ERROR_EVENT, CANCELLED_EVENT,
                                     STAGE_EVENT | {"stage": "awaiting_review", "progress": 0.95},
                                     STAGE_EVENT | {"stage": "queued", "progress": 0},
                                     ERROR_EVENT | {"cancel_requested": True}])
def test_each_event_kind_accepts_its_own_payload(payload):
    assert is_valid("TaskEvent", payload)


@pytest.mark.parametrize("payload", [
    {},
    {"task_id": "t_01"},
    STAGE_EVENT | {"stage": "failed"},                      # failed 必须带 error
    {k: v for k, v in STAGE_EVENT.items() if k != "cancel_requested"},
    STAGE_EVENT | {"error": ERROR},                         # 非 failed 不得带 error
    DONE_EVENT | {"progress": 0.9},                         # completed 的进度固定为 1
    DONE_EVENT | {"error": ERROR},
    ERROR_EVENT | {"error": None},
    {k: v for k, v in ERROR_EVENT.items() if k != "error"},
    CANCELLED_EVENT | {"cancel_requested": False},          # 取消必然先置标志（§4）
    STAGE_EVENT | {"failed_chunks": []},                    # 事件只带计数，不带失败块明细
])
def test_invalid_or_empty_event_payloads_are_rejected(payload):
    assert not is_valid("TaskEvent", payload)


# ── Task 快照（TASK-17、§4、§5）────────────────────────────────────────

def test_task_snapshot_carries_cancel_flag_and_failed_chunk_count():
    assert "cancel_requested" in SCHEMAS["Task"]["required"]
    assert SCHEMAS["TaskCounts"]["properties"]["chunks_failed"] == {"type": "integer", "minimum": 0}
    assert not is_valid("Task", BASE_TASK | {"stage": "extracting"} | {"cancel_requested": None})
    del_flag = {k: v for k, v in BASE_TASK.items() if k != "cancel_requested"}
    assert not is_valid("Task", del_flag | {"stage": "extracting"})


@pytest.mark.parametrize("stage", ["queued", "extracting", "awaiting_review", "completed", "cancelled"])
def test_task_error_must_be_absent_or_null_unless_failed(stage):
    assert is_valid("Task", BASE_TASK | {"stage": stage})
    assert is_valid("Task", BASE_TASK | {"stage": stage, "error": None})
    assert not is_valid("Task", BASE_TASK | {"stage": stage, "error": ERROR})


def test_failed_task_requires_a_non_null_error():
    assert is_valid("Task", BASE_TASK | {"stage": "failed", "error": ERROR})
    assert not is_valid("Task", BASE_TASK | {"stage": "failed"})
    assert not is_valid("Task", BASE_TASK | {"stage": "failed", "error": None})


def test_failed_chunks_need_a_location_and_final_error_code():
    ok = [{"chunk_id": "k1", "page": 3, "code": "LLM_UNAVAILABLE"},
          {"chunk_id": "k2", "section_path": "第3章 > 3.1", "code": "INTERNAL_ERROR"}]
    assert is_valid("Task", BASE_TASK | {"stage": "awaiting_review", "failed_chunks": ok})
    for bad in ({"chunk_id": "k1", "code": "LLM_UNAVAILABLE"},
                {"chunk_id": "k1", "page": 3},
                {"chunk_id": "k1", "page": 0, "code": "LLM_UNAVAILABLE"},
                {"page": 3, "code": "LLM_UNAVAILABLE"}):
        assert not is_valid("Task", BASE_TASK | {"stage": "awaiting_review", "failed_chunks": [bad]})


def test_task_stage_description_points_to_the_signed_state_machine():
    description = SCHEMAS["TaskStage"]["description"]
    assert "specs/task-processing.md" in description
    assert "任意阶段可转" not in description and "任意非终态可转" not in description


# ── 取消端点（§4）──────────────────────────────────────────────────────

def test_cancel_describes_accepted_request_and_three_conflict_reasons():
    responses = operation("/tasks/{tid}/cancel", "post")["responses"]
    ok = responses["200"]["description"]
    assert "stage" in ok and "cancel_requested" in ok and "已转入" not in ok
    conflict = responses["409"]["description"]
    for reason in ("persisting_uninterruptible", "processing_finished", "already_terminal"):
        assert reason in conflict
    assert "TASK_NOT_CANCELLABLE" in conflict


# ── 事件票据与任务类授权语义（identity-access §5、§7、矩阵）──────────────

def test_event_ticket_issuance_operation():
    issue = operation("/tasks/{tid}/event-ticket", "post")
    assert issue["operationId"] == "issueEventTicket"
    assert "security" not in issue, "申领沿用全局 Bearer"
    assert issue["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/EventTicket"
    }
    assert {"401", "403", "404"} <= set(issue["responses"])
    ticket = SCHEMAS["EventTicket"]
    assert set(ticket["required"]) == {"ticket", "expires_in"}
    assert is_valid("EventTicket", {"ticket": "A" * 22, "expires_in": 60})
    assert not is_valid("EventTicket", {"ticket": "A" * 22, "expires_in": 3600})
    assert not is_valid("EventTicket", {"ticket": "short", "expires_in": 60})


def test_stream_uses_one_time_ticket_instead_of_bearer():
    stream = operation("/tasks/{tid}/events", "get")
    assert stream["security"] == [{"eventTicket": []}]
    params = [p for p in stream.get("parameters", []) if p.get("in") == "query"]
    assert [(p["name"], p["required"]) for p in params] == [("ticket", True)]
    assert "token" not in {p["name"] for p in params}
    assert stream["responses"]["401"] == {"$ref": "#/components/responses/Unauthenticated"}
    assert "401" in stream["description"] and "已用" in stream["description"]


@pytest.mark.parametrize("path,method", [
    ("/tasks/{tid}", "get"), ("/tasks/{tid}/events", "get"),
    ("/tasks/{tid}/cancel", "post"), ("/tasks/{tid}/event-ticket", "post"),
])
def test_task_operations_hide_other_courses_behind_404(path, method):
    responses = operation(path, method)["responses"]
    assert "ROLE_FORBIDDEN" in responses["403"]["description"]
    assert "COURSE_FORBIDDEN" not in responses["403"]["description"]
    assert "非成员" in responses["404"]["description"]


# ── events.v1.md 按已签收规格改写（task-processing §7、identity-access §5）────

def test_events_doc_follows_signed_specs():
    assert "通过 `?token=` 查询参数传递" not in EVENTS_DOC, "旧写法：把令牌放进 URL"
    assert "specs/identity-access.md" in EVENTS_DOC and "ticket" in EVENTS_DOC
    assert "规范转换表" not in EVENTS_DOC, "转换表只在 specs/task-processing.md §2"
    assert "互斥且恰好发生一次" not in EVENTS_DOC
    assert "每个连接恰好以一条结束事件收尾" in EVENTS_DOC
    assert "EventSource` 自动重连；" not in EVENTS_DOC
    assert "终态集合" in EVENTS_DOC
