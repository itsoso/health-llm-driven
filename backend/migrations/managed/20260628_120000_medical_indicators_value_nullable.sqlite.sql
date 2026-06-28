-- SQLite no-op:测试/CI 的 sqlite 库由 Base.metadata.create_all 从模型建,
-- 模型 family_health.py 的 value 早已 nullable=True → sqlite 库本就允许 NULL。
-- 且 SQLite 不支持 ALTER COLUMN ... DROP NOT NULL(需重建表)。故此处无操作,
-- 仅占位让 runner 两 dialect 配对(checksum 去重)。
SELECT 1;
