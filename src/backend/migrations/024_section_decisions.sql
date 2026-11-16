-- Completed local semantic decisions can be reused before their section checkpoint exists.
-- Stop API/workers, back up SQLite and wait for active task leases to clear.
-- Run these statements in one transaction. Only the cache and its migration record are removed.
-- ROLLBACK: CREATE TEMP TABLE section_decision_rollback_guard(ok INTEGER CHECK(ok=1));
-- ROLLBACK: INSERT INTO section_decision_rollback_guard SELECT NOT EXISTS(SELECT 1 FROM processing_tasks WHERE lease_token IS NOT NULL AND lease_expires_at >= unixepoch());
-- ROLLBACK: DROP TABLE task_section_decisions;
-- ROLLBACK: DROP TABLE section_decision_rollback_guard;
-- ROLLBACK: DELETE FROM schema_migrations WHERE version = '024';
CREATE TABLE task_section_decisions (
    task_id TEXT NOT NULL REFERENCES processing_tasks(id) ON DELETE CASCADE,
    course_id TEXT NOT NULL CHECK(length(trim(course_id)) > 0),
    section_id TEXT NOT NULL CHECK(length(trim(section_id)) > 0),
    input_digest TEXT NOT NULL CHECK(length(trim(input_digest)) > 0),
    left_id TEXT NOT NULL CHECK(length(trim(left_id)) > 0),
    right_id TEXT NOT NULL CHECK(left_id < right_id),
    decision TEXT NOT NULL CHECK(
        CASE WHEN json_valid(decision) THEN
            json_type(decision) = 'object'
            AND json_extract(decision, '$.status') IS 'complete'
            AND COALESCE(json_extract(decision, '$.verdict') IN ('SAME', 'DIFFERENT', 'UNCERTAIN'), 0)
            AND json_extract(decision, '$.left_id') IS left_id
            AND json_extract(decision, '$.right_id') IS right_id
        ELSE 0 END
    ),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY(task_id, section_id, input_digest, left_id, right_id)
);

CREATE TRIGGER task_section_decisions_scope BEFORE INSERT ON task_section_decisions
WHEN NOT EXISTS (
    SELECT 1 FROM processing_tasks WHERE id = NEW.task_id AND course_id = NEW.course_id
)
BEGIN
    SELECT RAISE(ABORT, 'task_section_decisions: course does not match task');
END;

CREATE TRIGGER task_section_decisions_immutable BEFORE UPDATE ON task_section_decisions
BEGIN
    SELECT RAISE(ABORT, 'task_section_decisions: rows are immutable');
END;
