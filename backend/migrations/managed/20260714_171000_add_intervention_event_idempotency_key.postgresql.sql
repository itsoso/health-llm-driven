ALTER TABLE intervention_events
    ADD COLUMN IF NOT EXISTS event_idempotency_key VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS uq_intervention_events_event_idempotency_key
    ON intervention_events(event_idempotency_key)
    WHERE event_idempotency_key IS NOT NULL;
