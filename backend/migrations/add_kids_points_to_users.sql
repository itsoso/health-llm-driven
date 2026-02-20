-- Add kids mode points to users for skin shop persistence.
ALTER TABLE users
ADD COLUMN IF NOT EXISTS kids_points INTEGER NOT NULL DEFAULT 0;
