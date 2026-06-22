-- P4 锻炼链:health_protocols.chain_key + partial unique index(sqlite 变体)。
-- sqlite 的 ADD COLUMN 无 IF NOT EXISTS;managed runner 按文件名记录已应用、只跑一次。
-- 测试库由 Base.metadata.create_all 直接带列与索引,不走本迁移。sqlite 支持 partial index。
ALTER TABLE health_protocols ADD COLUMN chain_key VARCHAR(120);

CREATE UNIQUE INDEX IF NOT EXISTS uq_health_protocols_user_chain_key
    ON health_protocols (user_id, chain_key)
    WHERE chain_key IS NOT NULL;
