-- 用药管理表

CREATE TABLE IF NOT EXISTS medications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name VARCHAR(200) NOT NULL,
    dosage VARCHAR(100),
    frequency VARCHAR(100),
    times_per_day INTEGER DEFAULT 1,
    reminder_times JSONB,
    category VARCHAR(50),
    purpose VARCHAR(200),
    side_effects TEXT,
    interactions TEXT,
    start_date DATE,
    end_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_medications_user_active ON medications(user_id, is_active);

CREATE TABLE IF NOT EXISTS medication_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    medication_id INTEGER NOT NULL REFERENCES medications(id),
    taken_date DATE NOT NULL,
    taken_time VARCHAR(10),
    status VARCHAR(20) NOT NULL DEFAULT 'taken',
    skip_reason VARCHAR(200),
    actual_dosage VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_medication_logs_user_date ON medication_logs(user_id, taken_date);
CREATE INDEX IF NOT EXISTS ix_medication_logs_med_date ON medication_logs(medication_id, taken_date);

-- 约束
ALTER TABLE medication_logs ADD CONSTRAINT chk_med_log_status CHECK (status IN ('taken', 'skipped', 'delayed'));
