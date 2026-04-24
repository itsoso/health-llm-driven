-- 扩 garmin_data 加 Training Readiness / Training Status / ACWR 相关字段
-- 来源：garminconnect.get_training_readiness() + get_training_status()

ALTER TABLE garmin_data
    ADD COLUMN IF NOT EXISTS training_readiness_score INTEGER,
    ADD COLUMN IF NOT EXISTS training_readiness_level VARCHAR(32),
    ADD COLUMN IF NOT EXISTS training_readiness_factors JSONB,
    ADD COLUMN IF NOT EXISTS training_status VARCHAR(32),
    ADD COLUMN IF NOT EXISTS training_status_feedback TEXT,
    ADD COLUMN IF NOT EXISTS acute_load DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS load_ratio DOUBLE PRECISION;

COMMENT ON COLUMN garmin_data.training_readiness_score IS 'Garmin Training Readiness 评分 0-100';
COMMENT ON COLUMN garmin_data.training_status IS 'productive | maintaining | detraining | overreaching | peaking | recovery | unproductive';
COMMENT ON COLUMN garmin_data.load_ratio IS 'Acute:Chronic Workload Ratio (Garmin 自家计算)';
