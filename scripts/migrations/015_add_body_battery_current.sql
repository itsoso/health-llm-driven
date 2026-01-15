-- 添加当前实时电量字段
-- Migration: 015_add_body_battery_current.sql
-- Date: 2026-01-15

-- 添加 body_battery_current 列到 garmin_data 表
ALTER TABLE garmin_data ADD COLUMN body_battery_current INTEGER;

-- 添加注释说明
-- body_battery_current: 当前实时身体电量值（从 Garmin 数据的最新时间点获取）
