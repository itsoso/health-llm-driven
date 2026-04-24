-- Nocturnal SpO2 Events: 分析夜间 SpO2 时序后落盘的氧降事件
-- 每条 = 一次连续下降 ≥4% 持续 ≥10s 的事件（临床 ODI 口径）
-- 供 Mobile 图上红点渲染、4 周 A/B 对比、行为关联规则消费

CREATE TABLE IF NOT EXISTS nocturnal_spo2_events (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    night_date DATE NOT NULL,
    start_ts TIMESTAMP WITH TIME ZONE NOT NULL,
    end_ts TIMESTAMP WITH TIME ZONE NOT NULL,
    duration_seconds INTEGER NOT NULL,
    min_spo2 DOUBLE PRECISION NOT NULL,
    baseline_spo2 DOUBLE PRECISION,
    drop_magnitude DOUBLE PRECISION NOT NULL,          -- 百分点
    concurrent_hr_delta DOUBLE PRECISION,              -- 相对基线心率变化 (bpm)
    concurrent_respiration_rate DOUBLE PRECISION,      -- 事件期间平均呼吸率
    sleep_stage VARCHAR(16),                           -- awake/light/deep/rem
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_nocturnal_events_user_night
    ON nocturnal_spo2_events(user_id, night_date);
CREATE INDEX IF NOT EXISTS ix_nocturnal_events_user_start
    ON nocturnal_spo2_events(user_id, start_ts);

-- 幂等键：同夜同起点唯一（重跑分析可覆盖）
CREATE UNIQUE INDEX IF NOT EXISTS uq_nocturnal_events_user_night_start
    ON nocturnal_spo2_events(user_id, night_date, start_ts);

ALTER TABLE nocturnal_spo2_events OWNER TO health_user;
ALTER SEQUENCE nocturnal_spo2_events_id_seq OWNER TO health_user;

COMMENT ON TABLE nocturnal_spo2_events IS '夜间氧降事件（SpO2 连续下降 ≥4% 持续 ≥10s），供 P1b 根因分析';
COMMENT ON COLUMN nocturnal_spo2_events.sleep_stage IS '事件起点所在的睡眠分期';
