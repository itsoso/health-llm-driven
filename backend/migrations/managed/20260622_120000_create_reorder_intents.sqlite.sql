-- P5(D2)复购下单财务一等对象 ReorderIntent(SCAFFOLD)sqlite 变体。
-- 测试库由 create_all 直接建表,本迁移仅 prod 跑一次。幂等可重跑。
CREATE TABLE IF NOT EXISTS reorder_intents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    supplement_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    brand VARCHAR(100),
    spec VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'proposed',
    kuaishou_order_id VARCHAR(120),
    auto_reorder_enabled BOOLEAN NOT NULL DEFAULT 0,
    monthly_cap_cents INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMP,
    placed_at TIMESTAMP,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS ix_reorder_intents_user_status ON reorder_intents (user_id, status);
CREATE INDEX IF NOT EXISTS ix_reorder_intents_supplement ON reorder_intents (supplement_id);
CREATE INDEX IF NOT EXISTS ix_reorder_intents_user_id ON reorder_intents (user_id);
