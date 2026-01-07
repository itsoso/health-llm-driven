-- 添加 Garmin 数据新字段
-- 在服务器上执行: sqlite3 /opt/health-app/backend/health.db < scripts/add_garmin_fields.sql

-- HRV 扩展字段
ALTER TABLE garmin_data ADD COLUMN hrv_status VARCHAR;
ALTER TABLE garmin_data ADD COLUMN hrv_7day_avg FLOAT;

-- 卡路里详细分类
ALTER TABLE garmin_data ADD COLUMN active_calories INTEGER;
ALTER TABLE garmin_data ADD COLUMN bmr_calories INTEGER;

-- 强度活动时间
ALTER TABLE garmin_data ADD COLUMN intensity_minutes_goal INTEGER;
ALTER TABLE garmin_data ADD COLUMN moderate_intensity_minutes INTEGER;
ALTER TABLE garmin_data ADD COLUMN vigorous_intensity_minutes INTEGER;

-- 呼吸数据
ALTER TABLE garmin_data ADD COLUMN avg_respiration_awake FLOAT;
ALTER TABLE garmin_data ADD COLUMN avg_respiration_sleep FLOAT;
ALTER TABLE garmin_data ADD COLUMN lowest_respiration FLOAT;
ALTER TABLE garmin_data ADD COLUMN highest_respiration FLOAT;

-- 血氧饱和度
ALTER TABLE garmin_data ADD COLUMN spo2_avg FLOAT;
ALTER TABLE garmin_data ADD COLUMN spo2_min FLOAT;
ALTER TABLE garmin_data ADD COLUMN spo2_max FLOAT;

-- VO2 Max
ALTER TABLE garmin_data ADD COLUMN vo2max_running FLOAT;
ALTER TABLE garmin_data ADD COLUMN vo2max_cycling FLOAT;

-- 楼层和距离
ALTER TABLE garmin_data ADD COLUMN floors_climbed INTEGER;
ALTER TABLE garmin_data ADD COLUMN floors_goal INTEGER;
ALTER TABLE garmin_data ADD COLUMN distance_meters FLOAT;

-- 注意: SQLite 不支持一次添加多列，每个 ALTER TABLE 只能添加一列
-- 如果某列已存在会报错，可以忽略该错误继续执行后面的语句

