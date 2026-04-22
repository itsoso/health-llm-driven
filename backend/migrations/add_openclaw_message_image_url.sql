-- Add image_url column to openclaw_messages for persisting chat images
ALTER TABLE openclaw_messages ADD COLUMN IF NOT EXISTS image_url VARCHAR(500);
