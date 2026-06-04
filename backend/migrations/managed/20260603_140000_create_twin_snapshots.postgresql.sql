CREATE TABLE IF NOT EXISTS twin_snapshots (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    schema_version VARCHAR(16) NOT NULL DEFAULT '1',
    content_hash VARCHAR(64),
    purpose VARCHAR(40) NOT NULL DEFAULT 'manual',
    quality_grade VARCHAR(2),
    sources JSONB,
    twin_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_twin_snapshots_user_created ON twin_snapshots(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_twin_snapshots_user_purpose ON twin_snapshots(user_id, purpose);
CREATE INDEX IF NOT EXISTS idx_twin_snapshots_content_hash ON twin_snapshots(content_hash);
