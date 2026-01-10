-- 添加 route_data 字段到 workout_records 表
-- 用于存储 GPS 路线数据

ALTER TABLE workout_records 
ADD COLUMN route_data TEXT;

-- 添加注释
COMMENT ON COLUMN workout_records.route_data IS 'GPS路线数据 JSON格式 [{"lat": 39.9, "lng": 116.4, "elevation": 100, "time": 0}, ...]';
