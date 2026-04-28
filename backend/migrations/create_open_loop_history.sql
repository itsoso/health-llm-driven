-- Open-Loop Manager 推送历史 — 去重 + 用户反馈
-- 每条 APNs 推送写一行, 用户点击/snooze 异步更新.

CREATE TABLE IF NOT EXISTS open_loop_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,

    kind VARCHAR(40) NOT NULL,
    signal_key VARCHAR(100) NOT NULL,

    score INTEGER NOT NULL,
    title VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    deeplink VARCHAR(200),

    sent_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    delivery_ok INTEGER NOT NULL DEFAULT 1,
    delivery_error TEXT,

    user_action VARCHAR(20),
    action_at TIMESTAMP WITH TIME ZONE,
    snoozed_until TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_open_loop_history_user_id ON open_loop_history(user_id);
CREATE INDEX IF NOT EXISTS ix_open_loop_history_kind ON open_loop_history(kind);
CREATE INDEX IF NOT EXISTS ix_open_loop_history_sent_at ON open_loop_history(sent_at);
CREATE INDEX IF NOT EXISTS idx_open_loop_user_kind_signal
    ON open_loop_history(user_id, kind, signal_key);
CREATE INDEX IF NOT EXISTS idx_open_loop_user_sent
    ON open_loop_history(user_id, sent_at);
