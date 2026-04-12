CREATE TABLE IF NOT EXISTS dismissed_alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rule_id VARCHAR(100) NOT NULL,
    reason VARCHAR(30) DEFAULT 'known',
    note TEXT,
    dismissed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_dismissed_user_rule ON dismissed_alerts(user_id, rule_id);
