-- J10: one row for each chat request that passed P2 version binding.
-- Rollback: stop API/worker and restore backups/*-before-014.sqlite.
-- Manual rollback (drops chat history):
-- ROLLBACK: DROP INDEX chat_logs_created_at;
-- ROLLBACK: DROP TABLE chat_logs;
-- ROLLBACK: DELETE FROM schema_migrations WHERE filename LIKE '%_chat_logs.sql';
CREATE TABLE chat_logs (
    request_id TEXT PRIMARY KEY NOT NULL CHECK (length(request_id) > 0),
    user_id TEXT NOT NULL REFERENCES users(id),
    course_id TEXT NOT NULL REFERENCES courses(id),
    version_id TEXT NOT NULL REFERENCES graph_versions(version_id),
    question TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('answered', 'not_covered', 'error', 'aborted')),
    reason TEXT,
    error_code TEXT,
    error_reason TEXT,
    citations_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(citations_json)),
    unknown_citation_count INTEGER NOT NULL DEFAULT 0 CHECK (unknown_citation_count >= 0),
    invalidation_subtype TEXT CHECK (
        invalidation_subtype IN ('no_markers', 'unknown_only', 'uncited_sentence')
    ),
    uncovered_unit_count INTEGER NOT NULL DEFAULT 0 CHECK (uncovered_unit_count >= 0),
    truncated INTEGER NOT NULL DEFAULT 0 CHECK (truncated IN (0, 1)),
    latency_ms INTEGER NOT NULL CHECK (latency_ms >= 0),
    first_delta_latency_ms INTEGER CHECK (first_delta_latency_ms >= 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX chat_logs_created_at ON chat_logs(created_at);
