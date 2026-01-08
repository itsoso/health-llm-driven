-- 添加踢腿次数字段
-- 执行命令: sqlite3 health.db < scripts/migrations/20260108_02_add_leg_raises_count.sql

ALTER TABLE health_checkins ADD COLUMN leg_raises_count INTEGER;
