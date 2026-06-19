-- C1 周健身计划(P2)sqlite 变体。测试库由 create_all 直接建表,本迁移仅 prod 跑一次。幂等可重跑。
CREATE TABLE IF NOT EXISTS fitness_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    week_start DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'proposed',
    goal VARCHAR(40),
    acwr REAL,
    readiness_note TEXT,
    days TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fitness_plan_user_week ON fitness_plans (user_id, week_start);
CREATE INDEX IF NOT EXISTS ix_fitness_plans_user_status ON fitness_plans (user_id, status);
