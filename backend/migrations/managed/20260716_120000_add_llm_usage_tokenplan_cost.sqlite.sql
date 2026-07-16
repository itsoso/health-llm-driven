ALTER TABLE llm_usage_logs ADD COLUMN tokenplan_credits_estimate REAL;
ALTER TABLE llm_usage_logs ADD COLUMN tokenplan_cost_cny REAL;
ALTER TABLE llm_usage_logs ADD COLUMN tokenplan_payg_value_cny REAL;
ALTER TABLE llm_usage_logs ADD COLUMN tokenplan_cost_estimated INTEGER;
ALTER TABLE llm_usage_logs ADD COLUMN tokenplan_cost_source VARCHAR(500);
ALTER TABLE llm_usage_logs ADD COLUMN tokenplan_monthly_fee_cny REAL;
ALTER TABLE llm_usage_logs ADD COLUMN tokenplan_monthly_credits INTEGER;
