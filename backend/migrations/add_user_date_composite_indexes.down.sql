-- 回滚: 撤销 (user_id, record_date) 复合索引
DROP INDEX CONCURRENTLY IF EXISTS idx_garmin_data_user_date;
DROP INDEX CONCURRENTLY IF EXISTS idx_weight_records_user_date;
DROP INDEX CONCURRENTLY IF EXISTS idx_diet_records_user_date;
DROP INDEX CONCURRENTLY IF EXISTS idx_blood_pressure_user_date;
DROP INDEX CONCURRENTLY IF EXISTS idx_supplement_records_user_date;
DROP INDEX CONCURRENTLY IF EXISTS idx_health_checkins_user_date;
