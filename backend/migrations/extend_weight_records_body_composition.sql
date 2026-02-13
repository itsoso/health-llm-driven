-- 扩展 weight_records 表，添加身体成分字段
-- 注意：仅新增列，不影响已有数据

ALTER TABLE weight_records ADD COLUMN IF NOT EXISTS visceral_fat INTEGER;
ALTER TABLE weight_records ADD COLUMN IF NOT EXISTS bone_mass_kg FLOAT;
ALTER TABLE weight_records ADD COLUMN IF NOT EXISTS water_percentage FLOAT;
ALTER TABLE weight_records ADD COLUMN IF NOT EXISTS bmi FLOAT;
ALTER TABLE weight_records ADD COLUMN IF NOT EXISTS bmr INTEGER;
ALTER TABLE weight_records ADD COLUMN IF NOT EXISTS metabolic_age INTEGER;
ALTER TABLE weight_records ADD COLUMN IF NOT EXISTS subcutaneous_fat FLOAT;
ALTER TABLE weight_records ADD COLUMN IF NOT EXISTS skeletal_muscle_pct FLOAT;
ALTER TABLE weight_records ADD COLUMN IF NOT EXISTS protein_pct FLOAT;

-- 添加 CHECK 约束
ALTER TABLE weight_records ADD CONSTRAINT chk_visceral_fat CHECK (visceral_fat IS NULL OR (visceral_fat >= 1 AND visceral_fat <= 30));
ALTER TABLE weight_records ADD CONSTRAINT chk_water_percentage CHECK (water_percentage IS NULL OR (water_percentage >= 0 AND water_percentage <= 100));
ALTER TABLE weight_records ADD CONSTRAINT chk_bmi CHECK (bmi IS NULL OR (bmi >= 10 AND bmi <= 80));
ALTER TABLE weight_records ADD CONSTRAINT chk_protein_pct CHECK (protein_pct IS NULL OR (protein_pct >= 0 AND protein_pct <= 100));
ALTER TABLE weight_records ADD CONSTRAINT chk_skeletal_muscle_pct CHECK (skeletal_muscle_pct IS NULL OR (skeletal_muscle_pct >= 0 AND skeletal_muscle_pct <= 100));
ALTER TABLE weight_records ADD CONSTRAINT chk_subcutaneous_fat CHECK (subcutaneous_fat IS NULL OR (subcutaneous_fat >= 0 AND subcutaneous_fat <= 100));

-- 添加索引（已有 user_id + record_date 索引，不需要额外索引）
