ALTER TABLE client_events
ADD COLUMN IF NOT EXISTS event_key VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS uq_client_events_owner_name_key
ON client_events(user_id, event_name, event_key)
WHERE event_key IS NOT NULL;
