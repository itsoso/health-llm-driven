-- 压力时序采样（每 ~3 分钟一个点，全天 ~480 个点）
-- 来源：garminconnect.get_stress_data() / get_all_day_stress()

CREATE TABLE IF NOT EXISTS stress_samples (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    record_date DATE NOT NULL,
    sample_time TIME NOT NULL,
    stress_value INTEGER NOT NULL,
    epoch_ms BIGINT,
    source VARCHAR(30) NOT NULL DEFAULT 'garmin',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stress_user_date
    ON stress_samples(user_id, record_date);
CREATE INDEX IF NOT EXISTS idx_stress_user_date_time
    ON stress_samples(user_id, record_date, sample_time);
CREATE UNIQUE INDEX IF NOT EXISTS uq_stress_user_date_time
    ON stress_samples(user_id, record_date, sample_time);

COMMENT ON TABLE stress_samples IS '压力逐分钟采样 0-100，-1/-2 表示无数据/休息';
