CREATE TABLE IF NOT EXISTS aigc_media_jobs (
    id VARCHAR(64) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id INTEGER REFERENCES agent_conversations(id) ON DELETE SET NULL,
    source_message_id INTEGER REFERENCES agent_messages(id) ON DELETE SET NULL,
    source_image_index INTEGER,
    kind VARCHAR(32) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    model VARCHAR(80) NOT NULL,
    provider_task_id VARCHAR(128) UNIQUE,
    idempotency_key VARCHAR(128) NOT NULL,
    request_fingerprint VARCHAR(64) NOT NULL,
    output_filename VARCHAR(256),
    output_media_type VARCHAR(32),
    result_metadata JSONB,
    provider_error_code VARCHAR(120),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    cancelled_at TIMESTAMP WITH TIME ZONE,
    last_provider_checked_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_aigc_media_jobs_user_idempotency UNIQUE (user_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_aigc_media_jobs_user_created ON aigc_media_jobs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_aigc_media_jobs_user_status ON aigc_media_jobs (user_id, status);
