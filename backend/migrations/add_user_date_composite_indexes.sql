-- 添加 (user_id, record_date) 复合索引
-- ============================================
-- 原因: 6 张热表只有 record_date 单列索引, 每个 "WHERE user_id=? AND record_date BETWEEN" 查询
-- 都要扫 record_date 索引再 filter user_id, 当一个用户 540 天 × N 用户时性能差.
--
-- 影响:
-- - garmin_data: 每次 dashboard / 卡片 / SafetyPanel 查询都打这个表
-- - diet_records: 每日饮食卡 + 饮食统计
-- - weight_records: 体重卡 + 减重轨迹
-- - blood_pressure_records: BP 卡 + 趋势分析
-- - supplement_records: 补剂打卡 + 周报
-- - health_checkins: 鼻炎喷嚏数等核心 checkin 查询
--
-- 用 IF NOT EXISTS 防止重复执行.
-- 用 CONCURRENTLY 避免锁表 (PostgreSQL only).
-- ============================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_garmin_data_user_date
  ON garmin_data(user_id, record_date);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_weight_records_user_date
  ON weight_records(user_id, record_date);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_diet_records_user_date
  ON diet_records(user_id, record_date);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_blood_pressure_user_date
  ON blood_pressure_records(user_id, record_date);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_supplement_records_user_date
  ON supplement_records(user_id, record_date);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_health_checkins_user_date
  ON health_checkins(user_id, checkin_date);

-- ============================================
-- 验证执行后状态:
--   SELECT schemaname, tablename, indexname, indexdef
--   FROM pg_indexes
--   WHERE indexname LIKE 'idx_%_user_date'
--   ORDER BY tablename;
--
-- 预期看到 6 行新索引.
-- ============================================

-- 顺手让 PostgreSQL 重新统计 (帮助优化器选择新索引):
ANALYZE garmin_data;
ANALYZE weight_records;
ANALYZE diet_records;
ANALYZE blood_pressure_records;
ANALYZE supplement_records;
ANALYZE health_checkins;
