"""Immutable local semantic decisions. The caller owns the lease and stage checks."""

from collections.abc import Mapping
import json
import sqlite3


def has_live_lease(db: sqlite3.Connection, *, task_id: str, token: str) -> bool:
    return db.execute(
        'SELECT 1 FROM processing_tasks WHERE id=? AND lease_token=? AND lease_expires_at>unixepoch()',
        (task_id, token),
    ).fetchone() is not None


def read_decision(
    db: sqlite3.Connection, *, course_id: str, task_id: str, section_id: str,
    input_digest: str, left_id: str, right_id: str,
) -> dict | None:
    row = db.execute(
        """SELECT decision FROM task_section_decisions
        WHERE course_id=? AND task_id=? AND section_id=? AND input_digest=?
          AND left_id=? AND right_id=?""",
        (course_id, task_id, section_id, input_digest, left_id, right_id),
    ).fetchone()
    return None if row is None else json.loads(row[0])


def put_decision(
    db: sqlite3.Connection, *, course_id: str, task_id: str, section_id: str,
    input_digest: str, decision: Mapping[str, object],
) -> bool:
    """Insert a complete decision once inside the caller's leased transaction."""
    if not db.in_transaction:
        raise RuntimeError("put_decision requires the caller's leased transaction")
    if not isinstance(decision, Mapping) or decision.get("status") != "complete":
        raise ValueError("only complete semantic decisions can be cached")
    if decision.get("verdict") not in ("SAME", "DIFFERENT", "UNCERTAIN"):
        raise ValueError("invalid semantic verdict")
    left_id, right_id = decision.get("left_id"), decision.get("right_id")
    scope = (course_id, task_id, section_id, input_digest, left_id, right_id)
    if any(not isinstance(value, str) or not value.strip() for value in scope):
        raise ValueError("decision scope and pair IDs must be nonempty strings")
    if left_id >= right_id:
        raise ValueError("semantic pair IDs must be distinct and ordered")
    return db.execute(
        """INSERT INTO task_section_decisions
        (course_id, task_id, section_id, input_digest, left_id, right_id, decision)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(task_id, section_id, input_digest, left_id, right_id) DO NOTHING""",
        (*scope, json.dumps(dict(decision), ensure_ascii=False, sort_keys=True, allow_nan=False)),
    ).rowcount == 1
