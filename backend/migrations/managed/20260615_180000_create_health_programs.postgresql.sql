-- 健康项目(第 4 个一等对象):8–12 周目标容器,串 Problem→Protocol→outcome
CREATE TABLE IF NOT EXISTS health_programs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name VARCHAR(200) NOT NULL,
    program_type VARCHAR(30) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    problem_id INTEGER,
    primary_metrics JSONB,
    secondary_metrics JSONB,
    baseline JSONB,
    target JSONB,
    latest JSONB,
    started_on DATE,
    target_end_on DATE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS ix_health_programs_user_status ON health_programs(user_id, status);
