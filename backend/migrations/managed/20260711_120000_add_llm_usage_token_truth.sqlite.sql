ALTER TABLE llm_usage_logs ADD COLUMN cached_tokens INTEGER;
ALTER TABLE llm_usage_logs ADD COLUMN token_source VARCHAR(16);
