"""B10: task snapshot, task SSE events, cancel semantics, and event tickets."""

import copy
import importlib.util
import sys
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


def generated_models():
    """导入入库的 Pydantic 生成物；生成器丢掉的约束在这里暴露（REVIEW-B10-R01）。"""
    path = ROOT / "src/contracts/v1/generated/python/models.py"
    spec = importlib.util.spec_from_file_location("b10_generated_models", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module   # Pydantic 按模块命名空间解析前向引用
    spec.loader.exec_module(module)
    return module


ERROR = {"code": "LLM_UNAVAILABLE", "message": "主备模型均不可用"}
BASE_TASK = {
    "id": "t_01", "course_id": "c_01", "document_id": "d_01", "progress": 0.34,
    "cancel_requested": False,
    "created_at": "2026-09-24T08:00:00Z", "updated_at": "2026-09-24T08:01:00Z",
}
# 每个阶段一份自洽快照：固定进度（§1）、取消标志（I5）、failed ⇔ error（TASK-17）。
TASK_BY_STAGE = {
    "queued": BASE_TASK | {"stage": "queued", "progress": 0},
    "extracting": BASE_TASK | {"stage": "extracting"},
    "awaiting_review": BASE_TASK | {"stage": "awaiting_review", "progress": 0.95},
    "completed": BASE_TASK | {"stage": "completed", "progress": 1},
    "failed": BASE_TASK | {"stage": "failed", "error": ERROR},
    "cancelled": BASE_TASK | {"stage": "cancelled", "cancel_requested": True},
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
    STAGE_EVENT | {"stage": "awaiting_review", "progress": 0.9},  # §1：awaiting_review 固定 0.95
    STAGE_EVENT | {"stage": "queued", "progress": 0.3},           # §1：queued 固定 0
])
def test_invalid_or_empty_event_payloads_are_rejected(payload):
    assert not is_valid("TaskEvent", payload)


# ── Task 快照（TASK-17、§4、§5）────────────────────────────────────────

def test_task_snapshot_carries_cancel_flag_and_failed_chunk_count():
    assert "cancel_requested" in SCHEMAS["TaskBase"]["required"]
    assert SCHEMAS["TaskCounts"]["properties"]["chunks_failed"] == {"type": "integer", "minimum": 0}
    assert not is_valid("Task", BASE_TASK | {"stage": "extracting"} | {"cancel_requested": None})
    del_flag = {k: v for k, v in BASE_TASK.items() if k != "cancel_requested"}
    assert not is_valid("Task", del_flag | {"stage": "extracting"})


@pytest.mark.parametrize("stage", ["queued", "extracting", "awaiting_review", "completed", "cancelled"])
def test_task_error_must_be_absent_or_null_unless_failed(stage):
    snapshot = TASK_BY_STAGE[stage]
    assert is_valid("Task", snapshot)
    assert is_valid("Task", snapshot | {"error": None})
    assert not is_valid("Task", snapshot | {"error": ERROR})


def test_failed_task_requires_a_non_null_error():
    failed = TASK_BY_STAGE["failed"]
    no_error = {k: v for k, v in failed.items() if k != "error"}
    assert is_valid("Task", failed)
    assert is_valid("Task", failed | {"cancel_requested": True})   # TASK-7：取消中失败保持 true
    assert not is_valid("Task", no_error)
    assert not is_valid("Task", failed | {"error": None})


@pytest.mark.parametrize("snapshot", [
    TASK_BY_STAGE["cancelled"] | {"cancel_requested": False},   # I5：cancelled ⇒ cancel_requested
    TASK_BY_STAGE["completed"] | {"progress": 0.95},             # §1：completed 固定 1
    TASK_BY_STAGE["awaiting_review"] | {"progress": 0.9},        # §1：awaiting_review 固定 0.95
    TASK_BY_STAGE["queued"] | {"progress": 0.3},                 # §1：queued 固定 0
])
def test_task_snapshot_enforces_the_same_invariants_as_events(snapshot):
    assert not is_valid("Task", snapshot)


def test_task_is_a_union_by_stage_so_generators_keep_the_invariants():
    task = SCHEMAS["Task"]
    assert "if" not in task, "if/then/else 会被 datamodel-codegen 与 openapi-typescript 忽略"
    refs = [item["$ref"].rsplit("/", 1)[-1] for item in task["oneOf"]]
    assert refs == ["TaskActive", "TaskCompleted", "TaskFailed", "TaskCancelled"]
    assert task["discriminator"]["propertyName"] == "stage"
    assert set(task["discriminator"]["mapping"]) == set(SCHEMAS["TaskStage"]["enum"])


def test_generated_pydantic_task_rejects_what_the_contract_rejects():
    Task = generated_models().Task
    for snapshot in TASK_BY_STAGE.values():
        Task.model_validate(snapshot)
    no_error = {k: v for k, v in TASK_BY_STAGE["failed"].items() if k != "error"}
    for bad in (no_error,
                TASK_BY_STAGE["failed"] | {"error": None},
                TASK_BY_STAGE["extracting"] | {"error": ERROR},
                TASK_BY_STAGE["cancelled"] | {"cancel_requested": False},
                TASK_BY_STAGE["completed"] | {"progress": 0.95}):
        with pytest.raises(Exception):
            Task.model_validate(bad)


def test_failed_chunks_need_a_location_and_final_error_code():
    ok = [{"chunk_id": "k1", "page": 3, "code": "LLM_UNAVAILABLE"},
          {"chunk_id": "k2", "section_path": "第3章 > 3.1", "code": "INTERNAL_ERROR"}]
    assert is_valid("Task", TASK_BY_STAGE["awaiting_review"] | {"failed_chunks": ok})
    for bad in ({"chunk_id": "k1", "code": "LLM_UNAVAILABLE"},
                {"chunk_id": "k1", "page": 3},
                {"chunk_id": "k1", "page": 0, "code": "LLM_UNAVAILABLE"},
                {"page": 3, "code": "LLM_UNAVAILABLE"}):
        assert not is_valid("Task", TASK_BY_STAGE["awaiting_review"] | {"failed_chunks": [bad]})


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


def test_cancel_conflict_details_are_a_closed_structure():
    conflict = operation("/tasks/{tid}/cancel", "post")["responses"]["409"]
    schema = conflict["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/TaskNotCancellableError"}

    def body(stage, reason):
        return {"code": "TASK_NOT_CANCELLABLE", "message": "当前阶段不可取消",
                "details": {"stage": stage, "reason": reason}}

    for ok in (body("persisting", "persisting_uninterruptible"),
               body("awaiting_review", "processing_finished"),
               body("completed", "already_terminal"),
               body("failed", "already_terminal"),
               body("cancelled", "already_terminal")):
        assert is_valid("TaskNotCancellableError", ok), ok
    for bad in (body("persisting", "persisting"),                 # reason 拼错
                body("extracting", "already_terminal"),           # stage 与 reason 不符
                body("awaiting_review", "persisting_uninterruptible"),
                {"code": "TASK_NOT_CANCELLABLE", "message": "x", "details": {"reason": "already_terminal"}},
                {"code": "TASK_NOT_CANCELLABLE", "message": "x"},
                body("completed", "already_terminal") | {"code": "NODE_LOCKED"}):
        assert not is_valid("TaskNotCancellableError", bad), bad


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
