-- 性能优化：添加复合索引
-- 生成时间：2026-01-24
-- 说明：这些索引基于实际查询模式优化，可显著提升查询性能

-- GarminData 表索引
CREATE INDEX IF NOT EXISTS idx_garmin_user_date ON garmin_data(user_id, record_date);

-- DietRecord 表索引  
CREATE INDEX IF NOT EXISTS idx_diet_user_date ON diet_records(user_id, record_date);
CREATE INDEX IF NOT EXISTS idx_diet_user_date_meal ON diet_records(user_id, record_date, meal_type);

-- WaterIntake 表索引
CREATE INDEX IF NOT EXISTS idx_water_user_date ON water_intakes(user_id, record_date);

-- HeartRateSample 表索引
CREATE INDEX IF NOT EXISTS idx_hr_user_date ON heart_rate_samples(user_id, record_date);
CREATE INDEX IF NOT EXISTS idx_hr_user_date_time ON heart_rate_samples(user_id, record_date, sample_time);

-- WorkoutRecord 表索引
CREATE INDEX IF NOT EXISTS idx_workout_user_date ON workout_records(user_id, workout_date);
CREATE INDEX IF NOT EXISTS idx_workout_user_type ON workout_records(user_id, workout_type);
CREATE INDEX IF NOT EXISTS idx_workout_source_external ON workout_records(source, external_id);

-- BasicHealthData 表索引
CREATE INDEX IF NOT EXISTS idx_basic_health_user_date ON basic_health_data(user_id, record_date);

-- CheckinTemplate 表索引
CREATE INDEX IF NOT EXISTS idx_checkin_tmpl_user_category ON checkin_templates(user_id, category, is_active);
CREATE INDEX IF NOT EXISTS idx_checkin_tmpl_user_active ON checkin_templates(user_id, is_active, sort_order);

-- CheckinRecord 表索引
CREATE INDEX IF NOT EXISTS idx_checkin_rec_user_date ON checkin_records(user_id, checkin_date);
CREATE INDEX IF NOT EXISTS idx_checkin_rec_template_date ON checkin_records(template_id, checkin_date);
CREATE INDEX IF NOT EXISTS idx_checkin_rec_user_template_date ON checkin_records(user_id, template_id, checkin_date);

-- DailyRecommendation 表索引（包含唯一约束）
CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_rec_user_rec_date ON daily_recommendations(user_id, recommendation_date);
CREATE INDEX IF NOT EXISTS idx_daily_rec_user_analysis_date ON daily_recommendations(user_id, analysis_date);

-- 完成后查看索引使用情况（PostgreSQL）
-- SELECT schemaname, tablename, indexname, idx_scan
-- FROM pg_stat_user_indexes  
-- ORDER BY idx_scan DESC;
