-- C09: worker claim and lease columns on processing_tasks (specs/task-processing.md §8.2, §8.3).
-- D-10: numbered as main's max (004, C02) + 1; renumber to the new max + 1 before merge if main
-- already has 005. Rollback: restore backups/*-before-005.sqlite (src/backend/README.md).
--
-- Internal fields only (never on the wire). Times are unix epoch seconds evaluated by SQLite
-- (unixepoch()), matching the migrator's live-lease guard `lease_expires_at >= unixepoch()`.
-- The lease is held iff lease_expires_at IS NOT NULL; token, owner and expiry are set and
-- cleared together. The token is at least 128 bits (32 hex characters).
ALTER TABLE processing_tasks ADD COLUMN lease_owner TEXT
    CHECK (lease_owner IS NULL OR length(lease_owner) BETWEEN 1 AND 255);
ALTER TABLE processing_tasks ADD COLUMN lease_token TEXT
    CHECK (lease_token IS NULL OR length(lease_token) >= 32);
ALTER TABLE processing_tasks ADD COLUMN lease_expires_at INTEGER
    CHECK (
        (lease_expires_at IS NULL) = (lease_token IS NULL)
        AND (lease_expires_at IS NULL) = (lease_owner IS NULL)
    );
-- Number of claims so far (L3 counts claims; graceful shutdown gives one back).
ALTER TABLE processing_tasks ADD COLUMN attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0);
-- Earliest claim time; initially the task's creation time (set by the trigger below, since
-- ADD COLUMN cannot take a non-constant default), later pushed back by the retry backoff.
ALTER TABLE processing_tasks ADD COLUMN not_before INTEGER;
-- A persisting failure whose storage cleanup has not finished yet (§8.4, set/cleared by F13).
ALTER TABLE processing_tasks ADD COLUMN cleanup_pending INTEGER NOT NULL DEFAULT 0
    CHECK (cleanup_pending IN (0, 1));

-- Task.error for T9 (§6, §8.3). I4: stage = failed ⇔ error present. details is a JSON object.
ALTER TABLE processing_tasks ADD COLUMN error_code TEXT;
ALTER TABLE processing_tasks ADD COLUMN error_message TEXT
    CHECK ((error_message IS NULL) = (error_code IS NULL));
ALTER TABLE processing_tasks ADD COLUMN error_details TEXT
    CHECK (
        (stage = 'failed') = (error_code IS NOT NULL)
        AND (error_code IS NULL OR length(trim(error_message)) > 0)
        AND (error_details IS NULL OR (error_code IS NOT NULL AND json_valid(error_details)
            AND json_type(error_details) = 'object'))
    );

UPDATE processing_tasks SET not_before = unixepoch(created_at) WHERE not_before IS NULL;

CREATE TRIGGER processing_tasks_not_before_default
AFTER INSERT ON processing_tasks
WHEN NEW.not_before IS NULL
BEGIN
    UPDATE processing_tasks SET not_before = unixepoch(NEW.created_at) WHERE id = NEW.id;
END;

CREATE TRIGGER processing_tasks_not_before_required
BEFORE UPDATE OF not_before ON processing_tasks
WHEN NEW.not_before IS NULL
BEGIN
    SELECT RAISE(ABORT, 'processing_tasks: not_before is required');
END;
