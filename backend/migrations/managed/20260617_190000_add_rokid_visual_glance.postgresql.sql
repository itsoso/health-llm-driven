-- Rokid visual input events and glanceable cards.
-- Comments avoid semicolons because the managed runner splits on semicolons.
CREATE TABLE IF NOT EXISTS visual_input_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    device_type VARCHAR(40) NOT NULL DEFAULT 'glasses',
    source VARCHAR(50) NOT NULL DEFAULT 'rokid_glasses',
    intent VARCHAR(40) NOT NULL,
    image_uri TEXT,
    image_sha256 VARCHAR(64),
    ocr_text TEXT,
    recognition_result JSONB,
    confidence DOUBLE PRECISION,
    status VARCHAR(30) NOT NULL DEFAULT 'pending_confirmation',
    privacy_class VARCHAR(30) NOT NULL DEFAULT 'health_l3',
    write_intent_id INTEGER REFERENCES write_intents(id),
    target_type VARCHAR(50),
    target_id INTEGER,
    safety_result JSONB,
    meta JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_visual_input_events_user_id ON visual_input_events (user_id);
CREATE INDEX IF NOT EXISTS ix_visual_input_events_captured_at ON visual_input_events (captured_at);
CREATE INDEX IF NOT EXISTS ix_visual_input_events_intent ON visual_input_events (intent);
CREATE INDEX IF NOT EXISTS ix_visual_input_events_status ON visual_input_events (status);
CREATE INDEX IF NOT EXISTS ix_visual_input_events_write_intent_id ON visual_input_events (write_intent_id);
CREATE INDEX IF NOT EXISTS idx_visual_input_user_captured ON visual_input_events (user_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_visual_input_user_intent ON visual_input_events (user_id, intent);

CREATE TABLE IF NOT EXISTS glance_cards (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    surface VARCHAR(40) NOT NULL DEFAULT 'rokid_glasses',
    card_type VARCHAR(40) NOT NULL DEFAULT 'action_prompt',
    title VARCHAR(80) NOT NULL,
    body TEXT NOT NULL,
    priority VARCHAR(20) NOT NULL DEFAULT 'normal',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    action JSONB,
    target_type VARCHAR(50),
    target_id INTEGER,
    expires_at TIMESTAMPTZ,
    displayed_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ,
    meta JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_glance_cards_user_id ON glance_cards (user_id);
CREATE INDEX IF NOT EXISTS ix_glance_cards_surface ON glance_cards (surface);
CREATE INDEX IF NOT EXISTS ix_glance_cards_card_type ON glance_cards (card_type);
CREATE INDEX IF NOT EXISTS ix_glance_cards_status ON glance_cards (status);
CREATE INDEX IF NOT EXISTS ix_glance_cards_expires_at ON glance_cards (expires_at);
CREATE INDEX IF NOT EXISTS idx_glance_cards_user_surface_status ON glance_cards (user_id, surface, status);
CREATE INDEX IF NOT EXISTS idx_glance_cards_user_expires ON glance_cards (user_id, expires_at);
