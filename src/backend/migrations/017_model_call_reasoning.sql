-- C02-2 (ADR-089): measure provider-side reasoning without storing it. All four columns are
-- nullable; providers that report nothing leave them NULL (unknown, not zero). usage_reasoning is
-- part of usage_output and is never billed separately. No existing data is changed.
-- Rollback: stop API/worker and restore backups/*-before-017.sqlite, or run (SQLite >= 3.35):
-- ROLLBACK: ALTER TABLE model_calls DROP COLUMN first_content_ms;
-- ROLLBACK: ALTER TABLE model_calls DROP COLUMN first_reasoning_ms;
-- ROLLBACK: ALTER TABLE model_calls DROP COLUMN reasoning_chars;
-- ROLLBACK: ALTER TABLE model_calls DROP COLUMN usage_reasoning;
-- ROLLBACK: DELETE FROM schema_migrations WHERE filename LIKE '%_model_call_reasoning.sql';
ALTER TABLE model_calls ADD COLUMN usage_reasoning INTEGER CHECK (usage_reasoning >= 0);
ALTER TABLE model_calls ADD COLUMN reasoning_chars INTEGER CHECK (reasoning_chars >= 0);
ALTER TABLE model_calls ADD COLUMN first_reasoning_ms INTEGER CHECK (first_reasoning_ms >= 0);
ALTER TABLE model_calls ADD COLUMN first_content_ms INTEGER CHECK (first_content_ms >= 0);
