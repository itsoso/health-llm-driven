ALTER TABLE llm_usage_logs ADD COLUMN IF NOT EXISTS run_id VARCHAR(64);
ALTER TABLE llm_usage_logs ADD COLUMN IF NOT EXISTS error_class VARCHAR(64);
ALTER TABLE llm_usage_logs ADD COLUMN IF NOT EXISTS recovery_action VARCHAR(64);
ALTER TABLE llm_usage_logs ADD COLUMN IF NOT EXISTS recovery_model VARCHAR(128);
CREATE INDEX IF NOT EXISTS idx_llm_usage_run_id ON llm_usage_logs(run_id);
