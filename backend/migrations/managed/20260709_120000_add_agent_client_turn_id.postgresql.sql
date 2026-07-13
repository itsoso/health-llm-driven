ALTER TABLE agent_messages
    ADD COLUMN IF NOT EXISTS client_turn_id VARCHAR(112);

ALTER TABLE agent_messages
    ALTER COLUMN client_turn_id TYPE VARCHAR(112);

UPDATE agent_messages AS message
SET client_turn_id = conversation.user_id::text || ':' || (message.meta ->> 'client_turn_id')
FROM agent_conversations AS conversation
WHERE message.conversation_id = conversation.id
  AND message.client_turn_id IS NULL
  AND message.meta ? 'client_turn_id';

WITH ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (PARTITION BY client_turn_id ORDER BY id ASC) AS duplicate_rank
    FROM agent_messages
    WHERE role = 'user' AND client_turn_id IS NOT NULL
)
UPDATE agent_messages AS message
SET client_turn_id = NULL
FROM ranked
WHERE message.id = ranked.id
  AND ranked.duplicate_rank > 1;

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_messages_user_client_turn
    ON agent_messages (client_turn_id)
    WHERE role = 'user' AND client_turn_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_agent_messages_client_turn_id
    ON agent_messages (client_turn_id);
