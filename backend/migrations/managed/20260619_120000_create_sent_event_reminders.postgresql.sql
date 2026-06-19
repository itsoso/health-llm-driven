-- P1-B 事件前提醒去重账。每 (user_id, item_key, remind_date) 至多提醒一次。
-- 不存 PII(无标题/无内容);仅幂等记账。幂等可重跑。
CREATE TABLE IF NOT EXISTS sent_event_reminders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    item_key VARCHAR(120) NOT NULL,
    remind_date DATE NOT NULL,
    kind VARCHAR(40),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sent_event_reminder_user_item_date
    ON sent_event_reminders (user_id, item_key, remind_date);
CREATE INDEX IF NOT EXISTS ix_sent_event_reminder_user_date
    ON sent_event_reminders (user_id, remind_date);
CREATE INDEX IF NOT EXISTS ix_sent_event_reminders_user_id
    ON sent_event_reminders (user_id);
