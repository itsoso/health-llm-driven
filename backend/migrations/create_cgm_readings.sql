-- CGM (Continuous Glucose Monitor) 读数表
-- 支持 Libre / Dexcom / Stelo / 手动录入

CREATE TABLE IF NOT EXISTS cgm_readings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    measured_at TIMESTAMP WITH TIME ZONE NOT NULL,
    glucose_mg_dl DOUBLE PRECISION NOT NULL,
    trend_arrow VARCHAR(20),
    trend_rate DOUBLE PRECISION,
    source VARCHAR(30) NOT NULL DEFAULT 'manual',
    device_serial VARCHAR(80),
    raw_id VARCHAR(120),
    notes VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_cgm_readings_user_id ON cgm_readings(user_id);
CREATE INDEX IF NOT EXISTS ix_cgm_readings_measured_at ON cgm_readings(measured_at);
CREATE INDEX IF NOT EXISTS ix_cgm_user_time ON cgm_readings(user_id, measured_at);
CREATE UNIQUE INDEX IF NOT EXISTS ix_cgm_user_raw ON cgm_readings(user_id, raw_id) WHERE raw_id IS NOT NULL;

COMMENT ON TABLE cgm_readings IS 'CGM 连续血糖读数（支持 Libre/Dexcom/Stelo 等，单位 mg/dL）';
