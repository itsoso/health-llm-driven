-- 用药自动驾驶 P1a：用药方案/疗程(多阶段)+ 把药品挂回疗程 (sqlite 变体)
CREATE TABLE IF NOT EXISTS medication_regimens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    source VARCHAR(40),
    template_id VARCHAR(60),
    status VARCHAR(20) DEFAULT 'active',
    current_phase INTEGER DEFAULT 0,
    phases TEXT,
    review_on_complete TEXT,
    started_on DATE,
    expected_end_on DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_medication_regimens_user_status ON medication_regimens(user_id, status);
ALTER TABLE medications ADD COLUMN regimen_id INTEGER;
