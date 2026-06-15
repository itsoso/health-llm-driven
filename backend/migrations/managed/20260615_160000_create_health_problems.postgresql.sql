-- 医学问题登记(R13):慢病/结节/异常 + 风险分层 + 红线 + 随访 + 升级
CREATE TABLE IF NOT EXISTS health_problems (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name VARCHAR(200) NOT NULL,
    risk_level VARCHAR(4) DEFAULT 'P1',
    status VARCHAR(20) DEFAULT 'active',
    diagnosis JSONB,
    risk_stratification VARCHAR(60),
    red_lines JSONB,
    responsible VARCHAR(120),
    follow_up JSONB,
    escalation_path TEXT,
    evidence_tier VARCHAR(4),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS ix_health_problems_user_status ON health_problems(user_id, status);
