CREATE TABLE IF NOT EXISTS app_release_policies (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(32) NOT NULL,
    channel VARCHAR(64) NOT NULL,
    config_version INTEGER NOT NULL,
    ota_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    rollout_percent INTEGER NOT NULL DEFAULT 100,
    minimum_native_build VARCHAR(32),
    recommended_native_build VARCHAR(32),
    forced_update BOOLEAN NOT NULL DEFAULT FALSE,
    kill_switches JSONB NOT NULL DEFAULT '{}'::jsonb,
    rollback_update_id VARCHAR(128),
    expires_at TIMESTAMP WITH TIME ZONE,
    created_by_user_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_app_release_policies_scope_version
    ON app_release_policies(platform, channel, config_version);
