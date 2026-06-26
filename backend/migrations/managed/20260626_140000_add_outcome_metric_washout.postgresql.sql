-- R16 P3: 跨周期洗脱期归因(attribution_state / washout_until)。
-- 纯增列、可空;NULL = legacy = attributable(单周期用户行为不变,无 backfill)。
ALTER TABLE outcome_metrics ADD COLUMN IF NOT EXISTS attribution_state VARCHAR(16);
ALTER TABLE outcome_metrics ADD COLUMN IF NOT EXISTS washout_until DATE;
