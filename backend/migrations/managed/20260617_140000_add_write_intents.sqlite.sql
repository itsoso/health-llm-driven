-- Write 层 v0 写意图账本(write_intents)。SQLite 变体(CI / 本地)。幂等可重跑。
-- 注 runner 按裸分号切分语句,注释里不能出现分号。
CREATE TABLE IF NOT EXISTS write_intents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    kind VARCHAR(40) NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    source VARCHAR(50),
    trust_tier VARCHAR(20) NOT NULL DEFAULT 'manual_confirm',
    target_type VARCHAR(40),
    target_id INTEGER,
    payload JSON,
    executed_ref VARCHAR(80),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_write_intents_user_id ON write_intents (user_id);
CREATE INDEX IF NOT EXISTS ix_write_intents_status ON write_intents (status);
CREATE INDEX IF NOT EXISTS ix_write_intents_user_status ON write_intents (user_id, status);
