-- Meal monitoring sessions (Rokid/phone periodic-sampling meal capture).
-- Frames reuse visual_input_events (linked by meta.meal_session_id); this table
-- only tracks session lifecycle, consent, frame count, raw-media TTL, and the
-- observational draft/summary. Comments must not contain bare semicolons because
-- the runner splits on semicolons.
CREATE TABLE IF NOT EXISTS meal_monitoring_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    source VARCHAR(50) NOT NULL DEFAULT 'rokid_glasses',
    device_type VARCHAR(40) NOT NULL DEFAULT 'glasses',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    consent_at TIMESTAMPTZ,
    frame_count INTEGER NOT NULL DEFAULT 0,
    privacy_class VARCHAR(30) NOT NULL DEFAULT 'health_l3',
    raw_media_delete_at TIMESTAMPTZ,
    raw_media_deleted_at TIMESTAMPTZ,
    summary JSONB,
    write_intent_id INTEGER REFERENCES write_intents(id),
    target_type VARCHAR(50),
    target_id INTEGER,
    meta JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_meal_monitoring_sessions_user_id ON meal_monitoring_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_meal_monitoring_sessions_status ON meal_monitoring_sessions (status);
CREATE INDEX IF NOT EXISTS ix_meal_monitoring_sessions_started_at ON meal_monitoring_sessions (started_at);
CREATE INDEX IF NOT EXISTS ix_meal_monitoring_sessions_raw_media_delete_at ON meal_monitoring_sessions (raw_media_delete_at);
CREATE INDEX IF NOT EXISTS ix_meal_monitoring_sessions_write_intent_id ON meal_monitoring_sessions (write_intent_id);
CREATE INDEX IF NOT EXISTS idx_meal_sessions_user_status ON meal_monitoring_sessions (user_id, status);
CREATE INDEX IF NOT EXISTS idx_meal_sessions_user_started ON meal_monitoring_sessions (user_id, started_at);
