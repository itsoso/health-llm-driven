CREATE TABLE IF NOT EXISTS intervention_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    cycle_type VARCHAR(40) NOT NULL DEFAULT 'metabolic_90d',
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    start_date DATE NOT NULL,
    planned_end_date DATE,
    baseline_snapshot_id INTEGER REFERENCES twin_snapshots(id),
    latest_snapshot_id INTEGER REFERENCES twin_snapshots(id),
    target_metrics JSON,
    stop_conditions JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_intervention_cycles_user_status ON intervention_cycles(user_id, status);

CREATE TABLE IF NOT EXISTS outcome_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER NOT NULL REFERENCES intervention_cycles(id) ON DELETE CASCADE,
    metric_code VARCHAR(40) NOT NULL,
    unit VARCHAR(32),
    baseline_value FLOAT,
    target_value FLOAT,
    latest_value FLOAT,
    delta FLOAT,
    delta_pct FLOAT,
    direction VARCHAR(8) DEFAULT 'down',
    status VARCHAR(12) DEFAULT 'pending',
    baseline_observed_at TIMESTAMP,
    latest_observed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_outcome_metrics_cycle ON outcome_metrics(cycle_id);
