CREATE TABLE IF NOT EXISTS agent_capacity_leases (
    lease_id VARCHAR(64) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    origin VARCHAR(32) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    released_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_agent_capacity_leases_user_id
    ON agent_capacity_leases (user_id);
CREATE INDEX IF NOT EXISTS ix_agent_capacity_leases_expires_at
    ON agent_capacity_leases (expires_at);
CREATE INDEX IF NOT EXISTS ix_agent_capacity_active_user_expiry
    ON agent_capacity_leases (user_id, released_at, expires_at);
