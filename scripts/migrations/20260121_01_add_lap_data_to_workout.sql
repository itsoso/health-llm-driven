-- 添加计圈数据字段到 workout_records 表
-- 日期: 2026-01-21
-- 描述: 支持存储运动的计圈/分段数据，包括每圈的距离、时间、心率、配速等
-- 注意: 如果字段已存在会报错，可以忽略

-- 添加 lap_data 字段（JSON格式）
-- 计圈数据 JSON格式: [{"lap": 1, "distance": 1000, "duration": 300, "avg_hr": 150, "avg_pace": 300, "elevation_gain": 10}, ...]
ALTER TABLE workout_records ADD COLUMN lap_data TEXT;
