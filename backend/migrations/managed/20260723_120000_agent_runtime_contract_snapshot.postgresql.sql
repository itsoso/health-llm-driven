ALTER TABLE agent_runs
    ADD COLUMN IF NOT EXISTS runtime_contract_version VARCHAR(32);

ALTER TABLE agent_runs
    ADD COLUMN IF NOT EXISTS tool_registry_digest VARCHAR(64);

ALTER TABLE agent_runs
    ADD COLUMN IF NOT EXISTS capability_policy_digest VARCHAR(64);
