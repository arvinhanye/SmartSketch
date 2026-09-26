-- I01: original student progress survives graph edits, deletion, and rollback.
-- Rollback: stop API/worker and restore backups/*-before-011.sqlite. Manual
-- DROP TABLE is safe only after exporting progress because it destroys history.
-- ROLLBACK: DROP INDEX learning_progress_course_kp;
-- ROLLBACK: DROP TABLE learning_progress;
-- ROLLBACK: DELETE FROM schema_migrations WHERE filename LIKE '%_progress.sql';
CREATE TABLE learning_progress (
    user_id TEXT NOT NULL REFERENCES users(id),
    course_id TEXT NOT NULL REFERENCES courses(id),
    kp_id TEXT NOT NULL CHECK (length(kp_id) > 0),
    status TEXT NOT NULL CHECK (status IN ('unknown', 'learning', 'mastered')),
    updated_at TEXT NOT NULL,
    write_seq INTEGER NOT NULL UNIQUE CHECK (write_seq >= 1),
    PRIMARY KEY (user_id, course_id, kp_id)
);
CREATE INDEX learning_progress_course_kp ON learning_progress(course_id, kp_id);
