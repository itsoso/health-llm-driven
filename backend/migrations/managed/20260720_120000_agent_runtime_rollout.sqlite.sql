CREATE TABLE IF NOT EXISTS agent_runtime_rollout_state (
    id INTEGER PRIMARY KEY,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    reason_code VARCHAR(64),
    version INTEGER NOT NULL DEFAULT 1,
    window_started_at TIMESTAMP,
    last_evaluated_at TIMESTAMP,
    reconciliation_generation INTEGER NOT NULL DEFAULT 0,
    reconciliation_acknowledged_generation INTEGER NOT NULL DEFAULT 0,
    terminal_runs INTEGER NOT NULL DEFAULT 0,
    failed_runs INTEGER NOT NULL DEFAULT 0,
    reconciliation_runs INTEGER NOT NULL DEFAULT 0,
    stale_active_runs INTEGER NOT NULL DEFAULT 0,
    updated_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_agent_runtime_rollout_state_singleton CHECK (id = 1),
    CONSTRAINT ck_agent_runtime_rollout_state_status CHECK (status IN ('active', 'paused')),
    CONSTRAINT ck_agent_runtime_rollout_state_reason CHECK (
        (status = 'active' AND reason_code IS NULL) OR
        (status = 'paused' AND reason_code IS NOT NULL AND reason_code IN (
            'manual_pause', 'system_failure_rate',
            'reconciliation_detected', 'stale_lease_detected'
        ))
    ),
    CONSTRAINT ck_agent_runtime_rollout_state_counts CHECK (
        version >= 1 AND terminal_runs >= 0 AND failed_runs >= 0 AND
        reconciliation_runs >= 0 AND stale_active_runs >= 0 AND
        reconciliation_generation >= 0 AND
        reconciliation_acknowledged_generation >= 0 AND
        reconciliation_acknowledged_generation <= reconciliation_generation
    )
);

INSERT OR IGNORE INTO agent_runtime_rollout_state (
    id, status, version, reconciliation_generation,
    reconciliation_acknowledged_generation
)
VALUES (
    1, 'active', 1,
    (SELECT COUNT(*) FROM agent_runs WHERE status = 'reconciliation_required'),
    0
);

CREATE TABLE IF NOT EXISTS agent_runtime_rollout_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action VARCHAR(16) NOT NULL,
    actor_kind VARCHAR(16) NOT NULL,
    reason_code VARCHAR(64) NOT NULL,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    terminal_runs INTEGER NOT NULL DEFAULT 0,
    failed_runs INTEGER NOT NULL DEFAULT 0,
    reconciliation_runs INTEGER NOT NULL DEFAULT 0,
    stale_active_runs INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_agent_runtime_rollout_events_action CHECK (action IN ('pause', 'resume')),
    CONSTRAINT ck_agent_runtime_rollout_events_actor CHECK (actor_kind IN ('system', 'admin')),
    CONSTRAINT ck_agent_runtime_rollout_events_reason CHECK (
        reason_code IN (
            'manual_pause', 'manual_resume', 'system_failure_rate',
            'reconciliation_detected', 'stale_lease_detected'
        )
    ),
    CONSTRAINT ck_agent_runtime_rollout_events_transition CHECK (
        (action = 'resume' AND actor_kind = 'admin' AND reason_code = 'manual_resume') OR
        (action = 'pause' AND (
            (actor_kind = 'admin' AND reason_code = 'manual_pause') OR
            (actor_kind = 'system' AND reason_code IN (
                'system_failure_rate', 'reconciliation_detected',
                'stale_lease_detected'
            ))
        ))
    ),
    CONSTRAINT ck_agent_runtime_rollout_events_counts CHECK (
        terminal_runs >= 0 AND failed_runs >= 0 AND
        reconciliation_runs >= 0 AND stale_active_runs >= 0
    )
);

CREATE INDEX IF NOT EXISTS ix_agent_runtime_rollout_events_created
    ON agent_runtime_rollout_events(created_at);

CREATE INDEX IF NOT EXISTS ix_agent_runs_finished_status
    ON agent_runs(finished_at, status);

CREATE INDEX IF NOT EXISTS ix_agent_tool_operations_created_status
    ON agent_tool_operations(created_at, status);
