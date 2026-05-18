CREATE TABLE IF NOT EXISTS intervention_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    plan_id INTEGER REFERENCES daily_operating_plans(id),
    plan_date DATE NOT NULL,
    action_key VARCHAR(160) NOT NULL,
    action_domain VARCHAR(40),
    action_title VARCHAR(220) NOT NULL,
    feedback_status VARCHAR(20) NOT NULL,
    reason TEXT,
    source VARCHAR(40) NOT NULL DEFAULT 'daily_plan',
    action_snapshot JSON NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_intervention_events_user_date
    ON intervention_events(user_id, plan_date);

CREATE INDEX IF NOT EXISTS idx_intervention_events_user_action
    ON intervention_events(user_id, action_key);

CREATE INDEX IF NOT EXISTS idx_intervention_events_status
    ON intervention_events(feedback_status);

CREATE INDEX IF NOT EXISTS idx_intervention_events_plan_id
    ON intervention_events(plan_id);
