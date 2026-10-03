-- N01/N06 (ADR-082 decision 1): a configuration identity that never repeats, even after
-- clear-and-recreate resets ``version`` to 1. Every save writes a fresh random revision; the
-- QA model cache and the conditional test-result write compare it instead of ``version``.
-- Existing rows get a random backfill. No data is removed.
-- Rollback: stop API/worker and restore backups/*-before-016.sqlite, or run (SQLite >= 3.35):
-- ROLLBACK: ALTER TABLE user_model_configs DROP COLUMN revision;
-- ROLLBACK: DELETE FROM schema_migrations WHERE filename LIKE '%_model_config_revision.sql';
ALTER TABLE user_model_configs ADD COLUMN revision TEXT;
UPDATE user_model_configs SET revision = lower(hex(randomblob(16))) WHERE revision IS NULL;
