-- INVITE-01 / ADR-096: recoverable teacher-visible codes with permanent revocation history.
-- Stop API/worker and back up SQLite before rollback. Existing course memberships remain.
-- Rolling back removes invite history; re-enabling requires teachers to distribute new codes.
-- ROLLBACK: DROP TABLE course_invite_codes;
-- ROLLBACK: DELETE FROM schema_migrations WHERE version = '020';
CREATE TABLE course_invite_codes (
    code TEXT PRIMARY KEY NOT NULL
        CHECK (length(code) = 6 AND code NOT GLOB '*[^ABCDEFGHJKLMNPQRSTUVWXYZ23456789]*'),
    course_id TEXT NOT NULL REFERENCES courses(id),
    rotated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    revoked_at TEXT
);

-- Revoked codes stay globally unique and can never become another course's valid code.
CREATE UNIQUE INDEX idx_course_invite_active
    ON course_invite_codes(course_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_course_invite_history ON course_invite_codes(course_id);
