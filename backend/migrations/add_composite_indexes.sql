-- Phase 2.3: 高频查询复合索引补齐
-- 所有索引使用 IF NOT EXISTS，幂等可重复执行
-- 使用 CONCURRENTLY 避免锁表（需在事务外执行）

-- 补剂定义表：按 user_id + is_active 查询
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_supplement_definitions_user_active
    ON supplement_definitions (user_id, is_active);

-- 补剂记录表：按 user_id + record_date + taken 查询
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_supplement_records_user_date
    ON supplement_records (user_id, record_date, taken);

-- 健康打卡表：按 user_id + checkin_date 查询
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_health_checkins_user_date
    ON health_checkins (user_id, checkin_date);

-- 血压记录表：按 user_id + record_date DESC 查询最新
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_blood_pressure_records_user_date
    ON blood_pressure_records (user_id, record_date DESC);

-- 体检表：按 user_id + exam_date DESC 查询最新
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_medical_exams_user_date
    ON medical_exams (user_id, exam_date DESC);

-- 体检明细表：按 exam_id 查询（JOIN 用）
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_medical_exam_items_exam_id
    ON medical_exam_items (exam_id);
