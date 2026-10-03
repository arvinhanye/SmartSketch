-- L04: per-user model credentials and per-task immutable snapshots (ADR-080).
-- Rollback: stop API/worker and restore backups/*-before-015.sqlite. Manual rollback drops
-- every saved credential and needs SQLite >= 3.35 for DROP COLUMN.
-- ROLLBACK: DROP TABLE task_model_bindings;
-- ROLLBACK: DROP TABLE user_model_configs;
-- ROLLBACK: DROP INDEX idx_model_calls_user_created;
-- ROLLBACK: ALTER TABLE model_calls DROP COLUMN user_id;
-- ROLLBACK: ALTER TABLE processing_tasks DROP COLUMN created_by;
-- ROLLBACK: DELETE FROM schema_migrations WHERE filename LIKE '%_user_model_configs.sql';
CREATE TABLE user_model_configs (
    user_id TEXT PRIMARY KEY NOT NULL REFERENCES users(id),
    base_url TEXT NOT NULL CHECK (length(base_url) BETWEEN 9 AND 512),
    model TEXT NOT NULL CHECK (length(trim(model)) BETWEEN 1 AND 128),
    key_ciphertext BLOB NOT NULL,
    key_nonce BLOB NOT NULL CHECK (length(key_nonce) = 12),
    key_hint TEXT NOT NULL CHECK (length(key_hint) BETWEEN 1 AND 4),
    version INTEGER NOT NULL CHECK (version >= 1),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_test_at TEXT,
    last_test_ok INTEGER CHECK (last_test_ok IN (0, 1)),
    last_test_error_class TEXT
);

-- The key columns are a copy of the owner's ciphertext at task creation; they are nulled
-- (never rewritten) when the task ends or the owner clears the configuration.
CREATE TABLE task_model_bindings (
    task_id TEXT PRIMARY KEY NOT NULL REFERENCES processing_tasks(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id),
    config_version INTEGER NOT NULL CHECK (config_version >= 1),
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    key_ciphertext BLOB,
    key_nonce BLOB,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    scrubbed_at TEXT,
    scrub_reason TEXT CHECK (scrub_reason IN ('terminal', 'revoked')),
    CHECK ((key_ciphertext IS NULL) = (key_nonce IS NULL)),
    CHECK ((key_ciphertext IS NULL) = (scrubbed_at IS NOT NULL)),
    CHECK ((scrubbed_at IS NULL) = (scrub_reason IS NULL))
);
CREATE INDEX idx_task_model_bindings_user ON task_model_bindings(user_id);

ALTER TABLE processing_tasks ADD COLUMN created_by TEXT REFERENCES users(id);
ALTER TABLE model_calls ADD COLUMN user_id TEXT;
CREATE INDEX idx_model_calls_user_created ON model_calls(user_id, created_at);
