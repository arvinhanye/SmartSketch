-- ADR-102: append-only replacements; original extraction checkpoints are never updated.
-- Stop API/workers and back up SQLite before rollback. Finish/cancel pinned tasks.
-- ROLLBACK: CREATE TEMP TABLE relation_rollback_guard(ok INTEGER CHECK(ok=1));
-- ROLLBACK: INSERT INTO relation_rollback_guard SELECT CASE WHEN EXISTS(SELECT 1 FROM task_chunk_checkpoints c JOIN processing_tasks t ON t.id=c.task_id WHERE json_extract(c.metadata,'$.normalization_version')=1 AND t.stage NOT IN ('completed','failed','cancelled')) THEN 0 ELSE 1 END;
-- ROLLBACK: DROP TABLE task_relation_revisions;
-- ROLLBACK: DROP TABLE relation_rollback_guard;
-- ROLLBACK: DELETE FROM schema_migrations WHERE version = '023';
CREATE TABLE task_relation_revisions (
    task_id TEXT NOT NULL REFERENCES processing_tasks(id) ON DELETE CASCADE,
    course_id TEXT NOT NULL CHECK(length(trim(course_id))>0),
    section_id TEXT NOT NULL CHECK(length(section_id)>0),
    input_digest TEXT NOT NULL CHECK(length(input_digest)>0),
    status TEXT NOT NULL CHECK(status IN ('done','failed')),
    attempts INTEGER NOT NULL CHECK(attempts>=1),
    error_code TEXT,
    result TEXT CHECK(result IS NULL OR (json_valid(result) AND json_type(result)='object')),
    metadata TEXT CHECK(metadata IS NULL OR (json_valid(metadata) AND json_type(metadata)='object')),
    created_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY(task_id,section_id,input_digest),
    CHECK((status='failed')=(error_code IS NOT NULL)),
    CHECK((status='done')=(result IS NOT NULL))
);
CREATE TRIGGER task_relation_revisions_scope BEFORE INSERT ON task_relation_revisions
WHEN NOT EXISTS(SELECT 1 FROM processing_tasks WHERE id=NEW.task_id AND course_id=NEW.course_id)
BEGIN SELECT RAISE(ABORT,'task_relation_revisions: course does not match task'); END;
CREATE TRIGGER task_relation_revisions_immutable BEFORE UPDATE ON task_relation_revisions
BEGIN SELECT RAISE(ABORT,'task_relation_revisions: rows are immutable'); END;
