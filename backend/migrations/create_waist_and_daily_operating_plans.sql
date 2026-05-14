-- Phase 0: Waist records + Daily Operating Plan

CREATE TABLE IF NOT EXISTS waist_records (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    record_date DATE NOT NULL,
    waist_cm DOUBLE PRECISION NOT NULL,
    source VARCHAR(50) DEFAULT 'manual',
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_waist_records_user_date
    ON waist_records(user_id, record_date);

CREATE TABLE IF NOT EXISTS daily_operating_plans (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    plan_date DATE NOT NULL,
    primary_goal VARCHAR(80) DEFAULT 'metabolic_health',
    status VARCHAR(20) DEFAULT 'active',
    state_summary JSONB DEFAULT '{}'::jsonb,
    actions JSONB DEFAULT '[]'::jsonb,
    nutrition_targets JSONB DEFAULT '{}'::jsonb,
    movement_targets JSONB DEFAULT '{}'::jsonb,
    sleep_targets JSONB DEFAULT '{}'::jsonb,
    measurements JSONB DEFAULT '{}'::jsonb,
    doctor_escalation JSONB DEFAULT '{}'::jsonb,
    verification JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_daily_operating_plans_user_date UNIQUE(user_id, plan_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_operating_plans_user_date
    ON daily_operating_plans(user_id, plan_date);
