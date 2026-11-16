-- Durable global pair plans and complete semantic decisions, scoped to their full inputs.
-- Stop API/workers before rollback. Rollback discards only this resumable analysis cache.
-- ROLLBACK: CREATE TEMP TABLE fusion_decisions_rollback_guard(ok INTEGER CHECK(ok=1));
-- ROLLBACK: INSERT INTO fusion_decisions_rollback_guard SELECT NOT EXISTS(SELECT 1 FROM processing_tasks WHERE (lease_token IS NOT NULL AND lease_expires_at >= unixepoch()) OR stage IN ('queued','parsing','extracting','merging','persisting'));
-- ROLLBACK: DROP TABLE task_fusion_decisions;
-- ROLLBACK: DROP TABLE task_fusion_analysis;
-- ROLLBACK: DROP TABLE fusion_decisions_rollback_guard;
-- ROLLBACK: DELETE FROM schema_migrations WHERE version='026';
CREATE TABLE task_fusion_analysis (
    task_id TEXT NOT NULL REFERENCES processing_tasks(id) ON DELETE CASCADE,
    course_id TEXT NOT NULL,
    input_digest TEXT NOT NULL CHECK(length(trim(input_digest))>0),
    total_possible INTEGER NOT NULL CHECK(total_possible>=0),
    total INTEGER NOT NULL CHECK(total>=0 AND total<=total_possible),
    plan_json TEXT NOT NULL CHECK(json_valid(plan_json) AND json_type(plan_json)='array' AND json_array_length(plan_json)=total),
    context_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(context_json) AND json_type(context_json)='object'),
    selected_plan_id TEXT REFERENCES fusion_plans(plan_id) ON DELETE SET NULL,
    active_attempt INTEGER NOT NULL CHECK(active_attempt>=1),
    is_current INTEGER NOT NULL CHECK(is_current IN (0,1)),
    phase TEXT NOT NULL CHECK(phase IN ('running','complete')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY(task_id,input_digest), UNIQUE(task_id,input_digest,course_id)
);
CREATE UNIQUE INDEX task_fusion_analysis_current ON task_fusion_analysis(task_id) WHERE is_current=1;
CREATE TRIGGER task_fusion_analysis_scope BEFORE INSERT ON task_fusion_analysis
WHEN NOT EXISTS(SELECT 1 FROM processing_tasks WHERE id=NEW.task_id AND course_id=NEW.course_id)
BEGIN SELECT RAISE(ABORT,'fusion analysis: task outside course'); END;
CREATE TRIGGER task_fusion_analysis_identity BEFORE UPDATE ON task_fusion_analysis
WHEN OLD.task_id<>NEW.task_id OR OLD.course_id<>NEW.course_id OR OLD.input_digest<>NEW.input_digest
  OR OLD.total<>NEW.total OR OLD.total_possible<>NEW.total_possible OR OLD.plan_json<>NEW.plan_json
  OR OLD.context_json<>NEW.context_json
BEGIN SELECT RAISE(ABORT,'fusion analysis: immutable plan identity'); END;
CREATE TRIGGER task_fusion_analysis_selection_insert BEFORE INSERT ON task_fusion_analysis
WHEN NEW.selected_plan_id IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM fusion_plans WHERE plan_id=NEW.selected_plan_id AND task_id=NEW.task_id
    AND course_id=NEW.course_id AND json_extract(payload,'$.analysis_input_digest')=NEW.input_digest)
BEGIN SELECT RAISE(ABORT,'fusion analysis: selected output outside analysis'); END;
CREATE TRIGGER task_fusion_analysis_selection_update BEFORE UPDATE OF selected_plan_id ON task_fusion_analysis
WHEN NEW.selected_plan_id IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM fusion_plans WHERE plan_id=NEW.selected_plan_id AND task_id=NEW.task_id
    AND course_id=NEW.course_id AND json_extract(payload,'$.analysis_input_digest')=NEW.input_digest)
BEGIN SELECT RAISE(ABORT,'fusion analysis: selected output outside analysis'); END;
CREATE TABLE task_fusion_decisions (
    task_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    input_digest TEXT NOT NULL,
    left_id TEXT NOT NULL CHECK(length(trim(left_id))>0),
    right_id TEXT NOT NULL CHECK(left_id<right_id),
    ordinal INTEGER NOT NULL CHECK(ordinal>=0),
    status TEXT NOT NULL CHECK(status IN ('pending','running','complete','failed','deferred')),
    payload TEXT CHECK(payload IS NULL OR (json_valid(payload) AND json_type(payload)='object')),
    attempt INTEGER NOT NULL CHECK(attempt>=1),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY(task_id,input_digest,left_id,right_id), UNIQUE(task_id,input_digest,ordinal),
    FOREIGN KEY(task_id,input_digest,course_id) REFERENCES task_fusion_analysis(task_id,input_digest,course_id) ON DELETE CASCADE,
    CHECK(CASE WHEN status IN ('complete','failed','deferred') THEN payload IS NOT NULL
      AND json_extract(payload,'$.status') IS status AND json_extract(payload,'$.left_id') IS left_id
      AND json_extract(payload,'$.right_id') IS right_id ELSE payload IS NULL END),
    CHECK(status<>'complete' OR COALESCE(json_extract(payload,'$.verdict') IN ('SAME','DIFFERENT','UNCERTAIN'),0))
);
CREATE TRIGGER task_fusion_decisions_immutable BEFORE UPDATE ON task_fusion_decisions
WHEN OLD.status='complete' OR OLD.task_id<>NEW.task_id OR OLD.course_id<>NEW.course_id
 OR OLD.input_digest<>NEW.input_digest OR OLD.left_id<>NEW.left_id OR OLD.right_id<>NEW.right_id OR OLD.ordinal<>NEW.ordinal
BEGIN SELECT RAISE(ABORT,'fusion decision: completed result and identity are immutable'); END;
