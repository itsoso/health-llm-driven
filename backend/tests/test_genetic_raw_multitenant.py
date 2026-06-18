"""多租户基因原始数据库测试 —— per-tenant 加密 + 应用层隔离 + 审计 + 软删.

RLS 行级隔离 (Postgres policy) 在 SQLite 测不了, 须在 Postgres 部署用 TEST_DATABASE_URL
验证 (set app.user_id=A 后查不到 B 的行)。本文件覆盖 RLS 之外的全部行为:
per-tenant crypto / 应用层 user_id 过滤 / 审计 / 软删 / 去重。
"""
import hashlib
import json
import uuid
from datetime import date

import pytest
from cryptography.fernet import InvalidToken

from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.models.genetic_raw import GeneticRawFile, GeneticRawAudit
from app.models.user import User
from app.services import tenant_crypto


# ── helpers ──

def _make_user(db) -> User:
    u = User(
        username=f"mt_{uuid.uuid4().hex[:8]}",
        email=f"mt_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="多租户测试",
        is_active=True, is_approved=True,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _make_profile_with_raw(db, user_id: int, raw: dict) -> GeneticProfile:
    profile = GeneticProfile(user_id=user_id, test_provider="微基因", test_date=date(2025, 1, 1))
    db.add(profile); db.commit(); db.refresh(profile)
    plaintext = json.dumps(raw, ensure_ascii=False)
    db.add(GeneticRawFile(
        user_id=user_id,
        profile_id=profile.id,
        raw_sha256=hashlib.sha256(plaintext.encode()).hexdigest(),
        snp_count=len(raw),
        byte_size=len(plaintext.encode()),
        ciphertext=tenant_crypto.encrypt_for(user_id, plaintext),
    ))
    db.commit()
    return profile


# ── per-tenant crypto ──

def test_cross_tenant_decrypt_fails():
    """A 加密的密文用 B 的 user_id 解密必须抛 InvalidToken (隔离纵深)。"""
    token = tenant_crypto.encrypt_for(1, "rs1801133:AG")
    assert tenant_crypto.decrypt_for(1, token) == "rs1801133:AG"
    with pytest.raises(InvalidToken):
        tenant_crypto.decrypt_for(2, token)


def test_same_tenant_roundtrip():
    payload = json.dumps({"rs7946": "AA"})
    token = tenant_crypto.encrypt_for(42, payload)
    assert token != payload  # 密文 != 明文
    assert tenant_crypto.decrypt_for(42, token) == payload


def test_encrypt_failure_raises(monkeypatch):
    """加密失败必须 raise (最高隐私级, 绝不明文落库)。"""
    class _BoomFernet:
        def encrypt(self, _b):
            raise RuntimeError("boom")

    monkeypatch.setattr(tenant_crypto, "_derive_fernet", lambda _uid: _BoomFernet())
    with pytest.raises(RuntimeError):
        tenant_crypto.encrypt_for(1, "sensitive-genotype")


def test_decrypt_failure_raises(monkeypatch):
    class _BoomFernet:
        def decrypt(self, _b):
            raise InvalidToken()

    monkeypatch.setattr(tenant_crypto, "_derive_fernet", lambda _uid: _BoomFernet())
    with pytest.raises(InvalidToken):
        tenant_crypto.decrypt_for(1, "garbage")


# ── GeneticRawFile service-layer round-trip ──

def test_raw_file_db_roundtrip(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    raw = {"rs7946": "AA", "rs9999999": "CT"}
    profile = _make_profile_with_raw(db, user.id, raw)
    db.expire_all()
    rf = db.query(GeneticRawFile).filter_by(profile_id=profile.id).first()
    assert rf.ciphertext != json.dumps(raw, ensure_ascii=False)
    assert json.loads(tenant_crypto.decrypt_for(user.id, rf.ciphertext)) == raw


# ── 应用层隔离: 别的 user 的 profile → 404 ──

def test_reparse_other_user_404(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    other = _make_user(db)
    profile = _make_profile_with_raw(db, other.id, {"rs7946": "AA"})
    res = client.post(f"/api/v1/genetic/profiles/{profile.id}/reparse", headers=headers)
    assert res.status_code == 404


def test_raw_lookup_other_user_404(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    other = _make_user(db)
    profile = _make_profile_with_raw(db, other.id, {"rs7946": "AA"})
    res = client.get(
        f"/api/v1/genetic/profiles/{profile.id}/raw-lookup",
        params={"rsid": "rs7946"}, headers=headers,
    )
    assert res.status_code == 404


def test_delete_other_user_404(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    other = _make_user(db)
    profile = _make_profile_with_raw(db, other.id, {"rs7946": "AA"})
    res = client.delete(f"/api/v1/genetic/profiles/{profile.id}/raw", headers=headers)
    assert res.status_code == 404


# ── 审计: lookup 后落一行 action=lookup ──

def test_lookup_writes_audit(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    profile = _make_profile_with_raw(db, user.id, {"rs7946": "AA"})
    res = client.get(
        f"/api/v1/genetic/profiles/{profile.id}/raw-lookup",
        params={"rsid": "rs7946"}, headers=headers,
    )
    assert res.status_code == 200, res.text
    rows = db.query(GeneticRawAudit).filter_by(
        user_id=user.id, profile_id=profile.id, action="lookup",
    ).all()
    assert len(rows) == 1
    assert rows[0].detail == {"rsid": "rs7946"}


# ── 软删 (被遗忘权) ──

def test_delete_then_lookup_404(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    profile = _make_profile_with_raw(db, user.id, {"rs7946": "AA"})

    res_del = client.delete(f"/api/v1/genetic/profiles/{profile.id}/raw", headers=headers)
    assert res_del.status_code == 200, res_del.text
    assert res_del.json()["deleted"] is True

    # deleted_at 已置, 行仍在但读路径过滤掉 → 无原始数据 → 400
    res_lk = client.get(
        f"/api/v1/genetic/profiles/{profile.id}/raw-lookup",
        params={"rsid": "rs7946"}, headers=headers,
    )
    assert res_lk.status_code == 400

    # 审计落了 delete 一行
    delete_rows = db.query(GeneticRawAudit).filter_by(
        user_id=user.id, profile_id=profile.id, action="delete",
    ).all()
    assert len(delete_rows) == 1

    # 物理行仍在 (软删, deleted_at 非空)
    rf = db.query(GeneticRawFile).filter_by(profile_id=profile.id).first()
    assert rf.deleted_at is not None


# ── upload → 落 GeneticRawFile (非 import_job blob) + UniqueConstraint 去重 ──

def test_upload_writes_raw_file_and_dedups(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    txt = (
        "# rsid\tchromosome\tposition\tgenotype\n"
        "rs1801133\t1\t200\tAG\n"
        "rs7946\t12\t100\tAA\n"
    )
    body = {
        "test_provider": "微基因",
        "test_date": "2025-01-01",
        "txt_content": txt,
        "retain_raw": True,
    }
    res = client.post("/api/v1/genetic/profiles/upload-txt", json=body, headers=headers)
    assert res.status_code == 200, res.text

    rows = db.query(GeneticRawFile).filter_by(user_id=user.id).all()
    assert len(rows) == 1
    # import_job.raw_genotypes 不再写 (弃用)
    from app.models.genetic_data import GeneticImportJob
    jobs = db.query(GeneticImportJob).filter_by(user_id=user.id).all()
    assert all(j.raw_genotypes is None for j in jobs)
    # upload 审计落了
    up_audit = db.query(GeneticRawAudit).filter_by(user_id=user.id, action="upload").all()
    assert len(up_audit) == 1

    # 同一份 txt 再传 → UniqueConstraint(user_id, raw_sha256) 去重, 不新增第二行
    res2 = client.post("/api/v1/genetic/profiles/upload-txt", json=body, headers=headers)
    assert res2.status_code == 200, res2.text
    rows2 = db.query(GeneticRawFile).filter_by(user_id=user.id, deleted_at=None).all()
    assert len(rows2) == 1


# ── RLS 行级隔离: 真 Postgres 集成测试 (无 PG 则 skip) ──
import os as _os
from sqlalchemy import create_engine as _create_engine, text as _sql_text

_PG_URL = _os.getenv("TEST_DATABASE_URL", "")


@pytest.mark.skipif(
    not _PG_URL.startswith("postgres"),
    reason="RLS 须真 Postgres; 设 TEST_DATABASE_URL=postgresql://...test... 启用",
)
def test_rls_row_isolation_postgres():
    """真 RLS 机制验证(生产 genetic_raw_files policy 用的同一模式 USING current_setting +
    ENABLE/FORCE):set app.user_id=A 只见 A 行;app.user_id 未设(NULL)→ 0 行 fail-closed。
    用独立探针表避免 FK/fixture 依赖,验证的是迁移里那套 RLS 语义本身。"""
    eng = _create_engine(_PG_URL)
    try:
        with eng.connect() as conn:
            # ⚠ superuser 绕过 RLS(含 FORCE)—— 以 superuser 连接此测试会「假绿/假红」,
            # 无法回归边界。明确 skip + 警告,而非给出误导性结果(测真 RLS 须用非 superuser 角色)。
            is_super = conn.execute(_sql_text("SELECT current_setting('is_superuser')")).scalar()
            if is_super == "on":
                pytest.skip(
                    "TEST_DATABASE_URL 连接角色是 superuser,会绕过 RLS,无法验证隔离;"
                    "请用非 superuser 角色(如生产的 health_user)跑此测试。")
            conn.execute(_sql_text("DROP TABLE IF EXISTS _rls_probe"))
            conn.execute(_sql_text(
                "CREATE TABLE _rls_probe (id serial PRIMARY KEY, user_id bigint NOT NULL, v text)"))
            conn.execute(_sql_text("ALTER TABLE _rls_probe ENABLE ROW LEVEL SECURITY"))
            conn.execute(_sql_text("ALTER TABLE _rls_probe FORCE ROW LEVEL SECURITY"))
            conn.execute(_sql_text(
                "CREATE POLICY p ON _rls_probe "
                "USING (user_id = current_setting('app.user_id', true)::bigint) "
                "WITH CHECK (user_id = current_setting('app.user_id', true)::bigint)"))
            conn.commit()
            for uid in (1, 2):  # 各以自身租户身份插入(FORCE RLS 的 WITH CHECK 要求匹配)
                conn.execute(_sql_text("SELECT set_config('app.user_id', :u, false)"), {"u": str(uid)})
                conn.execute(_sql_text("INSERT INTO _rls_probe (user_id, v) VALUES (:u, 'x')"), {"u": uid})
            conn.commit()
            # 租户 A 只见自己的行
            conn.execute(_sql_text("SELECT set_config('app.user_id', '1', false)"))
            assert conn.execute(_sql_text("SELECT user_id FROM _rls_probe")).scalars().all() == [1]
            # 漏设 app.user_id(NULL)→ 0 行(fail-closed,全拒而非泄漏)
            conn.execute(_sql_text("SELECT set_config('app.user_id', NULL, false)"))
            assert conn.execute(_sql_text("SELECT user_id FROM _rls_probe")).scalars().all() == []
            conn.execute(_sql_text("DROP TABLE IF EXISTS _rls_probe"))
            conn.commit()
    finally:
        eng.dispose()
