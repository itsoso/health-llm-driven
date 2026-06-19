-- C1 周健身计划(P2):系统起草(proposed)→ 用户一键确认(confirmed)→ 排程。幂等可重跑。
-- days 是一周(7 天)结构化 JSON 快照;一周一行(uq user+week_start),确认幂等靠原子 UPDATE 门(应用层)。
CREATE TABLE IF NOT EXISTS fitness_plans (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    week_start DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'proposed',
    goal VARCHAR(40),
    acwr DOUBLE PRECISION,
    readiness_note TEXT,
    days JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    confirmed_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fitness_plan_user_week ON fitness_plans (user_id, week_start);
CREATE INDEX IF NOT EXISTS ix_fitness_plans_user_status ON fitness_plans (user_id, status);
