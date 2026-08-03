CREATE TABLE registration_invitations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code_digest VARCHAR(128) NOT NULL,
    link_token_digest VARCHAR(128) NOT NULL,
    phone_ciphertext VARCHAR(512) NOT NULL,
    phone_hmac VARCHAR(128) NOT NULL,
    phone_masked VARCHAR(32) NOT NULL,
    note VARCHAR(200),
    status VARCHAR(20) NOT NULL DEFAULT 'created',
    expires_at DATETIME NOT NULL,
    consumed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    consumed_at DATETIME,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    send_attempt_count INTEGER NOT NULL DEFAULT 0,
    last_send_error_code VARCHAR(64),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_registration_invitations_code_digest UNIQUE (code_digest),
    CONSTRAINT uq_registration_invitations_link_token_digest UNIQUE (link_token_digest),
    CONSTRAINT ck_registration_invitations_status CHECK (
        status IN ('created', 'sent', 'send_failed', 'consumed', 'revoked', 'expired')
    )
);

CREATE INDEX ix_registration_invitations_phone_hmac
    ON registration_invitations(phone_hmac);
CREATE INDEX ix_registration_invitations_status
    ON registration_invitations(status);
CREATE INDEX ix_registration_invitations_expires_at
    ON registration_invitations(expires_at);
CREATE INDEX ix_registration_invitations_consumed_by
    ON registration_invitations(consumed_by);
CREATE INDEX ix_registration_invitations_created_by
    ON registration_invitations(created_by);
CREATE UNIQUE INDEX uq_registration_invitations_active_phone_hmac
    ON registration_invitations(phone_hmac)
    WHERE status IN ('created', 'sent', 'send_failed');

CREATE TABLE phone_registration_grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_digest VARCHAR(128) NOT NULL,
    phone_hmac VARCHAR(128) NOT NULL,
    phone_ciphertext VARCHAR(512) NOT NULL,
    expires_at DATETIME NOT NULL,
    consumed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    idempotency_key_digest VARCHAR(128),
    consumed_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_phone_registration_grants_token_digest UNIQUE (token_digest)
);

CREATE INDEX ix_phone_registration_grants_phone_hmac
    ON phone_registration_grants(phone_hmac);
CREATE INDEX ix_phone_registration_grants_expires_at
    ON phone_registration_grants(expires_at);
CREATE INDEX ix_phone_registration_grants_consumed_by
    ON phone_registration_grants(consumed_by);

CREATE TABLE registration_auth_attempt_audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    outcome VARCHAR(16) NOT NULL,
    error_code VARCHAR(64),
    invitation_id INTEGER REFERENCES registration_invitations(id) ON DELETE SET NULL,
    grant_id INTEGER REFERENCES phone_registration_grants(id) ON DELETE SET NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    phone_masked VARCHAR(32),
    source_hmac VARCHAR(128),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_registration_auth_attempt_audits_outcome CHECK (
        outcome IN ('success', 'rejected')
    )
);

CREATE INDEX ix_registration_auth_attempt_audits_outcome
    ON registration_auth_attempt_audits(outcome);
CREATE INDEX ix_registration_auth_attempt_audits_error_code
    ON registration_auth_attempt_audits(error_code);
CREATE INDEX ix_registration_auth_attempt_audits_invitation_id
    ON registration_auth_attempt_audits(invitation_id);
CREATE INDEX ix_registration_auth_attempt_audits_grant_id
    ON registration_auth_attempt_audits(grant_id);
CREATE INDEX ix_registration_auth_attempt_audits_user_id
    ON registration_auth_attempt_audits(user_id);
