-- 2026-05-12: GPS 反查只存了 detected_city (e.g. "海淀"), 但下游 weather_service /
-- air_quality_service 用城市名查 _city_to_coords() / _city_to_location_id() 字典,
-- "海淀" 不在字典 → fallback 到杭州坐标 (30.27, 120.16). 用户在北京却看到杭州的天气/AQ.
--
-- 修法: 把 GPS 拿到的精确 lat/lon 一起存进 profile, environment.py 优先读这两列
-- 透传给 service, 跳过城市字典查询. 区/县级精度也能保留 (qweather AQ v1 1km 精度).

ALTER TABLE user_profiles
    ADD COLUMN IF NOT EXISTS detected_lat DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS detected_lon DOUBLE PRECISION;
