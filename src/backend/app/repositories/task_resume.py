"""Atomic, course-scoped reads and writes for explicit cancelled-task resume."""
from dataclasses import dataclass, field
import sqlite3

from app.repositories.model_configs import SealedKey
from app.repositories.tasks import TaskSnapshotRow, read_task_snapshot


@dataclass(frozen=True)
class ResumeContext:
    snapshot: TaskSnapshotRow
    created_by: str | None
    has_lease: bool
    artifacts_available: bool
    has_revision: bool


@dataclass(frozen=True)
class ResumeCredential:
    user_id: str
    compatible: bool
    version: int
    sealed: SealedKey = field(repr=False)


def read_context(db: sqlite3.Connection, task_id: str, course_id: str) -> ResumeContext | None:
    snapshot = read_task_snapshot(db, task_id, course_id=course_id)
    if snapshot is None:
        return None
    row = db.execute('''SELECT created_by,
        lease_owner IS NOT NULL OR lease_token IS NOT NULL OR lease_expires_at IS NOT NULL,
        cleanup_pending=0 AND t6_seq IS NULL AND EXISTS(
            SELECT 1 FROM materials m WHERE m.id=t.document_id AND m.course_id=t.course_id),
        EXISTS(SELECT 1 FROM task_revisions r WHERE r.task_id=t.id
            AND r.course_id=t.course_id AND r.material_id=t.document_id)
        FROM processing_tasks t WHERE id=? AND course_id=?''', (task_id, course_id)).fetchone()
    return ResumeContext(snapshot, row[0], bool(row[1]), bool(row[2]), bool(row[3]))


def read_credential(db: sqlite3.Connection, task_id: str, user_id: str) -> ResumeCredential | None:
    row = db.execute('''SELECT c.user_id,c.version,c.key_ciphertext,c.key_nonce,
        b.user_id=c.user_id AND b.base_url=c.base_url AND b.model=c.model
            AND b.disable_thinking=c.disable_thinking
        FROM user_model_configs c LEFT JOIN task_model_bindings b ON b.task_id=?
        WHERE c.user_id=?''', (task_id, user_id)).fetchone()
    if row is None:
        return None
    return ResumeCredential(row[0], bool(row[4]), row[1], SealedKey(bytes(row[2]), bytes(row[3])))


def restore_credential(db: sqlite3.Connection, task_id: str, credential: ResumeCredential) -> None:
    changed = db.execute('''UPDATE task_model_bindings SET config_version=?,key_ciphertext=?,key_nonce=?,
        scrubbed_at=NULL,scrub_reason=NULL WHERE task_id=? AND user_id=?''',
        (credential.version, credential.sealed.ciphertext, credential.sealed.nonce, task_id, credential.user_id)).rowcount
    if changed != 1:
        raise RuntimeError('task credential binding changed during resume')


def resume_cancelled(db: sqlite3.Connection, task_id: str, course_id: str, stage: str) -> bool:
    return db.execute('''UPDATE processing_tasks SET stage=?,cancel_requested=0,
        resume_attempt_base=attempt,resume_count=resume_count+1,not_before=0,
        updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
        WHERE id=? AND course_id=? AND stage='cancelled' AND cancel_requested=1
          AND lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL
          AND cleanup_pending=0 AND t6_seq IS NULL''', (stage, task_id, course_id)).rowcount == 1
