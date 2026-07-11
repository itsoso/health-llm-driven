-- Harness Slice 3: 程序性记忆/配方 (sqlite mirror)。
CREATE TABLE IF NOT EXISTS procedure_recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name VARCHAR(100) NOT NULL,
    trigger_phrases JSON NOT NULL DEFAULT '[]',
    steps JSON NOT NULL DEFAULT '[]',
    created_from_conversation_id INTEGER,
    use_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_procedure_recipes_user_id
    ON procedure_recipes(user_id);
