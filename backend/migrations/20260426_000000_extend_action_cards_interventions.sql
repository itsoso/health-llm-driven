-- Extend action cards so Agent advice can persist as measurable interventions.
ALTER TABLE action_cards
    ADD COLUMN IF NOT EXISTS metric_key VARCHAR(50),
    ADD COLUMN IF NOT EXISTS baseline_value VARCHAR(100),
    ADD COLUMN IF NOT EXISTS target_value VARCHAR(100),
    ADD COLUMN IF NOT EXISTS verification_days INTEGER,
    ADD COLUMN IF NOT EXISTS checklist JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS last_assessed_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS assessment_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS latest_assessment JSONB;

CREATE INDEX IF NOT EXISTS idx_action_cards_user_metric
    ON action_cards(user_id, metric_key)
    WHERE metric_key IS NOT NULL;
