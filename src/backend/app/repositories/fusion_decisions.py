"""Global pair plan/cache storage. Callers own write transactions and worker fences."""
import json
import sqlite3

_NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _transaction(db):
    if not db.in_transaction:
        raise RuntimeError('fusion decision writes require a fenced transaction')


def initialize_plan(db, *, course_id, task_id, input_digest, pairs, total_possible, attempt, context=None):
    """Activate one exact plan and reset only its unfinished pairs for this attempt."""
    _transaction(db)
    payload = _json(pairs)
    encoded_context = _json(context or {})
    if type(total_possible) is not int or total_possible < len(pairs):
        raise ValueError('invalid global pair total')
    keys = [(p['left_id'], p['right_id']) for p in pairs]
    if len(set(keys)) != len(keys) or any(not a or not a < b for a, b in keys):
        raise ValueError('global pairs must be unique and ordered')
    saved = db.execute('SELECT course_id,total_possible,plan_json,context_json FROM task_fusion_analysis WHERE task_id=? AND input_digest=?', (task_id,input_digest)).fetchone()
    if saved is not None and saved != (course_id,total_possible,payload,encoded_context):
        raise ValueError('analysis digest identifies different global inputs')
    db.execute('UPDATE task_fusion_analysis SET is_current=0 WHERE task_id=? AND is_current=1', (task_id,))
    db.execute(f'''INSERT INTO task_fusion_analysis(task_id,course_id,input_digest,total_possible,total,plan_json,context_json,active_attempt,is_current,phase)
        VALUES(?,?,?,?,?,?,?,?,1,'running') ON CONFLICT(task_id,input_digest) DO UPDATE SET
        active_attempt=excluded.active_attempt,is_current=1,phase='running',selected_plan_id=NULL,updated_at={_NOW}''',
        (task_id,course_id,input_digest,total_possible,len(pairs),payload,encoded_context,attempt))
    db.executemany('''INSERT INTO task_fusion_decisions(task_id,course_id,input_digest,left_id,right_id,ordinal,status,attempt)
        VALUES(?,?,?,?,?,?,'pending',?) ON CONFLICT(task_id,input_digest,left_id,right_id) DO NOTHING''',
        [(task_id,course_id,input_digest,a,b,i,attempt) for i,(a,b) in enumerate(keys)])
    db.execute(f'''UPDATE task_fusion_decisions SET status='pending',payload=NULL,attempt=?,updated_at={_NOW}
        WHERE task_id=? AND course_id=? AND input_digest=? AND status<>'complete' ''',
        (attempt,task_id,course_id,input_digest))
    preanalysis = (context or {}).get('preanalysis_input_digest')
    if isinstance(preanalysis,str) and preanalysis:
        # The source/configuration input is identical; only recall coverage changed.
        # Copy complete matching pairs, keeping their original attempt and timestamp.
        inherited = db.execute('''SELECT d.left_id,d.right_id,d.payload,d.attempt,d.updated_at
            FROM task_fusion_decisions d JOIN task_fusion_analysis a
              ON a.task_id=d.task_id AND a.input_digest=d.input_digest AND a.course_id=d.course_id
            JOIN task_fusion_decisions target ON target.task_id=d.task_id AND target.course_id=d.course_id
              AND target.input_digest=? AND target.left_id=d.left_id AND target.right_id=d.right_id
            WHERE d.task_id=? AND d.course_id=? AND d.status='complete' AND target.status='pending'
              AND json_extract(a.context_json,'$.preanalysis_input_digest')=?
            ORDER BY d.updated_at,a.rowid,d.ordinal''',
            (input_digest,task_id,course_id,preanalysis)).fetchall()
        for left,right,payload,original_attempt,updated in inherited:
            db.execute('''UPDATE task_fusion_decisions SET status='complete',payload=?,attempt=?,updated_at=?
                WHERE task_id=? AND course_id=? AND input_digest=? AND left_id=? AND right_id=? AND status='pending' ''',
                (payload,original_attempt,updated,task_id,course_id,input_digest,left,right))


def read_context(db, *, course_id, task_id, preanalysis_input_digest):
    """Reuse the saved recall only for identical source/configuration inputs."""
    row = db.execute('''SELECT context_json FROM task_fusion_analysis
        WHERE task_id=? AND course_id=? AND json_extract(context_json,'$.preanalysis_input_digest')=?
        ORDER BY is_current DESC,active_attempt DESC,rowid DESC LIMIT 1''',
        (task_id,course_id,preanalysis_input_digest)).fetchone()
    return None if row is None else json.loads(row[0])


def activate_plan(db, *, course_id, task_id, input_digest, attempt):
    """Select an already complete plan without modifying its immutable decisions."""
    _transaction(db)
    if db.execute("SELECT 1 FROM task_fusion_analysis WHERE task_id=? AND course_id=? AND input_digest=? AND phase='complete'",
                  (task_id,course_id,input_digest)).fetchone() is None:
        return False
    db.execute('UPDATE task_fusion_analysis SET is_current=0 WHERE task_id=? AND is_current=1', (task_id,))
    db.execute(f'''UPDATE task_fusion_analysis SET is_current=1,active_attempt=?,updated_at={_NOW}
        WHERE task_id=? AND course_id=? AND input_digest=?''', (attempt,task_id,course_id,input_digest))
    return True


def select_output_plan(db, *, course_id, task_id, input_digest, plan_id):
    """Bind persistence to one explicit outcome, including reactivated old inputs."""
    _transaction(db)
    changed = db.execute(f'''UPDATE task_fusion_analysis SET selected_plan_id=?,updated_at={_NOW}
        WHERE task_id=? AND course_id=? AND input_digest=? AND is_current=1 AND phase='complete' ''',
        (plan_id,task_id,course_id,input_digest)).rowcount
    if changed != 1:
        raise RuntimeError('output plan requires the completed current analysis')


def read_complete(db, *, course_id, task_id, input_digest):
    return {(a,b):json.loads(payload) for a,b,payload in db.execute('''SELECT left_id,right_id,payload
        FROM task_fusion_decisions WHERE course_id=? AND task_id=? AND input_digest=? AND status='complete'
        ORDER BY ordinal''', (course_id,task_id,input_digest))}


def mark_running(db, *, course_id, task_id, input_digest, left_id, right_id, attempt):
    _transaction(db)
    changed = db.execute(f'''UPDATE task_fusion_decisions SET status='running',payload=NULL,attempt=?,updated_at={_NOW}
        WHERE task_id=? AND course_id=? AND input_digest=? AND left_id=? AND right_id=? AND status='pending' ''',
        (attempt,task_id,course_id,input_digest,left_id,right_id)).rowcount
    if changed != 1:
        raise RuntimeError('global pair is not pending in this plan')


def put_result(db, *, course_id, task_id, input_digest, decision, attempt):
    _transaction(db)
    if decision.get('status') not in ('complete','failed','deferred'):
        raise ValueError('invalid semantic decision status')
    changed = db.execute(f'''UPDATE task_fusion_decisions SET status=?,payload=?,attempt=?,updated_at={_NOW}
        WHERE task_id=? AND course_id=? AND input_digest=? AND left_id=? AND right_id=? AND status='running' ''',
        (decision['status'],_json(decision),attempt,task_id,course_id,input_digest,decision['left_id'],decision['right_id'])).rowcount
    if changed != 1:
        raise RuntimeError('global pair is not running in this plan')


def finish_plan(db, *, course_id, task_id, input_digest):
    _transaction(db)
    db.execute(f'''UPDATE task_fusion_analysis SET phase='complete',updated_at={_NOW}
        WHERE task_id=? AND course_id=? AND input_digest=? AND NOT EXISTS(
            SELECT 1 FROM task_fusion_decisions d WHERE d.task_id=? AND d.input_digest=? AND status IN ('pending','running'))''',
        (task_id,course_id,input_digest,task_id,input_digest))


def read_progress(db: sqlite3.Connection, *, course_id: str, task_id: str, now: float | None = None) -> dict | None:
    """Current-attempt plan only; no estimate is fabricated before a plan is persisted."""
    plan = db.execute('''SELECT a.input_digest,a.total,a.total_possible,a.phase,a.active_attempt,a.updated_at,
        t.stage='merging' AND t.cancel_requested=0 AND t.lease_token IS NOT NULL
            AND t.lease_expires_at>COALESCE(?,unixepoch())
        FROM task_fusion_analysis a JOIN processing_tasks t ON t.id=a.task_id AND t.course_id=a.course_id
        WHERE a.task_id=? AND a.course_id=? AND a.is_current=1 AND a.active_attempt=t.attempt''',
        (now,task_id,course_id)).fetchone()
    if plan is None:
        return None
    digest,total,total_possible,phase,attempt,updated,active = plan
    counts = {status:n for status,n in db.execute('''SELECT status,count(*) FROM task_fusion_decisions
        WHERE task_id=? AND course_id=? AND input_digest=? GROUP BY status''', (task_id,course_id,digest))}
    reused,last = db.execute('''SELECT count(*) FILTER(WHERE status='complete' AND attempt<?),max(updated_at)
        FROM task_fusion_decisions WHERE task_id=? AND course_id=? AND input_digest=?''', (attempt,task_id,course_id,digest)).fetchone()
    inflight = counts.get('running',0) if active else 0
    return dict(input_digest=digest,attempt=attempt,total=total,total_possible=total_possible,
        completed=counts.get('complete',0),failed=counts.get('failed',0),deferred=counts.get('deferred',0),
        reused=reused,inflight=inflight,pending=counts.get('pending',0)+counts.get('running',0)-inflight,
        phase=phase,updated_at=max(updated,last or updated))
