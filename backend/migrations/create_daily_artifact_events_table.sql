-- Daily Artifact events: impressions, accepts, completions, and skip reasons.
CREATE TABLE IF NOT EXISTS daily_artifact_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    artifact_date DATE NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    top_action_id VARCHAR(200),
    skip_reason VARCHAR(80),
    delivered_context JSONB,
    week_index INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_artifact_events_user_id
    ON daily_artifact_events(user_id);

CREATE INDEX IF NOT EXISTS idx_daily_artifact_events_artifact_date
    ON daily_artifact_events(artifact_date);

CREATE INDEX IF NOT EXISTS idx_daily_artifact_events_event_type
    ON daily_artifact_events(event_type);

CREATE INDEX IF NOT EXISTS idx_daily_artifact_events_top_action_id
    ON daily_artifact_events(top_action_id);

CREATE INDEX IF NOT EXISTS idx_daily_artifact_events_user_date
    ON daily_artifact_events(user_id, artifact_date);

CREATE INDEX IF NOT EXISTS idx_daily_artifact_events_user_event_created
    ON daily_artifact_events(user_id, event_type, created_at);
