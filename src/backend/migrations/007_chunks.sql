-- D10: material revisions and immutable source chunks (ADR-012 revision 1 decision 9, ADR-018;
-- specs/teacher-review-publish.md V2; specs/task-processing.md §8.4 `parsing`, §8.6).
-- D-10: numbered as main's max (006, C16) + 1; renumber to the new max + 1 before merge if main
-- already has 007.
--
-- Rollback (preferred): stop API and worker, restore backups/*-before-007.sqlite
-- (src/backend/README.md). Manual rollback, which discards every stored revision and chunk;
-- run the lines below in one transaction with API and worker stopped (tested in test_d10.py):
-- ROLLBACK: DROP TABLE chunks;
-- ROLLBACK: DROP TABLE task_revisions;
-- ROLLBACK: DROP TABLE material_revisions;
-- ROLLBACK: DELETE FROM schema_migrations WHERE filename LIKE '%_chunks.sql';
--
-- Ids come from app.services.chunk_identity (D09): revision_id = rev_<64 hex> derived from
-- (material_id, content_hash, parser_version); chunk_id = revision_id || '-' || ordinal.
-- parser_version is the composite <parser>+chunk/<rule>@<target>-<overlap> (ADR-018).
-- material_id is the same concept as document_id / processing_tasks.document_id (ADR-016).

-- One row per material revision. A revision is course-scoped through its material.
CREATE TABLE material_revisions (
    revision_id TEXT PRIMARY KEY NOT NULL CHECK (
        length(revision_id) = 68
        AND substr(revision_id, 1, 4) = 'rev_'
        AND substr(revision_id, 5) NOT GLOB '*[^0-9a-f]*'
    ),
    course_id TEXT NOT NULL CHECK (length(trim(course_id)) > 0),
    material_id TEXT NOT NULL,
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 71
        AND substr(content_hash, 1, 7) = 'sha256:'
        AND substr(content_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    parser_version TEXT NOT NULL CHECK (instr(parser_version, '+chunk/') > 1),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (material_id, content_hash, parser_version),
    UNIQUE (revision_id, course_id, material_id),
    FOREIGN KEY (course_id, material_id) REFERENCES materials(course_id, id) ON DELETE RESTRICT
);

CREATE INDEX idx_material_revisions_course_material
    ON material_revisions(course_id, material_id, created_at, revision_id);

-- Which task produced which revision: the publish set (V3 rule 1) and the deletion protection
-- (V2, §8.6) both read it. Tasks processing the same revision share its chunks.
CREATE TABLE task_revisions (
    task_id TEXT NOT NULL REFERENCES processing_tasks(id) ON DELETE RESTRICT,
    revision_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    material_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (task_id, revision_id),
    FOREIGN KEY (revision_id, course_id, material_id)
        REFERENCES material_revisions(revision_id, course_id, material_id) ON DELETE RESTRICT
);

CREATE INDEX idx_task_revisions_revision ON task_revisions(revision_id, task_id);

-- Source chunks. Immutable once written: text and locators never change (PUB-30).
-- section_titles is a JSON array of strings; sources is a non-empty JSON array of
-- {block_ordinal, start, end, locator: {page?, section_titles, paragraph?, line_start?, line_end?}}.
CREATE TABLE chunks (
    chunk_id TEXT PRIMARY KEY NOT NULL,
    revision_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    material_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (typeof(ordinal) = 'integer' AND ordinal >= 0),
    text TEXT NOT NULL CHECK (length(text) > 0),
    text_sha256 TEXT NOT NULL CHECK (
        length(text_sha256) = 71
        AND substr(text_sha256, 1, 7) = 'sha256:'
        AND substr(text_sha256, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    section_titles TEXT NOT NULL CHECK (
        json_valid(section_titles) AND json_type(section_titles) = 'array'
    ),
    sources TEXT NOT NULL CHECK (
        json_valid(sources) AND json_type(sources) = 'array' AND json_array_length(sources) >= 1
    ),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (chunk_id = revision_id || '-' || ordinal),
    FOREIGN KEY (revision_id, course_id, material_id)
        REFERENCES material_revisions(revision_id, course_id, material_id) ON DELETE RESTRICT
);

CREATE INDEX idx_chunks_course_material
    ON chunks(course_id, material_id, revision_id, ordinal);
CREATE INDEX idx_chunks_revision ON chunks(revision_id, ordinal);

CREATE TRIGGER chunks_immutable
BEFORE UPDATE ON chunks
BEGIN
    SELECT RAISE(ABORT, 'chunks: rows are immutable');
END;

CREATE TRIGGER material_revisions_immutable
BEFORE UPDATE ON material_revisions
BEGIN
    SELECT RAISE(ABORT, 'material_revisions: rows are immutable');
END;

CREATE TRIGGER task_revisions_immutable
BEFORE UPDATE ON task_revisions
BEGIN
    SELECT RAISE(ABORT, 'task_revisions: rows are immutable');
END;

-- A link must name a task of the same course that processes the revision's material.
CREATE TRIGGER task_revisions_task_scope
BEFORE INSERT ON task_revisions
WHEN NOT EXISTS (
    SELECT 1 FROM processing_tasks
    WHERE id = NEW.task_id AND course_id = NEW.course_id AND document_id = NEW.material_id
)
BEGIN
    SELECT RAISE(ABORT, 'task_revisions: task must belong to the same course and material');
END;
