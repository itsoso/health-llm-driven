-- provider 真值 usage:cached_tokens(前缀缓存验收唯一真值)+ token_source(api/estimate)
ALTER TABLE llm_usage_logs ADD COLUMN IF NOT EXISTS cached_tokens INTEGER;
ALTER TABLE llm_usage_logs ADD COLUMN IF NOT EXISTS token_source VARCHAR(16);
