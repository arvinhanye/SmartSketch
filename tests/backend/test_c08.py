"""C08: pure document-task state transitions from ADR-010 §2."""

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
    assert_rejected(start, TransitionEvent("made_up"))


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
