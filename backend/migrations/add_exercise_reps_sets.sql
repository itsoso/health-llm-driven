-- 给 exercise_records 表添加 reps 和 sets 字段
ALTER TABLE exercise_records ADD COLUMN IF NOT EXISTS reps INTEGER;
ALTER TABLE exercise_records ADD COLUMN IF NOT EXISTS sets INTEGER;
