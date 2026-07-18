CREATE TABLE IF NOT EXISTS aigc_media_confirmations (
    id VARCHAR(64) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id INTEGER NULL REFERENCES agent_conversations(id) ON DELETE SET NULL,
    source_message_id INTEGER NULL REFERENCES agent_messages(id) ON DELETE SET NULL,
    source_image_index INTEGER NULL,
    kind VARCHAR(32) NOT NULL,
    purpose VARCHAR(48) NOT NULL,
    model VARCHAR(80) NOT NULL,
    prompt_ciphertext TEXT NOT NULL,
    prompt_fingerprint VARCHAR(64) NOT NULL,
    duration_seconds INTEGER NOT NULL DEFAULT 5,
    ratio VARCHAR(12) NOT NULL DEFAULT '9:16',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    job_id VARCHAR(64) NULL UNIQUE REFERENCES aigc_media_jobs(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    consumed_at TIMESTAMP WITH TIME ZONE NULL,
    updated_at TIMESTAMP WITH TIME ZONE NULL
);
CREATE INDEX IF NOT EXISTS idx_aigc_media_confirmations_owner_state
    ON aigc_media_confirmations(user_id, status, expires_at);
