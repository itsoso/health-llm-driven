CREATE TABLE IF NOT EXISTS app_release_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform VARCHAR(32) NOT NULL,
    channel VARCHAR(64) NOT NULL,
    config_version INTEGER NOT NULL,
    ota_enabled BOOLEAN NOT NULL DEFAULT 1,
    rollout_percent INTEGER NOT NULL DEFAULT 100,
    minimum_native_build VARCHAR(32),
    recommended_native_build VARCHAR(32),
    forced_update BOOLEAN NOT NULL DEFAULT 0,
    kill_switches TEXT NOT NULL DEFAULT '{}',
    rollback_update_id VARCHAR(128),
    expires_at DATETIME,
    created_by_user_id INTEGER REFERENCES users(id),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_app_release_policies_scope_version
    ON app_release_policies(platform, channel, config_version);
