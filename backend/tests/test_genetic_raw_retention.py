"""基因原始全量保留 + 重解析 + 任意基因查询 (A+B 改动) 测试.

覆盖:
- _parse_raw_txt_genotypes: tab 解析 / 跳 '--'/'#' / 去重
- PEMT 在 KNOWN_SNPS 且 _known_variant_payload 产出 hedged label
- reparse: 已有 MTHFR variant, raw 含 rs7946, reparse 后新增 PEMT 且不重复 MTHFR
- raw-lookup: 按 rsid 取原始 genotype(含白名单外) / 按 gene=PEMT 取
- 属主校验: 别的 user 的 profile → 404
- EncryptedText round-trip
"""
import json
import uuid
from datetime import date

import pytest

from app.api.genetic_data import (
    KNOWN_SNPS,
    _GENE_RSIDS,
    _parse_raw_txt_genotypes,
    _known_variant_payload,
)
from app.models.genetic_data import GeneticProfile, GeneticImportJob, GeneticVariant
from app.models.genetic_raw import GeneticRawFile
from app.models.user import User
from app.services import tenant_crypto


# ── A: PEMT 白名单 + hedged 解读 ──

def test_pemt_in_whitelist():
    assert "rs7946" in KNOWN_SNPS
    assert "rs12325817" in KNOWN_SNPS
    assert KNOWN_SNPS["rs7946"]["gene"] == "PEMT"
    assert KNOWN_SNPS["rs12325817"]["gene"] == "PEMT"


def test_pemt_payload_is_hedged():
    payload = _known_variant_payload("rs7946", "AA", KNOWN_SNPS["rs7946"])
    assert payload is not None
    label = payload["result_label"]
    # hedged: 不能出现绝对/处方式断言, 必须有 可能/或/筛查级 之一
    assert any(w in label for w in ("可能", "或", "筛查级"))
    assert payload["risk_level"] in ("low", "info", "medium")
    # 筛查级别不应升到 high
    assert payload["risk_level"] != "high"


def test_pemt_promoter_payload_hedged():
    payload = _known_variant_payload("rs12325817", "CC", KNOWN_SNPS["rs12325817"])
    assert payload is not None
    assert any(w in payload["result_label"] for w in ("可能", "或", "筛查级"))


# ── B: _parse_raw_txt_genotypes ──

def test_parse_raw_txt_basic():
    txt = (
        "# rsid\tchromosome\tposition\tgenotype\n"
        "rs7946\t12\t100\tAA\n"
        "rs1801133\t1\t200\tAG\n"
    )
    raw, count, dup = _parse_raw_txt_genotypes(txt)
    assert raw == {"rs7946": "AA", "rs1801133": "AG"}
    assert count == 2
    assert dup == 0


def test_parse_raw_txt_skips_nocall_and_comments():
    txt = (
        "# header comment\n"
        "rs7946\t12\t100\t--\n"          # no-call skipped
        "\n"                               # blank skipped
        "rs1801133\t1\t200\tAG\n"
        "badline\t1\n"                     # <4 fields skipped
    )
    raw, count, dup = _parse_raw_txt_genotypes(txt)
    assert raw == {"rs1801133": "AG"}
    assert count == 1
    assert dup == 0


def test_parse_raw_txt_dedup():
    txt = (
        "rs7946\t12\t100\tAA\n"
        "rs7946\t12\t100\tGG\n"          # duplicate rsid -> kept first, counted dup
    )
    raw, count, dup = _parse_raw_txt_genotypes(txt)
    assert raw == {"rs7946": "AA"}
    assert count == 2
    assert dup == 1


# ── helpers ──

def _make_user(db) -> User:
    u = User(
        username=f"g_{uuid.uuid4().hex[:8]}",
        email=f"g_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="基因测试",
        is_active=True, is_approved=True,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _make_profile_with_raw(db, user_id: int, raw: dict) -> GeneticProfile:
    """建 profile + per-tenant 加密的 GeneticRawFile (新多租户表, 取代旧 blob)。"""
    import hashlib

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


# ── B: GeneticRawFile per-tenant round-trip ──

def test_raw_file_roundtrip(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    raw = {"rs7946": "AA", "rs9999999": "CT"}
    profile = _make_profile_with_raw(db, user.id, raw)
    db.expire_all()
    rf = db.query(GeneticRawFile).filter_by(profile_id=profile.id).first()
    # 库里只见密文, 用 user 的派生密钥解密还原
    assert rf.ciphertext != json.dumps(raw, ensure_ascii=False)
    assert json.loads(tenant_crypto.decrypt_for(user.id, rf.ciphertext)) == raw


# ── B: reparse ──

def test_reparse_adds_pemt_without_duplicating_mthfr(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    raw = {"rs1801133": "AG", "rs7946": "AA"}
    profile = _make_profile_with_raw(db, user.id, raw)
    # 预先只解析了 MTHFR (模拟 PEMT 加白名单之前导入的旧档案)
    db.add(GeneticVariant(
        user_id=user.id, profile_id=profile.id, rsid="rs1801133",
        category="nutrition", gene_name="MTHFR", genotype="CT",
    ))
    db.commit()

    res = client.post(f"/api/v1/genetic/profiles/{profile.id}/reparse", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    genes = {v["gene"] for v in body["newly_added"]}
    assert "PEMT" in genes
    assert "MTHFR" not in genes  # 已存在, skip 不重复

    # DB 里 MTHFR 仍只有一条
    mthfr = db.query(GeneticVariant).filter_by(profile_id=profile.id, gene_name="MTHFR").all()
    assert len(mthfr) == 1
    pemt = db.query(GeneticVariant).filter_by(profile_id=profile.id, gene_name="PEMT").all()
    assert len(pemt) == 1


def test_reparse_no_raw_returns_400(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    profile = GeneticProfile(user_id=user.id, test_provider="x", test_date=date(2025, 1, 1))
    db.add(profile); db.commit(); db.refresh(profile)
    res = client.post(f"/api/v1/genetic/profiles/{profile.id}/reparse", headers=headers)
    assert res.status_code == 400


def test_reparse_other_user_profile_404(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    other = _make_user(db)
    profile = _make_profile_with_raw(db, other.id, {"rs7946": "AA"})
    res = client.post(f"/api/v1/genetic/profiles/{profile.id}/reparse", headers=headers)
    assert res.status_code == 404


# ── B: raw-lookup ──

def test_raw_lookup_by_rsid_including_whitelist_absent(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    raw = {"rs7946": "AA", "rs9999999": "CT"}  # rs9999999 白名单外
    profile = _make_profile_with_raw(db, user.id, raw)

    res = client.get(f"/api/v1/genetic/profiles/{profile.id}/raw-lookup", params={"rsid": "rs9999999"}, headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["rsid"] == "rs9999999"
    assert body["genotype"] == "CT"
    assert body["in_whitelist"] is False

    res2 = client.get(f"/api/v1/genetic/profiles/{profile.id}/raw-lookup", params={"rsid": "rs7946"}, headers=headers)
    assert res2.json()["in_whitelist"] is True
    assert res2.json()["genotype"] == "AA"


def test_raw_lookup_by_gene_pemt(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    raw = {"rs7946": "AA", "rs12325817": "CG"}
    profile = _make_profile_with_raw(db, user.id, raw)
    res = client.get(f"/api/v1/genetic/profiles/{profile.id}/raw-lookup", params={"gene": "PEMT"}, headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["gene"] == "PEMT"
    got = {v["rsid"]: v["genotype"] for v in body["variants"]}
    assert got == {"rs7946": "AA", "rs12325817": "CG"}


def test_raw_lookup_unknown_gene_400(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    profile = _make_profile_with_raw(db, user.id, {"rs7946": "AA"})
    res = client.get(f"/api/v1/genetic/profiles/{profile.id}/raw-lookup", params={"gene": "NOTAGENE"}, headers=headers)
    assert res.status_code == 400


def test_raw_lookup_no_params_422(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    profile = _make_profile_with_raw(db, user.id, {"rs7946": "AA"})
    res = client.get(f"/api/v1/genetic/profiles/{profile.id}/raw-lookup", headers=headers)
    assert res.status_code == 422


def test_raw_lookup_other_user_404(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    other = _make_user(db)
    profile = _make_profile_with_raw(db, other.id, {"rs7946": "AA"})
    res = client.get(f"/api/v1/genetic/profiles/{profile.id}/raw-lookup", params={"rsid": "rs7946"}, headers=headers)
    assert res.status_code == 404


def test_gene_rsids_mapping_has_required_genes():
    for g in ("PEMT", "COMT", "MTHFR"):
        assert g in _GENE_RSIDS
    assert _GENE_RSIDS["PEMT"] == ["rs7946", "rs12325817"]


def test_encrypted_text_raises_on_encrypt_failure(monkeypatch):
    """最高隐私级:EncryptedText encrypt 失败必须 raise,绝不明文落库(安全评审 required)。"""
    from app.models import _encrypted

    class _BoomFernet:
        def encrypt(self, _b):
            raise RuntimeError("boom")

    monkeypatch.setattr(_encrypted, "_fernet", _BoomFernet())
    with pytest.raises(RuntimeError):
        _encrypted.EncryptedText().process_bind_param("sensitive-genotype", None)
