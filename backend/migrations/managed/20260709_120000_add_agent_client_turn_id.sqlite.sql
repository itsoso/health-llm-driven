ALTER TABLE agent_messages ADD COLUMN client_turn_id VARCHAR(112);

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_messages_user_client_turn
    ON agent_messages (client_turn_id)
    WHERE role = 'user' AND client_turn_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_agent_messages_client_turn_id
    ON agent_messages (client_turn_id);
