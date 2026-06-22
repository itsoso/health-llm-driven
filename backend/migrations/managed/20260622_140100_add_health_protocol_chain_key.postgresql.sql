-- P4 锻炼链:health_protocols.chain_key + partial unique index(并发物化 DB 级幂等 backstop)。
-- chain_key = "{chain_id}:{chain_step}";非链协议恒 NULL → 不受唯一约束(partial WHERE NOT NULL)。
-- additive、幂等可重跑。
ALTER TABLE health_protocols ADD COLUMN IF NOT EXISTS chain_key VARCHAR(120);

CREATE UNIQUE INDEX IF NOT EXISTS uq_health_protocols_user_chain_key
    ON health_protocols (user_id, chain_key)
    WHERE chain_key IS NOT NULL;
