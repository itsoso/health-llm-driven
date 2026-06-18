-- 逐分钟血氧幂等(DB 兜底): (user_id, record_date, sample_time, source) 唯一。
-- spo2_samples 之前只有非唯一索引, HealthKit (_save_spo2_samples) 与 garmin 采集器
-- (_sync_spo2_samples) 都靠「按 (user,date,source) 删后插」+「同源导入串行」假设保幂等。
-- 同一 (user, source) 两个并发导入会双删双插 → 同分钟落 2 行 → 虚高 spo2_below_90_pct /
-- spo2_odi → 污染 vitals.spo2_min_nocturnal_severe 的「持续负荷」佐证 (单点伪影会被误当真低氧
-- 拉 CRITICAL)。约束含 source, 多设备同日同分钟 (apple-watch vs ringconn vs garmin) 是不同槽。
-- 脏数据前置: 先删现存重复 (同槽保留最新 max(id)), 否则在脏数据上建唯一索引会失败。
-- 注 runner 按裸分号切分语句, 注释里不能出现分号。幂等可重跑。
DELETE FROM spo2_samples a
    USING spo2_samples b
    WHERE a.user_id = b.user_id
      AND a.record_date = b.record_date
      AND a.sample_time = b.sample_time
      AND COALESCE(a.source, '') = COALESCE(b.source, '')
      AND a.id < b.id;
CREATE UNIQUE INDEX IF NOT EXISTS uq_spo2_user_date_time_source
    ON spo2_samples (user_id, record_date, sample_time, source);
