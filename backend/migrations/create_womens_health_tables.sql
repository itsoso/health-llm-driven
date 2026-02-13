-- 创建女性健康相关表
-- menstrual_cycles: 经期周期记录
-- cycle_symptoms: 周期症状记录

CREATE TABLE IF NOT EXISTS menstrual_cycles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    start_date DATE NOT NULL,
    end_date DATE,
    cycle_length INTEGER,
    period_length INTEGER,
    flow_intensity VARCHAR(20),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_menstrual_cycles_user_start ON menstrual_cycles(user_id, start_date);

CREATE TABLE IF NOT EXISTS cycle_symptoms (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    cycle_id INTEGER REFERENCES menstrual_cycles(id),
    record_date DATE NOT NULL,
    symptom_type VARCHAR(50) NOT NULL,
    severity INTEGER DEFAULT 1,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_cycle_symptoms_user_date ON cycle_symptoms(user_id, record_date);
CREATE INDEX IF NOT EXISTS ix_cycle_symptoms_cycle ON cycle_symptoms(cycle_id);

-- 添加 CHECK 约束
ALTER TABLE menstrual_cycles ADD CONSTRAINT chk_flow_intensity
    CHECK (flow_intensity IS NULL OR flow_intensity IN ('light', 'moderate', 'heavy'));
ALTER TABLE cycle_symptoms ADD CONSTRAINT chk_severity
    CHECK (severity >= 1 AND severity <= 5);
