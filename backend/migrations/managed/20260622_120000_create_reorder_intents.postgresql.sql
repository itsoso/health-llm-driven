-- P5(D2)复购下单财务一等对象 ReorderIntent(SCAFFOLD,不真下单)。
-- 见 docs/specs/active/2026-06-22-p5-reorder-ordering.md(一等对象准入 Gate)。
-- 状态机:proposed→user_confirmed→order_placed|order_failed|cancelled。
-- 财务硬边界:kuaishou_order_id 仅成功下单时非空;本期 skill 未就绪,恒为 NULL(confirm→501)。
-- 无价格/支付凭据列 —— 后端永不处理支付。幂等可重跑。
CREATE TABLE IF NOT EXISTS reorder_intents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    supplement_id INTEGER NOT NULL REFERENCES supplement_definitions(id),
    quantity INTEGER NOT NULL,
    brand VARCHAR(100),
    spec VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'proposed',
    kuaishou_order_id VARCHAR(120),
    auto_reorder_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    monthly_cap_cents INTEGER,
    created_at TIMESTAMPTZ DEFAULT now(),
    confirmed_at TIMESTAMPTZ,
    placed_at TIMESTAMPTZ,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS ix_reorder_intents_user_status ON reorder_intents (user_id, status);
CREATE INDEX IF NOT EXISTS ix_reorder_intents_supplement ON reorder_intents (supplement_id);
CREATE INDEX IF NOT EXISTS ix_reorder_intents_user_id ON reorder_intents (user_id);
