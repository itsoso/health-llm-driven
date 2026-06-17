-- Ambient wearable P0 tables for audio input events and hearing health tasks.
-- Comments must not contain bare semicolons because the runner splits on semicolons.
CREATE TABLE IF NOT EXISTS audio_input_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    captured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    device_type VARCHAR(40) NOT NULL DEFAULT 'unknown',
    source VARCHAR(50) NOT NULL DEFAULT 'ambient_audio',
    intent VARCHAR(40) NOT NULL,
    transcript TEXT NOT NULL,
    confidence FLOAT,
    status VARCHAR(30) NOT NULL DEFAULT 'pending_confirmation',
    privacy_class VARCHAR(30) NOT NULL DEFAULT 'health_l3',
    write_intent_id INTEGER REFERENCES write_intents(id),
    target_type VARCHAR(50),
    target_id INTEGER,
    safety_result JSON,
    meta JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_audio_input_events_user_id ON audio_input_events (user_id);
CREATE INDEX IF NOT EXISTS ix_audio_input_events_captured_at ON audio_input_events (captured_at);
CREATE INDEX IF NOT EXISTS ix_audio_input_events_intent ON audio_input_events (intent);
CREATE INDEX IF NOT EXISTS ix_audio_input_events_status ON audio_input_events (status);
CREATE INDEX IF NOT EXISTS ix_audio_input_events_write_intent_id ON audio_input_events (write_intent_id);
CREATE INDEX IF NOT EXISTS idx_audio_input_user_captured ON audio_input_events (user_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_audio_input_user_intent ON audio_input_events (user_id, intent);

CREATE TABLE IF NOT EXISTS hearing_health_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    task_type VARCHAR(40) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    source VARCHAR(50) NOT NULL DEFAULT 'ambient_hearing',
    reason TEXT,
    due_at TIMESTAMP,
    priority VARCHAR(20) NOT NULL DEFAULT 'normal',
    write_intent_id INTEGER REFERENCES write_intents(id),
    payload JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    completed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_hearing_health_tasks_user_id ON hearing_health_tasks (user_id);
CREATE INDEX IF NOT EXISTS ix_hearing_health_tasks_task_type ON hearing_health_tasks (task_type);
CREATE INDEX IF NOT EXISTS ix_hearing_health_tasks_status ON hearing_health_tasks (status);
CREATE INDEX IF NOT EXISTS ix_hearing_health_tasks_write_intent_id ON hearing_health_tasks (write_intent_id);
CREATE INDEX IF NOT EXISTS idx_hearing_tasks_user_status ON hearing_health_tasks (user_id, status);
CREATE INDEX IF NOT EXISTS idx_hearing_tasks_user_type_status ON hearing_health_tasks (user_id, task_type, status);
