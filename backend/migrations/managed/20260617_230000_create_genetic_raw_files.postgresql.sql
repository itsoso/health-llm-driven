-- 多租户基因原始数据专用表 + Postgres RLS (DB 层强制租户隔离)。
-- ciphertext 是 per-tenant 加密的全量基因型 JSON (应用层 tenant_crypto/Fernet 加密),
-- 库里只见密文。RLS policy 用 current_setting('app.user_id') 比对 user_id,
-- 由 deps.tenant_scope + database.after_begin 在每个事务注入。
-- FORCE ROW LEVEL SECURITY 对表 owner 也生效。
-- 注意 Postgres superuser 角色会绕过 RLS(含 FORCE)—— 生产 app 连接必须用「非 superuser」角色,
-- 否则租户隔离退化为仅应用层 WHERE。main.py 启动时校验 is_superuser 并 fail-loud 告警。
-- 注 runner 按裸分号切语句, 注释里不能出现分号。幂等可重跑。
CREATE TABLE IF NOT EXISTS genetic_raw_files (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    profile_id BIGINT NOT NULL REFERENCES genetic_profiles(id) ON DELETE CASCADE,
    import_job_id BIGINT REFERENCES genetic_import_jobs(id),
    raw_sha256 VARCHAR(64),
    snp_count INTEGER,
    byte_size INTEGER,
    key_version SMALLINT DEFAULT 1,
    enc_algo VARCHAR(20) DEFAULT 'fernet-hkdf',
    ciphertext TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_genetic_raw_user_sha ON genetic_raw_files (user_id, raw_sha256);
CREATE INDEX IF NOT EXISTS ix_genetic_raw_files_user_id ON genetic_raw_files (user_id);
CREATE INDEX IF NOT EXISTS ix_genetic_raw_user_profile ON genetic_raw_files (user_id, profile_id);

CREATE TABLE IF NOT EXISTS genetic_raw_audit (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    profile_id BIGINT,
    action VARCHAR(20) NOT NULL,
    detail JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_genetic_raw_audit_user_id ON genetic_raw_audit (user_id);

ALTER TABLE genetic_raw_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE genetic_raw_files FORCE ROW LEVEL SECURITY;
ALTER TABLE genetic_raw_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE genetic_raw_audit FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_raw ON genetic_raw_files;
CREATE POLICY tenant_isolation_raw ON genetic_raw_files
    USING (user_id = current_setting('app.user_id', true)::bigint)
    WITH CHECK (user_id = current_setting('app.user_id', true)::bigint);

DROP POLICY IF EXISTS tenant_isolation_raw_audit ON genetic_raw_audit;
CREATE POLICY tenant_isolation_raw_audit ON genetic_raw_audit
    USING (user_id = current_setting('app.user_id', true)::bigint)
    WITH CHECK (user_id = current_setting('app.user_id', true)::bigint);
