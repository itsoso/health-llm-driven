-- 扩 garmin_data 加 Endurance / Hill / Race predictions / Hydration / Fitness age
-- 来源：garminconnect 各专项 API

ALTER TABLE garmin_data
    ADD COLUMN IF NOT EXISTS endurance_score INTEGER,
    ADD COLUMN IF NOT EXISTS hill_score INTEGER,
    ADD COLUMN IF NOT EXISTS race_predictions JSONB,
    ADD COLUMN IF NOT EXISTS hydration_ml INTEGER,
    ADD COLUMN IF NOT EXISTS vo2max_fitness_age INTEGER;

COMMENT ON COLUMN garmin_data.race_predictions IS '{5k, 10k, half_marathon, marathon} 预计完成时间（秒）';
COMMENT ON COLUMN garmin_data.hydration_ml IS '当日水合量（毫升）';
