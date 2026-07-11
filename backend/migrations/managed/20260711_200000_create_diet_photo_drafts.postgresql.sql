CREATE TABLE IF NOT EXISTS diet_photo_drafts (
    token VARCHAR(64) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    image_url VARCHAR,
    image_type VARCHAR(20) NOT NULL,
    recognition_result JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    consumed_record_id INTEGER UNIQUE REFERENCES diet_records(id) ON DELETE SET NULL,
    consumed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT ck_diet_photo_drafts_status
        CHECK (status IN ('pending', 'consumed', 'cancelled', 'expired'))
);

CREATE INDEX IF NOT EXISTS idx_diet_photo_drafts_user_status
    ON diet_photo_drafts (user_id, status);

CREATE INDEX IF NOT EXISTS idx_diet_photo_drafts_expires_at
    ON diet_photo_drafts (expires_at);
