ALTER TABLE agent_runs
    ADD COLUMN runtime_contract_version VARCHAR(32);

ALTER TABLE agent_runs
    ADD COLUMN tool_registry_digest VARCHAR(64);

ALTER TABLE agent_runs
    ADD COLUMN capability_policy_digest VARCHAR(64);
