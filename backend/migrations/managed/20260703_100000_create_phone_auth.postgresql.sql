-- Phone-first login/register support.
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM users
        WHERE phone IS NOT NULL AND phone <> ''
        GROUP BY phone
        HAVING COUNT(*) > 1
    ) THEN
        CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone_not_null
            ON users(phone)
            WHERE phone IS NOT NULL AND phone <> '';
    ELSE
        RAISE WARNING 'Skipped uq_users_phone_not_null because duplicate phone values exist';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS auth_phone_codes (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(32) NOT NULL,
    purpose VARCHAR(32) NOT NULL DEFAULT 'login',
    code_hash VARCHAR(128) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    request_ip_hash VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_auth_phone_codes_phone ON auth_phone_codes(phone);
CREATE INDEX IF NOT EXISTS idx_auth_phone_codes_phone_purpose_created
    ON auth_phone_codes(phone, purpose, created_at);
