CREATE TABLE IF NOT EXISTS intervention_cycles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    cycle_type VARCHAR(40) NOT NULL DEFAULT 'metabolic_90d',
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    start_date DATE NOT NULL,
    planned_end_date DATE,
    baseline_snapshot_id INTEGER REFERENCES twin_snapshots(id),
    latest_snapshot_id INTEGER REFERENCES twin_snapshots(id),
    target_metrics JSONB,
    stop_conditions JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_intervention_cycles_user_status ON intervention_cycles(user_id, status);

CREATE TABLE IF NOT EXISTS outcome_metrics (
    id SERIAL PRIMARY KEY,
    cycle_id INTEGER NOT NULL REFERENCES intervention_cycles(id) ON DELETE CASCADE,
    metric_code VARCHAR(40) NOT NULL,
    unit VARCHAR(32),
    baseline_value DOUBLE PRECISION,
    target_value DOUBLE PRECISION,
    latest_value DOUBLE PRECISION,
    delta DOUBLE PRECISION,
    delta_pct DOUBLE PRECISION,
    direction VARCHAR(8) DEFAULT 'down',
    status VARCHAR(12) DEFAULT 'pending',
    baseline_observed_at TIMESTAMP WITH TIME ZONE,
    latest_observed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_outcome_metrics_cycle ON outcome_metrics(cycle_id);
