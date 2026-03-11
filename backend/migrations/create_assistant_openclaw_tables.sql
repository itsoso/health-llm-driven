CREATE TABLE IF NOT EXISTS assistant_openclaw_bindings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    display_name VARCHAR(100) NOT NULL DEFAULT '我的 OpenClaw',
    gateway_url VARCHAR(255) NOT NULL,
    gateway_token_encrypted TEXT NOT NULL,
    gateway_token_last4 VARCHAR(8) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(20) NOT NULL DEFAULT 'unconfigured',
    last_tested_at TIMESTAMP NULL,
    last_error TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assistant_openclaw_bindings_status
    ON assistant_openclaw_bindings(status);

CREATE TABLE IF NOT EXISTS assistant_openclaw_conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(200) DEFAULT '新对话',
    session_key VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_assistant_openclaw_conversations_user_id
    ON assistant_openclaw_conversations(user_id);

CREATE INDEX IF NOT EXISTS ix_assistant_openclaw_conv_user_updated
    ON assistant_openclaw_conversations(user_id, updated_at);

CREATE TABLE IF NOT EXISTS assistant_openclaw_messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES assistant_openclaw_conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_assistant_openclaw_messages_conversation_id
    ON assistant_openclaw_messages(conversation_id);
