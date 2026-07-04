-- Add image_url column to the legacy physical agent message table.
ALTER TABLE openclaw_messages ADD COLUMN IF NOT EXISTS image_url VARCHAR(500);
