-- Disable LifeNav routes and revoke grants before application rollback.
-- Retain these tables for credential revocation and access audit history.
CREATE TABLE IF NOT EXISTS lifenav_grants (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    recipient_id VARCHAR(100) NOT NULL,
    audience VARCHAR(20) NOT NULL,
    scope VARCHAR(40) NOT NULL,
    window_policy VARCHAR(40) NOT NULL,
    policy_version VARCHAR(40) NOT NULL,
    redirect_uri VARCHAR(500) NOT NULL,
    recipient_secret_hash VARCHAR(64) NOT NULL,
    state_hash VARCHAR(64) NOT NULL,
    code_challenge VARCHAR(43) NOT NULL,
    code_hash VARCHAR(64) NOT NULL UNIQUE,
    code_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    code_used_at TIMESTAMP WITH TIME ZONE,
    token_hash VARCHAR(64) UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS ix_lifenav_grants_user_id ON lifenav_grants(user_id);
CREATE TABLE IF NOT EXISTS lifenav_access_audits (
    id SERIAL PRIMARY KEY,
    grant_id VARCHAR(36) REFERENCES lifenav_grants(id),
    request_id VARCHAR(36) NOT NULL,
    field_category VARCHAR(40) NOT NULL,
    outcome VARCHAR(20) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_lifenav_access_audits_grant_id ON lifenav_access_audits(grant_id);
