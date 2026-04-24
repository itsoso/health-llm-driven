-- HRV 逐夜读数（睡眠期间 每 ~5 分钟一个点）
-- 来源：garminconnect.get_hrv_data() → hrvReadings

CREATE TABLE IF NOT EXISTS hrv_readings (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    record_date DATE NOT NULL,
    reading_time TIME NOT NULL,
    hrv_value DOUBLE PRECISION NOT NULL,
    reading_type VARCHAR(32),
    epoch_ms BIGINT,
    source VARCHAR(30) NOT NULL DEFAULT 'garmin',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hrv_user_date
    ON hrv_readings(user_id, record_date);
CREATE INDEX IF NOT EXISTS idx_hrv_user_date_time
    ON hrv_readings(user_id, record_date, reading_time);
CREATE UNIQUE INDEX IF NOT EXISTS uq_hrv_user_date_time
    ON hrv_readings(user_id, record_date, reading_time);

COMMENT ON TABLE hrv_readings IS 'HRV 逐夜时序（RMSSD ms），用于 RecoveryCoach 真趋势评分';
COMMENT ON COLUMN hrv_readings.reading_type IS 'nightly | 5min_avg | instantaneous';
