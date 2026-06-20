-- D1 补剂库存(P3)sqlite 变体。测试库由 create_all 直接建表,本迁移仅 prod 跑一次。幂等可重跑。
CREATE TABLE IF NOT EXISTS supplement_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    supplement_id INTEGER NOT NULL,
    units_remaining INTEGER,
    package_units INTEGER,
    brand VARCHAR(100),
    spec VARCHAR(100),
    last_restock_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_supp_inventory_supplement ON supplement_inventory (supplement_id);
CREATE INDEX IF NOT EXISTS ix_supp_inventory_user ON supplement_inventory (user_id);
