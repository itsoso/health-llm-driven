-- 睡眠阶段时间段表（deep/light/rem/awake，每晚约 30-60 段）
CREATE TABLE IF NOT EXISTS sleep_level_intervals (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    record_date DATE NOT NULL,
    start_epoch_ms BIGINT NOT NULL,
    end_epoch_ms BIGINT NOT NULL,
    activity_level VARCHAR(10) NOT NULL,  -- deep, light, rem, awake
    source VARCHAR DEFAULT 'garmin',
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sleep_level_user_date ON sleep_level_intervals(user_id, record_date);
