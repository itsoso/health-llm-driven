CREATE TABLE IF NOT EXISTS diet_photo_assets (
    id VARCHAR(64) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    diet_record_id INTEGER REFERENCES diet_records(id) ON DELETE SET NULL,
    photo_draft_token VARCHAR(64) REFERENCES diet_photo_drafts(token) ON DELETE SET NULL,
    storage_key VARCHAR(1024) NOT NULL,
    content_sha256 VARCHAR(64) NOT NULL,
    media_type VARCHAR(40) NOT NULL,
    origin VARCHAR(40) NOT NULL,
    origin_message_id INTEGER,
    ordinal INTEGER NOT NULL DEFAULT 0,
    captured_at TIMESTAMP,
    captured_timezone VARCHAR(64),
    classification VARCHAR(24) NOT NULL,
    recognition_confidence REAL,
    intent_decision VARCHAR(24) NOT NULL,
    recognition_snapshot TEXT,
    lifecycle VARCHAR(24) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    attached_at TIMESTAMP,
    deleted_at TIMESTAMP,
    CONSTRAINT ck_diet_photo_assets_storage_key_canonical CHECK (storage_key NOT LIKE '%?%'),
    CONSTRAINT ck_diet_photo_assets_ordinal CHECK (ordinal >= 0),
    CONSTRAINT ck_diet_photo_assets_classification CHECK (classification IN ('food', 'non_food', 'unknown')),
    CONSTRAINT ck_diet_photo_assets_intent_decision CHECK (intent_decision IN ('auto_record', 'confirm', 'analyze_only')),
    CONSTRAINT ck_diet_photo_assets_lifecycle CHECK (lifecycle IN ('pending', 'attached', 'deleted')),
    CONSTRAINT uq_diet_photo_assets_user_origin_ordinal UNIQUE (user_id, origin_message_id, ordinal),
    CONSTRAINT uq_diet_photo_assets_record_ordinal UNIQUE (diet_record_id, ordinal)
);

CREATE INDEX IF NOT EXISTS idx_diet_photo_assets_user_record
    ON diet_photo_assets (user_id, diet_record_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_diet_photo_assets_draft
    ON diet_photo_assets (photo_draft_token);
CREATE INDEX IF NOT EXISTS idx_diet_photo_assets_user_hash
    ON diet_photo_assets (user_id, content_sha256, created_at);
