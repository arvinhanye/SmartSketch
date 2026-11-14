"""Immutable replacement relation units; caller owns lease/stage transaction fences."""
import json

from app.repositories.extraction_checkpoints import Checkpoint


def read_revision(db, *, course_id, task_id, section_id, input_digest):
    row = db.execute('''SELECT status,attempts,error_code,result,metadata FROM task_relation_revisions
        WHERE course_id=? AND task_id=? AND section_id=? AND input_digest=?''',
        (course_id,task_id,section_id,input_digest)).fetchone()
    if row is None:
        return None
    status,attempts,code,result,metadata = row
    return Checkpoint('section',section_id,status,attempts,code,
                      None if result is None else json.loads(result),
                      None if metadata is None else json.loads(metadata))


def put_revision(db, *, course_id, task_id, section_id, input_digest, status, attempts,
                 error_code=None, result=None, metadata=None):
    if not db.in_transaction:
        raise RuntimeError('put_revision requires the caller leased transaction')
    encode = lambda value: None if value is None else json.dumps(value,ensure_ascii=False,sort_keys=True)
    return db.execute('''INSERT INTO task_relation_revisions
        (course_id,task_id,section_id,input_digest,status,attempts,error_code,result,metadata)
        VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(task_id,section_id,input_digest) DO NOTHING''',
        (course_id,task_id,section_id,input_digest,status,attempts,error_code,encode(result),encode(metadata))).rowcount == 1
