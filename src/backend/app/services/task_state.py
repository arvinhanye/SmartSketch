"""Pure task-state transitions; persistence/CAS belongs to C09.

The transition vocabulary and guards follow ``specs/task-processing.md`` §2.
Callers must commit an accepted state with their own conditional write before
emitting an event; this function performs no I/O and does not settle races.
"""

from dataclasses import dataclass
from math import isfinite
from typing import Mapping


class _FrozenDetails(dict):
    """A ``dict`` that refuses mutation, so ``json.dumps``/``asdict``/pickle still work."""

    def _readonly(self, *args: object, **kwargs: object) -> None:
        raise TypeError("error details are immutable")

    __setitem__ = __delitem__ = __ior__ = _readonly
    clear = pop = popitem = setdefault = update = _readonly

    def __reduce__(self) -> tuple[type, tuple[dict[str, object]]]:
        return (type(self), (dict(self),))


def _freeze_detail(value: object) -> object:
    """Copy strict-JSON error details so terminal errors cannot change by alias."""
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("error detail keys must be strings")
        return _FrozenDetails({key: _freeze_detail(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_detail(item) for item in value)
    if isinstance(value, float) and not isfinite(value):
        raise TypeError("error details must be finite JSON numbers")
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    raise TypeError("error details must contain JSON-like values")


@dataclass(frozen=True)
class TaskError:
    code: str
    message: str
    details: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.details is not None:
            if not isinstance(self.details, Mapping):
                raise TypeError("error details must be a mapping")
            object.__setattr__(self, "details", _freeze_detail(self.details))


@dataclass(frozen=True)
class TaskState:
    stage: str
    progress: float
    cancel_requested: bool = False
    error: TaskError | None = None


@dataclass(frozen=True)
class TransitionEvent:
    kind: str
    progress: float | None = None
    error: TaskError | None = None


@dataclass(frozen=True)
class Applied:
    state: TaskState
    changed: bool


@dataclass(frozen=True)
class Rejected:
    state: TaskState
    reason: str


TASK_STAGES = (
    "queued",
    "parsing",
    "extracting",
    "merging",
    "persisting",
    "awaiting_review",
    "completed",
    "failed",
    "cancelled",
)
_RANGES = {
    "queued": (0.0, 0.0),
    "parsing": (0.0, 0.10),
    "extracting": (0.10, 0.60),
    "merging": (0.60, 0.80),
    "persisting": (0.80, 0.95),
    "awaiting_review": (0.95, 0.95),
    "completed": (1.0, 1.0),
    "failed": (0.0, 0.95),
    "cancelled": (0.0, 0.80),
}
_TERMINAL = frozenset({"completed", "failed", "cancelled"})
_CANCELLABLE = frozenset({"parsing", "extracting", "merging"})
_PROCESSING = _CANCELLABLE | {"persisting"}
_NEXT = {"parsing": "extracting", "extracting": "merging", "merging": "persisting"}
_EVENT_KINDS = frozenset(
    {"claim", "stage_done", "checkpoint", "progress", "persisted", "fail", "cancel_request", "published"}
)
# specs/task-processing.md §6: closed failure-code set and the stages that may raise each code.
FAILURE_CODE_STAGES = {
    "DOCUMENT_UNREADABLE": frozenset({"parsing"}),
    "LLM_UNAVAILABLE": frozenset({"extracting"}),
    "EXTRACTION_INCOMPLETE": frozenset({"extracting"}),
    "CYCLE_DETECTED": frozenset({"persisting"}),
    "STORAGE_UNAVAILABLE": _PROCESSING,
    "INTERNAL_ERROR": _PROCESSING,
    "TASK_ATTEMPTS_EXHAUSTED": _PROCESSING,
}


def stage_progress_range(stage: str) -> tuple[float, float]:
    """Allowed ``progress`` bounds for a stage (``events.v1.md`` stage table)."""
    return _RANGES[stage]


def _valid_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _valid_error(error: object) -> bool:
    return (
        isinstance(error, TaskError)
        and isinstance(error.code, str)
        and error.code in FAILURE_CODE_STAGES
        and isinstance(error.message, str)
        and bool(error.message.strip())
        and (error.details is None or isinstance(error.details, Mapping))
    )


def _valid_state(state: TaskState) -> bool:
    if not isinstance(state, TaskState) or not isinstance(state.stage, str) or state.stage not in _RANGES or not _valid_number(state.progress):
        return False
    lower, upper = _RANGES[state.stage]
    if not lower <= state.progress <= upper or not isinstance(state.cancel_requested, bool):
        return False
    if (state.stage == "failed") != (state.error is not None):
        return False
    if state.error is not None and not _valid_error(state.error):
        return False
    if state.stage == "cancelled" and not state.cancel_requested:
        return False
    if state.cancel_requested and state.stage in {"queued", "persisting", "awaiting_review", "completed"}:
        return False
    return True


def apply_event(state: TaskState, event: TransitionEvent) -> Applied | Rejected:
    """Apply one event or return a reason without changing the input state."""
    def reject(reason: str) -> Rejected:
        return Rejected(state, reason)

    def accept(next_state: TaskState) -> Applied:
        return Applied(next_state, changed=next_state != state)

    if not _valid_state(state):
        return reject("invalid_state")
    if not isinstance(event, TransitionEvent):
        return reject("invalid_event")
    if state.stage in _TERMINAL:
        return reject("already_terminal")

    kind = event.kind
    if not isinstance(kind, str) or kind not in _EVENT_KINDS:
        return reject("invalid_event")
    if kind == "progress":
        if event.error is not None or not _valid_number(event.progress):
            return reject("invalid_event")
    elif event.progress is not None or (kind != "fail" and event.error is not None):
        return reject("invalid_event")

    if kind == "cancel_request":
        if state.stage == "queued":
            return accept(TaskState("cancelled", state.progress, True))
        if state.stage in _CANCELLABLE:
            return accept(TaskState(state.stage, state.progress, True))
        if state.stage == "persisting":
            return reject("persisting_uninterruptible")
        return reject("processing_finished")

    if kind == "claim" and state.stage == "queued":
        return accept(TaskState("parsing", 0))

    if kind in {"stage_done", "checkpoint"} and state.stage in _CANCELLABLE:
        if state.cancel_requested:
            return accept(TaskState("cancelled", state.progress, True))
        if kind == "checkpoint":
            return accept(state)
        next_stage = _NEXT[state.stage]
        return accept(TaskState(next_stage, max(state.progress, _RANGES[next_stage][0])))

    if kind == "progress" and state.stage in _PROCESSING:
        if event.progress < state.progress:
            return reject("progress_regression")
        lower, upper = _RANGES[state.stage]
        if not lower <= event.progress <= upper:
            return reject("progress_out_of_stage")
        return accept(TaskState(state.stage, event.progress, state.cancel_requested))

    if kind == "persisted" and state.stage == "persisting":
        return accept(TaskState("awaiting_review", .95))

    if kind == "fail" and state.stage in _PROCESSING:
        if not _valid_error(event.error):
            return reject("invalid_error")
        if state.stage not in FAILURE_CODE_STAGES[event.error.code]:
            return reject("error_stage_mismatch")
        return accept(TaskState("failed", state.progress, state.cancel_requested, event.error))

    if kind == "published" and state.stage == "awaiting_review":
        return accept(TaskState("completed", 1))

    return reject("invalid_transition")
