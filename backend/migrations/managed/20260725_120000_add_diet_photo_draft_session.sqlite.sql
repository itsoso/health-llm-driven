ALTER TABLE diet_photo_drafts
    ADD COLUMN source_message_id INTEGER;

CREATE UNIQUE INDEX IF NOT EXISTS uq_diet_photo_drafts_user_source_message
    ON diet_photo_drafts (user_id, source_message_id)
    WHERE source_message_id IS NOT NULL;
