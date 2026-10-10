CREATE TABLE agent_runtime_rollout_events_operator_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action VARCHAR(16) NOT NULL,
    actor_kind VARCHAR(16) NOT NULL,
    operator_review JSON,
    reason_code VARCHAR(64) NOT NULL,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    terminal_runs INTEGER NOT NULL DEFAULT 0,
    failed_runs INTEGER NOT NULL DEFAULT 0,
    reconciliation_runs INTEGER NOT NULL DEFAULT 0,
    stale_active_runs INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_agent_runtime_rollout_events_action CHECK (action IN ('pause', 'resume')),
    CONSTRAINT ck_agent_runtime_rollout_events_actor CHECK (actor_kind IN ('system', 'admin', 'operator')),
    CONSTRAINT ck_agent_runtime_rollout_events_reason CHECK (
        reason_code IN (
            'manual_pause', 'manual_resume', 'system_failure_rate',
            'reconciliation_detected', 'stale_lease_detected'
        )
    ),
    CONSTRAINT ck_agent_runtime_rollout_events_transition CHECK (
        (action = 'resume' AND actor_kind IN ('admin', 'operator') AND reason_code = 'manual_resume') OR
        (action = 'pause' AND (
            (actor_kind = 'admin' AND reason_code = 'manual_pause') OR
            (actor_kind = 'system' AND reason_code IN (
                'system_failure_rate', 'reconciliation_detected',
                'stale_lease_detected'
            ))
        ))
    ),
    CONSTRAINT ck_agent_runtime_rollout_events_operator_review CHECK (
        (actor_kind = 'operator' AND actor_user_id IS NULL AND operator_review IS NOT NULL AND json_valid(operator_review) AND json_type(operator_review) = 'object') OR
        (actor_kind <> 'operator' AND operator_review IS NULL)
    ),
    CONSTRAINT ck_agent_runtime_rollout_events_counts CHECK (
        terminal_runs >= 0 AND failed_runs >= 0 AND
        reconciliation_runs >= 0 AND stale_active_runs >= 0
    )
);

INSERT INTO agent_runtime_rollout_events_operator_new
(id, action, actor_kind, reason_code, actor_user_id, terminal_runs, failed_runs, reconciliation_runs, stale_active_runs, created_at)
SELECT id, action, actor_kind, reason_code, actor_user_id, terminal_runs, failed_runs, reconciliation_runs, stale_active_runs, created_at
FROM agent_runtime_rollout_events;
DROP TABLE agent_runtime_rollout_events;
ALTER TABLE agent_runtime_rollout_events_operator_new RENAME TO agent_runtime_rollout_events;
CREATE INDEX IF NOT EXISTS ix_agent_runtime_rollout_events_created
    ON agent_runtime_rollout_events(created_at);
