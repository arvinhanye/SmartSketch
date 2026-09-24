-- C01 takes ownership of the B06 bootstrap table without changing its row.
CREATE TABLE IF NOT EXISTS embedding_space_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL CHECK (dimensions >= 1),
    is_fake INTEGER NOT NULL CHECK (is_fake IN (0, 1))
);
