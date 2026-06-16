-- 测试库由 ORM 模型直接建表(create_all),已含 uq_hpe_protocol_date 唯一约束、无重复行。
-- no-op,保持与 postgresql variant 成对。
-- (SQLite 无 DELETE ... USING 语法,生产去重逻辑仅 PG 需要。)
SELECT 1;
