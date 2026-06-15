-- 医学问题登记(R13)(sqlite 变体)
CREATE TABLE IF NOT EXISTS health_problems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    risk_level VARCHAR(4) DEFAULT 'P1',
    status VARCHAR(20) DEFAULT 'active',
    diagnosis TEXT,
    risk_stratification VARCHAR(60),
    red_lines TEXT,
    responsible VARCHAR(120),
    follow_up TEXT,
    escalation_path TEXT,
    evidence_tier VARCHAR(4),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_health_problems_user_status ON health_problems(user_id, status);
