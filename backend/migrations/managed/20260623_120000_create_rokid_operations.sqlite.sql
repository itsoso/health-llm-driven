-- Thin Rokid operation ledger for cross-device diagnostics.
-- Domain records stay in meal_monitoring_sessions, visual_inputs, rokid_pushup_sessions, write_intents, and client_events.
CREATE TABLE IF NOT EXISTS rokid_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id VARCHAR(80) NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    type VARCHAR(60) NOT NULL,
    state VARCHAR(30) NOT NULL DEFAULT 'queued',
    primary_surface VARCHAR(80) NOT NULL DEFAULT 'rokid_glasses',
    summary TEXT,
    last_error_code VARCHAR(120),
    meta JSON,
    entity_refs JSON,
    write_intent_id INTEGER REFERENCES write_intents(id),
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_rokid_operations_operation_id ON rokid_operations (operation_id);
CREATE INDEX IF NOT EXISTS ix_rokid_operations_user_id ON rokid_operations (user_id);
CREATE INDEX IF NOT EXISTS ix_rokid_operations_type ON rokid_operations (type);
CREATE INDEX IF NOT EXISTS ix_rokid_operations_state ON rokid_operations (state);
CREATE INDEX IF NOT EXISTS ix_rokid_operations_write_intent_id ON rokid_operations (write_intent_id);
CREATE INDEX IF NOT EXISTS ix_rokid_operations_started_at ON rokid_operations (started_at);
CREATE INDEX IF NOT EXISTS idx_rokid_operations_user_started ON rokid_operations (user_id, started_at);
CREATE INDEX IF NOT EXISTS idx_rokid_operations_user_state ON rokid_operations (user_id, state);
