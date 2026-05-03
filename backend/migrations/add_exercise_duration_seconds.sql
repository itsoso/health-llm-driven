-- 给 exercise_records 表加 duration_seconds 字段, 用于秒级时长记录
-- (例: 倒立 60 秒). 已有 duration 字段是分钟整数, 不够细.
ALTER TABLE exercise_records ADD COLUMN IF NOT EXISTS duration_seconds INTEGER;
