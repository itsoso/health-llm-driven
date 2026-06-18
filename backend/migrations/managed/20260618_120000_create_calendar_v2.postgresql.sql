-- Calendar v2 (C1):多源日历 + 详细事件。幂等可重跑。
-- 凭据与事件 PII(标题/地点/描述/参会人)均在应用层 Fernet 加密后才进 encrypted_* 列,本表只存密文 TEXT。
CREATE TABLE IF NOT EXISTS calendar_sources (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    provider VARCHAR(20) NOT NULL DEFAULT 'caldav',
    name VARCHAR(200) NOT NULL,
    color VARCHAR(20),
    encrypted_credentials TEXT NOT NULL,
    writable BOOLEAN DEFAULT FALSE,
    sync_enabled BOOLEAN DEFAULT TRUE,
    last_sync_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_calsource_user ON calendar_sources (user_id);

CREATE TABLE IF NOT EXISTS calendar_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    source_id INTEGER NOT NULL REFERENCES calendar_sources(id),
    uid VARCHAR(255) NOT NULL,
    encrypted_title TEXT,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    all_day BOOLEAN DEFAULT FALSE,
    encrypted_location TEXT,
    encrypted_description TEXT,
    encrypted_attendees TEXT,
    status VARCHAR(40),
    last_synced_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_calevent_source_uid ON calendar_events (source_id, uid);
CREATE INDEX IF NOT EXISTS ix_calevent_user ON calendar_events (user_id);
CREATE INDEX IF NOT EXISTS ix_calevent_source ON calendar_events (source_id);

-- 数据迁移:把老 calendar_credentials 每条搬进一条 calendar_sources(同一把 Fernet 密钥,密文逐字拷贝)。
-- 幂等:仅当该用户当前还没有任何 caldav 源时才插,重跑安全。
INSERT INTO calendar_sources (user_id, provider, name, color, encrypted_credentials, writable, sync_enabled)
SELECT cc.user_id, 'caldav', '我的日历', NULL, cc.encrypted_credentials, FALSE, COALESCE(cc.sync_enabled, TRUE)
FROM calendar_credentials cc
WHERE NOT EXISTS (
    SELECT 1 FROM calendar_sources cs
    WHERE cs.user_id = cc.user_id AND cs.provider = 'caldav'
);
