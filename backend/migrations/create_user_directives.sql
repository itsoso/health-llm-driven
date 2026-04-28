-- User Directives — 医生指令 / 用户硬约束, specialist 必须遵循
CREATE TABLE IF NOT EXISTS user_directives (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    kind VARCHAR(40) NOT NULL,
    instruction TEXT NOT NULL,
    metric_key VARCHAR(50),
    target_value VARCHAR(100),
    medication_name VARCHAR(100),
    severity VARCHAR(20),
    source VARCHAR(40) DEFAULT 'manual',
    source_message_id VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active',
    effective_from TIMESTAMP WITH TIME ZONE DEFAULT now(),
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE,
    revoked_reason VARCHAR(200)
);
CREATE INDEX IF NOT EXISTS ix_user_directives_user_id ON user_directives(user_id);
CREATE INDEX IF NOT EXISTS ix_user_directives_kind ON user_directives(kind);
CREATE INDEX IF NOT EXISTS ix_user_directives_source ON user_directives(source);
CREATE INDEX IF NOT EXISTS ix_user_directives_status ON user_directives(status);
CREATE INDEX IF NOT EXISTS idx_user_directive_user_status ON user_directives(user_id, status);
CREATE INDEX IF NOT EXISTS idx_user_directive_user_metric ON user_directives(user_id, metric_key);
