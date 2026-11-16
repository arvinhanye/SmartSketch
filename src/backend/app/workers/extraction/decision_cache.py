"""Short, lease-fenced transactions for reusable complete semantic decisions."""
from collections.abc import Callable, Mapping
from contextlib import contextmanager
import sqlite3

from app.repositories.section_decisions import has_live_lease, put_decision, read_decision
from app.repositories.task_leases import Lease, LeaseLost, leased_transaction
from app.repositories.tasks import read_leased_task
from app.workers.extraction.types import _Halt


class SectionDecisionCache:
    def __init__(self, sqlite_url: str, lease: Lease, section_id: str, *,
                 guard: Callable[[], None] | None = None) -> None:
        self.sqlite_url, self.lease, self.section_id = sqlite_url, lease, section_id
        self.guard = guard

    @contextmanager
    def _transaction(self, *, saving_complete: bool = False):
        try:
            if self.guard is not None:
                self.guard()
            with leased_transaction(self.sqlite_url, self.lease.task_id, self.lease.token) as db:
                if not has_live_lease(db, task_id=self.lease.task_id, token=self.lease.token):
                    raise _Halt('lost')
                task = read_leased_task(db, self.lease.task_id, self.lease.token)
                if task is None or task.course_id != self.lease.course_id or task.stage != 'extracting':
                    raise _Halt('lost')
                if task.cancel_requested and not saving_complete:
                    raise _Halt('cancel')
                yield db
        except LeaseLost as exc:
            raise _Halt('lost') from exc
        except sqlite3.Error as exc:
            raise _Halt('storage') from exc

    def get(self, digest: str, left: str, right: str) -> dict | None:
        with self._transaction() as db:
            return read_decision(db, course_id=self.lease.course_id, task_id=self.lease.task_id,
                                 section_id=self.section_id, input_digest=digest,
                                 left_id=left, right_id=right)

    def put(self, digest: str, decision: Mapping) -> None:
        # A request already in flight may finish after cancellation was requested.
        # Keep its complete result while the original extracting lease is still live.
        with self._transaction(saving_complete=True) as db:
            put_decision(db, course_id=self.lease.course_id, task_id=self.lease.task_id,
                         section_id=self.section_id, input_digest=digest, decision=decision)
