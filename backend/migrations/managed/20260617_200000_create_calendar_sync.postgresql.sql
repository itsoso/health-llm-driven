-- CalDAV 日历同步:加密凭据 + 当日忙碌块(timing-solver 避开会议)。幂等可重跑。
-- 凭据/标题在应用层 Fernet 加密后才进 encrypted_* 列;本表不存明文。
CREATE TABLE IF NOT EXISTS calendar_credentials (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    provider VARCHAR(40) NOT NULL DEFAULT 'caldav',
    encrypted_credentials TEXT NOT NULL,
    sync_enabled BOOLEAN DEFAULT TRUE,
    last_sync_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_credentials_user ON calendar_credentials (user_id);
CREATE TABLE IF NOT EXISTS calendar_busy_blocks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    event_date DATE NOT NULL,
    start_time VARCHAR(5) NOT NULL,
    end_time VARCHAR(5) NOT NULL,
    encrypted_title TEXT,
    external_uid VARCHAR(255),
    source VARCHAR(20) NOT NULL DEFAULT 'caldav',
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_calbusy_user_date_uid ON calendar_busy_blocks (user_id, event_date, external_uid);
CREATE INDEX IF NOT EXISTS ix_calbusy_user_date ON calendar_busy_blocks (user_id, event_date);
