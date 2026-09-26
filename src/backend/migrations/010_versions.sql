-- G02: graph versions and publish/rollback attempts (specs/teacher-review-publish.md V1, V2, V5, V6;
-- ADR-012) and the global commit sequence (ADR-012 修订 3). D-10: numbered as main's max (009, F13) + 1;
-- renumber to the new max + 1 before merge if main already has 010.
--
-- Rollback (preferred): stop API and worker, restore backups/*-before-010.sqlite
-- (src/backend/README.md). Manual rollback, only while no course has ever published (every
-- committed version and the publish pointer would be lost otherwise); run the lines below in one
-- transaction with API and worker stopped (tested in test_g02.py):
-- ROLLBACK: DROP TRIGGER graph_versions_committed_no_delete;
-- ROLLBACK: DROP TRIGGER graph_versions_committed_frozen;
-- ROLLBACK: DROP TABLE commit_sequence;
-- ROLLBACK: DROP TABLE graph_versions;
-- ROLLBACK: DELETE FROM schema_migrations WHERE filename LIKE '%_versions.sql';
--
-- One row per publish or rollback attempt; a row becomes a version only when it reaches
-- `committed`. `version` and `commit_seq` are assigned in the commit transaction, so failed
-- attempts use no number and version numbers have no gaps. Lease times are unix epoch seconds
-- from unixepoch(), like course_locks; audit times are ISO-8601 UTC text.
CREATE TABLE graph_versions (
    version_id TEXT PRIMARY KEY NOT NULL CHECK (length(version_id) = 26 AND version_id != 'draft'),
    course_id TEXT NOT NULL REFERENCES courses(id),
    version INTEGER CHECK (version IS NULL OR version >= 1),
    kind TEXT NOT NULL CHECK (kind IN ('publish', 'rollback')),
    source_version INTEGER CHECK (source_version IS NULL OR source_version >= 1),
    state TEXT NOT NULL DEFAULT 'preparing'
        CHECK (state IN ('preparing', 'materialized', 'committed', 'failed')),
    expires_at INTEGER NOT NULL,
    snapshot_json TEXT,
    digest TEXT CHECK (
        digest IS NULL OR (
            length(digest) = 71
            AND substr(digest, 1, 7) = 'sha256:'
            AND substr(digest, 8) NOT GLOB '*[^0-9a-f]*'
        )
    ),
    node_count INTEGER CHECK (node_count IS NULL OR node_count >= 0),
    edge_count INTEGER CHECK (edge_count IS NULL OR edge_count >= 0),
    excluded TEXT CHECK (excluded IS NULL OR json_valid(excluded)),
    draft_revision INTEGER CHECK (draft_revision IS NULL OR draft_revision >= 0),
    task_watermark INTEGER CHECK (task_watermark IS NULL OR task_watermark >= 0),
    embedding_space TEXT CHECK (embedding_space IS NULL OR length(embedding_space) >= 1),
    failure_reason TEXT CHECK (failure_reason IS NULL OR length(failure_reason) BETWEEN 1 AND 255),
    cleanup_pending INTEGER NOT NULL DEFAULT 0 CHECK (cleanup_pending IN (0, 1)),
    created_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    committed_at TEXT,
    commit_seq INTEGER CHECK (commit_seq IS NULL OR commit_seq >= 1),
    CHECK ((kind = 'rollback') = (source_version IS NOT NULL)),
    CHECK ((snapshot_json IS NULL) = (digest IS NULL)),
    CHECK (state IN ('preparing', 'failed') OR digest IS NOT NULL),
    CHECK ((state = 'committed') = (version IS NOT NULL)),
    CHECK ((state = 'committed') = (commit_seq IS NOT NULL)),
    CHECK ((state = 'committed') = (committed_at IS NOT NULL)),
    CHECK ((state = 'failed') = (failure_reason IS NOT NULL)),
    CHECK (state = 'failed' OR cleanup_pending = 0)
);

-- One committed row per (course, version) and per commit sequence number.
CREATE UNIQUE INDEX graph_versions_course_version ON graph_versions (course_id, version)
    WHERE version IS NOT NULL;
CREATE UNIQUE INDEX graph_versions_commit_seq ON graph_versions (commit_seq)
    WHERE commit_seq IS NOT NULL;
-- V2: the only mechanism that keeps one publish or rollback per course at a time.
CREATE UNIQUE INDEX graph_versions_one_active ON graph_versions (course_id)
    WHERE state IN ('preparing', 'materialized');
CREATE INDEX graph_versions_cleanup ON graph_versions (course_id) WHERE cleanup_pending = 1;

-- Committed rows are the version history: never deleted, content never changed. Only
-- embedding_space may move (V12 re-vectorisation).
CREATE TRIGGER graph_versions_committed_no_delete
BEFORE DELETE ON graph_versions
WHEN OLD.state = 'committed'
BEGIN
    SELECT RAISE(ABORT, 'committed graph versions are never deleted');
END;

CREATE TRIGGER graph_versions_committed_frozen
BEFORE UPDATE OF version_id, course_id, version, kind, source_version, state, snapshot_json, digest,
    node_count, edge_count, excluded, draft_revision, task_watermark, created_by, created_at,
    committed_at, commit_seq, failure_reason, cleanup_pending ON graph_versions
WHEN OLD.state = 'committed'
BEGIN
    SELECT RAISE(ABORT, 'committed graph versions are immutable');
END;

-- ADR-012 修订 3: one global sequence shared by version commits and progress writes.
CREATE TABLE commit_sequence (
    singleton INTEGER PRIMARY KEY NOT NULL CHECK (singleton = 1),
    value INTEGER NOT NULL CHECK (value >= 0)
);
INSERT INTO commit_sequence (singleton, value) VALUES (1, 0);
