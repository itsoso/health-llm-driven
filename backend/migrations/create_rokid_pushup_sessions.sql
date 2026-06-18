CREATE TABLE IF NOT EXISTS rokid_pushup_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    status VARCHAR(24) NOT NULL DEFAULT 'active',
    target_reps INTEGER NOT NULL DEFAULT 20,
    source_device VARCHAR(80) NOT NULL DEFAULT 'rokid_glasses',
    ingest_token_hash VARCHAR(64) NOT NULL,
    meta JSONB,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    last_event_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_rokid_pushup_sessions_id
    ON rokid_pushup_sessions(id);
CREATE INDEX IF NOT EXISTS ix_rokid_pushup_sessions_user_id
    ON rokid_pushup_sessions(user_id);
CREATE INDEX IF NOT EXISTS ix_rokid_pushup_sessions_status
    ON rokid_pushup_sessions(status);
CREATE INDEX IF NOT EXISTS ix_rokid_pushup_sessions_ingest_token_hash
    ON rokid_pushup_sessions(ingest_token_hash);
CREATE INDEX IF NOT EXISTS ix_rokid_pushup_sessions_last_event_at
    ON rokid_pushup_sessions(last_event_at);
CREATE INDEX IF NOT EXISTS idx_rokid_pushup_sessions_user_status
    ON rokid_pushup_sessions(user_id, status);

CREATE TABLE IF NOT EXISTS rokid_pushup_events (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES rokid_pushup_sessions(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    event_type VARCHAR(30) NOT NULL,
    reps INTEGER,
    phase VARCHAR(24),
    elbow_angle_deg DOUBLE PRECISION,
    shoulder_hip_ankle_angle_deg DOUBLE PRECISION,
    visibility DOUBLE PRECISION,
    quality_score DOUBLE PRECISION,
    payload JSONB,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_rokid_pushup_events_id
    ON rokid_pushup_events(id);
CREATE INDEX IF NOT EXISTS ix_rokid_pushup_events_session_id
    ON rokid_pushup_events(session_id);
CREATE INDEX IF NOT EXISTS ix_rokid_pushup_events_user_id
    ON rokid_pushup_events(user_id);
CREATE INDEX IF NOT EXISTS ix_rokid_pushup_events_event_type
    ON rokid_pushup_events(event_type);
CREATE INDEX IF NOT EXISTS ix_rokid_pushup_events_occurred_at
    ON rokid_pushup_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_rokid_pushup_events_session_id
    ON rokid_pushup_events(session_id, id);
CREATE INDEX IF NOT EXISTS idx_rokid_pushup_events_user_occurred
    ON rokid_pushup_events(user_id, occurred_at);
