-- Phone-first login/register support.
ALTER TABLE users ADD COLUMN phone_verified_at DATETIME;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone_not_null
    ON users(phone)
    WHERE phone IS NOT NULL AND phone <> '';

CREATE TABLE IF NOT EXISTS auth_phone_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone VARCHAR(32) NOT NULL,
    purpose VARCHAR(32) NOT NULL DEFAULT 'login',
    code_hash VARCHAR(128) NOT NULL,
    expires_at DATETIME NOT NULL,
    consumed_at DATETIME,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    request_ip_hash VARCHAR(128),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_auth_phone_codes_phone ON auth_phone_codes(phone);
CREATE INDEX IF NOT EXISTS idx_auth_phone_codes_phone_purpose_created
    ON auth_phone_codes(phone, purpose, created_at);
