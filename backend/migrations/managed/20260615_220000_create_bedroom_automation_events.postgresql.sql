-- 卧室自动化事件(HA automation / 手动操作上行)。设计文档 §7/§10。隐私敏感, 不进通用 LLM。
-- 注 runner 按裸分号切分,注释里不能有分号。
CREATE TABLE IF NOT EXISTS bedroom_automation_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    room_id VARCHAR(64) NOT NULL DEFAULT 'bedroom',
    event_type VARCHAR(64) NOT NULL,
    reason VARCHAR(256),
    command_entity_id VARCHAR(128),
    command_mode VARCHAR(64),
    source VARCHAR(16) NOT NULL DEFAULT 'ha',
    manual_override BOOLEAN NOT NULL DEFAULT FALSE,
    audit_ref VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bedroom_event_user_created
    ON bedroom_automation_events (user_id, created_at);
