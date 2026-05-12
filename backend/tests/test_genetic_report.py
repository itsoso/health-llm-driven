"""test_genetic_report —— G-W1 报告聚合 service + endpoint."""

import uuid
from unittest.mock import patch

from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.models.user import User
from app.services import genetic_report
from app.services.auth import auth_service


def _make_user(db, name="genetic_report_user"):
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
    token = auth_service.create_access_token({"sub": str(u.id)})
    return u, {"Authorization": f"Bearer {token}"}


def _make_profile(db, user_id, test_provider="WeGene"):
    from datetime import date as _d
    p = GeneticProfile(
        user_id=user_id,
        test_provider=test_provider,
        test_date=_d(2026, 1, 1),
        notes="测试",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _make_variant(db, profile, gene, variant_name, **kw):
    base = dict(
        user_id=profile.user_id,
        profile_id=profile.id,
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


# ── build_report ────────────────────────────────────────────────────────


def test_build_report_no_profile_returns_empty(db):
    user = _make_user(db)[0]
    r = genetic_report.build_report(db, user.id)
    assert r["profile"] is None
    assert r["items"] == []
    assert r["stats"]["hits"] == 0
    assert r["stats"]["miss"] == r["stats"]["total_known"]


def test_build_report_marks_hits_and_misses(db):
    user = _make_user(db, "hits_misses")[0]
    p = _make_profile(db, user.id)
    # 命中 MTHFR (KNOWN_SNPS 字典里有)
    _make_variant(
        db, p, gene="MTHFR", variant_name="C677T",
        genotype="CT", result_label="叶酸代谢轻度减弱", risk_level="medium",
    )
    r = genetic_report.build_report(db, user.id)
    assert r["stats"]["hits"] == 1
    assert r["stats"]["miss"] == r["stats"]["total_known"] - 1

    mthfr = next(it for it in r["items"] if it["gene"] == "MTHFR")
    assert mthfr["hit"] is True
    assert mthfr["genotype"] == "CT"
    assert mthfr["risk_level"] == "medium"

    # 未命中的应该有 hit=False, genotype=None
    apoe_or_other = next((it for it in r["items"] if not it["hit"]), None)
    assert apoe_or_other is not None
    assert apoe_or_other["genotype"] is None


def test_build_report_orders_hits_first_high_risk_top(db):
    user = _make_user(db, "ordering")[0]
    p = _make_profile(db, user.id)
    _make_variant(db, p, gene="MTHFR", variant_name="C677T", risk_level="medium")
    _make_variant(db, p, gene="ALDH2", variant_name="酒精代谢", risk_level="high")
    _make_variant(db, p, gene="VDR", variant_name="维生素D受体", risk_level="low")

    r = genetic_report.build_report(db, user.id)
    hit_items = [it for it in r["items"] if it["hit"]]
    # high 在最前
    assert hit_items[0]["risk_level"] == "high"
    # 命中的全部在未命中之前
    first_miss_idx = next(i for i, it in enumerate(r["items"]) if not it["hit"])
    last_hit_idx = max(i for i, it in enumerate(r["items"]) if it["hit"])
    assert last_hit_idx < first_miss_idx


def test_build_report_picks_profile_with_most_variants(db):
    user = _make_user(db, "multi_profile")[0]
    p1 = _make_profile(db, user.id, "微基因 (旧)")
    p2 = _make_profile(db, user.id, "WeGene 完整")
    # p2 有 2 条 variants, p1 有 1 条 → 选 p2
    _make_variant(db, p1, gene="MTHFR", variant_name="C677T")
    _make_variant(db, p2, gene="MTHFR", variant_name="C677T")
    _make_variant(db, p2, gene="ALDH2", variant_name="酒精代谢")

    r = genetic_report.build_report(db, user.id)
    assert r["profile"]["id"] == p2.id
    assert r["stats"]["hits"] == 2


# ── endpoint ────────────────────────────────────────────────────────────


def test_endpoint_no_data_returns_empty_shape(client, db):
    user, headers = _make_user(db, "endpoint_empty")
    resp = client.get("/api/v1/genetic/report/me?include_summary=false", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile"] is None
    assert body["items"] == []
    assert body["agent_summary"] is None


def test_endpoint_returns_full_shape_with_summary_skipped(client, db):
    user, headers = _make_user(db, "endpoint_full")
    p = _make_profile(db, user.id)
    _make_variant(db, p, gene="MTHFR", variant_name="C677T", risk_level="medium")
    resp = client.get(
        "/api/v1/genetic/report/me?include_summary=false", headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile"]["test_provider"] == "WeGene"
    assert body["stats"]["hits"] == 1
    assert body["stats"]["total_known"] == 52
    assert body["agent_summary"] is None  # skipped


def test_endpoint_returns_summary_when_requested(client, db):
    user, headers = _make_user(db, "endpoint_summary")
    p = _make_profile(db, user.id)
    _make_variant(db, p, gene="MTHFR", variant_name="C677T", risk_level="medium")

    with patch.object(genetic_report, "get_agent_summary", return_value="模拟总结"):
        resp = client.get("/api/v1/genetic/report/me", headers=headers)
    assert resp.json()["agent_summary"] == "模拟总结"


def test_endpoint_requires_auth(client):
    resp = client.get("/api/v1/genetic/report/me")
    assert resp.status_code in (401, 403)


# ── G-W3 Why 面板: related_cards 关联 ──────────────────────────────────


def test_related_cards_match_by_gene_alias(db):
    from app.models.action_card import ActionCard
    user = _make_user(db, "related_cards")[0]
    p = _make_profile(db, user.id)
    _make_variant(db, p, gene="FADS1", variant_name="Omega-3代谢", risk_level="medium")

    db.add(ActionCard(
        user_id=user.id,
        title="补 EPA + DHA",
        content="基于 FADS1 杂合, Omega-3 转化能力中等, 建议每日 EPA 1g + DHA 0.5g",
        card_type="recommendation",
        source_type="weekly_advisor",
        user_decision="accepted",
        outcome="improved",
        effect_size=0.12,
    ))
    db.add(ActionCard(
        user_id=user.id, title="多喝水", content="每天 2L",
        card_type="recommendation", source_type="weekly_advisor",
    ))
    db.commit()

    r = genetic_report.build_report(db, user.id)
    fads1 = next(it for it in r["items"] if it["gene"] == "FADS1")
    assert len(fads1["related_cards"]) == 1
    assert fads1["related_cards"][0]["title"] == "补 EPA + DHA"
    assert fads1["related_cards"][0]["outcome"] == "improved"
    assert fads1["related_cards"][0]["effect_size"] == 0.12


def test_related_cards_limit_3(db):
    from app.models.action_card import ActionCard
    user = _make_user(db, "limit_3")[0]
    p = _make_profile(db, user.id)
    _make_variant(db, p, gene="MTHFR", variant_name="C677T", risk_level="medium")
    for i in range(5):
        db.add(ActionCard(
            user_id=user.id,
            title=f"MTHFR 建议 {i}",
            content="叶酸代谢相关",
            card_type="recommendation", source_type="weekly_advisor",
        ))
    db.commit()
    r = genetic_report.build_report(db, user.id)
    mthfr = next(it for it in r["items"] if it["gene"] == "MTHFR")
    assert len(mthfr["related_cards"]) == 3


def test_miss_items_have_empty_related_cards(db):
    from app.models.action_card import ActionCard
    user = _make_user(db, "miss_no_relate")[0]
    p = _make_profile(db, user.id)
    db.add(ActionCard(
        user_id=user.id, title="ALDH2 警告", content="酒精代谢",
        card_type="alert", source_type="safety_alert",
    ))
    db.commit()
    r = genetic_report.build_report(db, user.id)
    aldh2 = next(it for it in r["items"] if it["gene"] == "ALDH2")
    assert aldh2["hit"] is False
    assert aldh2["related_cards"] == []
