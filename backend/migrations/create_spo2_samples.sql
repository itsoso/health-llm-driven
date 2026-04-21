-- 血氧采样数据表（睡眠期间逐分钟采样）
CREATE TABLE IF NOT EXISTS spo2_samples (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    record_date DATE NOT NULL,
    sample_time TIME NOT NULL,
    spo2_value INTEGER NOT NULL,
    epoch_ms BIGINT,
    source VARCHAR DEFAULT 'garmin',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_spo2_user_date ON spo2_samples(user_id, record_date);
CREATE INDEX IF NOT EXISTS idx_spo2_user_date_time ON spo2_samples(user_id, record_date, sample_time);
