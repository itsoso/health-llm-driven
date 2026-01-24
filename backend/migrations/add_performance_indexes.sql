-- 性能优化索引创建脚本
-- 执行方式: psql -U health_user -d health_db -f add_performance_indexes.sql

-- ============================================
-- 1. 用户相关表索引
-- ============================================

-- Garmin 数据表
CREATE INDEX IF NOT EXISTS idx_garmin_data_user_date 
ON garmin_data(user_id, record_date DESC);

CREATE INDEX IF NOT EXISTS idx_garmin_data_user_date_type 
ON garmin_data(user_id, record_date DESC, data_type);

-- 饮食记录表
CREATE INDEX IF NOT EXISTS idx_diet_records_user_date 
ON diet_records(user_id, record_date DESC);

CREATE INDEX IF NOT EXISTS idx_diet_records_user_date_meal 
ON diet_records(user_id, record_date DESC, meal_type);

-- 补剂记录表
CREATE INDEX IF NOT EXISTS idx_supplement_records_user_date 
ON supplement_records(user_id, record_date);

CREATE INDEX IF NOT EXISTS idx_supplement_records_supp_date 
ON supplement_records(supplement_id, record_date);

-- 补剂定义表
CREATE INDEX IF NOT EXISTS idx_supplement_definitions_user_active 
ON supplement_definitions(user_id, is_active);

-- 用户画像表
CREATE INDEX IF NOT EXISTS idx_user_profiles_user 
ON user_profiles(user_id);

-- ============================================
-- 2. 性能监控表索引
-- ============================================

-- 性能指标表
CREATE INDEX IF NOT EXISTS idx_performance_metrics_timestamp 
ON performance_metrics(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_performance_metrics_type_time 
ON performance_metrics(metric_type, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_performance_metrics_platform_time 
ON performance_metrics(platform, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_performance_metrics_user_time 
ON performance_metrics(user_id, timestamp DESC) 
WHERE user_id IS NOT NULL;

-- 性能告警表
CREATE INDEX IF NOT EXISTS idx_performance_alerts_created 
ON performance_alerts(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_performance_alerts_resolved 
ON performance_alerts(is_resolved, created_at DESC);

-- ============================================
-- 3. 复合索引（高频查询）
-- ============================================

-- 用户最近的 Garmin 数据
CREATE INDEX IF NOT EXISTS idx_garmin_user_recent 
ON garmin_data(user_id, record_date DESC, id DESC);

-- 用户今日饮食记录
CREATE INDEX IF NOT EXISTS idx_diet_user_today 
ON diet_records(user_id, record_date DESC, meal_type, created_at DESC);

-- 用户补剂打卡状态
CREATE INDEX IF NOT EXISTS idx_supplement_records_status 
ON supplement_records(user_id, record_date, taken);

-- ============================================
-- 4. 部分索引（条件索引）
-- ============================================

-- 仅索引活跃的补剂定义
CREATE INDEX IF NOT EXISTS idx_supplement_definitions_active 
ON supplement_definitions(user_id, timing, sort_order) 
WHERE is_active = true;

-- 仅索引 AI 识别的饮食记录
CREATE INDEX IF NOT EXISTS idx_diet_records_ai 
ON diet_records(user_id, record_date DESC) 
WHERE ai_recognized = true;

-- 仅索引未解决的性能告警
CREATE INDEX IF NOT EXISTS idx_performance_alerts_unresolved 
ON performance_alerts(metric_type, created_at DESC) 
WHERE is_resolved = false;

-- ============================================
-- 5. 全文搜索索引（可选）
-- ============================================

-- 饮食记录食物名称搜索
CREATE INDEX IF NOT EXISTS idx_diet_records_food_search 
ON diet_records USING gin(to_tsvector('simple', food_items));

-- 补剂名称搜索
CREATE INDEX IF NOT EXISTS idx_supplement_definitions_name_search 
ON supplement_definitions USING gin(to_tsvector('simple', name));

-- ============================================
-- 6. 验证索引创建
-- ============================================

-- 查看所有索引
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;

-- 查看索引大小
SELECT 
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;

-- ============================================
-- 7. 索引使用统计
-- ============================================

-- 查看索引使用情况
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;

-- 查找未使用的索引
SELECT 
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
AND idx_scan = 0
AND indexrelid NOT IN (
    SELECT indexrelid 
    FROM pg_index 
    WHERE indisprimary OR indisunique
)
ORDER BY pg_relation_size(indexrelid) DESC;

-- ============================================
-- 8. 维护建议
-- ============================================

-- 定期执行 VACUUM ANALYZE
VACUUM ANALYZE garmin_data;
VACUUM ANALYZE diet_records;
VACUUM ANALYZE supplement_records;
VACUUM ANALYZE performance_metrics;

-- 重建索引（如果性能下降）
-- REINDEX TABLE garmin_data;
-- REINDEX TABLE diet_records;

-- ============================================
-- 完成提示
-- ============================================

\echo '✅ 索引创建完成！'
\echo ''
\echo '📊 索引统计:'
SELECT COUNT(*) as total_indexes 
FROM pg_indexes 
WHERE schemaname = 'public';

\echo ''
\echo '💾 总索引大小:'
SELECT pg_size_pretty(SUM(pg_relation_size(indexrelid))) as total_index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public';

\echo ''
\echo '🎯 下一步:'
\echo '1. 运行 EXPLAIN ANALYZE 测试查询性能'
\echo '2. 监控索引使用情况'
\echo '3. 定期执行 VACUUM ANALYZE'
