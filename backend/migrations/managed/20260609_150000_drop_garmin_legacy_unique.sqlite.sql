-- SQLite 无需处理:测试库由 ORM 模型直接建表,只含 idx_garmin_user_date_source
-- 复合唯一索引,不存在 (user_id, record_date) 遗留约束;SQLite 也不支持 DROP CONSTRAINT。
-- no-op,保持与 postgresql variant 成对。
SELECT 1;
