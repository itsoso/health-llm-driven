-- CalDAV 日历同步(sqlite 变体)。测试库由 create_all 直接建表,本迁移仅 prod 跑一次。
CREATE TABLE IF NOT EXISTS calendar_credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    provider VARCHAR(40) NOT NULL DEFAULT 'caldav',
    encrypted_credentials TEXT NOT NULL,
    sync_enabled BOOLEAN DEFAULT 1,
    last_sync_at TIMESTAMP,
    last_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_credentials_user ON calendar_credentials (user_id);
CREATE TABLE IF NOT EXISTS calendar_busy_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_date DATE NOT NULL,
    start_time VARCHAR(5) NOT NULL,
    end_time VARCHAR(5) NOT NULL,
    encrypted_title TEXT,
    external_uid VARCHAR(255),
    source VARCHAR(20) NOT NULL DEFAULT 'caldav',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_calbusy_user_date_uid ON calendar_busy_blocks (user_id, event_date, external_uid);
CREATE INDEX IF NOT EXISTS ix_calbusy_user_date ON calendar_busy_blocks (user_id, event_date);
