-- Multi-source health data: garmin_data 现承载 Apple Watch / RingConn / Oura 等通过 HealthKit
-- 上行的同质指标。引入 data_source 区分来源,(user_id, record_date, data_source) 复合唯一,
-- 让 upsert 在多源共存时不互相覆盖。
-- vo2max 不再扩 generic 列 — 现有 vo2max_running / vo2max_cycling 已够用,HealthKit
-- VO2Max identifier 走 vo2max_running。

ALTER TABLE garmin_data ADD COLUMN IF NOT EXISTS data_source VARCHAR(30) NOT NULL DEFAULT 'garmin';
ALTER TABLE garmin_data ADD COLUMN IF NOT EXISTS body_temp_deviation_c FLOAT;
ALTER TABLE garmin_data ADD COLUMN IF NOT EXISTS respiratory_rate_min FLOAT;
ALTER TABLE garmin_data ADD COLUMN IF NOT EXISTS respiratory_rate_max FLOAT;

-- backfill 防御:DEFAULT 已托底,但若历史曾以 nullable 加列则补一遍
UPDATE garmin_data SET data_source = 'garmin' WHERE data_source IS NULL;

-- 复合唯一约束:同 (user, date, source) 唯一,允许同一天来自不同源各一行
CREATE UNIQUE INDEX IF NOT EXISTS idx_garmin_user_date_source
    ON garmin_data (user_id, record_date, data_source);
