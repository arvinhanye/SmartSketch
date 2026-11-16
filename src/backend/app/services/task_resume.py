"""Explicit, guarded continuation of a cancelled task using its saved artifacts."""
from app.config import Settings
from app.repositories import task_resume as rows
from app.repositories.tasks import cancel_transaction, read_task_snapshot
from app.services.access import role_forbidden
from app.services.credentials import CredentialCipher, CredentialError, ModelConfigRequired
from app.services.task_cancel import TaskNotFound, TaskSnapshot, snapshot_from_row
from app.services.task_state import Applied, TaskState, TransitionEvent, apply_event


class TaskNotResumable(Exception):
    def __init__(self, stage: str, reason: str):
        self.stage, self.reason = stage, reason
        super().__init__(reason)


def resume_task(settings: Settings, task_id: str, *, course_id: str, user_id: str) -> TaskSnapshot:
    # The same lock serializes resume, cancellation, credential scrub and worker claims.
    with cancel_transaction(settings.SQLITE_URL) as db:
        context = rows.read_context(db, task_id, course_id)
        if context is None:
            raise TaskNotFound(task_id)
        task = snapshot_from_row(context.snapshot)
        if settings.LLM_MODE == 'personal' and context.created_by != user_id:
            raise role_forbidden()
        if task.stage != 'cancelled':
            raise TaskNotResumable(task.stage, 'not_cancelled')
        if context.has_lease:
            raise TaskNotResumable(task.stage, 'worker_active')
        decision = apply_event(TaskState(task.stage, task.progress, task.cancel_requested), TransitionEvent('resume'))
        if (not isinstance(decision, Applied) or not context.artifacts_available or
                (decision.state.stage in ('extracting', 'merging') and not context.has_revision)):
            raise TaskNotResumable(task.stage, 'artifacts_missing')
        if settings.LLM_MODE == 'personal':
            credential = rows.read_credential(db, task_id, user_id)
            if credential is None:
                raise ModelConfigRequired()
            if not credential.compatible:
                raise TaskNotResumable(task.stage, 'model_config_changed')
            try:
                CredentialCipher.from_settings(settings).open(user_id, credential.sealed)
            except CredentialError:
                raise ModelConfigRequired() from None
            rows.restore_credential(db, task_id, credential)
        if not rows.resume_cancelled(db, task_id, course_id, decision.state.stage):
            raise TaskNotResumable(task.stage, 'not_cancelled')
        return snapshot_from_row(read_task_snapshot(db, task_id, course_id=course_id))
