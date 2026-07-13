ALTER TABLE diet_records
    ADD COLUMN IF NOT EXISTS client_action_id VARCHAR(160);

CREATE UNIQUE INDEX IF NOT EXISTS uq_diet_records_user_client_action_id
    ON diet_records (user_id, client_action_id)
    WHERE client_action_id IS NOT NULL;
