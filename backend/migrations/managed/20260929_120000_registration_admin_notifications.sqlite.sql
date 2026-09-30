-- Additive outbox. Rollback keeps pending rows; do not drop undelivered events.
CREATE TABLE IF NOT EXISTS registration_admin_notifications (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP,
    last_error VARCHAR(32)
);
CREATE INDEX IF NOT EXISTS ix_registration_admin_notifications_due
    ON registration_admin_notifications (status, next_attempt_at);
