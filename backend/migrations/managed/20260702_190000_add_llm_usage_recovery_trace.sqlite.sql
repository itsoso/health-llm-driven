ALTER TABLE llm_usage_logs ADD COLUMN run_id VARCHAR(64);
ALTER TABLE llm_usage_logs ADD COLUMN error_class VARCHAR(64);
ALTER TABLE llm_usage_logs ADD COLUMN recovery_action VARCHAR(64);
ALTER TABLE llm_usage_logs ADD COLUMN recovery_model VARCHAR(128);
CREATE INDEX idx_llm_usage_run_id ON llm_usage_logs(run_id);
