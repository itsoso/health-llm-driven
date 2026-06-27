-- Health Runtime Governance: data connection, consent, provenance, and connector policy.

CREATE TABLE IF NOT EXISTS data_connections (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    provider VARCHAR(80) NOT NULL,
    provider_type VARCHAR(40) NOT NULL,
    display_name VARCHAR(160) NOT NULL,
    connection_status VARCHAR(30) NOT NULL DEFAULT 'active',
    scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
    token_status VARCHAR(30) NOT NULL DEFAULT 'none',
    last_success_at TIMESTAMP WITH TIME ZONE,
    last_attempt_at TIMESTAMP WITH TIME ZONE,
    sync_error TEXT,
    source_ref VARCHAR(200),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_data_connections_user_provider
    ON data_connections(user_id, provider);
CREATE INDEX IF NOT EXISTS ix_data_connections_user_id
    ON data_connections(user_id);
CREATE INDEX IF NOT EXISTS ix_data_connections_provider_type
    ON data_connections(provider_type);
CREATE INDEX IF NOT EXISTS ix_data_connections_connection_status
    ON data_connections(connection_status);

CREATE TABLE IF NOT EXISTS consent_grants (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    connection_id INTEGER NOT NULL REFERENCES data_connections(id) ON DELETE CASCADE,
    grantee_type VARCHAR(40) NOT NULL,
    grantee_id VARCHAR(120),
    scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
    purpose VARCHAR(240) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    granted_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_consent_grants_user_id
    ON consent_grants(user_id);
CREATE INDEX IF NOT EXISTS ix_consent_grants_connection_id
    ON consent_grants(connection_id);
CREATE INDEX IF NOT EXISTS ix_consent_grants_grantee_type
    ON consent_grants(grantee_type);
CREATE INDEX IF NOT EXISTS ix_consent_grants_status
    ON consent_grants(status);
CREATE INDEX IF NOT EXISTS ix_consent_grants_user_connection
    ON consent_grants(user_id, connection_id);

CREATE TABLE IF NOT EXISTS connector_policies (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    connection_id INTEGER NOT NULL REFERENCES data_connections(id) ON DELETE CASCADE,
    scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
    rate_limit VARCHAR(80) NOT NULL DEFAULT 'provider_default',
    token_status VARCHAR(30) NOT NULL DEFAULT 'none',
    degraded_behavior VARCHAR(80) NOT NULL DEFAULT 'read_only',
    data_minimization VARCHAR(120) NOT NULL DEFAULT 'scoped_fields_only',
    revoke_deletes_derived BOOLEAN NOT NULL DEFAULT TRUE,
    audit_required BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_connector_policies_user_id
    ON connector_policies(user_id);
CREATE INDEX IF NOT EXISTS ix_connector_policies_connection_id
    ON connector_policies(connection_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_connector_policies_user_connection
    ON connector_policies(user_id, connection_id);

CREATE TABLE IF NOT EXISTS provenance_records (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    connection_id INTEGER REFERENCES data_connections(id) ON DELETE SET NULL,
    source_kind VARCHAR(40) NOT NULL,
    source_id VARCHAR(160) NOT NULL,
    object_type VARCHAR(120) NOT NULL,
    object_id VARCHAR(160) NOT NULL,
    observed_at TIMESTAMP WITH TIME ZONE,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    transformed_by VARCHAR(120) NOT NULL,
    confidence VARCHAR(30) NOT NULL DEFAULT 'unknown',
    privacy_classification VARCHAR(20) NOT NULL DEFAULT 'L3',
    user_correction JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_hash VARCHAR(128),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_provenance_records_user_id
    ON provenance_records(user_id);
CREATE INDEX IF NOT EXISTS ix_provenance_records_connection_id
    ON provenance_records(connection_id);
CREATE INDEX IF NOT EXISTS ix_provenance_records_source_kind
    ON provenance_records(source_kind);
CREATE INDEX IF NOT EXISTS ix_provenance_records_object_type
    ON provenance_records(object_type);
CREATE INDEX IF NOT EXISTS ix_provenance_records_object_id
    ON provenance_records(object_id);
CREATE INDEX IF NOT EXISTS ix_provenance_records_user_object
    ON provenance_records(user_id, object_type, object_id);
