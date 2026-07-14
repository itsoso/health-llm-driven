BEGIN;

CREATE TABLE IF NOT EXISTS account_deletion_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    active_user_id INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'requested',
    channel VARCHAR(30) NOT NULL DEFAULT 'mobile_app',
    scope TEXT NOT NULL DEFAULT 'account,health_data,device_connections',
    audit_id INTEGER,
    processing_admin_id INTEGER,
    processing_note TEXT,
    verification_reference VARCHAR(200),
    requested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT ck_account_deletion_requests_status
        CHECK (status IN ('requested', 'processing', 'completed', 'rejected'))
);

CREATE INDEX IF NOT EXISTS ix_account_deletion_requests_user_id
    ON account_deletion_requests(user_id);
CREATE INDEX IF NOT EXISTS ix_account_deletion_requests_status
    ON account_deletion_requests(status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_account_deletion_requests_active_user_id
    ON account_deletion_requests(active_user_id)
    WHERE active_user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_account_deletion_requests_audit_id
    ON account_deletion_requests(audit_id)
    WHERE audit_id IS NOT NULL;

COMMIT;
