-- sqlite test fixture mirror — 见 .postgresql.sql 注释。
-- SQLite 无 RLS, 只建表 (行级隔离须在 Postgres 部署验证)。
-- ciphertext 是 per-tenant 加密的全量基因型 JSON (应用层 tenant_crypto/Fernet 加密)。
CREATE TABLE IF NOT EXISTS genetic_raw_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id BIGINT NOT NULL,
    profile_id BIGINT NOT NULL REFERENCES genetic_profiles(id) ON DELETE CASCADE,
    import_job_id BIGINT REFERENCES genetic_import_jobs(id),
    raw_sha256 VARCHAR(64),
    snp_count INTEGER,
    byte_size INTEGER,
    key_version SMALLINT DEFAULT 1,
    enc_algo VARCHAR(20) DEFAULT 'fernet-hkdf',
    ciphertext TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_genetic_raw_user_sha ON genetic_raw_files (user_id, raw_sha256);
CREATE INDEX IF NOT EXISTS ix_genetic_raw_files_user_id ON genetic_raw_files (user_id);
CREATE INDEX IF NOT EXISTS ix_genetic_raw_user_profile ON genetic_raw_files (user_id, profile_id);

CREATE TABLE IF NOT EXISTS genetic_raw_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id BIGINT NOT NULL,
    profile_id BIGINT,
    action VARCHAR(20) NOT NULL,
    detail TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_genetic_raw_audit_user_id ON genetic_raw_audit (user_id);
