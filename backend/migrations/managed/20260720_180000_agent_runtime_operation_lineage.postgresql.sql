ALTER TABLE agent_tool_operations
    ADD COLUMN IF NOT EXISTS logical_operation_key_hash VARCHAR(64);

ALTER TABLE agent_tool_operations
    ADD COLUMN IF NOT EXISTS created_attempt_no INTEGER;

ALTER TABLE agent_tool_operations
    ADD COLUMN IF NOT EXISTS logical_operation_scope_hash VARCHAR(64);

ALTER TABLE agent_tool_operations
    ADD COLUMN IF NOT EXISTS logical_operation_discriminator_kind VARCHAR(24);

ALTER TABLE agent_tool_operations
    ADD COLUMN IF NOT EXISTS logical_operation_discriminator_hash VARCHAR(64);

UPDATE agent_tool_operations
SET logical_operation_key_hash = operation_fingerprint
WHERE logical_operation_key_hash IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_tool_operations_run_logical_key
    ON agent_tool_operations(run_id, logical_operation_key_hash)
    WHERE logical_operation_key_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_agent_tool_operations_run_scope
    ON agent_tool_operations(run_id, logical_operation_scope_hash);
