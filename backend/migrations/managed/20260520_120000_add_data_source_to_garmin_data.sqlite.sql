-- sqlite test fixture mirror — 见 .postgresql.sql 注释。
-- SQLite 不支持 ADD COLUMN IF NOT EXISTS / CREATE UNIQUE INDEX 在已有重复行上,
-- 但测试库每次 in-memory 全新,不会撞到。

ALTER TABLE garmin_data ADD COLUMN data_source VARCHAR(30) NOT NULL DEFAULT 'garmin';
ALTER TABLE garmin_data ADD COLUMN body_temp_deviation_c FLOAT;
ALTER TABLE garmin_data ADD COLUMN respiratory_rate_min FLOAT;
ALTER TABLE garmin_data ADD COLUMN respiratory_rate_max FLOAT;

UPDATE garmin_data SET data_source = 'garmin' WHERE data_source IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_garmin_user_date_source
    ON garmin_data (user_id, record_date, data_source);
