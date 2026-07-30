"""test_genetic_report_evidence_refs —— per-gene system-KB evidence on build_report items."""

import uuid
from pathlib import Path

from sqlalchemy import event

from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.models.system_knowledge import KBDocument, KBEdge
from app.models.user import User
from app.services import genetic_report
from app.services.auth import auth_service
from app.services.genetic_registry import KNOWN_SNPS
from app.services.system_knowledge_importer import import_system_kb_artifacts


def _make_user(db, name="evref_user"):
    u = User(
        username=f"{name}_{uuid.uuid4().hex[:8]}",
        email=f"{name}_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name=name,
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    auth_service.create_access_token({"sub": str(u.id)})
    return u


def _make_profile(db, user_id):
    from datetime import date as _d
    p = GeneticProfile(
        user_id=user_id,
        test_provider="WeGene",
        test_date=_d(2026, 1, 1),
        notes="evref test",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _make_variant(db, profile, gene, variant_name, rsid, **kw):
    base = dict(
        user_id=profile.user_id,
        profile_id=profile.id,
        rsid=rsid,
        gene_name=gene,
        variant_name=variant_name,
        category=kw.get("category", "nutrition"),
        genotype=kw.get("genotype", "AA"),
        result_label=kw.get("result_label", "正常"),
        risk_level=kw.get("risk_level", "low"),
        variant_nature=kw.get("variant_nature", "neutral"),
    )
    base.update({k: v for k, v in kw.items() if k not in base})
    v = GeneticVariant(**base)
    db.add(v)
    db.commit()
    return v


def _seed_entity(db, gene_symbol):
    doc_id = f"entity:gene/{gene_symbol}"
    d = KBDocument(
        doc_id=doc_id,
        doc_type="entity",
        entity_type="gene",
        entity_id=gene_symbol,
        title=f"{gene_symbol} entity",
        summary=f"{gene_symbol} summary",
        confidence=1.0,
        evidence_level="A",
        metadata_json={"review_status": "reviewed"},
        is_archived=False,
    )
    db.add(d)
    return doc_id


def _seed_claim(db, claim_slug, confidence=0.8, evidence_level="B", archived=False):
    doc_id = f"claim:{claim_slug}"
    d = KBDocument(
        doc_id=doc_id,
        doc_type="claim",
        entity_type=None,
        entity_id=None,
        title=f"Claim {claim_slug}",
        summary=f"summary for {claim_slug}",
        body=f"body for {claim_slug}",
        confidence=confidence,
        evidence_level=evidence_level,
        metadata_json={"review_status": "reviewed"},
        is_archived=archived,
    )
    db.add(d)
    return doc_id


def _link(db, src, dst, relation="supports", confidence=0.9):
    e = KBEdge(
        src_doc_id=src,
        dst_doc_id=dst,
        relation=relation,
        confidence=confidence,
    )
    db.add(e)


def test_evidence_refs_per_gene_top_confidence(db):
    """MTHFR gene 关联 3 条 claim, 排序按 confidence desc, 取前 3."""
    user = _make_user(db, "mthfr_user")
    p = _make_profile(db, user.id)
    _make_variant(db, p, gene="MTHFR", variant_name="C677T", rsid="rs1801133", genotype="CT")

    g = _seed_entity(db, "MTHFR")
    c_low = _seed_claim(db, "nutrition/folate-low", confidence=0.5)
    c_high = _seed_claim(db, "nutrition/folate-high", confidence=0.95)
    c_mid = _seed_claim(db, "nutrition/folate-mid", confidence=0.7)
    _link(db, g, c_low)
    _link(db, g, c_high)
    _link(db, g, c_mid)
    db.commit()

    r = genetic_report.build_report(db, user.id)
    mthfr = next(it for it in r["items"] if it["gene"] == "MTHFR")
    assert mthfr["hit"] is True
    assert mthfr["evidence_refs"] == [c_high, c_mid, c_low]


def test_evidence_refs_caps_at_three(db):
    """4 条 claim → 取前 3."""
    user = _make_user(db, "cap_user")
    p = _make_profile(db, user.id)
    _make_variant(db, p, gene="APOE", variant_name="ε4 (rs429358)", rsid="rs429358", genotype="CC")

    g = _seed_entity(db, "APOE")
    ids = []
    for i, conf in enumerate([0.6, 0.9, 0.4, 0.75]):
        c = _seed_claim(db, f"lipid/apoe-{i}", confidence=conf)
        _link(db, g, c)
        ids.append((conf, c))
    db.commit()

    r = genetic_report.build_report(db, user.id)
    apoe = next(it for it in r["items"] if it["gene"] == "APOE")
    assert len(apoe["evidence_refs"]) == 3
    expected = [c for _, c in sorted(ids, key=lambda x: -x[0])][:3]
    assert apoe["evidence_refs"] == expected


def test_evidence_refs_empty_for_miss_and_unknown(db):
    """Miss 的 item evidence_refs 是 []; 命中但 KB 无 entity 的也是 []."""
    user = _make_user(db, "miss_user")
    p = _make_profile(db, user.id)
    # 命中 FTO 但 KB 没种 FTO entity
    _make_variant(db, p, gene="FTO", variant_name="肥胖倾向", rsid="rs9939609", genotype="AT")
    db.commit()

    r = genetic_report.build_report(db, user.id)
    fto = next(it for it in r["items"] if it["gene"] == "FTO")
    assert fto["hit"] is True
    assert fto["evidence_refs"] == []

    miss = next(it for it in r["items"] if not it["hit"])
    assert miss["evidence_refs"] == []


def test_evidence_refs_skips_archived_claims(db):
    """is_archived=True 的 claim 不进结果."""
    user = _make_user(db, "arch_user")
    p = _make_profile(db, user.id)
    _make_variant(db, p, gene="MTHFR", variant_name="C677T", rsid="rs1801133", genotype="CT")

    g = _seed_entity(db, "MTHFR")
    c_live = _seed_claim(db, "nutrition/folate-live", confidence=0.6)
    c_dead = _seed_claim(db, "nutrition/folate-dead", confidence=0.99, archived=True)
    _link(db, g, c_live)
    _link(db, g, c_dead)
    db.commit()

    r = genetic_report.build_report(db, user.id)
    mthfr = next(it for it in r["items"] if it["gene"] == "MTHFR")
    assert mthfr["evidence_refs"] == [c_live]


def test_evidence_refs_skips_runtime_only_claims(db):
    """通用基因报告不得绕过 runtime-only claim hold."""
    user = _make_user(db, "runtime_hold_user")
    p = _make_profile(db, user.id)
    _make_variant(db, p, gene="MTHFR", variant_name="C677T", rsid="rs1801133", genotype="CT")

    gene = _seed_entity(db, "MTHFR")
    visible = _seed_claim(db, "nutrition/folate-visible", confidence=0.6)
    held = _seed_claim(
        db,
        "c_low_back_emergency_neurologic_red_flags",
        confidence=0.99,
    )
    _link(db, gene, visible)
    _link(db, gene, held)
    db.commit()

    report = genetic_report.build_report(db, user.id)
    mthfr = next(item for item in report["items"] if item["gene"] == "MTHFR")

    assert mthfr["evidence_refs"] == [visible]


def test_evidence_refs_query_count_bounded(db):
    """N 个 hit gene → KB 部分只增 3 条 SQL (entity / edge / claim_conf), 与 N 无关."""
    user = _make_user(db, "qc_user")
    p = _make_profile(db, user.id)
    # 5 个 hit gene, 每个挂 2 条 claim. variant_name/rsid 对齐 KNOWN_SNPS
    snp_seeds = [
        ("MTHFR", "C677T", "rs1801133"),
        ("APOE", "ε4 (rs429358)", "rs429358"),
        ("FADS1", "Omega-3代谢", "rs174547"),
        ("VDR", "维生素D受体", "rs1544410"),
        ("FTO", "肥胖倾向", "rs9939609"),
    ]
    for gene, variant, rsid in snp_seeds:
        _make_variant(db, p, gene=gene, variant_name=variant, rsid=rsid, genotype="AT")
        g = _seed_entity(db, gene)
        for i in range(2):
            c = _seed_claim(db, f"{gene}/c-{i}", confidence=0.7 + i * 0.1)
            _link(db, g, c)
    db.commit()

    query_count = {"n": 0}

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        query_count["n"] += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _before_cursor_execute)
    try:
        r = genetic_report.build_report(db, user.id)
    finally:
        event.remove(engine, "before_cursor_execute", _before_cursor_execute)

    populated = [it for it in r["items"] if it.get("evidence_refs")]
    assert len(populated) == 5
    assert query_count["n"] <= 15, f"too many queries: {query_count['n']}"


def test_user3_reanalysis_high_medium_hits_have_seed_evidence_refs(db):
    """Current user 3 high/medium registry hits should be backed by seed KB refs."""
    user = _make_user(db, "user3_reanalysis")
    p = _make_profile(db, user.id)

    production_high_medium = {
        "rs10757274": ("AA", "high"),
        "rs380390": ("CC", "high"),
        "rs137853280": ("GG", "high"),
        "rs121908763": ("GG", "high"),
        "rs149790377": ("GG", "high"),
        "rs186045772": ("GG", "high"),
        "rs5030655": ("II", "high"),
        "rs1061235": ("AA", "high"),
        "rs1801133": ("AA", "high"),
        "rs541862": ("TT", "medium"),
        "rs1410996": ("AA", "medium"),
        "rs7454108": ("CT", "medium"),
        "rs660895": ("AG", "medium"),
        "rs1800795": ("GG", "medium"),
        "rs401681": ("CC", "medium"),
        "rs4244285": ("AG", "medium"),
        "rs4149056": ("CT", "medium"),
        "rs12722": ("CC", "medium"),
        "rs671": ("AG", "medium"),
        "rs4988235": ("GG", "medium"),
        "rs1801394": ("AA", "medium"),
        "rs4654748": ("TT", "medium"),
        "rs1050450": ("CC", "medium"),
    }

    for rsid, (genotype, expected_risk) in production_high_medium.items():
        snp = KNOWN_SNPS[rsid]
        result_label = snp["map"][genotype][1]
        _make_variant(
            db,
            p,
            gene=snp["gene"],
            variant_name=snp["variant"],
            rsid=rsid,
            category=snp["category"],
            genotype=genotype,
            result_label=result_label,
            risk_level=expected_risk,
            variant_nature="risk",
        )

    artifact_dir = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
    import_system_kb_artifacts(db, artifact_dir, actor="test:user3_reanalysis")

    report = genetic_report.build_report(db, user.id)
    missing = sorted(
        f"{it['rsid']}:{it['gene']}"
        for it in report["items"]
        if it.get("hit")
        and it.get("risk_level") in {"high", "medium"}
        and not it.get("evidence_refs")
    )

    assert missing == []
