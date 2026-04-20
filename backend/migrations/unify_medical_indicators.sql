-- 统一体检指标存储：medical_indicators 成为唯一指标表
-- 执行方式: psql $DATABASE_URL -f backend/migrations/unify_medical_indicators.sql

BEGIN;

ALTER TABLE medical_indicators ADD COLUMN IF NOT EXISTS exam_id INTEGER REFERENCES medical_exams(id) ON DELETE SET NULL;
ALTER TABLE medical_indicators ADD COLUMN IF NOT EXISTS item_code VARCHAR(100);
ALTER TABLE medical_indicators ADD COLUMN IF NOT EXISTS value_text TEXT;
ALTER TABLE medical_indicators ADD COLUMN IF NOT EXISTS reference_range VARCHAR(200);
ALTER TABLE medical_indicators ADD COLUMN IF NOT EXISTS result VARCHAR(100);
ALTER TABLE medical_indicators ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE medical_indicators ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'manual';

ALTER TABLE medical_indicators ALTER COLUMN value DROP NOT NULL;

COMMIT;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_indicator_user_code_date
    ON medical_indicators(user_id, item_code, record_date);
