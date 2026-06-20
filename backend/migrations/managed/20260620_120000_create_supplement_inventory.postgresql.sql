-- D1 补剂库存(P3:复购检测 + 提醒,不下单)。一行 = 一个用户的一种补剂的剩余量。
-- 只承载物流事实(还剩多少 / 一包多少 / 上次补货何时),无价格/支付/订单 —— 财务面是 P5(D2)。
-- 一种补剂一行(uq supplement_id),restock 累加 / manual set 覆盖,幂等。幂等可重跑。
CREATE TABLE IF NOT EXISTS supplement_inventory (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    supplement_id INTEGER NOT NULL REFERENCES supplement_definitions(id),
    units_remaining INTEGER,
    package_units INTEGER,
    brand VARCHAR(100),
    spec VARCHAR(100),
    last_restock_date DATE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_supp_inventory_supplement ON supplement_inventory (supplement_id);
CREATE INDEX IF NOT EXISTS ix_supp_inventory_user ON supplement_inventory (user_id);
