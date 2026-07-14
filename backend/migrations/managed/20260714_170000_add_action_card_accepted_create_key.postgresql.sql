ALTER TABLE action_cards
    ADD COLUMN IF NOT EXISTS accepted_create_key VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS uq_action_cards_accepted_create_key
    ON action_cards (accepted_create_key)
    WHERE accepted_create_key IS NOT NULL;
