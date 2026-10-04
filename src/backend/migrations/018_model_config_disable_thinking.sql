-- ADR-090 (plan C, option B): per-user "disable model thinking" switch, snapshotted into each
-- task binding together with base_url and model. Defaults to 0 (off), which keeps every request
-- body exactly as before. No existing data is changed.
-- Rollback: stop API/worker and restore backups/*-before-018.sqlite, or run (SQLite >= 3.35):
-- ROLLBACK: ALTER TABLE task_model_bindings DROP COLUMN disable_thinking;
-- ROLLBACK: ALTER TABLE user_model_configs DROP COLUMN disable_thinking;
-- ROLLBACK: DELETE FROM schema_migrations WHERE filename LIKE '%_model_config_disable_thinking.sql';
ALTER TABLE user_model_configs ADD COLUMN disable_thinking INTEGER NOT NULL DEFAULT 0
    CHECK (disable_thinking IN (0, 1));
ALTER TABLE task_model_bindings ADD COLUMN disable_thinking INTEGER NOT NULL DEFAULT 0
    CHECK (disable_thinking IN (0, 1));
