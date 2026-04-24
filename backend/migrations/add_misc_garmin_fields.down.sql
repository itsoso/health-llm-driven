-- Rollback: add_misc_garmin_fields.sql
ALTER TABLE garmin_data
    DROP COLUMN IF EXISTS endurance_score,
    DROP COLUMN IF EXISTS hill_score,
    DROP COLUMN IF EXISTS race_predictions,
    DROP COLUMN IF EXISTS hydration_ml,
    DROP COLUMN IF EXISTS vo2max_fitness_age;
