-- 呼吸频率时序采样（睡眠期间每 ~1 分钟一个点）
-- 来源：garminconnect.get_respiration_data() → respirationValuesArray

CREATE TABLE IF NOT EXISTS respiration_samples (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    record_date DATE NOT NULL,
    sample_time TIME NOT NULL,
    respiration_rate DOUBLE PRECISION NOT NULL,
    epoch_ms BIGINT,
    source VARCHAR(30) NOT NULL DEFAULT 'garmin',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_resp_user_date
    ON respiration_samples(user_id, record_date);
CREATE INDEX IF NOT EXISTS idx_resp_user_date_time
    ON respiration_samples(user_id, record_date, sample_time);
CREATE UNIQUE INDEX IF NOT EXISTS uq_resp_user_date_time
    ON respiration_samples(user_id, record_date, sample_time);

COMMENT ON TABLE respiration_samples IS '呼吸频率采样（brpm），供夜间 SpO2 根因分析识别阻塞事件';
