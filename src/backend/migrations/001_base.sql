-- C01 takes ownership of the B06 bootstrap table without changing its row.
CREATE TABLE IF NOT EXISTS embedding_space_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL CHECK (dimensions >= 1),
    is_fake INTEGER NOT NULL CHECK (is_fake IN (0, 1))
);

-- ADR-011 revision 2: one row per physical model call, including retries.
CREATE TABLE IF NOT EXISTS model_calls (
    call_id TEXT PRIMARY KEY NOT NULL,
    status TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent', 'ok', 'error')),
    course_id TEXT NOT NULL,
    task_id TEXT,
    chunk_id TEXT,
    request_id TEXT,
    purpose TEXT NOT NULL,
    task_attempt INTEGER,
    chunk_attempt INTEGER,
    call_seq INTEGER,
    provider_role TEXT NOT NULL,
    is_repair INTEGER NOT NULL CHECK (is_repair IN (0, 1)),
    model_requested TEXT NOT NULL,
    model_responded TEXT,
    input_tokens_est INTEGER NOT NULL CHECK (input_tokens_est >= 0),
    max_output_tokens INTEGER NOT NULL CHECK (max_output_tokens >= 0),
    usage_input INTEGER CHECK (usage_input >= 0),
    usage_output INTEGER CHECK (usage_output >= 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    finished_at TEXT,
    latency_ms INTEGER CHECK (latency_ms >= 0),
    error_class TEXT
);

CREATE INDEX IF NOT EXISTS idx_model_calls_task_id ON model_calls(task_id);
CREATE INDEX IF NOT EXISTS idx_model_calls_request_id ON model_calls(request_id);
CREATE INDEX IF NOT EXISTS idx_model_calls_created_at ON model_calls(created_at);
