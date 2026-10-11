ALTER TABLE excretion_records ADD COLUMN photo_key VARCHAR(300);
ALTER TABLE excretion_records ADD COLUMN client_request_id VARCHAR(36);
ALTER TABLE excretion_records ADD COLUMN client_request_hash VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS uq_excretion_user_client_request
    ON excretion_records (user_id, client_request_id);
