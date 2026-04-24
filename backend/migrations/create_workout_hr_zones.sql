-- Workout HR Zones: 单次训练的心率区间分布
-- 来源：garminconnect.get_activity_hr_in_timezones(activity_id)
-- 每个 workout 通常 5 个 zone (Z1-Z5)

CREATE TABLE IF NOT EXISTS workout_hr_zones (
    id SERIAL PRIMARY KEY,
    workout_id INTEGER NOT NULL REFERENCES workout_records(id) ON DELETE CASCADE,
    zone_index INTEGER NOT NULL,
    zone_name VARCHAR(32),
    lower_bpm INTEGER,
    upper_bpm INTEGER,
    seconds_in_zone INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_workout_hr_zones_workout
    ON workout_hr_zones(workout_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_workout_hr_zones_workout_zone
    ON workout_hr_zones(workout_id, zone_index);

COMMENT ON TABLE workout_hr_zones IS '单次训练心率区间分布（Z1-Z5），供 MovementCoach 判断训练类型';
