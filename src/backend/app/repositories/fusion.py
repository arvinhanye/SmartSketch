"""Immutable fusion plans and atomic SQLite draft-head selection.

Mutation helpers never open their own transaction: lease/course-lock fencing and
T6 are owned by the service/worker. A prepared graph generation is not visible.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import sqlite3

from app.repositories.neo4j import GraphScope


class StaleFusionPlan(RuntimeError):
    pass


@dataclass(frozen=True)
class DraftHead:
    course_id: str
    draft_revision: int
    storage_version_id: str
    effective_task_ids: tuple[str, ...]
    review_decisions: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class FusionPlan:
    plan_id: str
    course_id: str
    task_id: str
    head: DraftHead
    input_digest: str
    storage_version_id: str
    payload: dict = field(repr=False)
    state: str = "prepared"
    applied: bool = False
    reason: str | None = None


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def read_draft_head(database: sqlite3.Connection, course_id: str) -> DraftHead:
    row = database.execute("""SELECT c.draft_revision, c.draft_storage_version,
        (SELECT json_group_array(id) FROM (SELECT id FROM processing_tasks
         WHERE course_id=c.id AND stage IN ('awaiting_review','completed') ORDER BY id)),
        (SELECT json_group_array(json_array(kind,item_key)) FROM
          (SELECT kind,item_key FROM review_dismissals WHERE course_id=c.id ORDER BY kind,item_key))
        FROM courses c WHERE c.id=?""", (course_id,)).fetchone()
    if row is None: raise LookupError("course not found")
    return DraftHead(course_id, int(row[0]), row[1], tuple(json.loads(row[2])),
                     tuple(tuple(r) for r in json.loads(row[3])))


def read_draft_scope(database: sqlite3.Connection, course_id: str) -> GraphScope:
    try:
        head = read_draft_head(database, course_id)
    except LookupError:
        # Preserve legacy repository callers with task-only fixtures/imports.
        # New projection preparation still requires read_draft_head and a real course.
        from app.repositories.tasks import read_effective_task_ids
        return GraphScope(course_id, "draft", read_effective_task_ids(database, course_id))
    return GraphScope(course_id, "draft", head.effective_task_ids,
                      storage_version_id=None if head.storage_version_id == "draft" else head.storage_version_id)


def _transaction(database):
    if not database.in_transaction: raise RuntimeError("fusion mutation needs a fenced transaction")


_COLUMNS = "plan_id,course_id,task_id,head_json,input_digest,storage_version_id,payload,state,applied,reason"


def _plan(row) -> FusionPlan | None:
    if row is None: return None
    head = json.loads(row[3]); head["effective_task_ids"] = tuple(head["effective_task_ids"])
    head["review_decisions"] = tuple(tuple(r) for r in head.get("review_decisions", ()))
    return FusionPlan(row[0], row[1], row[2], DraftHead(**head), row[4], row[5], json.loads(row[6]),
                      row[7], bool(row[8]), row[9])


def get_plan(database, course_id: str, plan_id: str) -> FusionPlan | None:
    return _plan(database.execute(f"SELECT {_COLUMNS} FROM fusion_plans WHERE course_id=? AND plan_id=?",
                                   (course_id, plan_id)).fetchone())


def task_plan(database, course_id: str, task_id: str) -> FusionPlan | None:
    return _plan(database.execute(f"SELECT {_COLUMNS} FROM fusion_plans WHERE course_id=? AND task_id=? "
                                  "ORDER BY rowid DESC LIMIT 1", (course_id, task_id)).fetchone())


def list_plans(database, course_id: str) -> tuple[FusionPlan, ...]:
    return tuple(_plan(row) for row in database.execute(
        f"SELECT {_COLUMNS} FROM fusion_plans WHERE course_id=? ORDER BY rowid", (course_id,)))


def latest_review_plan(database, course_id: str) -> FusionPlan | None:
    """Only T6-visible tasks can supply review conclusions; prefer newest T6."""
    columns = ','.join('p.'+column for column in _COLUMNS.split(','))
    return _plan(database.execute(f"""SELECT {columns} FROM fusion_plans p
        JOIN processing_tasks t ON t.id=p.task_id AND t.course_id=p.course_id
        WHERE p.course_id=? AND t.stage IN ('awaiting_review','completed')
          AND p.state IN ('committed','skipped')
        ORDER BY t.t6_seq DESC,p.rowid DESC LIMIT 1""", (course_id,)).fetchone())


def review_snapshot(sqlite_url: str, course_id: str):
    """One SQLite read snapshot for the graph scope and its semantic decision head."""
    from app.repositories.sqlite import connect
    with connect(sqlite_url) as db:
        db.execute('BEGIN')
        head = read_draft_head(db,course_id)
        scope = read_draft_scope(db,course_id)
        plan = latest_review_plan(db,course_id)
        undone = () if plan is None else undone_groups(db,course_id,plan.plan_id)
        return head,scope,plan,undone


def merge_history_page(sqlite_url: str, course_id: str, *, after, limit: int):
    """Keep history rows and the revision used by its undo buttons in one snapshot."""
    from app.repositories.sqlite import connect
    with connect(sqlite_url) as db:
        db.execute('BEGIN')
        return read_draft_head(db,course_id),merge_history(db,course_id,after=after,limit=limit)


def merge_history(database, course_id: str, *, after: tuple[int,int] | None, limit: int) -> list[dict]:
    """Bounded public group summaries; no whole graph payload leaves this repository."""
    sequence, index = (None,None) if after is None else after
    rows = database.execute("""SELECT p.rowid,CAST(g.key AS INTEGER),p.plan_id,p.task_id,
        json_extract(g.value,'$.group_id'),json_extract(g.value,'$.canonical_id'),p.created_at,u.created_at,
        (SELECT json_group_array(json_object('id',json_extract(n.value,'$.kp_id'),
                'name',json_extract(n.value,'$.name'),'type',json_extract(n.value,'$.type')))
         FROM json_each(p.payload,'$.before.nodes') n
         WHERE json_extract(n.value,'$.kp_id') IN (SELECT value FROM json_each(g.value,'$.members')))
        FROM fusion_plans p JOIN json_each(p.payload,'$.groups') g
        LEFT JOIN fusion_undos u ON u.course_id=p.course_id AND u.plan_id=p.plan_id
             AND u.group_id=json_extract(g.value,'$.group_id')
        WHERE p.course_id=? AND p.state='committed' AND p.applied=1
          AND (? IS NULL OR p.rowid<? OR (p.rowid=? AND CAST(g.key AS INTEGER)>?))
        ORDER BY p.rowid DESC,CAST(g.key AS INTEGER) ASC LIMIT ?""",
        (course_id,sequence,sequence,sequence,index,limit)).fetchall()
    return [dict(sequence=row[0],index=row[1],plan_id=row[2],task_id=row[3],group_id=row[4],canonical_id=row[5],
        created_at=row[6],undone_at=row[7],status='undone' if row[7] else 'applied',
        members=sorted(json.loads(row[8]),key=lambda n:n['id'])) for row in rows]


def put_plan(database, *, course_id: str, task_id: str, head: DraftHead,
             input_digest: str, payload: dict) -> FusionPlan:
    _transaction(database)
    if head.course_id != course_id or not input_digest:
        raise ValueError("invalid fusion plan scope")
    task = database.execute("SELECT 1 FROM processing_tasks WHERE id=? AND course_id=?", (task_id, course_id)).fetchone()
    if task is None: raise ValueError("task outside course")
    digest = hashlib.sha256(_json([course_id, task_id, input_digest]).encode()).hexdigest()[:40]
    plan_id, storage = "fplan_"+digest, "draftgen_"+digest
    database.execute("""INSERT INTO fusion_plans
        (plan_id,course_id,task_id,head_json,input_digest,storage_version_id,payload)
        VALUES (?,?,?,?,?,?,?) ON CONFLICT(course_id,task_id,input_digest) DO NOTHING""",
        (plan_id, course_id, task_id, _json(asdict(head)), input_digest, storage, _json(payload)))
    result = get_plan(database, course_id, plan_id)
    assert result is not None
    return result


def activate_plan(database, plan: FusionPlan, *, applied: bool, reason: str | None = None) -> None:
    _transaction(database)
    if applied:
        if read_draft_head(database, plan.course_id) != plan.head:
            raise StaleFusionPlan("draft changed since fusion analysis")
        database.execute("UPDATE courses SET draft_storage_version=? WHERE id=?",
                         (plan.storage_version_id, plan.course_id))
    database.execute("UPDATE fusion_plans SET state=?,applied=?,reason=? WHERE course_id=? AND plan_id=?",
                     ("committed" if reason is None else "skipped", int(applied), reason,
                      plan.course_id, plan.plan_id))


def require_teacher(database, course_id: str, actor_id: str) -> None:
    if database.execute("SELECT 1 FROM course_members WHERE course_id=? AND user_id=? AND role='teacher'",
                        (course_id, actor_id)).fetchone() is None:
        raise PermissionError('teacher membership required')


def undone_groups(database, course_id: str, plan_id: str) -> tuple[str, ...]:
    return tuple(r[0] for r in database.execute(
        'SELECT group_id FROM fusion_undos WHERE course_id=? AND plan_id=? ORDER BY group_id', (course_id, plan_id)))


def record_undo(database, *, course_id, plan_id, group_id, actor_id, head, storage_version_id, payload):
    _transaction(database)
    require_teacher(database, course_id, actor_id)
    if read_draft_head(database, course_id) != head: raise StaleFusionPlan('draft changed before undo commit')
    undo_id = 'fundo_'+hashlib.sha256(_json([course_id, plan_id, group_id]).encode()).hexdigest()[:40]
    database.execute('UPDATE courses SET draft_storage_version=?,draft_revision=draft_revision+1 WHERE id=?',
                     (storage_version_id, course_id))
    database.execute('''INSERT INTO fusion_undos(undo_id,course_id,plan_id,group_id,actor_id,payload)
                        VALUES(?,?,?,?,?,?)''', (undo_id, course_id, plan_id, group_id, actor_id, _json(payload)))
    return undo_id


# Same bounded SQLite acquisition as the task/T6 fence, without changing a task's state.
from contextlib import contextmanager
from app.repositories.task_leases import _immediate, LeaseLost


@contextmanager
def undo_transaction(sqlite_url, head, token, *, deadline, on_acquired):
    with _immediate(sqlite_url, deadline=deadline, on_acquired=on_acquired) as database:
        if database.execute('SELECT 1 FROM course_locks WHERE course_id=? AND token=? AND expires_at>unixepoch()',
                            (head.course_id, token)).fetchone() is None:
            raise LeaseLost('undo course lease lost')
        if read_draft_head(database, head.course_id) != head: raise StaleFusionPlan('draft changed before undo')
        yield database
