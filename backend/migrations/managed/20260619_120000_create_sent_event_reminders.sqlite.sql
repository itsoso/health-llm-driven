-- P1-B 事件前提醒去重账 sqlite 变体。测试库由 create_all 直接建表,本迁移仅 prod 跑一次。幂等可重跑。
CREATE TABLE IF NOT EXISTS sent_event_reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    item_key VARCHAR(120) NOT NULL,
    remind_date DATE NOT NULL,
    kind VARCHAR(40),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sent_event_reminder_user_item_date
    ON sent_event_reminders (user_id, item_key, remind_date);
CREATE INDEX IF NOT EXISTS ix_sent_event_reminder_user_date
    ON sent_event_reminders (user_id, remind_date);
CREATE INDEX IF NOT EXISTS ix_sent_event_reminders_user_id
    ON sent_event_reminders (user_id);
