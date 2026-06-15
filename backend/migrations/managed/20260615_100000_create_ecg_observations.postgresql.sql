-- Apple Watch ECG 房颤筛查观测(点事件, 非日聚合)。筛查信号非诊断。
-- 注 runner 按裸分号切分,注释里不能有分号。
CREATE TABLE IF NOT EXISTS ecg_observations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    classification VARCHAR(64) NOT NULL,
    recorded_at TIMESTAMPTZ,
    afib_event_count INTEGER NOT NULL DEFAULT 0,
    data_source VARCHAR(32) NOT NULL DEFAULT 'apple-watch',
    raw_data JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_ecg_user_recorded UNIQUE (user_id, recorded_at)
);
CREATE INDEX IF NOT EXISTS ix_ecg_user_recorded
    ON ecg_observations (user_id, recorded_at);
