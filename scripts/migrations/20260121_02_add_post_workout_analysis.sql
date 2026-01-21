-- 添加运动后科学分析字段到 workout_records 表
-- 日期: 2026-01-21
-- 描述: 保存运动后科学分析结果，避免重复生成

-- 添加 post_workout_analysis 字段（JSON格式）
ALTER TABLE workout_records ADD COLUMN IF NOT EXISTS post_workout_analysis TEXT;

-- 添加注释
COMMENT ON COLUMN workout_records.post_workout_analysis IS '运动后科学分析 JSON: 包含心率分析、强度评估、恢复建议、改进建议等';
