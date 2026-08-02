CREATE TABLE IF NOT EXISTS registration_invitations (
    id BIGSERIAL PRIMARY KEY,
    code_digest VARCHAR(128) NOT NULL,
    link_token_digest VARCHAR(128) NOT NULL,
    phone_ciphertext VARCHAR(512) NOT NULL,
    phone_hmac VARCHAR(128) NOT NULL,
    phone_masked VARCHAR(32) NOT NULL,
    note VARCHAR(200),
    status VARCHAR(20) NOT NULL DEFAULT 'created',
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    consumed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    consumed_at TIMESTAMP WITH TIME ZONE,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    send_attempt_count INTEGER NOT NULL DEFAULT 0,
    last_send_error_code VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_registration_invitations_code_digest UNIQUE (code_digest),
    CONSTRAINT uq_registration_invitations_link_token_digest UNIQUE (link_token_digest),
    CONSTRAINT ck_registration_invitations_status CHECK (
        status IN ('created', 'sent', 'send_failed', 'consumed', 'revoked', 'expired')
    )
);

CREATE INDEX IF NOT EXISTS ix_registration_invitations_phone_hmac
    ON registration_invitations(phone_hmac);
CREATE INDEX IF NOT EXISTS ix_registration_invitations_status
    ON registration_invitations(status);
CREATE INDEX IF NOT EXISTS ix_registration_invitations_expires_at
    ON registration_invitations(expires_at);
CREATE INDEX IF NOT EXISTS ix_registration_invitations_consumed_by
    ON registration_invitations(consumed_by);
CREATE INDEX IF NOT EXISTS ix_registration_invitations_created_by
    ON registration_invitations(created_by);
CREATE UNIQUE INDEX IF NOT EXISTS uq_registration_invitations_active_phone_hmac
    ON registration_invitations(phone_hmac)
    WHERE status IN ('created', 'sent', 'send_failed');

CREATE TABLE IF NOT EXISTS phone_registration_grants (
    id BIGSERIAL PRIMARY KEY,
    token_digest VARCHAR(128) NOT NULL,
    phone_hmac VARCHAR(128) NOT NULL,
    phone_ciphertext VARCHAR(512) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    consumed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_phone_registration_grants_token_digest UNIQUE (token_digest)
);

CREATE INDEX IF NOT EXISTS ix_phone_registration_grants_phone_hmac
    ON phone_registration_grants(phone_hmac);
CREATE INDEX IF NOT EXISTS ix_phone_registration_grants_expires_at
    ON phone_registration_grants(expires_at);
