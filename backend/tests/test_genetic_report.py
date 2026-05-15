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


def test_build_report_picks_profile_with_most_known_hits(db):
    """优先选 KNOWN_SNPS 命中多的 profile, 不是 variants 总数最多的.

    bug 历史 (2026-05-12): user 3 的 PDF profile 有 605 variants 但 gene/result
    串字段, TXT profile 只 104 variants 但干净. 之前简单按总数排选了脏 PDF.
    """
    user = _make_user(db, "multi_profile")[0]
    p1 = _make_profile(db, user.id, "微基因 (旧)")
    p2 = _make_profile(db, user.id, "WeGene 完整")
    # p2 有 2 条字典命中, p1 只 1 条 → 选 p2
    _make_variant(db, p1, gene="MTHFR", variant_name="C677T")
    _make_variant(db, p2, gene="MTHFR", variant_name="C677T")
    _make_variant(db, p2, gene="ALDH2", variant_name="酒精代谢")

    r = genetic_report.build_report(db, user.id)
    assert r["profile"]["id"] == p2.id
    assert r["stats"]["hits"] == 2


def test_build_report_prefers_clean_txt_over_dirty_pdf(db):
    """profile_5 风格: variants 多但字段串错, 应该选 profile_4 风格干净小集合."""
    user = _make_user(db, "clean_vs_dirty")[0]
    clean = _make_profile(db, user.id, "WeGene TXT")
    dirty = _make_profile(db, user.id, "PDF 脏数据")

    # 干净的 — 3 条字典命中
    _make_variant(db, clean, gene="MTHFR", variant_name="C677T", risk_level="medium")
    _make_variant(db, clean, gene="ALDH2", variant_name="酒精代谢", risk_level="medium")
    _make_variant(db, clean, gene="VDR", variant_name="维生素D受体", risk_level="low")

    # 脏的 — 100 条 variants, 但 gene_name 不在字典里 (模拟 PDF 解析串字段)
    for i in range(100):
        _make_variant(
            db, dirty,
            gene=f"BOGUS_GENE_{i}",
            variant_name=f"RS{1000000 + i}",
            risk_level="low",
        )

    r = genetic_report.build_report(db, user.id)
    assert r["profile"]["id"] == clean.id
    assert r["stats"]["hits"] == 3


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


# ── G-W4 clusters: 按 category 聚合 ──────────────────────────────────────


def test_clusters_present_in_response_shape(db):
    """空 profile 也要返回 clusters (全 hits=0), 让 mobile 头部不 undefined."""
    user = _make_user(db, "clusters_empty")[0]
    r = genetic_report.build_report(db, user.id)
    assert "clusters" in r
    assert isinstance(r["clusters"], list)
    # KNOWN_SNPS 至少覆盖 nutrition / exercise / drug_sensitivity
    cats = {cl["category"] for cl in r["clusters"]}
    assert "nutrition" in cats
    assert "exercise" in cats
    # 每个 cluster 含必要字段
    for cl in r["clusters"]:
        assert set(cl.keys()) >= {
            "category", "category_zh", "total", "hits",
            "high_count", "medium_count", "rsids",
        }


def test_clusters_aggregate_hits_per_category(db):
    """两条 nutrition 命中 + 一条 exercise 命中 → nutrition.hits=2, exercise.hits=1."""
    user = _make_user(db, "clusters_agg")[0]
    p = _make_profile(db, user.id)
    _make_variant(db, p, gene="MTHFR", variant_name="C677T", risk_level="medium")
    _make_variant(db, p, gene="ALDH2", variant_name="酒精代谢", risk_level="high")
    _make_variant(db, p, gene="ACTN3", variant_name="R577X", risk_level="low")

    r = genetic_report.build_report(db, user.id)
    nutrition = next(cl for cl in r["clusters"] if cl["category"] == "nutrition")
    exercise = next(cl for cl in r["clusters"] if cl["category"] == "exercise")
    assert nutrition["hits"] == 2
    assert nutrition["high_count"] == 1  # ALDH2
    assert nutrition["medium_count"] == 1  # MTHFR
    assert exercise["hits"] == 1


def test_clusters_sorted_by_high_then_medium(db):
    """有 high 命中的 cluster 排前面."""
    user = _make_user(db, "clusters_sort")[0]
    p = _make_profile(db, user.id)
    # exercise: 1 high
    _make_variant(db, p, gene="ACTN3", variant_name="R577X", risk_level="high")
    # nutrition: 1 medium
    _make_variant(db, p, gene="MTHFR", variant_name="C677T", risk_level="medium")

    r = genetic_report.build_report(db, user.id)
    # 第一个应该是有 high 的 exercise
    assert r["clusters"][0]["category"] == "exercise"
    assert r["clusters"][0]["high_count"] == 1


# ── G-W4 单 SNP 详情 ─────────────────────────────────────────────────────


def test_get_snp_detail_unknown_rsid_returns_none(db):
    user = _make_user(db, "snp_unknown")[0]
    assert genetic_report.get_snp_detail(db, user.id, "rs99999999") is None


def test_get_snp_detail_user_not_hit_returns_static(db):
    """用户没测过该 SNP — 返回静态 + user.hit=False, actions 可能 None."""
    user = _make_user(db, "snp_no_hit")[0]
    # 不创建 profile/variant
    with patch.object(genetic_report, "_build_snp_detail_prompt") as mock_prompt:
        # 用户未命中, prompt 不应该走到 (LLM 不会被调) — 但当前实现仍会调 LLM
        # 为防 LLM 出错影响测试, 直接 mock provider 返回 None
        with patch("app.services.llm.get_llm_provider") as mock_llm:
            mock_llm.side_effect = Exception("test: skip LLM")
            d = genetic_report.get_snp_detail(db, user.id, "rs1801133")
    assert d is not None
    assert d["rsid"] == "rs1801133"
    assert d["gene"] == "MTHFR"
    assert d["user"]["hit"] is False
    assert d["user"]["genotype"] is None
    # LLM 失败 → actions 仍可能为 None, 但静态信息必须有
    assert d["actions"] is None or isinstance(d["actions"], dict)


def test_get_snp_detail_user_hit_llm_failure_falls_back_to_static(db):
    """用户命中 + LLM 抛异常 → actions=None, 但 user/static block 完整."""
    user = _make_user(db, "snp_llm_fail")[0]
    p = _make_profile(db, user.id)
    _make_variant(
        db, p, gene="MTHFR", variant_name="C677T",
        genotype="CT", result_label="叶酸代谢轻度减弱", risk_level="medium",
    )
    with patch("app.services.llm.get_llm_provider") as mock_llm:
        mock_llm.side_effect = RuntimeError("LLM down")
        d = genetic_report.get_snp_detail(db, user.id, "rs1801133")
    assert d is not None
    assert d["user"]["hit"] is True
    assert d["user"]["genotype"] == "CT"
    assert d["actions"] is None


def test_get_snp_detail_uses_same_variant_match_as_report(db):
    """详情页必须和列表页使用同一个 SNP 命中, 避免列表高风险详情低风险."""
    user = _make_user(db, "snp_match_consistency")[0]
    p = _make_profile(db, user.id)
    _make_variant(
        db, p, gene="CYP2D6", variant_name="其他药物代谢",
        category="drug_sensitivity", genotype="DD", result_label="正常代谢", risk_level="low",
    )
    _make_variant(
        db, p, gene="CYP2D6", variant_name="止痛药代谢",
        category="drug_sensitivity", genotype="II", result_label="慢代谢(需调整剂量)", risk_level="high",
    )

    report = genetic_report.build_report(db, user.id)
    cyp2d6 = next(it for it in report["items"] if it["rsid"] == "rs5030655")

    with patch("app.services.llm.get_llm_provider") as mock_llm:
        mock_llm.side_effect = RuntimeError("skip llm")
        detail = genetic_report.get_snp_detail(db, user.id, "rs5030655")

    assert cyp2d6["risk_level"] == "high"
    assert detail is not None
    assert detail["user"]["hit"] is True
    assert detail["user"]["risk_level"] == cyp2d6["risk_level"]
    assert detail["user"]["genotype"] == cyp2d6["genotype"]


def test_get_snp_detail_returns_siblings_in_same_category(db):
    """siblings 不含本 rsid, 且都在同 category."""
    user = _make_user(db, "snp_sibs")[0]
    with patch("app.services.llm.get_llm_provider") as mock_llm:
        mock_llm.side_effect = Exception("skip")
        d = genetic_report.get_snp_detail(db, user.id, "rs1801133")  # MTHFR (nutrition)
    assert d is not None
    assert all(s["rsid"] != "rs1801133" for s in d["siblings"])
    # 至少有几个同 category 的 (nutrition 在 KNOWN_SNPS 里多于 1 条)
    assert len(d["siblings"]) >= 1


# ── G-W4 endpoint /snp/{rsid} ───────────────────────────────────────────


def test_snp_endpoint_unknown_rsid_returns_404(client, db):
    _, headers = _make_user(db, "snp_ep_unknown")
    resp = client.get("/api/v1/genetic/snp/rs99999999", headers=headers)
    assert resp.status_code == 404


def test_snp_endpoint_returns_full_shape(client, db):
    user, headers = _make_user(db, "snp_ep_full")
    p = _make_profile(db, user.id)
    _make_variant(
        db, p, gene="MTHFR", variant_name="C677T",
        genotype="CT", result_label="叶酸代谢轻度减弱", risk_level="medium",
    )
    with patch("app.services.llm.get_llm_provider") as mock_llm:
        mock_llm.side_effect = Exception("skip llm")
        resp = client.get("/api/v1/genetic/snp/rs1801133", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    # 静态 block
    assert body["rsid"] == "rs1801133"
    assert body["gene"] == "MTHFR"
    assert body["category"] == "nutrition"
    assert isinstance(body["genotype_meanings"], list)
    # 用户 block
    assert body["user"]["hit"] is True
    assert body["user"]["genotype"] == "CT"
    # actions 因 LLM stub 抛异常 → None
    assert body["actions"] is None
    # related_cards / siblings 字段存在 (空 list ok)
    assert "related_cards" in body
    assert isinstance(body["siblings"], list)


def test_snp_endpoint_requires_auth(client):
    resp = client.get("/api/v1/genetic/snp/rs1801133")
    assert resp.status_code in (401, 403)
