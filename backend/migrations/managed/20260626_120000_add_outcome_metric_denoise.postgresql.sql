-- R16 P2: 干预结局端点去噪溯源(7d-MA 平滑 / 稀疏未平滑)。
-- 纯增列、可空;NULL = 旧行未经 P2 去噪 → 按原始单点 delta(legacy 行为不变,无 backfill)。
ALTER TABLE outcome_metrics ADD COLUMN IF NOT EXISTS smoothing_method VARCHAR(12);
ALTER TABLE outcome_metrics ADD COLUMN IF NOT EXISTS sample_n INTEGER;
