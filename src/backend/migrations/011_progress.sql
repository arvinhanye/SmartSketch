-- I01: raw learning progress (specs/learning-path.md §5; ADR-014 修订 1 决定 8、9; ADR-012 修订 3
-- 决定 24; ADR-049). D-10: number 011 reserved on the task board (第九批); renumber to the new
-- max + 1 before merge if main already has 011.
--
-- Rollback (preferred): stop API and worker, restore backups/*-before-011.sqlite
-- (src/backend/README.md). Manual rollback loses every student's progress; run the lines below in one
-- transaction with API and worker stopped (tested in test_i01.py). commit_sequence belongs to 010
-- and is left as is (numbers already taken are never reused):
-- ROLLBACK: DROP TABLE learning_progress;
-- ROLLBACK: DELETE FROM schema_migrations WHERE filename LIKE '%_progress.sql';
--
-- One row per (student, course, kp_id): the student's own declared status, never a projection.
-- Rows are never copied per version and never deleted when a node leaves a version (dormant rows
-- stay for rollback and history reads); merge inheritance is computed at read time.
-- write_seq is taken from the shared commit_sequence (010) inside the write transaction, one
-- number per write transaction; a same-value write judged a no-op takes no number (A08S-R01).
-- updated_at is ISO-8601 UTC text for display only; ordering never uses it.
CREATE TABLE learning_progress (
    user_id TEXT NOT NULL REFERENCES users(id),
    course_id TEXT NOT NULL REFERENCES courses(id),
    kp_id TEXT NOT NULL CHECK (length(kp_id) >= 1),
    status TEXT NOT NULL CHECK (status IN ('unknown', 'learning', 'mastered')),
    write_seq INTEGER NOT NULL CHECK (write_seq >= 1),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (user_id, course_id, kp_id)
) WITHOUT ROWID;
