-- SQLite 等价(测试库)。
CREATE TABLE IF NOT EXISTS bedroom_automation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    room_id VARCHAR(64) NOT NULL DEFAULT 'bedroom',
    event_type VARCHAR(64) NOT NULL,
    reason VARCHAR(256),
    command_entity_id VARCHAR(128),
    command_mode VARCHAR(64),
    source VARCHAR(16) NOT NULL DEFAULT 'ha',
    manual_override BOOLEAN NOT NULL DEFAULT 0,
    audit_ref VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_bedroom_event_user_created
    ON bedroom_automation_events (user_id, created_at);
