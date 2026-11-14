-- ADR-101: keep failure results NULL; audit metadata is independent of candidates.
-- Stop API/workers and back up SQLite before rollback. Finish/cancel window tasks
-- first: dropping metadata discards their pinned window policy and coverage.
-- Existing candidates, task checkpoints and immutable/course guards are preserved.
-- ROLLBACK: CREATE TEMP TABLE window_rollback_guard(ok INTEGER CHECK(ok=1));
-- ROLLBACK: INSERT INTO window_rollback_guard SELECT CASE WHEN EXISTS(SELECT 1 FROM task_chunk_checkpoints c JOIN processing_tasks t ON t.id=c.task_id WHERE c.metadata IS NOT NULL AND t.stage NOT IN ('completed','failed','cancelled')) THEN 0 ELSE 1 END;
-- ROLLBACK: ALTER TABLE task_chunk_checkpoints DROP COLUMN metadata;
-- ROLLBACK: DROP TABLE window_rollback_guard;
-- ROLLBACK: DELETE FROM schema_migrations WHERE version = '022';
ALTER TABLE task_chunk_checkpoints ADD COLUMN metadata TEXT
    CHECK (metadata IS NULL OR (json_valid(metadata) AND json_type(metadata) = 'object'));
