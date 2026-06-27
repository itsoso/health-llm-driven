-- Health Runtime governance controls: data source quality, source preference, and derived-output controls.

CREATE TABLE IF NOT EXISTS data_source_quality (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    source_kind VARCHAR(40) NOT NULL,
    source_id VARCHAR(160) NOT NULL,
    metric VARCHAR(80) NOT NULL,
    quality_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    confidence VARCHAR(30) NOT NULL DEFAULT 'unknown',
    freshness_seconds INTEGER,
    status VARCHAR(30) NOT NULL DEFAULT 'usable',
    reason TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_data_source_quality_user_source_metric
    ON data_source_quality(user_id, source_kind, source_id, metric);
CREATE INDEX IF NOT EXISTS ix_data_source_quality_user_id ON data_source_quality(user_id);
CREATE INDEX IF NOT EXISTS ix_data_source_quality_source_kind ON data_source_quality(source_kind);
CREATE INDEX IF NOT EXISTS ix_data_source_quality_metric ON data_source_quality(metric);
CREATE INDEX IF NOT EXISTS ix_data_source_quality_status ON data_source_quality(status);

CREATE TABLE IF NOT EXISTS user_data_source_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    metric VARCHAR(80) NOT NULL,
    preferred_source_kind VARCHAR(40) NOT NULL,
    preferred_source_id VARCHAR(160) NOT NULL,
    scope VARCHAR(80) NOT NULL DEFAULT 'global',
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_user_source_preferences_user_metric_scope
    ON user_data_source_preferences(user_id, metric, scope);
CREATE INDEX IF NOT EXISTS ix_user_data_source_preferences_user_id ON user_data_source_preferences(user_id);
CREATE INDEX IF NOT EXISTS ix_user_data_source_preferences_metric ON user_data_source_preferences(metric);
CREATE INDEX IF NOT EXISTS ix_user_data_source_preferences_scope ON user_data_source_preferences(scope);

CREATE TABLE IF NOT EXISTS health_runtime_controls (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    control_type VARCHAR(40) NOT NULL,
    target_key VARCHAR(120) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    reason TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_health_runtime_controls_user_target
    ON health_runtime_controls(user_id, control_type, target_key);
CREATE INDEX IF NOT EXISTS ix_health_runtime_controls_user_id ON health_runtime_controls(user_id);
CREATE INDEX IF NOT EXISTS ix_health_runtime_controls_control_type ON health_runtime_controls(control_type);
CREATE INDEX IF NOT EXISTS ix_health_runtime_controls_target_key ON health_runtime_controls(target_key);
CREATE INDEX IF NOT EXISTS ix_health_runtime_controls_status ON health_runtime_controls(status);
