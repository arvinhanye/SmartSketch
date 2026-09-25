-- C06: a material and its first processing task are created in one SQLite transaction.
CREATE TABLE materials (
    id TEXT PRIMARY KEY NOT NULL,
    course_id TEXT NOT NULL CHECK (length(trim(course_id)) > 0),
    filename TEXT NOT NULL CHECK (length(filename) BETWEEN 1 AND 255),
    format TEXT NOT NULL CHECK (format IN ('pdf', 'docx', 'txt', 'markdown')),
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 71
        AND substr(content_hash, 1, 7) = 'sha256:'
        AND substr(content_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    storage_name TEXT NOT NULL UNIQUE,
    parse_status TEXT NOT NULL DEFAULT 'queued' CHECK (
        parse_status IN (
            'queued', 'parsing', 'extracting', 'merging', 'persisting',
            'awaiting_review', 'completed', 'failed', 'cancelled'
        )
    ),
    uploaded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (course_id, id)
);

CREATE TABLE processing_tasks (
    id TEXT PRIMARY KEY NOT NULL,
    course_id TEXT NOT NULL CHECK (length(trim(course_id)) > 0),
    document_id TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT 'queued' CHECK (
        stage IN (
            'queued', 'parsing', 'extracting', 'merging', 'persisting',
            'awaiting_review', 'completed', 'failed', 'cancelled'
        )
    ),
    progress REAL NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 1),
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    idempotency_key TEXT NOT NULL CHECK (
        length(trim(idempotency_key)) BETWEEN 1 AND 255
    ),
    UNIQUE (course_id, idempotency_key),
    FOREIGN KEY (course_id, document_id)
        REFERENCES materials(course_id, id) ON DELETE RESTRICT,
    CHECK (stage != 'queued' OR progress = 0),
    CHECK (stage != 'cancelled' OR cancel_requested = 1)
);

CREATE INDEX idx_processing_tasks_course_stage_created
    ON processing_tasks(course_id, stage, created_at, id);
