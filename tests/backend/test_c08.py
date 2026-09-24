"""C08: pure document-task state transitions from ADR-010 §2."""

import copy
import dataclasses
import json
import pickle
import re
from pathlib import Path

import pytest

from app.services.task_state import Applied, Rejected, TaskError, TaskState, TransitionEvent, apply_event


def test_claim_moves_queued_to_parsing_without_mutating_input():
    queued = TaskState(stage="queued", progress=0)

    result = apply_event(queued, TransitionEvent(kind="claim"))

    assert isinstance(result, Applied)
    assert result.state == TaskState(stage="parsing", progress=0)
    assert result.changed is True
    assert queued == TaskState(stage="queued", progress=0)


@pytest.mark.parametrize(
    ("start", "event", "expected"),
    [
        (TaskState("queued", 0), TransitionEvent("cancel_request"), TaskState("cancelled", 0, True)),
        (TaskState("parsing", .07), TransitionEvent("stage_done"), TaskState("extracting", .10)),
        (TaskState("extracting", .4), TransitionEvent("stage_done"), TaskState("merging", .60)),
        (TaskState("merging", .73), TransitionEvent("stage_done"), TaskState("persisting", .80)),
        (TaskState("persisting", .9), TransitionEvent("persisted"), TaskState("awaiting_review", .95)),
        (TaskState("awaiting_review", .95), TransitionEvent("published"), TaskState("completed", 1)),
        (TaskState("parsing", .03, True), TransitionEvent("checkpoint"), TaskState("cancelled", .03, True)),
        (TaskState("extracting", .4, True), TransitionEvent("stage_done"), TaskState("cancelled", .4, True)),
    ],
)
def test_legal_stage_transitions(start, event, expected):
    result = apply_event(start, event)
    assert result == Applied(expected, changed=True)


@pytest.mark.parametrize("stage,progress", [("parsing", .04), ("extracting", .4), ("merging", .7), ("persisting", .9)])
def test_failure_from_processing_stage_preserves_progress_and_cancel_flag(stage, progress):
    error = TaskError("INTERNAL_ERROR", "worker stopped")
    start = TaskState(stage, progress, cancel_requested=stage == "extracting")
    result = apply_event(start, TransitionEvent("fail", error=error))
    assert result == Applied(TaskState("failed", progress, start.cancel_requested, error), changed=True)


@pytest.mark.parametrize("stage,progress", [("parsing", .04), ("extracting", .4), ("merging", .7)])
def test_cancel_request_is_idempotent_until_checkpoint(stage, progress):
    start = TaskState(stage, progress)
    accepted = apply_event(start, TransitionEvent("cancel_request"))
    assert accepted == Applied(TaskState(stage, progress, True), changed=True)
    assert apply_event(accepted.state, TransitionEvent("cancel_request")) == Applied(accepted.state, changed=False)
    assert apply_event(start, TransitionEvent("checkpoint")) == Applied(start, changed=False)


@pytest.mark.parametrize("stage,progress", [("parsing", .04), ("extracting", .4), ("merging", .7), ("persisting", .9)])
def test_progress_monotonic_within_stage(stage, progress):
    start = TaskState(stage, progress)
    assert apply_event(start, TransitionEvent("progress", progress=progress)) == Applied(start, changed=False)
    assert apply_event(start, TransitionEvent("progress", progress=progress + .01)) == Applied(
        TaskState(stage, progress + .01), changed=True
    )
    assert_rejected(start, TransitionEvent("progress", progress=progress - .01), "progress_regression")


def assert_rejected(start, event, reason=None):
    result = apply_event(start, event)
    assert isinstance(result, Rejected)
    assert result.state is start
    if reason is not None:
        assert result.reason == reason


@pytest.mark.parametrize(
    ("stage", "progress", "reason"),
    [
        ("persisting", .85, "persisting_uninterruptible"),
        ("awaiting_review", .95, "processing_finished"),
        ("completed", 1, "already_terminal"),
        ("failed", .5, "already_terminal"),
        ("cancelled", .5, "already_terminal"),
    ],
)
def test_cancel_rejection_reasons(stage, progress, reason):
    error = TaskError("INTERNAL_ERROR", "broken") if stage == "failed" else None
    start = TaskState(stage, progress, stage == "cancelled", error)
    assert_rejected(start, TransitionEvent("cancel_request"), reason)


@pytest.mark.parametrize("stage,progress", [("completed", 1), ("failed", .4), ("cancelled", .4)])
@pytest.mark.parametrize("event", [TransitionEvent("claim"), TransitionEvent("progress", progress=.5), TransitionEvent("published"), TransitionEvent("fail", error=TaskError("INTERNAL_ERROR", "broken"))])
def test_terminal_state_rejects_every_write(stage, progress, event):
    start = TaskState(stage, progress, stage == "cancelled", TaskError("INTERNAL_ERROR", "broken") if stage == "failed" else None)
    assert_rejected(start, event, "already_terminal")


@pytest.mark.parametrize(
    ("start", "event"),
    [
        (TaskState("queued", 0), TransitionEvent("fail", error=TaskError("INTERNAL_ERROR", "broken"))),
        (TaskState("queued", 0), TransitionEvent("stage_done")),
        (TaskState("parsing", .1), TransitionEvent("persisted")),
        (TaskState("parsing", .1), TransitionEvent("published")),
        (TaskState("awaiting_review", .95), TransitionEvent("fail", error=TaskError("INTERNAL_ERROR", "broken"))),
        (TaskState("awaiting_review", .95), TransitionEvent("checkpoint")),
        (TaskState("persisting", .8), TransitionEvent("checkpoint")),
        (TaskState("persisting", .8), TransitionEvent("stage_done")),
    ],
)
def test_illegal_stage_or_cancelled_work_rejected(start, event):
    assert_rejected(start, event)


def test_progress_remains_legal_while_cancel_is_pending():
    start = TaskState("merging", .6, True)
    assert apply_event(start, TransitionEvent("progress", progress=.65)) == Applied(
        TaskState("merging", .65, True), changed=True
    )


@pytest.mark.parametrize("value", [None, -1, 1, float("nan"), float("inf"), True, "0.3"])
def test_invalid_progress_payload_rejected(value):
    assert_rejected(TaskState("extracting", .3), TransitionEvent("progress", progress=value))


@pytest.mark.parametrize("value", [.09, .61])
def test_progress_outside_current_stage_rejected(value):
    assert_rejected(TaskState("extracting", .3), TransitionEvent("progress", progress=value))


def test_failure_requires_nonempty_error_and_other_events_reject_payloads():
    start = TaskState("parsing", .04)
    assert_rejected(start, TransitionEvent("fail"))
    assert_rejected(start, TransitionEvent("fail", error=TaskError("", "broken")))
    assert_rejected(start, TransitionEvent("fail", error=TaskError("INTERNAL_ERROR", "")))
    assert_rejected(start, TransitionEvent("claim", progress=.2))


def test_failed_terminal_error_details_are_deeply_immutable():
    caller_details = {"attempts": [1, {"stage": "parsing"}]}
    error = TaskError("TASK_ATTEMPTS_EXHAUSTED", "attempts exhausted", caller_details)
    result = apply_event(TaskState("parsing", .04), TransitionEvent("fail", error=error))
    assert isinstance(result, Applied)
    caller_details["attempts"][1]["stage"] = "changed"
    assert result.state.error.details["attempts"][1]["stage"] == "parsing"
    with pytest.raises(TypeError):
        result.state.error.details["attempts"][1]["stage"] = "changed"


@pytest.mark.parametrize("kind", [[], {}])
def test_unhashable_event_kind_is_rejected(kind):
    assert_rejected(TaskState("parsing", .04), TransitionEvent(kind))


def test_unhashable_stage_is_rejected():
    assert_rejected(TaskState([], .04), TransitionEvent("claim"), "invalid_state")


@pytest.mark.parametrize(
    "state",
    [
        TaskState("queued", .1),
        TaskState("awaiting_review", .94),
        TaskState("completed", .99),
        TaskState("failed", .4),
        TaskState("cancelled", .4),
        TaskState("persisting", .8, True),
        TaskState("extracting", .7),
    ],
)
def test_invalid_input_state_rejected(state):
    assert_rejected(state, TransitionEvent("cancel_request"), "invalid_state")


# REVIEW-C08 R01: terminal error details must survive the C09/C11 persistence path.
def test_failed_error_details_serialize_to_json_and_asdict():
    details = {"attempts": 3, "stage": "parsing", "history": [{"code": "LLM_UNAVAILABLE", "ratio": .5}], "note": None}
    result = apply_event(TaskState("parsing", .04), TransitionEvent("fail", error=TaskError("TASK_ATTEMPTS_EXHAUSTED", "exhausted", details)))
    assert isinstance(result, Applied)
    error = result.state.error
    assert json.loads(json.dumps(error.details)) == details
    assert dataclasses.asdict(result.state)["error"]["details"] == {**details, "history": ({"code": "LLM_UNAVAILABLE", "ratio": .5},)}
    assert json.loads(json.dumps(dataclasses.asdict(result.state)))["error"]["details"] == details
    assert pickle.loads(pickle.dumps(result.state)) == result.state
    assert copy.deepcopy(result.state) == result.state


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.__setitem__("stage", "x"),
        lambda d: d.__delitem__("stage"),
        lambda d: d.update(stage="x"),
        lambda d: d.setdefault("new", 1),
        lambda d: d.pop("stage"),
        lambda d: d.popitem(),
        lambda d: d.clear(),
        lambda d: d.__ior__({"stage": "x"}),
    ],
)
def test_error_details_reject_every_mutation(mutate):
    error = TaskError("INTERNAL_ERROR", "broken", {"stage": "parsing"})
    with pytest.raises(TypeError):
        mutate(error.details)
    assert error.details == {"stage": "parsing"}


@pytest.mark.parametrize("details", [{"ratio": float("nan")}, {"ratio": float("inf")}, {"nested": [{1: "x"}]}, {"obj": object()}])
def test_error_details_must_be_strict_json(details):
    with pytest.raises(TypeError):
        TaskError("INTERNAL_ERROR", "broken", details)


# REVIEW-C08 R02: failure codes are the closed, stage-bound set in specs/task-processing.md §6.
FAILURE_CODE_STAGES = {
    "DOCUMENT_UNREADABLE": {"parsing"},
    "LLM_UNAVAILABLE": {"extracting"},
    "EXTRACTION_INCOMPLETE": {"extracting"},
    "CYCLE_DETECTED": {"persisting"},
    "STORAGE_UNAVAILABLE": {"parsing", "extracting", "merging", "persisting"},
    "INTERNAL_ERROR": {"parsing", "extracting", "merging", "persisting"},
    "TASK_ATTEMPTS_EXHAUSTED": {"parsing", "extracting", "merging", "persisting"},
}
PROCESSING = [("parsing", .04), ("extracting", .4), ("merging", .7), ("persisting", .9)]


@pytest.mark.parametrize("stage,progress", PROCESSING)
@pytest.mark.parametrize("code", sorted(FAILURE_CODE_STAGES))
def test_failure_code_is_bound_to_stage(code, stage, progress):
    start = TaskState(stage, progress)
    event = TransitionEvent("fail", error=TaskError(code, "failed"))
    if stage in FAILURE_CODE_STAGES[code]:
        assert apply_event(start, event) == Applied(TaskState("failed", progress, False, event.error), changed=True)
    else:
        assert_rejected(start, event, "error_stage_mismatch")


@pytest.mark.parametrize("code", ["PUBLISH_BLOCKED", "NOT_A_CODE", "VALIDATION_ERROR", "internal_error"])
def test_failure_code_outside_task_table_rejected(code):
    assert_rejected(TaskState("merging", .7), TransitionEvent("fail", error=TaskError(code, "failed")), "invalid_error")


def test_failed_input_state_with_unknown_code_is_invalid():
    assert_rejected(TaskState("failed", .4, error=TaskError("NOT_A_CODE", "broken")), TransitionEvent("claim"), "invalid_state")


# REVIEW-C08 R03: an unknown event kind is not a legal event in the wrong stage.
@pytest.mark.parametrize("kind", ["made_up", "resume", "CLAIM", ""])
def test_unknown_event_kind_is_invalid_event(kind):
    assert_rejected(TaskState("parsing", .04), TransitionEvent(kind), "invalid_event")


def test_known_event_in_wrong_stage_is_invalid_transition():
    assert_rejected(TaskState("parsing", .04), TransitionEvent("published"), "invalid_transition")


# REVIEW-C08 R04: stage names, fixed progress and ranges must not drift from the contracts.
CONTRACTS = Path(__file__).resolve().parents[2] / "src" / "contracts"


def _openapi_schemas():
    return json.loads((CONTRACTS / "v1" / "generated" / "openapi.json").read_text(encoding="utf-8"))["components"]["schemas"]


def _events_stage_table():
    text = (CONTRACTS / "events.v1.md").read_text(encoding="utf-8")
    section = text.split("### 阶段与进度映射", 1)[1]
    rows = {}
    for stages, cell in re.findall(r"^\| (`[^|]+`) \| ([^|]+) \|$", section, re.M):
        for stage in re.findall(r"`([a-z_]+)`", stages):
            numbers = [float(n) for n in re.findall(r"\d+\.\d+", cell)]
            rows[stage] = tuple(numbers) if numbers else None
    return rows


def test_stage_vocabulary_matches_contract_enum():
    from app.services.task_state import TASK_STAGES

    assert list(TASK_STAGES) == _openapi_schemas()["TaskStage"]["enum"]


def test_stage_ranges_match_events_contract():
    from app.services.task_state import TASK_STAGES, stage_progress_range

    table = _events_stage_table()
    assert set(table) == set(TASK_STAGES)
    for stage, expected in table.items():
        if expected is None:  # failed / cancelled keep the value at entry
            continue
        lower, upper = expected if len(expected) == 2 else (expected[0], expected[0])
        assert stage_progress_range(stage) == (lower, upper), stage


def test_fixed_progress_matches_contract_consts():
    from app.services.task_state import stage_progress_range

    schemas = _openapi_schemas()
    fixed = {
        rule["if"]["properties"]["stage"]["const"]: rule["then"]["properties"]["progress"]["const"]
        for rule in schemas["FixedStageProgress"]["allOf"]
    }
    completed = next(part for part in schemas["TaskCompleted"]["allOf"] if "properties" in part)
    fixed["completed"] = completed["properties"]["progress"]["const"]
    assert fixed == {"queued": 0, "awaiting_review": .95, "completed": 1}
    for stage, value in fixed.items():
        assert stage_progress_range(stage) == (value, value)


def test_failure_codes_exist_in_contract_error_code_enum():
    from app.services.task_state import FAILURE_CODE_STAGES as implemented

    assert {code: set(stages) for code, stages in implemented.items()} == FAILURE_CODE_STAGES
    assert set(implemented) <= set(_openapi_schemas()["ErrorCode"]["enum"])
