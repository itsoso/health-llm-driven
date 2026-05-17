ALTER TABLE action_cards
ADD COLUMN IF NOT EXISTS evidence_refs JSONB DEFAULT '[]'::jsonb;
