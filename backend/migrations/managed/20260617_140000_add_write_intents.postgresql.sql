-- Write 层 v0 写意图账本(write_intents)。Agent/规则提议替你写一件事,用户一键确认才执行。
-- 见 docs/design/health-os/architecture-lens.md。幂等可重跑(IF NOT EXISTS)。
-- 注 runner 按裸分号切分语句,注释里不能出现分号。
CREATE TABLE IF NOT EXISTS write_intents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    kind VARCHAR(40) NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    source VARCHAR(50),
    trust_tier VARCHAR(20) NOT NULL DEFAULT 'manual_confirm',
    target_type VARCHAR(40),
    target_id INTEGER,
    payload JSONB,
    executed_ref VARCHAR(80),
    created_at TIMESTAMPTZ DEFAULT now(),
    decided_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_write_intents_user_id ON write_intents (user_id);
CREATE INDEX IF NOT EXISTS ix_write_intents_status ON write_intents (status);
CREATE INDEX IF NOT EXISTS ix_write_intents_user_status ON write_intents (user_id, status);
