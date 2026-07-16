ALTER TABLE llm_usage_logs ADD COLUMN IF NOT EXISTS tokenplan_credits_estimate DOUBLE PRECISION;
ALTER TABLE llm_usage_logs ADD COLUMN IF NOT EXISTS tokenplan_cost_cny DOUBLE PRECISION;
ALTER TABLE llm_usage_logs ADD COLUMN IF NOT EXISTS tokenplan_payg_value_cny DOUBLE PRECISION;
ALTER TABLE llm_usage_logs ADD COLUMN IF NOT EXISTS tokenplan_cost_estimated INTEGER;
ALTER TABLE llm_usage_logs ADD COLUMN IF NOT EXISTS tokenplan_cost_source VARCHAR(500);
ALTER TABLE llm_usage_logs ADD COLUMN IF NOT EXISTS tokenplan_monthly_fee_cny DOUBLE PRECISION;
ALTER TABLE llm_usage_logs ADD COLUMN IF NOT EXISTS tokenplan_monthly_credits INTEGER;
