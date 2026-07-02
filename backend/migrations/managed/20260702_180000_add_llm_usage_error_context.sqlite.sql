ALTER TABLE llm_usage_logs ADD COLUMN error_type VARCHAR(64);
ALTER TABLE llm_usage_logs ADD COLUMN error_code VARCHAR(64);
ALTER TABLE llm_usage_logs ADD COLUMN error_message VARCHAR(500);
