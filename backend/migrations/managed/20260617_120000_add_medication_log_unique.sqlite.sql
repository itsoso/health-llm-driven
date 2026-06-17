-- SQLite 等价(测试库 create_all 已由模型直接带上 uq_medlog_med_date_time, 本文件供裸表 / 生产同形)。
-- SQLite 无 DELETE ... USING 语法, 去重逻辑仅 PG 需要(测试 / 新库不含重复行)。
-- COALESCE(taken_time,'') 把「今日按日标记」的 NULL 折叠去重, 多剂不同 taken_time 仍并存。
CREATE UNIQUE INDEX IF NOT EXISTS uq_medlog_med_date_time
    ON medication_logs (medication_id, taken_date, COALESCE(taken_time, ''));
DROP INDEX IF EXISTS ix_medication_logs_med_date;
