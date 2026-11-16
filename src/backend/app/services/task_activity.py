"""Describe actual completed work and in-flight requests without synthetic progress."""

from datetime import datetime, timezone
from collections import Counter
import hashlib
import json
import time

from app.repositories.task_activity import read_activity
from app.schemas.task_activity import TaskActivity


_PROCESSING = frozenset({"parsing", "extracting", "merging", "persisting"})
_TERMINAL = frozenset({"cancelled", "failed", "completed", "awaiting_review"})
_RELATIONS = frozenset({"extract_relations", "extract_normalized_relations"})
_ENTITIES = frozenset({"extract_entities", "extract_entities_gleaning"})
_SAFE_PURPOSES = _RELATIONS | _ENTITIES | {
    "resolve_duplicate", "judge_duplicate", "summarize_definition", "repair", "embedding",
}


def _stamp(now: float) -> str:
    return datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def get_activity(
    sqlite_url: str, task_id: str, *, course_id: str, viewer_id: str, personal: bool = False,
    now: float | None = None,
) -> TaskActivity | None:
    now = time.time() if now is None else now
    inputs = read_activity(sqlite_url, task_id, course_id=course_id, now=now)
    if inputs is None:
        return None
    task = inputs.task
    stage = task["stage"]
    worker_active = bool(
        stage in _PROCESSING and task["lease_owner"] and task["lease_token"]
        and task["lease_expires_at"] is not None and task["lease_expires_at"] > now
    )
    active = [dict(purpose=purpose, count=count, started_at=started)
              for purpose, count, started in inputs.pending_calls
              if worker_active and purpose in _SAFE_PURPOSES]
    retry_at = (_stamp(task["not_before"]) if stage in _PROCESSING and not worker_active
                and task["not_before"] is not None and task["not_before"] > now else None)
    if stage in _TERMINAL:
        phase = stage
    elif task["cancel_requested"]:
        phase = "cancelling"
    elif retry_at is not None:
        phase = "retrying"
    elif stage == "queued":
        phase = "queued"
    elif not worker_active:
        phase = "waiting"
    elif stage not in {"extracting", "merging"}:
        phase = stage
    else:
        purposes = {item["purpose"] for item in active}
        if purposes & _RELATIONS:
            phase = "relations"
        elif "resolve_duplicate" in purposes:
            phase = "disambiguating"
        elif purposes & _ENTITIES:
            phase = "entities"
        elif "repair" in purposes:
            phase = "repair"
        else:
            phase = "merging" if stage == "merging" else "waiting"
    chunk_ids = {chunk_id for chunk_id, _, _ in inputs.chunks}
    # Same immutable section identity as the extraction worker: revision plus title path.
    section_ids = {
        "sec_" + hashlib.sha256(json.dumps([revision, json.loads(titles)], ensure_ascii=False).encode()).hexdigest()
        for _, revision, titles in inputs.chunks
    }
    valid_units = {"chunk": chunk_ids, "section": section_ids}
    counts = Counter((kind, status) for kind, unit_id, status in inputs.checkpoints
                     if unit_id in valid_units.get(kind, ()))
    resumable = bool(
        stage == "cancelled" and task["lease_owner"] is None and task["lease_token"] is None
        and task["lease_expires_at"] is None and not task["cleanup_pending"] and task["t6_seq"] is None
        and task["material_exists"] and (task["progress"] < 0.1 or task["has_revision"])
        and (not personal or task["created_by"] == viewer_id)
    )
    global_progress = None if inputs.global_disambiguation is None else {
        key: inputs.global_disambiguation[key] for key in (
            "total", "completed", "failed", "deferred", "reused", "inflight", "pending",
            "total_possible", "phase", "updated_at",
        )
    }
    return TaskActivity.model_validate(dict(
        task_id=task_id, stage=stage, progress=1 if stage == "completed" else task["progress"],
        cancel_requested=bool(task["cancel_requested"]), phase=phase, attempt=task["attempt"],
        observed_at=_stamp(now), last_activity_at=max((task["updated_at"], *inputs.latest_work_at)),
        worker_active=worker_active, retry_at=retry_at, active_requests=active,
        chunks=dict(completed=counts.get(("chunk", "done"), 0), failed=counts.get(("chunk", "failed"), 0),
                    total=len(chunk_ids)),
        sections=dict(completed=counts.get(("section", "done"), 0), failed=counts.get(("section", "failed"), 0),
                      total=len(section_ids)),
        disambiguation=dict(completed=inputs.decisions_completed),
        global_disambiguation=global_progress, resumable=resumable,
    ))
