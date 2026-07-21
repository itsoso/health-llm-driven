-- A source Agent message may own at most one medication intake batch intent.
-- SQLite does not enforce VARCHAR lengths; fresh schemas use VARCHAR(255) from
-- the SQLAlchemy model while existing SQLite files need no table rebuild.
ALTER TABLE write_intents
    ADD COLUMN decision_status VARCHAR(20);

CREATE UNIQUE INDEX IF NOT EXISTS uq_write_intents_medication_batch_source
    ON write_intents(user_id, kind, target_type, target_id)
    WHERE kind = 'medication_intake_batch'
      AND target_type = 'agent_message';
