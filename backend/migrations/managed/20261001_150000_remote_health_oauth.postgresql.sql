-- Additive OAuth storage. No users, credentials or grants are created.
-- Rollback: disable REMOTE_HEALTH_ENABLED. Retain tables to preserve revocation history.

CREATE TABLE IF NOT EXISTS remote_health_grants (
	id VARCHAR(36) NOT NULL,
	user_id INTEGER NOT NULL,
	client_id VARCHAR(200) NOT NULL,
	scope VARCHAR(32) NOT NULL,
	resource VARCHAR(500) NOT NULL,
	created_at BIGINT NOT NULL,
	expires_at BIGINT NOT NULL,
	revoked_at BIGINT,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_remote_health_grants_user_id ON remote_health_grants (user_id);

CREATE TABLE IF NOT EXISTS remote_health_credentials (
	digest VARCHAR(64) NOT NULL,
	kind VARCHAR(16) NOT NULL,
	grant_id VARCHAR(36),
	expires_at BIGINT NOT NULL,
	used_at BIGINT,
	payload JSONB NOT NULL,
	PRIMARY KEY (digest),
	FOREIGN KEY(grant_id) REFERENCES remote_health_grants (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_remote_health_credentials_expires_at ON remote_health_credentials (expires_at);

CREATE INDEX IF NOT EXISTS ix_remote_health_credentials_grant_id ON remote_health_credentials (grant_id);

CREATE TABLE IF NOT EXISTS remote_health_rate_buckets (
	key VARCHAR(80) NOT NULL,
	"window" BIGINT NOT NULL,
	count INTEGER NOT NULL,
	PRIMARY KEY (key, "window")
);

CREATE INDEX IF NOT EXISTS ix_remote_health_rate_window ON remote_health_rate_buckets ("window");
