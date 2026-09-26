-- F13: course write lock (specs/task-processing.md §8.5; teacher-review-publish.md V4) and the T6
-- commit sequence (§3 任务水位). D-10: numbered as main's max (008, E12) + 1; renumber to the new
-- max + 1 before merge if main already has 009.
--
-- Rollback (preferred): stop API and worker, restore backups/*-before-009.sqlite
-- (src/backend/README.md). Manual rollback, which forgets every T6 sequence number (publishing then
-- has no task watermark until tasks are re-run); run the lines below in one transaction with API
-- and worker stopped (tested in test_f13.py):
-- ROLLBACK: DROP INDEX processing_tasks_t6_seq;
-- ROLLBACK: ALTER TABLE processing_tasks DROP COLUMN t6_seq;
-- ROLLBACK: DROP TABLE course_locks;
-- ROLLBACK: DELETE FROM schema_migrations WHERE filename LIKE '%_course_locks.sql';
--
-- One row per held lock, same shape as the task lease (§8.2): times are unix epoch seconds from
-- unixepoch(), matching the migrator's live-lock guard `expires_at >= unixepoch()`. Acquire with
-- INSERT … ON CONFLICT(course_id) DO UPDATE … WHERE course_locks.expires_at < unixepoch();
-- release with DELETE … WHERE token = ?. An expired row may be taken over by anyone.
CREATE TABLE course_locks (
    course_id TEXT PRIMARY KEY NOT NULL CHECK (length(trim(course_id)) > 0),
    holder TEXT NOT NULL CHECK (length(holder) BETWEEN 1 AND 255),
    token TEXT NOT NULL CHECK (length(token) >= 32),
    expires_at INTEGER NOT NULL
);

-- T6 commit sequence: assigned in the T6 transaction, strictly increasing per course, never on the
-- wire. NULL until the task reaches awaiting_review.
ALTER TABLE processing_tasks ADD COLUMN t6_seq INTEGER CHECK (t6_seq IS NULL OR t6_seq >= 1);
CREATE UNIQUE INDEX processing_tasks_t6_seq ON processing_tasks (course_id, t6_seq)
    WHERE t6_seq IS NOT NULL;
