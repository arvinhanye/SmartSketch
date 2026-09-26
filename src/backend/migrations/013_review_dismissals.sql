-- F11: review-queue items a teacher kept as they are (ADR-060). "Not a duplicate" pairs
-- (kind = suspected_duplicate, item_key = JSON array of the two kp_ids in ascending order) and
-- "keep this isolated node" (kind = isolated_node, item_key = kp_id) leave the queue without
-- touching the draft graph. Number 013 was pre-assigned by the coordinator (012 = F12).
--
-- Rollback (preferred): stop API and worker, restore backups/*-before-013.sqlite
-- (src/backend/README.md). Manual rollback only drops the teachers' dismissals, so the
-- dismissed items reappear in the queue; no graph data is lost (tested in test_f11.py):
-- ROLLBACK: DROP TABLE review_dismissals;
-- ROLLBACK: DELETE FROM schema_migrations WHERE filename LIKE '%_review_dismissals.sql';
CREATE TABLE review_dismissals (
    course_id TEXT NOT NULL REFERENCES courses(id),
    kind TEXT NOT NULL CHECK (kind IN ('suspected_duplicate', 'isolated_node')),
    item_key TEXT NOT NULL CHECK (length(item_key) > 0),
    dismissed_by TEXT NOT NULL REFERENCES users(id),
    dismissed_at TEXT NOT NULL,
    PRIMARY KEY (course_id, kind, item_key)
);
