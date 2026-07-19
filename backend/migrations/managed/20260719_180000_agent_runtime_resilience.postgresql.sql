ALTER TABLE agent_runs
    ADD COLUMN IF NOT EXISTS cancel_requested_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX IF NOT EXISTS ix_agent_run_attempts_running_lease
    ON agent_run_attempts(lease_expires_at)
    WHERE status = 'running';
