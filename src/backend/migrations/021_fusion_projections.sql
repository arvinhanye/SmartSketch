-- DISAMBIG-BE-02: isolated draft projections; immutable plan data, append-only undo.
-- Before rollback: stop workers, back up SQLite/Neo4j, materialize the active
-- projection as legacy draft and verify its digest. Do not simply drop this column.
-- ROLLBACK: CREATE TEMP TABLE fusion_rollback_guard(ok INTEGER CHECK(ok=1));
-- ROLLBACK: INSERT INTO fusion_rollback_guard SELECT CASE WHEN EXISTS(SELECT 1 FROM courses WHERE draft_storage_version <> 'draft') THEN 0 ELSE 1 END;
-- ROLLBACK: DROP TABLE fusion_undos;
-- ROLLBACK: DROP TABLE fusion_plans;
-- ROLLBACK: ALTER TABLE courses DROP COLUMN draft_storage_version;
-- ROLLBACK: DROP TABLE fusion_rollback_guard;
-- ROLLBACK: DELETE FROM schema_migrations WHERE version = '021';
ALTER TABLE courses ADD COLUMN draft_storage_version TEXT NOT NULL DEFAULT 'draft'
    CHECK (draft_storage_version = 'draft' OR draft_storage_version GLOB 'draftgen_*');

CREATE TABLE fusion_plans (
    plan_id TEXT PRIMARY KEY NOT NULL,
    course_id TEXT NOT NULL REFERENCES courses(id),
    task_id TEXT NOT NULL REFERENCES processing_tasks(id),
    head_json TEXT NOT NULL,
    input_digest TEXT NOT NULL,
    storage_version_id TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'prepared' CHECK (state IN ('prepared','committed','skipped')),
    applied INTEGER NOT NULL DEFAULT 0 CHECK (applied IN (0,1)),
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(course_id, task_id, input_digest)
);
CREATE INDEX idx_fusion_task ON fusion_plans(course_id, task_id);
CREATE TRIGGER fusion_plan_immutable BEFORE UPDATE OF
    plan_id, course_id, task_id, head_json, input_digest, storage_version_id, payload ON fusion_plans
BEGIN SELECT RAISE(ABORT, 'immutable fusion plan'); END;

CREATE TABLE fusion_undos (
    undo_id TEXT PRIMARY KEY NOT NULL,
    course_id TEXT NOT NULL REFERENCES courses(id),
    plan_id TEXT NOT NULL REFERENCES fusion_plans(plan_id),
    group_id TEXT NOT NULL,
    actor_id TEXT NOT NULL REFERENCES users(id),
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(course_id, plan_id, group_id)
);
CREATE TRIGGER fusion_undo_immutable BEFORE UPDATE ON fusion_undos
BEGIN SELECT RAISE(ABORT, 'immutable fusion undo'); END;
