-- Add garth_session column to garmin_credentials table for OAuth token caching
-- This prevents frequent logins which can trigger Garmin account lockout

ALTER TABLE garmin_credentials
ADD COLUMN garth_session TEXT;

-- Add session_expires_at to track when the cached session might expire
ALTER TABLE garmin_credentials
ADD COLUMN session_expires_at DATETIME;

-- Comment: garth_session stores the serialized garth session data (JSON format)
-- This allows reusing OAuth tokens instead of logging in every time
