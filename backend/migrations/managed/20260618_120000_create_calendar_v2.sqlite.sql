-- Calendar v2 (C1) sqlite 变体。测试库由 create_all 直接建表,本迁移仅 prod 跑一次。幂等可重跑。
CREATE TABLE IF NOT EXISTS calendar_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    provider VARCHAR(20) NOT NULL DEFAULT 'caldav',
    name VARCHAR(200) NOT NULL,
    color VARCHAR(20),
    encrypted_credentials TEXT NOT NULL,
    writable BOOLEAN DEFAULT 0,
    sync_enabled BOOLEAN DEFAULT 1,
    last_sync_at TIMESTAMP,
    last_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_calsource_user ON calendar_sources (user_id);

CREATE TABLE IF NOT EXISTS calendar_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    uid VARCHAR(255) NOT NULL,
    encrypted_title TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    all_day BOOLEAN DEFAULT 0,
    encrypted_location TEXT,
    encrypted_description TEXT,
    encrypted_attendees TEXT,
    status VARCHAR(40),
    last_synced_at TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_calevent_source_uid ON calendar_events (source_id, uid);
CREATE INDEX IF NOT EXISTS ix_calevent_user ON calendar_events (user_id);
CREATE INDEX IF NOT EXISTS ix_calevent_source ON calendar_events (source_id);

-- 数据迁移:老 calendar_credentials 每条搬进一条 calendar_sources(密文逐字拷贝,同一把 Fernet 密钥)。
-- 幂等:仅当该用户尚无 caldav 源时才插。
INSERT INTO calendar_sources (user_id, provider, name, color, encrypted_credentials, writable, sync_enabled)
SELECT cc.user_id, 'caldav', '我的日历', NULL, cc.encrypted_credentials, 0, COALESCE(cc.sync_enabled, 1)
FROM calendar_credentials cc
WHERE NOT EXISTS (
    SELECT 1 FROM calendar_sources cs
    WHERE cs.user_id = cc.user_id AND cs.provider = 'caldav'
);
