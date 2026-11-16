"""Read-only, course-scoped activity inputs from the existing durable ledgers."""

from dataclasses import dataclass
import sqlite3
from typing import Any

from app.repositories.fusion_decisions import read_progress
from app.repositories.sqlite import connect


@dataclass(frozen=True)
class ActivityInputs:
    task: dict[str, Any]
    chunks: tuple[tuple[str, str, str], ...]
    checkpoints: tuple[tuple[str, str, str], ...]
    decisions_completed: int
    pending_calls: tuple[tuple[str, int, str], ...]
    latest_work_at: tuple[str, ...]
    global_disambiguation: dict[str, Any] | None


def read_activity(sqlite_url: str, task_id: str, *, course_id: str,
                  now: float | None = None) -> ActivityInputs | None:
    """Read one consistent snapshot; never fetch prompts, results, source text or keys."""
    with connect(sqlite_url) as database:
        database.row_factory = sqlite3.Row
        database.execute("BEGIN")
        try:
            row = database.execute(
                """SELECT t.id,t.stage,t.progress,t.cancel_requested,t.attempt,t.created_at,t.updated_at,
                          t.lease_owner,t.lease_token,t.lease_expires_at,t.not_before,t.cleanup_pending,
                          t.t6_seq,t.created_by,
                          EXISTS(SELECT 1 FROM materials m WHERE m.id=t.document_id
                                 AND m.course_id=t.course_id) AS material_exists,
                          EXISTS(SELECT 1 FROM task_revisions r WHERE r.task_id=t.id
                                 AND r.course_id=t.course_id AND r.material_id=t.document_id) AS has_revision
                   FROM processing_tasks t WHERE t.id=? AND t.course_id=?""",
                (task_id, course_id),
            ).fetchone()
            if row is None:
                return None
            chunks = database.execute(
                """SELECT c.chunk_id,c.revision_id,c.section_titles FROM chunks c
                   JOIN task_revisions r ON r.revision_id=c.revision_id AND r.course_id=c.course_id
                   WHERE r.task_id=? AND r.course_id=?""", (task_id, course_id),
            ).fetchall()
            checkpoints = database.execute(
                """SELECT unit_kind,unit_id,status FROM task_chunk_checkpoints
                   WHERE task_id=? AND course_id=?""", (task_id, course_id),
            ).fetchall()
            decisions = database.execute(
                "SELECT count(*) FROM task_section_decisions WHERE task_id=? AND course_id=?",
                (task_id, course_id),
            ).fetchone()[0]
            pending = database.execute(
                """SELECT purpose,count(*),min(created_at) AS started_at FROM model_calls
                   WHERE task_id=? AND course_id=? AND task_attempt=? AND status='sent'
                   GROUP BY purpose ORDER BY started_at,purpose""", (task_id, course_id, row["attempt"]),
            ).fetchall()
            latest = []
            for table, expression in (
                ("model_calls", "COALESCE(finished_at,created_at)"),
                ("task_chunk_checkpoints", "created_at"),
                ("task_section_decisions", "created_at"),
            ):
                stamp = database.execute(
                    f"SELECT max({expression}) FROM {table} WHERE task_id=? AND course_id=?",
                    (task_id, course_id),
                ).fetchone()[0]
                if stamp is not None:
                    latest.append(stamp)
            global_progress = read_progress(database, course_id=course_id, task_id=task_id, now=now)
            if global_progress is not None:
                latest.append(global_progress["updated_at"])
            return ActivityInputs(
                task=dict(row), chunks=tuple(tuple(item) for item in chunks),
                checkpoints=tuple(tuple(item) for item in checkpoints), decisions_completed=decisions,
                pending_calls=tuple(tuple(item) for item in pending), latest_work_at=tuple(latest),
                global_disambiguation=global_progress,
            )
        finally:
            database.execute("ROLLBACK")
