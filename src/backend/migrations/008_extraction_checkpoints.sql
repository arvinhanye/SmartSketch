-- E12: extracting-stage checkpoints (specs/task-processing.md §8.4 `extracting`, §8.6, §8.7; ADR-011).
-- D-10: numbered as main's max (007, D10) + 1; renumber to the new max + 1 before merge if main
-- already has 008.
--
-- Rollback (preferred): stop API and worker, restore backups/*-before-008.sqlite
-- (src/backend/README.md). Manual rollback, which discards every stored checkpoint (tasks still in
-- `extracting` then re-run the stage from the start and call the model again for every chunk);
-- run the lines below in one transaction with API and worker stopped (tested in test_e12.py):
-- ROLLBACK: DROP TABLE task_chunk_checkpoints;
-- ROLLBACK: DELETE FROM schema_migrations WHERE filename LIKE '%_extraction_checkpoints.sql';
--
-- One row per finished extraction unit of a task: a source chunk (entity extraction, E05/E06) or a
-- section (relation extraction, E11). A unit without a row has not finished; a crash mid-unit leaves
-- no row, so a takeover gives it a full set of L2 attempts again. Rows are written in the same
-- transaction as the lease-token fence and never change afterwards. `result` is a JSON object
-- holding the unit's candidates (with sources) for a `done` unit, NULL for a `failed` unit.
-- Rows go with their task (ON DELETE CASCADE, ADR-021 document deletion); retention per §8.6.
CREATE TABLE task_chunk_checkpoints (
    task_id TEXT NOT NULL REFERENCES processing_tasks(id) ON DELETE CASCADE,
    course_id TEXT NOT NULL CHECK (length(trim(course_id)) > 0),
    unit_kind TEXT NOT NULL CHECK (unit_kind IN ('chunk', 'section')),
    unit_id TEXT NOT NULL CHECK (length(unit_id) BETWEEN 1 AND 255),
    status TEXT NOT NULL CHECK (status IN ('done', 'failed')),
    attempts INTEGER NOT NULL CHECK (attempts >= 1),
    error_code TEXT,
    result TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (task_id, unit_kind, unit_id),
    CHECK ((status = 'failed') = (error_code IS NOT NULL)),
    CHECK ((status = 'done') = (result IS NOT NULL)),
    CHECK (result IS NULL OR (json_valid(result) AND json_type(result) = 'object'))
);

-- Course isolation: a checkpoint belongs to the course of its task.
CREATE TRIGGER task_chunk_checkpoints_course_scope
BEFORE INSERT ON task_chunk_checkpoints
WHEN NOT EXISTS (SELECT 1 FROM processing_tasks WHERE id = NEW.task_id AND course_id = NEW.course_id)
BEGIN
    SELECT RAISE(ABORT, 'task_chunk_checkpoints: course does not match the task');
END;

-- Immutable once written (§8.4: a finished unit is never re-extracted).
CREATE TRIGGER task_chunk_checkpoints_immutable
BEFORE UPDATE ON task_chunk_checkpoints
BEGIN
    SELECT RAISE(ABORT, 'task_chunk_checkpoints: rows are immutable');
END;
