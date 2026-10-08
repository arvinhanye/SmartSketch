-- Teacher course embedding overrides. Additive; rollback by restoring the migrator backup
-- with API and worker stopped. Never delete Neo4j vector properties during rollback.
CREATE TABLE teacher_embedding_configs (
 user_id TEXT PRIMARY KEY NOT NULL REFERENCES users(id),
 base_url TEXT NOT NULL, model TEXT NOT NULL,
 dimensions INTEGER NOT NULL CHECK (dimensions BETWEEN 1 AND 4096),
 key_ciphertext BLOB NOT NULL, key_nonce BLOB NOT NULL CHECK(length(key_nonce)=12),
 key_hint TEXT NOT NULL, space TEXT NOT NULL, revision TEXT NOT NULL,
 version INTEGER NOT NULL CHECK(version>=1),
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TRIGGER teacher_embedding_role_insert BEFORE INSERT ON teacher_embedding_configs
WHEN NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.user_id AND role='teacher')
BEGIN SELECT RAISE(ABORT,'embedding configuration requires teacher'); END;
CREATE TRIGGER teacher_embedding_role_update BEFORE UPDATE ON teacher_embedding_configs
WHEN NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.user_id AND role='teacher')
BEGIN SELECT RAISE(ABORT,'embedding configuration requires teacher'); END;
