CREATE TABLE IF NOT EXISTS agent_runs (
    run_id VARCHAR(64) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id INTEGER REFERENCES agent_conversations(id) ON DELETE SET NULL,
    source_message_id INTEGER REFERENCES agent_messages(id) ON DELETE SET NULL,
    assistant_message_id INTEGER REFERENCES agent_messages(id) ON DELETE SET NULL,
    client_turn_id VARCHAR(112),
    input_seq INTEGER,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    origin VARCHAR(32) NOT NULL DEFAULT 'unknown',
    origin_device_id VARCHAR(128),
    local_execution_id VARCHAR(128),
    privacy_mode VARCHAR(32) NOT NULL DEFAULT 'cloud',
    deadline_at TIMESTAMP,
    error_code VARCHAR(80),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_agent_runs_status CHECK (
        status IN ('queued', 'running', 'waiting_for_user', 'succeeded', 'failed',
                   'cancelled', 'reconciliation_required')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_runs_user_client_turn
    ON agent_runs(user_id, client_turn_id) WHERE client_turn_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_runs_active_conversation
    ON agent_runs(conversation_id)
    WHERE conversation_id IS NOT NULL AND status IN ('queued', 'running');
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_runs_conversation_input_seq
    ON agent_runs(conversation_id, input_seq)
    WHERE conversation_id IS NOT NULL AND input_seq IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_agent_runs_user_id ON agent_runs(user_id);
CREATE INDEX IF NOT EXISTS ix_agent_runs_conversation_id ON agent_runs(conversation_id);
CREATE INDEX IF NOT EXISTS ix_agent_runs_status ON agent_runs(status);
CREATE INDEX IF NOT EXISTS ix_agent_runs_user_created ON agent_runs(user_id, created_at);

CREATE TABLE IF NOT EXISTS agent_run_attempts (
    attempt_id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    worker_id VARCHAR(128),
    lease_expires_at TIMESTAMP,
    heartbeat_at TIMESTAMP,
    error_code VARCHAR(80),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    CONSTRAINT ck_agent_run_attempts_status CHECK (
        status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')
    ),
    CONSTRAINT uq_agent_run_attempt_number UNIQUE (run_id, attempt_no)
);
CREATE INDEX IF NOT EXISTS ix_agent_run_attempts_run_id ON agent_run_attempts(run_id);
CREATE INDEX IF NOT EXISTS ix_agent_run_attempts_status ON agent_run_attempts(status);

CREATE TABLE IF NOT EXISTS agent_tool_operations (
    operation_id VARCHAR(96) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    attempt_id VARCHAR(64) REFERENCES agent_run_attempts(attempt_id) ON DELETE SET NULL,
    tool_name VARCHAR(80) NOT NULL,
    effect_class VARCHAR(32) NOT NULL,
    operation_fingerprint VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'requested',
    resource_type VARCHAR(80),
    resource_id VARCHAR(128),
    error_code VARCHAR(80),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMP,
    finished_at TIMESTAMP,
    CONSTRAINT ck_agent_tool_operations_status CHECK (
        status IN ('requested', 'executing', 'succeeded', 'failed', 'reconciliation_required')
    ),
    CONSTRAINT uq_agent_tool_operations_run_fingerprint UNIQUE (run_id, operation_fingerprint)
);
CREATE INDEX IF NOT EXISTS ix_agent_tool_operations_run_id ON agent_tool_operations(run_id);
CREATE INDEX IF NOT EXISTS ix_agent_tool_operations_status ON agent_tool_operations(status);

CREATE TABLE IF NOT EXISTS agent_run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id VARCHAR(64) NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    attempt_id VARCHAR(64) REFERENCES agent_run_attempts(attempt_id) ON DELETE SET NULL,
    sequence_no INTEGER NOT NULL,
    event_name VARCHAR(64) NOT NULL,
    payload TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_agent_run_events_sequence UNIQUE (run_id, sequence_no)
);
CREATE INDEX IF NOT EXISTS ix_agent_run_events_run_id ON agent_run_events(run_id);
CREATE INDEX IF NOT EXISTS ix_agent_run_events_event_name ON agent_run_events(event_name);
CREATE INDEX IF NOT EXISTS ix_agent_run_events_run_created ON agent_run_events(run_id, created_at);
