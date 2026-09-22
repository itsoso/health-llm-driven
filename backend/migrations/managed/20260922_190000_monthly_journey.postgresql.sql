-- Additive rollout. Rollback code only: retain user-confirmed annotations.
CREATE TABLE IF NOT EXISTS journey_places (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    diet_record_id INTEGER REFERENCES diet_records(id) ON DELETE CASCADE,
    life_event_id INTEGER REFERENCES health_episodes(id) ON DELETE CASCADE,
    chat_message_id INTEGER REFERENCES agent_messages(id) ON DELETE CASCADE,
    city VARCHAR(1024) NOT NULL,
    local_date DATE NOT NULL,
    timezone VARCHAR(64) NOT NULL,
    location_source VARCHAR(8) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_journey_one_source CHECK (
      (CASE WHEN diet_record_id IS NULL THEN 0 ELSE 1 END +
       CASE WHEN life_event_id IS NULL THEN 0 ELSE 1 END +
       CASE WHEN chat_message_id IS NULL THEN 0 ELSE 1 END) = 1
    ),
    CONSTRAINT ck_journey_location_source CHECK (location_source IN ('manual', 'device')),
    CONSTRAINT ck_journey_version CHECK (version > 0),
    CONSTRAINT uq_journey_owner_diet UNIQUE (user_id, diet_record_id),
    CONSTRAINT uq_journey_owner_life UNIQUE (user_id, life_event_id),
    CONSTRAINT uq_journey_owner_chat UNIQUE (user_id, chat_message_id)
);
CREATE INDEX IF NOT EXISTS ix_journey_owner_date_id ON journey_places(user_id, local_date, id);
