-- 用药自动驾驶 P1a：用药方案/疗程(多阶段)+ 把药品挂回疗程
CREATE TABLE IF NOT EXISTS medication_regimens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name VARCHAR(200) NOT NULL,
    source VARCHAR(40),
    template_id VARCHAR(60),
    status VARCHAR(20) DEFAULT 'active',
    current_phase INTEGER DEFAULT 0,
    phases JSONB,
    review_on_complete TEXT,
    started_on DATE,
    expected_end_on DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS ix_medication_regimens_user_status ON medication_regimens(user_id, status);
ALTER TABLE medications ADD COLUMN IF NOT EXISTS regimen_id INTEGER REFERENCES medication_regimens(id);
