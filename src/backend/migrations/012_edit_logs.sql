-- F12: teacher graph-edit audit log (ADR-061; specs/teacher-review-publish.md「图编辑审计」).
-- D-10: numbered as main's max (011, I01) + 1; renumber to the new max + 1 before merge if main
-- already has 012.
--
-- Rollback (preferred): stop API and worker, restore backups/*-before-012.sqlite
-- (src/backend/README.md). Manual rollback, which loses the audit history; export the table first
-- if it must be kept. Run the lines below in one transaction with API and worker stopped (tested in
-- test_f12.py):
-- ROLLBACK: DROP TRIGGER graph_edit_logs_final_frozen;
-- ROLLBACK: DROP TRIGGER graph_edit_logs_no_delete;
-- ROLLBACK: DROP INDEX graph_edit_logs_pending;
-- ROLLBACK: DROP INDEX graph_edit_logs_course_seq;
-- ROLLBACK: DROP TABLE graph_edit_logs;
-- ROLLBACK: DELETE FROM schema_migrations WHERE filename LIKE '%_edit_logs.sql';
--
-- One row per teacher write that got as far as bumping courses.draft_revision. The row is inserted
-- as `pending` in the same SQLite transaction as that bump (so `draft_revision` is exact), then set
-- to `committed` or `aborted` once the Neo4j write returns. A row left `pending` (the SQLite update
-- failed after Neo4j committed, or the process died) is resolved later against Neo4j while holding
-- the course write lock (app.services.graph.audit.reconcile). Times are ISO-8601 UTC text.
-- `summary` is a whitelisted, redacted JSON object; no tokens, passwords or request headers.
CREATE TABLE graph_edit_logs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE CHECK (length(event_id) = 32),
    course_id TEXT NOT NULL REFERENCES courses(id),
    actor_id TEXT NOT NULL REFERENCES users(id),
    action TEXT NOT NULL CHECK (action IN ('create', 'update', 'unlock', 'delete', 'merge')),
    kp_id TEXT NOT NULL CHECK (length(kp_id) > 0),
    draft_revision INTEGER NOT NULL CHECK (draft_revision >= 1),
    kp_revision_before INTEGER CHECK (kp_revision_before IS NULL OR kp_revision_before >= 0),
    kp_revision_after INTEGER CHECK (kp_revision_after IS NULL OR kp_revision_after >= 1),
    state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'committed', 'aborted')),
    summary TEXT NOT NULL CHECK (json_valid(summary) AND json_type(summary) = 'object'),
    failure_reason TEXT CHECK (failure_reason IS NULL OR length(failure_reason) BETWEEN 1 AND 255),
    resolved_by TEXT CHECK (resolved_by IS NULL OR resolved_by IN ('writer', 'reconcile')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    resolved_at TEXT,
    CHECK ((state = 'pending') = (resolved_at IS NULL)),
    CHECK ((state = 'pending') = (resolved_by IS NULL)),
    CHECK ((state = 'aborted') = (failure_reason IS NOT NULL))
);

CREATE INDEX graph_edit_logs_course_seq ON graph_edit_logs (course_id, seq);
CREATE INDEX graph_edit_logs_pending ON graph_edit_logs (course_id, seq) WHERE state = 'pending';

-- Audit rows are append-only: never deleted, and frozen once resolved.
CREATE TRIGGER graph_edit_logs_no_delete BEFORE DELETE ON graph_edit_logs
BEGIN
    SELECT RAISE(ABORT, 'graph_edit_logs rows are append-only');
END;

CREATE TRIGGER graph_edit_logs_final_frozen BEFORE UPDATE ON graph_edit_logs
WHEN OLD.state != 'pending'
BEGIN
    SELECT RAISE(ABORT, 'resolved graph_edit_logs rows are frozen');
END;
