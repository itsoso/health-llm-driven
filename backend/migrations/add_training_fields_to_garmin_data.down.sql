-- Rollback: add_training_fields_to_garmin_data.sql
ALTER TABLE garmin_data
    DROP COLUMN IF EXISTS training_readiness_score,
    DROP COLUMN IF EXISTS training_readiness_level,
    DROP COLUMN IF EXISTS training_readiness_factors,
    DROP COLUMN IF EXISTS training_status,
    DROP COLUMN IF EXISTS training_status_feedback,
    DROP COLUMN IF EXISTS acute_load,
    DROP COLUMN IF EXISTS load_ratio;
