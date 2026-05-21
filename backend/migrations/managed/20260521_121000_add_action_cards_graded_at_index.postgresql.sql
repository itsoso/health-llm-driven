CREATE INDEX IF NOT EXISTS idx_action_cards_graded_at_not_null
    ON action_cards(graded_at)
    WHERE graded_at IS NOT NULL;
