"""One bounded global pair pool, with durable completed decisions and lease fences."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import threading

from app.repositories import fusion_decisions as rows
from app.repositories.section_decisions import has_live_lease
from app.repositories.task_leases import LeaseLost, leased_transaction
from app.repositories.tasks import read_leased_task
from app.services.fusion.judge import FusionEntity
from app.services.fusion.resolution import SemanticDecision


class FusionCancelled(Exception):
    pass


class FusionInterrupted(Exception):
    pass


@dataclass(frozen=True)
class DecisionWork:
    left_id: str
    right_id: str
    left: FusionEntity | None
    right: FusionEntity | None
    deferred_code: str | None = None

    def identity(self):
        return dict(left_id=self.left_id,right_id=self.right_id,code=self.deferred_code)


class FusionDecisionCache:
    def __init__(self, sqlite_url, lease, *, credential_guard=None):
        self.sqlite_url,self.lease,self.credential_guard = sqlite_url,lease,credential_guard
        self.stop = threading.Event()
        self._failure_lock = threading.Lock()
        self.failure = None

    def abort(self, error):
        with self._failure_lock:
            if self.failure is None:
                self.failure = error
            self.stop.set()
            return self.failure

    @contextmanager
    def transaction(self, *, saving_complete=False):
        with leased_transaction(self.sqlite_url,self.lease.task_id,self.lease.token) as db:
            # Serialize the read-only credential check with revocation writes.
            # No network call is made while holding this short transaction.
            if self.credential_guard is not None:
                self.credential_guard()
            task = read_leased_task(db,self.lease.task_id,self.lease.token)
            if (not has_live_lease(db,task_id=self.lease.task_id,token=self.lease.token)
                or task is None or task.course_id != self.lease.course_id or task.stage != 'merging'):
                raise LeaseLost('global semantic lease no longer valid')
            if task.cancel_requested and not saving_complete:
                raise FusionCancelled()
            yield db

    def request_guard(self):
        if self.stop.is_set():
            raise FusionInterrupted()
        with self.transaction():
            pass
        if self.stop.is_set():
            raise FusionInterrupted()

    def scope(self, digest):
        return dict(course_id=self.lease.course_id,task_id=self.lease.task_id,input_digest=digest)


def _restore(payload):
    value = dict(payload)
    for field in ('left_source_ids','right_source_ids','differences','model_ids'):
        value[field] = tuple(value.get(field,()))
    return SemanticDecision(**value)


def run_decisions(cache, digest, items, *, resolver, total_possible, max_concurrency, context=None):
    """Complete only unfinished pairs; collect in plan order regardless of finish order."""
    if type(max_concurrency) is not int or max_concurrency < 1:
        raise ValueError('global pair concurrency must be positive')
    scope = cache.scope(digest)
    with cache.transaction() as db:
        rows.initialize_plan(db,**scope,pairs=[i.identity() for i in items],total_possible=total_possible,
                             attempt=cache.lease.attempt,context=context)
        complete = rows.read_complete(db,**scope)
    results = {key:_restore(value) for key,value in complete.items()}
    remaining = iter(i for i in items if (i.left_id,i.right_id) not in results)
    failure = None

    def work(item):
        try:
            cache.request_guard()
            with cache.transaction() as db:
                rows.mark_running(db,**scope,left_id=item.left_id,right_id=item.right_id,attempt=cache.lease.attempt)
            cache.request_guard()
            decision = (SemanticDecision(item.left_id,item.right_id,'deferred',code=item.deferred_code)
                        if item.deferred_code else resolver.resolve(item.left,item.right))
            with cache.transaction(saving_complete=decision.status=='complete') as db:
                rows.put_result(db,**scope,decision=asdict(decision),attempt=cache.lease.attempt)
            return decision
        except BaseException as exc:
            cache.abort(exc)
            raise

    with ThreadPoolExecutor(max_workers=max_concurrency,thread_name_prefix='fusion-pair') as pool:
        pending = set()
        exhausted = False
        while pending or not exhausted:
            while failure is None and not exhausted and len(pending)<max_concurrency:
                try:
                    cache.request_guard()
                    item = next(remaining)
                except StopIteration:
                    exhausted = True
                    break
                except BaseException as exc:
                    failure = cache.abort(exc);exhausted=True
                    break
                pending.add(pool.submit(work,item))
            if not pending:
                break
            finished,_ = wait(pending,return_when=FIRST_COMPLETED)
            for future in finished:
                pending.remove(future)
                try:
                    decision = future.result()
                    results[(decision.left_id,decision.right_id)] = decision
                except BaseException as exc:
                    if failure is None:
                        failure=cache.abort(exc);exhausted=True
    if failure is not None:
        raise failure
    with cache.transaction() as db:
        rows.finish_plan(db,**scope)
    return [results[(item.left_id,item.right_id)] for item in items]
