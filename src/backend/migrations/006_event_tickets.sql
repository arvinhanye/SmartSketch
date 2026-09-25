-- C16: one-time SSE event tickets (specs/identity-access.md §5).
-- D-10: 005 is taken by C09 (#220, task leases); this file assumes 005 merges first. If main has
-- no 005 when C16 merges, renumber to main's max + 1. Rollback: stop API and worker, restore
-- backups/*-before-006.sqlite (src/backend/README.md). Nothing else references this table, so
-- `DROP TABLE event_tickets;` plus deleting schema_migrations row '006' is equivalent.
--
-- Only sha256(ticket) is stored (64 lowercase hex); the plaintext never reaches the database.
-- Times are unix epoch seconds supplied by the API clock. Lifetime is fixed at 60 seconds and
-- the CHECK refuses anything longer. Redemption (C11) is a single conditional UPDATE of used_at.
CREATE TABLE event_tickets (
    ticket_hash TEXT PRIMARY KEY NOT NULL CHECK (
        length(ticket_hash) = 64 AND ticket_hash NOT GLOB '*[^0-9a-f]*'
    ),
    user_id TEXT NOT NULL REFERENCES users(id),
    task_id TEXT NOT NULL REFERENCES processing_tasks(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL,
    used_at INTEGER CHECK (used_at IS NULL OR used_at < expires_at),
    created_at INTEGER NOT NULL,
    CHECK (expires_at - created_at BETWEEN 1 AND 60)
);

-- Claims delete rows whose expiry is more than one hour old.
CREATE INDEX idx_event_tickets_expires_at ON event_tickets(expires_at);
