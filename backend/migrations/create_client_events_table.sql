-- Task 9: 观察期看板需要的客户端事件表 (UI 点击 / 页面 mount).
-- 与 InteractionFeedback 分开, 避免 message_id unique 约束.

BEGIN;

CREATE TABLE IF NOT EXISTS client_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    event_name VARCHAR(64) NOT NULL,
    meta JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_client_events_user_id ON client_events(user_id);
CREATE INDEX IF NOT EXISTS ix_client_events_event_name ON client_events(event_name);
CREATE INDEX IF NOT EXISTS ix_client_events_created_at ON client_events(created_at);
CREATE INDEX IF NOT EXISTS ix_client_events_name_created ON client_events(event_name, created_at);

COMMIT;
