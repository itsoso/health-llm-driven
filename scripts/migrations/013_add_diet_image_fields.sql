-- 013_add_diet_image_fields.sql
-- 为饮食记录表添加图片和AI识别相关字段

-- 添加图片URL字段
ALTER TABLE diet_records ADD COLUMN image_url TEXT;

-- 添加AI识别标记
ALTER TABLE diet_records ADD COLUMN ai_recognized INTEGER DEFAULT 0;

-- 添加AI识别置信度
ALTER TABLE diet_records ADD COLUMN ai_confidence REAL;

-- 添加AI原始结果
ALTER TABLE diet_records ADD COLUMN ai_raw_result TEXT;

-- 添加健康提示
ALTER TABLE diet_records ADD COLUMN health_tips TEXT;

-- 添加更新时间
ALTER TABLE diet_records ADD COLUMN updated_at DATETIME;
