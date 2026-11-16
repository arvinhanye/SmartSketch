-- Explicit teacher resume preserves cumulative attempt/audit identities, while granting
-- a fresh bounded set of automatic attempts. Stop API/workers before rolling back.
-- ROLLBACK: CREATE TEMP TABLE task_resume_rollback_guard(ok INTEGER CHECK(ok=1));
-- ROLLBACK: INSERT INTO task_resume_rollback_guard SELECT NOT EXISTS(SELECT 1 FROM processing_tasks WHERE (lease_token IS NOT NULL AND lease_expires_at >= unixepoch()) OR (resume_count > 0 AND stage IN ('queued','parsing','extracting','merging','persisting')));
-- ROLLBACK: ALTER TABLE processing_tasks DROP COLUMN resume_count;
-- ROLLBACK: ALTER TABLE processing_tasks DROP COLUMN resume_attempt_base;
-- ROLLBACK: DROP TABLE task_resume_rollback_guard;
-- ROLLBACK: DELETE FROM schema_migrations WHERE version = '025';
ALTER TABLE processing_tasks ADD COLUMN resume_attempt_base INTEGER NOT NULL DEFAULT 0
    CHECK(typeof(resume_attempt_base) = 'integer' AND resume_attempt_base >= 0 AND resume_attempt_base <= attempt);
ALTER TABLE processing_tasks ADD COLUMN resume_count INTEGER NOT NULL DEFAULT 0
    CHECK(typeof(resume_count) = 'integer' AND resume_count >= 0);
