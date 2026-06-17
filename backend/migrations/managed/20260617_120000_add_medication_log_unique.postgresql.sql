-- medication_logs 依从写回幂等(DB 兜底): (medication_id, taken_date, COALESCE(taken_time,'')) 唯一。
-- 腕上一键 /take 写「今日按日标记」(taken_time=NULL),无 DB 约束时并发双击 / bridge 重发 /
-- 重试两条 INSERT 都过 → 同一剂落 2 条 → get_adherence_stats 计数虚高 → 经
-- twin.medication.adherence_7d_pct 喂给 DDI/PGx/SafetyGuardian 当「确实在服」误证。
-- COALESCE(taken_time,'') 把按日标记的 NULL 折叠成同一槽去重, 而 times_per_day>1 的多剂
-- (08:00 / 20:00 不同 taken_time)是不同槽, 正常并存(不误伤合法多剂)。
-- 脏数据前置: 先删现存重复(同槽保留最新 max(id)), 否则在脏数据上直接建唯一索引会失败。
-- 注 runner 按裸分号切分语句, 注释里不能出现分号。幂等可重跑。
DELETE FROM medication_logs a
    USING medication_logs b
    WHERE a.medication_id = b.medication_id
      AND a.taken_date = b.taken_date
      AND COALESCE(a.taken_time, '') = COALESCE(b.taken_time, '')
      AND a.id < b.id;
CREATE UNIQUE INDEX IF NOT EXISTS uq_medlog_med_date_time
    ON medication_logs (medication_id, taken_date, COALESCE(taken_time, ''));
-- 旧的非唯一 ix_medication_logs_med_date 与新唯一索引同前缀, 冗余 → 删(模型已不再声明它)。
DROP INDEX IF EXISTS ix_medication_logs_med_date;
