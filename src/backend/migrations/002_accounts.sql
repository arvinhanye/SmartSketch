-- C13: local accounts (specs/identity-access.md §1.1, ADR-013). Disabled accounts keep
-- their row (disabled_at) so progress, chat and edit logs keep their foreign keys.
CREATE TABLE users (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) BETWEEN 32 AND 64),
    username TEXT NOT NULL UNIQUE CHECK (
        length(username) BETWEEN 3 AND 32
        AND username NOT GLOB '*[^a-z0-9_.-]*'
    ),
    -- argon2id PHC string only; a plaintext password can never satisfy this format
    password_hash TEXT NOT NULL CHECK (password_hash GLOB '$argon2id$v=*$m=*,t=*,p=*$*$*'),
    role TEXT NOT NULL CHECK (role IN ('teacher', 'student')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    disabled_at TEXT
);
