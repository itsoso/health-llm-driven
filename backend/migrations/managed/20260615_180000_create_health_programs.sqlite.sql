-- 健康项目(第 4 个一等对象)(sqlite 变体)
CREATE TABLE IF NOT EXISTS health_programs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    program_type VARCHAR(30) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    problem_id INTEGER,
    primary_metrics TEXT,
    secondary_metrics TEXT,
    baseline TEXT,
    target TEXT,
    latest TEXT,
    started_on DATE,
    target_end_on DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_health_programs_user_status ON health_programs(user_id, status);
