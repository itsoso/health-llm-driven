CREATE TABLE IF NOT EXISTS assistant_openclaw_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL DEFAULT '我的 OpenClaw',
    gateway_url TEXT NOT NULL,
    gateway_token_encrypted TEXT NOT NULL,
    gateway_token_last4 TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'unconfigured',
    last_tested_at DATETIME NULL,
    last_error TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_assistant_openclaw_bindings_status
    ON assistant_openclaw_bindings(status);

CREATE TABLE IF NOT EXISTS assistant_openclaw_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT DEFAULT '新对话',
    session_key TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_assistant_openclaw_conversations_user_id
    ON assistant_openclaw_conversations(user_id);

CREATE INDEX IF NOT EXISTS ix_assistant_openclaw_conv_user_updated
    ON assistant_openclaw_conversations(user_id, updated_at);

CREATE TABLE IF NOT EXISTS assistant_openclaw_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES assistant_openclaw_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_assistant_openclaw_messages_conversation_id
    ON assistant_openclaw_messages(conversation_id);
