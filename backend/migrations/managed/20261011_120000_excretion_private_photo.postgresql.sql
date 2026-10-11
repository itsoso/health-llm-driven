ALTER TABLE excretion_records ADD COLUMN IF NOT EXISTS photo_key VARCHAR(300);
ALTER TABLE excretion_records ADD COLUMN IF NOT EXISTS client_request_id VARCHAR(36);
ALTER TABLE excretion_records ADD COLUMN IF NOT EXISTS client_request_hash VARCHAR(64);
ALTER TABLE excretion_records ALTER COLUMN blood_present DROP DEFAULT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_excretion_user_client_request
    ON excretion_records (user_id, client_request_id);
