-- SQLite 等价 (测试库 create_all 已由模型直接带上 uq_spo2_user_date_time_source, 本文件供裸表 / 生产同形)。
-- SQLite 无 DELETE ... USING 语法, 用相关子查询去重 (测试 / 新库不含重复行, dedup 仅为生产同形保险)。
-- 同槽保留 max(id), 其余删除, 然后建唯一索引。
DELETE FROM spo2_samples
    WHERE id NOT IN (
        SELECT MAX(id) FROM spo2_samples
        GROUP BY user_id, record_date, sample_time, source
    );
CREATE UNIQUE INDEX IF NOT EXISTS uq_spo2_user_date_time_source
    ON spo2_samples (user_id, record_date, sample_time, source);
