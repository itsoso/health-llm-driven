"""genetic_report —— Mobile 报告页数据源 (G-W1, 2026-05-12).

聚合:
  - GeneticProfile + GeneticVariant (实测命中)
  - KNOWN_SNPS 字典 (52 SNP 全集) - 命中 = 用户测过, 未命中 = 用户没测/数据缺失
  - LLM 生成顶部 "基因 Agent 对你说" 一段总结 (缓存 1h)
  - G-W3 (2026-05-12): 每个命中 item 关联 active action_cards (按 gene_name 模糊
    匹配 content/title), 返回前 3 条 + outcome chip 数据 → Mobile 端 Why 面板用

返回结构 (mobile 报告页直接渲染):
  {
    profile: {id, provider, test_date, total_known, hits, miss},
    agent_summary: "你的代谢偏向... → 优先做的事: ...",
    items: [
      {rsid, gene, variant_name, category, hit: bool,
       genotype?, result_label?, risk_level?, variant_nature?,
       description,
       related_cards: [  # G-W3
         {id, title, status, user_decision, outcome, effect_size,
          accuracy_score, completed_at, graded_at}
       ]}
    ]
  }
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.action_card import ActionCard
from app.models.system_knowledge import KBDocument, KBEdge
from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.services.genetic_risk import clinical_status, effective_risk_level
from app.services.outcome_safety import user_facing_efficacy_fields
from app.services.system_knowledge_service import generic_serving_document_filters

logger = logging.getLogger(__name__)

# Risk 排序权重 — 报告页按 risk 优先, 同 risk 内按 category 字母序
_RISK_WEIGHT = {"high": 0, "medium": 1, "low": 2, "info": 3}

# 每个 SNP 关联建议数量上限 (避免长卡膨胀)
_RELATED_CARDS_LIMIT = 3

# G-W4 cluster 头部用的 category 中文名
_CATEGORY_ZH = {
    "nutrition": "营养代谢",
    "exercise": "运动天赋",
    "drug_sensitivity": "药物敏感",
    "disease_risk": "疾病风险",
    "sleep": "睡眠节律",
    "recovery": "恢复能力",
    "cognition": "认知功能",
    "personality": "人格特质",
    "height_trait": "身高倾向",
    "education_trait": "教育相关",
}


def _empty_clusters(known: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """无 profile 时也返回完整 cluster 列表 (hits=0), 让 mobile 头部不闪."""
    cluster_map: Dict[str, Dict[str, Any]] = {}
    for snp in known.values():
        cat = snp["category"]
        cl = cluster_map.setdefault(cat, {
            "category": cat,
            "category_zh": _CATEGORY_ZH.get(cat, cat),
            "total": 0,
            "hits": 0,
            "high_count": 0,
            "medium_count": 0,
            "rsids": [],
        })
        cl["total"] += 1
    return sorted(cluster_map.values(), key=lambda c: -c["total"])


def _get_known_snps() -> Dict[str, Dict[str, Any]]:
    """Return the versioned SNP registry used by import/report surfaces."""
    from app.services.genetic_registry import KNOWN_SNPS
    return KNOWN_SNPS


def _resolve_active_profile(db: Session, user_id: int) -> Optional[GeneticProfile]:
    """选用户的主报告 — 优先 KNOWN_SNPS 命中率高的 (避免 PDF 脏数据).

    bug 历史 (2026-05-12): 之前简单按 variants 总数排, 选到 PDF 解析的 605 条
    脏数据 profile (gene_name/result_label 串字段, 例 RS1801131 标成 MTHFR
    实际是 ACTN3). 改为按 "字典命中数" 排, TXT 解析的干净小集合反而胜出.

    perf (2026-05-20): 用户 3 有 6 profiles / 745 variants, 老版本每个 profile
    一次 .all() 拿全行做 Python score → 835ms. 改为单条批量 SQL 只拿评分要的
    3 列 (gene_name/variant_name/rsid), 单 profile 短路, 实测 → ~30ms.
    """
    profiles = (
        db.query(GeneticProfile)
        .filter(GeneticProfile.user_id == user_id)
        .all()
    )
    if not profiles:
        return None
    if len(profiles) == 1:
        return profiles[0]

    known = _get_known_snps()
    known_rsids = set(known.keys())
    known_genes = {snp["gene"] for snp in known.values()}
    known_gene_variant = {(snp["gene"], snp["variant"]) for snp in known.values()}

    profile_ids = [p.id for p in profiles]
    rows = (
        db.query(
            GeneticVariant.profile_id,
            GeneticVariant.gene_name,
            GeneticVariant.variant_name,
            GeneticVariant.rsid,
        )
        .filter(GeneticVariant.profile_id.in_(profile_ids))
        .all()
    )

    score_map: Dict[int, List[int]] = {pid: [0, 0] for pid in profile_ids}
    for r in rows:
        bucket = score_map[r.profile_id]
        if (r.rsid in known_rsids) or ((r.gene_name, r.variant_name or "") in known_gene_variant):
            bucket[0] += 1
        if r.gene_name in known_genes:
            bucket[1] += 1

    profiles.sort(key=lambda p: (score_map[p.id][0], score_map[p.id][1], p.id), reverse=True)
    return profiles[0]


def _fetch_related_cards(db: Session, user_id: int) -> List[ActionCard]:
    """G-W3: 拉用户活跃 + 已闭环的 action_cards (近 90 天), 用于按 gene 模糊关联.

    一次性拉, 之后每个 SNP 在 Python 侧 filter (避免 N+1 查询).
    """
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    return (
        db.query(ActionCard)
        .filter(
            ActionCard.user_id == user_id,
            ActionCard.created_at >= cutoff,
        )
        .order_by(desc(ActionCard.created_at))
        .limit(200)
        .all()
    )


def _gene_to_card_match_keys(gene: str, variant_name: str) -> List[str]:
    """生成模糊匹配的关键词列表 (基因符号 + 别名). 简化版, 避免误匹配过广."""
    keys = [gene]
    # 部分基因有中文别名
    aliases = {
        "MTHFR": ["MTHFR", "叶酸代谢", "5-MTHF"],
        "APOE": ["APOE", "脂代谢"],
        "FADS1": ["FADS1", "Omega-3", "EPA", "DHA"],
        "ALDH2": ["ALDH2", "酒精代谢", "饮酒"],
        "CYP2D6": ["CYP2D6", "药物代谢"],
        "VDR": ["VDR", "维生素D", "维D"],
        "LCT": ["LCT", "乳糖", "乳制品"],
        "ACTN3": ["ACTN3", "爆发力", "耐力"],
        "PPARGC1A": ["PPARGC1A", "有氧"],
        "TCF7L2": ["TCF7L2", "血糖", "胰岛素"],
        "HFE": ["HFE", "铁", "血色素"],
        "CYP1A2": ["CYP1A2", "咖啡因", "咖啡"],
        "COMT": ["COMT", "压力", "应激", "多巴胺"],
        "BDNF": ["BDNF", "情绪", "焦虑"],
        "CLOCK": ["CLOCK", "生物钟", "睡眠节律"],
    }
    return aliases.get(gene, keys)


def _card_matches_gene(card: ActionCard, keys: List[str]) -> bool:
    """卡片 content/title 是否含任一 key."""
    haystack = (card.title or "") + " " + (card.content or "")
    return any(k in haystack for k in keys)


def _card_to_dict(card: ActionCard) -> Dict[str, Any]:
    """精简 card 序列化, 只取 Mobile Why 面板需要的字段."""
    efficacy_fields = user_facing_efficacy_fields(card)
    return {
        "id": card.id,
        "title": card.title,
        "status": card.status,
        "user_decision": card.user_decision,
        **efficacy_fields,
        "metric_key": card.metric_key,
        "baseline_value": card.baseline_value,
        "actual_value": card.actual_value,
        "evidence_level": card.evidence_level,
        "created_at": card.created_at.isoformat() if card.created_at else None,
        "completed_at": card.completed_at.isoformat() if card.completed_at else None,
        "graded_at": card.graded_at.isoformat() if card.graded_at else None,
    }


def _match_variant_for_snp(
    variants: List[GeneticVariant],
    snp: Dict[str, Any],
) -> Optional[GeneticVariant]:
    """按 KNOWN_SNPS 条目匹配用户实测 variant.

    新导入数据先用 rsid 精确匹配; 老数据只兼容 (gene, variant) 完全匹配。
    不再退回同 gene, 因为 MTHFR/APOE/CYP 等同一基因可能有多个位点, 同 gene
    fallback 会造成列表和详情错配。
    """
    known = _get_known_snps()
    expected_rsid = None
    for candidate_rsid, candidate in known.items():
        if candidate is snp or (
            candidate["gene"] == snp["gene"]
            and candidate["variant"] == snp["variant"]
            and candidate["category"] == snp["category"]
        ):
            expected_rsid = candidate_rsid
            break

    gene = snp["gene"]
    variant_label = snp["variant"]
    rsid_exact: Optional[GeneticVariant] = None
    exact: Optional[GeneticVariant] = None

    for v in variants:
        if expected_rsid and getattr(v, "rsid", None) == expected_rsid:
            rsid_exact = v
            continue
        if v.gene_name != gene:
            continue
        if (v.variant_name or "") == variant_label:
            exact = v

    return rsid_exact or exact


_EVIDENCE_REFS_LIMIT = 3


def _attach_evidence_refs(db: Session, items: List[Dict[str, Any]]) -> None:
    """每个 hit item 加 evidence_refs: List[claim_doc_id], 按 confidence desc, 取前 3.

    数据通路: entity:gene/{symbol} —[supports|evidence_for|...]→ claim:*.
    成本: 3 条 batch SQL, 与 items 数 N 无关.
    Miss item 跳过, evidence_refs 设空 list.
    """
    hit_genes = sorted({it["gene"] for it in items if it.get("hit")})
    if not hit_genes:
        for it in items:
            it["evidence_refs"] = []
        return

    entity_rows = (
        db.query(KBDocument.doc_id, KBDocument.entity_id)
        .filter(
            KBDocument.doc_type == "entity",
            KBDocument.entity_type == "gene",
            KBDocument.entity_id.in_(hit_genes),
            *generic_serving_document_filters(),
        )
        .all()
    )
    entity_doc_by_gene: Dict[str, str] = {r.entity_id: r.doc_id for r in entity_rows}
    if not entity_doc_by_gene:
        for it in items:
            it["evidence_refs"] = []
        return

    gene_by_entity_doc: Dict[str, str] = {v: k for k, v in entity_doc_by_gene.items()}
    entity_doc_ids = list(entity_doc_by_gene.values())

    edges = (
        db.query(KBEdge.src_doc_id, KBEdge.dst_doc_id)
        .filter(
            KBEdge.src_doc_id.in_(entity_doc_ids),
            KBEdge.dst_doc_id.like("claim:%"),
        )
        .all()
    )
    claim_ids = list({e.dst_doc_id for e in edges})
    if not claim_ids:
        for it in items:
            it["evidence_refs"] = []
        return

    claim_rows = (
        db.query(KBDocument.doc_id, KBDocument.confidence)
        .filter(
            KBDocument.doc_id.in_(claim_ids),
            KBDocument.doc_type == "claim",
            *generic_serving_document_filters(),
        )
        .all()
    )
    confidence_by_claim: Dict[str, float] = {
        r.doc_id: (r.confidence if r.confidence is not None else 0.0) for r in claim_rows
    }

    gene_to_claims: Dict[str, List[str]] = {}
    for e in edges:
        gene = gene_by_entity_doc.get(e.src_doc_id)
        if not gene or e.dst_doc_id not in confidence_by_claim:
            continue
        gene_to_claims.setdefault(gene, []).append(e.dst_doc_id)
    for gene, ids in gene_to_claims.items():
        ids.sort(key=lambda i: confidence_by_claim.get(i, 0.0), reverse=True)
        gene_to_claims[gene] = ids[:_EVIDENCE_REFS_LIMIT]

    for it in items:
        if it.get("hit"):
            it["evidence_refs"] = gene_to_claims.get(it["gene"], [])
        else:
            it["evidence_refs"] = []


def build_report(db: Session, user_id: int) -> Dict[str, Any]:
    """主入口: 返回报告页所需全部数据 (除 LLM 总结, 它独立 cache)."""
    profile = _resolve_active_profile(db, user_id)
    known = _get_known_snps()

    if profile is None:
        return {
            "profile": None,
            "items": [],
            "clusters": _empty_clusters(known),
            "stats": {"total_known": len(known), "hits": 0, "miss": len(known)},
        }

    variants = (
        db.query(GeneticVariant)
        .filter(GeneticVariant.profile_id == profile.id)
        .all()
    )

    # G-W3: 一次性拉 user 近 90 天卡, Python filter 模糊匹配
    user_cards = _fetch_related_cards(db, user_id)

    items: List[Dict[str, Any]] = []
    hits = 0

    for rsid, snp in known.items():
        gene = snp["gene"]
        variant_label = snp["variant"]
        v = _match_variant_for_snp(variants, snp)

        if v is not None:
            hits += 1
            raw_risk = v.risk_level or "info"
            risk_level = effective_risk_level(
                raw_risk,
                v.category,
                getattr(v, "evidence_level", None),
                v.health_implications,
            )
            # G-W3: 关联建议
            keys = _gene_to_card_match_keys(gene, variant_label)
            related = [c for c in user_cards if _card_matches_gene(c, keys)][:_RELATED_CARDS_LIMIT]
            items.append({
                "rsid": rsid,
                "gene": gene,
                "variant_name": variant_label,
                "category": snp["category"],
                "description": snp["desc"],
                "hit": True,
                "genotype": v.genotype,
                "raw_genotype": getattr(v, "raw_genotype", None),
                "result_label": v.result_label,
                "risk_level": risk_level,
                "raw_risk_level": raw_risk,
                "variant_nature": v.variant_nature or "neutral",
                "mapping_source": getattr(v, "mapping_source", None),
                "evidence_level": getattr(v, "evidence_level", None),
                "clinical_status": clinical_status(
                    v.category,
                    getattr(v, "evidence_level", None),
                    v.health_implications,
                ),
                "health_implications": v.health_implications,
                "related_cards": [_card_to_dict(c) for c in related],
            })
        else:
            items.append({
                "rsid": rsid,
                "gene": gene,
                "variant_name": variant_label,
                "category": snp["category"],
                "description": snp["desc"],
                "hit": False,
                "genotype": None,
                "raw_genotype": None,
                "result_label": None,
                "risk_level": None,
                "raw_risk_level": None,
                "variant_nature": None,
                "mapping_source": None,
                "evidence_level": None,
                "clinical_status": None,
                "health_implications": None,
                "related_cards": [],
            })

    items.sort(key=lambda it: (
        0 if it["hit"] else 1,
        _RISK_WEIGHT.get(it.get("risk_level") or "info", 3),
        it["category"],
        it["gene"],
    ))

    _attach_evidence_refs(db, items)

    # G-W4 圆 (2026-05-12): cluster 聚合 — 按 category 分组, 每组 hits/total + top
    # risk_level. 让 mobile 头部一眼看到"叶酸/运动/药物/疾病" 各组占比.
    cluster_map: Dict[str, Dict[str, Any]] = {
        cat: {
            "category": cat,
            "category_zh": _CATEGORY_ZH.get(cat, cat),
            "total": 0,
            "hits": 0,
            "high_count": 0,
            "medium_count": 0,
            "rsids": [],
        }
        for cat in {snp["category"] for snp in known.values()}
    }
    for it in items:
        cat = it["category"]
        c = cluster_map.setdefault(cat, {
            "category": cat,
            "category_zh": _CATEGORY_ZH.get(cat, cat),
            "total": 0,
            "hits": 0,
            "high_count": 0,
            "medium_count": 0,
            "rsids": [],
        })
        c["total"] += 1
        if it["hit"]:
            c["hits"] += 1
            if it["risk_level"] == "high":
                c["high_count"] += 1
            elif it["risk_level"] == "medium":
                c["medium_count"] += 1
            c["rsids"].append(it["rsid"])
    clusters = sorted(
        cluster_map.values(),
        key=lambda c: (-c["high_count"], -c["medium_count"], -c["hits"]),
    )

    return {
        "profile": {
            "id": profile.id,
            "test_provider": profile.test_provider,
            "test_date": profile.test_date.isoformat() if profile.test_date else None,
            "notes": profile.notes,
        },
        "items": items,
        "clusters": clusters,
        "stats": {
            "total_known": len(known),
            "hits": hits,
            "miss": len(known) - hits,
        },
    }


# ── Agent Summary (LLM, 缓存 1h) ────────────────────────────────────────

_AGENT_SUMMARY_TTL_SECONDS = 3600


def _cache_key(user_id: int, profile_id: int) -> str:
    return f"genetic_report:agent_summary:v1:u{user_id}:p{profile_id}"


def _build_summary_prompt(items: List[Dict[str, Any]], stats: Dict[str, int]) -> str:
    """只挑命中的 high/medium risk + 关键基因, 让 LLM 写一段."""
    hit_items = [it for it in items if it["hit"]]
    notable = [
        it for it in hit_items
        if it.get("risk_level") in ("high", "medium")
        or it["gene"] in {"MTHFR", "APOE", "FADS1", "ALDH2", "CYP2D6", "SLCO1B1", "VDR", "LCT"}
    ][:12]

    lines = []
    for it in notable:
        lines.append(
            f"- {it['gene']} ({it['variant_name']}, {it['category']}): "
            f"{it['result_label']} [{it.get('risk_level','info')}]"
        )
    notable_block = "\n".join(lines) or "(用户实测命中数据少, 暂无显著解读)"

    return f"""你是用户的基因解读 Agent. 基于下面用户实测的关键基因位点, 用 4-6 句话总结:
1. 用户的代谢/恢复/疾病风险整体倾向 (1-2 句, 把多个相关 SNP 串起来讲, 不要逐条)
2. 立即可执行的 top-3 优先事项 (具体到补剂/饮食/运动/复查频率, 不写"多吃蔬菜"这种废话)
3. 不要列表, 不要 markdown, 自然口语, 像跟用户说话

总位点 {stats.get('total_known')} 个, 用户实测命中 {stats.get('hits')} 个, 关键命中:
{notable_block}

只返回这段总结文字, 不要解释."""


def get_agent_summary(db: Session, user_id: int) -> Optional[str]:
    """LLM 生成 Agent 总结. Redis 缓存 1h. 失败返 None (前端隐藏整段)."""
    profile = _resolve_active_profile(db, user_id)
    if profile is None:
        return None

    # Redis cache 命中
    try:
        from app.utils.redis_cache import RedisCache
        cached = RedisCache.get(_cache_key(user_id, profile.id))
        if cached:
            return cached.get("text") if isinstance(cached, dict) else str(cached)
    except Exception:
        pass

    # Cache miss → LLM
    try:
        report = build_report(db, user_id)
        prompt = _build_summary_prompt(report["items"], report["stats"])

        from app.services.llm import get_llm_provider
        provider = get_llm_provider()
        import asyncio

        async def _call():
            result = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=600,
            )
            return result if isinstance(result, str) else (result or {}).get("content", "")

        try:
            text = asyncio.run(_call())
        except RuntimeError:
            # Already in event loop (FastAPI sync route)
            import nest_asyncio
            nest_asyncio.apply()
            text = asyncio.get_event_loop().run_until_complete(_call())
        except Exception:
            text = None

        if not text or len(text) < 20:
            return None

        # 写缓存
        try:
            from app.utils.redis_cache import RedisCache
            RedisCache.set(
                _cache_key(user_id, profile.id),
                {"text": text, "generated_at": datetime.now(timezone.utc).isoformat()},
                ttl=_AGENT_SUMMARY_TTL_SECONDS,
            )
        except Exception:
            pass

        return text
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[genetic_report] agent summary 失败 user={user_id}: {e}")
        return None


# ── 单 SNP 详情 (LLM, 缓存 24h, key 包含 genotype) ─────────────────────

_SNP_DETAIL_TTL_SECONDS = 86400


def _snp_cache_key(user_id: int, rsid: str, genotype: Optional[str]) -> str:
    # v2 (2026-05-14): prompt 改造 - 详细可执行行动. v1 cache 自动失效.
    return f"genetic_snp_detail:v2:user={user_id}:rsid={rsid}:gt={genotype or 'none'}"


def _build_snp_detail_prompt(
    snp_static: Dict[str, Any],
    user_item: Dict[str, Any],
    user_context: Dict[str, Any],
) -> str:
    """生成 SNP 详情 LLM prompt. snp_static 是 KNOWN_SNPS 的条目, user_item
    是用户实测命中, user_context 含化验/在服补剂/慢病等差异化数据."""
    gene = snp_static["gene"]
    variant = snp_static["variant"]
    desc = snp_static["desc"]
    category = snp_static.get("category", "")

    if user_item.get("hit"):
        gt = user_item.get("genotype")
        label = user_item.get("result_label")
        risk = user_item.get("risk_level") or "info"
        user_part = f"用户实测: 基因型 {gt} → {label} (风险 {risk})"
    else:
        user_part = "用户未在该位点测出 (报告中无对应数据)"

    ctx_lines: List[str] = []
    labs = user_context.get("flagged_labs") or []
    if labs:
        ctx_lines.append(f"近期化验异常: {', '.join(labs[:5])}")
    sups = user_context.get("active_supplements") or []
    if sups:
        ctx_lines.append(f"在服补剂: {', '.join(sups[:6])}")
    chronic = user_context.get("active_conditions") or []
    if chronic:
        ctx_lines.append(f"慢病: {', '.join(chronic[:5])}")
    ctx_block = "\n".join(ctx_lines) or "(暂无化验/补剂/慢病数据)"

    boundary_lines = [
        "通用边界: 这是消费级基因筛查级解释, 不能替代诊断、治疗、处方或医生判断。",
        "所有建议必须写成可讨论/可复盘的生活方式或复查行动, 不得把基因结果写成确定命运。",
    ]
    if category == "drug_sensitivity":
        boundary_lines.extend([
            "药物边界: 不得建议停药、换药或调整剂量。",
            "drug_caution 只能写: 带着该基因结果、药名和既往反应去让医生或药师确认。",
        ])
    if category == "disease_risk":
        boundary_lines.extend([
            "疾病边界: 这是筛查级风险提示, 不是诊断。",
            "不得输出癌症、阿尔茨海默病、糖尿病等疾病的确定预测; 必须要求结合体检、家族史和症状。",
        ])
    if category in {"cognition", "personality"}:
        boundary_lines.extend([
            "认知/人格边界: 只能作为低置信度相关性解释, 不能预测个人能力、人格标签或教育结果。",
        ])
    if category == "height_trait":
        boundary_lines.extend([
            "身高边界: 只能作为探索性 marker 计数, 不能换算成厘米数或替代全量 PRS。",
        ])
    if category == "education_trait":
        boundary_lines.extend([
            "教育边界: 只能展示群体统计弱相关, 不能预测个人是否能上大学, 也不能用于能力评价或任何决策。",
        ])
    boundary_block = "\n".join(boundary_lines)

    return f"""你是基因解读 Agent. 用户在看 {gene} ({variant}) 这一个 SNP 的详情.
你必须给出**详细可执行**的行动, 不只是泛泛科普 — 这是 Agent 跟"基因解读网站"的差别.

【安全与科学边界】
{boundary_block}

【SNP 静态描述】
{desc}

【用户在该位点的命中】
{user_part}

【用户其它差异化数据】
{ctx_block}

输出严格按以下 JSON shape, 中文, 不要 markdown, 不要解释.

每条 action 要满足"详细可执行"标准:
- 写**具体**: 食材名 + 克数 + 频率/时段 (例: "三文鱼 150g/餐, 每周 3 次, 替代红肉")
- 写**为什么**: 1 短句解释机理 (例: "OMEGA-3 抗炎, 9p21 携带者血管炎症阈值低")
- **关联**用户已有数据时显式说明 (例: "你 LDL 4.1 偏高, 这条要从 14 天起每天做"); 没相关数据就不强加
- 给**复盘**: 行动结束后看哪个指标 (例: "30 天后复查 LDL 看是否 ≤3.6")
- **避免**已经在服补剂里的成分, 或已在 chat 中给过的方向

{{
  "headline": "1 句话给用户讲清这个 SNP 对他意味着什么 + 当前优先级 (≤40 字)",
  "nutrition_actions": [
    "饮食行动 1 (50-80字): 食材+克数/频率+机理+用户关联+复盘指标",
    "..."
  ],   // 0-3 条
  "supplement_actions": [
    "补剂行动 1 (50-80字): 成分+剂量+时段+机理+用户关联; 跟在服重复就跳过",
    "..."
  ],  // 0-3 条
  "exercise_actions": [
    "运动行动 1 (50-80字): 强度+频次+时长+跟 SNP 的关联",
    "..."
  ],    // 0-2 条, 不相关留空
  "lab_to_check": [
    "建议复查指标 1: 化验项名 + 频率 + 该 SNP 下的目标范围",
    "..."
  ],            // 0-3 条
  "drug_caution": ["药物注意 1", "..."],  // drug_sensitivity 类才给; 必须要求医生或药师确认
  "confidence": "high|medium|low"  // MTHFR/APOE/SLCO1B1 等强证据=high
}}

如果用户未命中 (报告中无该 SNP), 全部 action 留空, headline 写"未在你的报告中测到".
不要捏造用户没在数据中显示的化验/补剂.
不要捏造用户没在数据中显示的化验/补剂.
如果是药物相关基因, 具体可做的事是"整理药名/剂量/不良反应并找医生或药师确认", 不是自行改药。"""


def get_snp_detail(db: Session, user_id: int, rsid: str) -> Optional[Dict[str, Any]]:
    """单 SNP 详情. 静态信息 + 用户命中 + LLM 个性化建议 (cached 24h).

    返回 None 表示 rsid 不在 KNOWN_SNPS 字典中. 即使 LLM 失败, 也返回
    静态信息 + 命中, 让 mobile 能 fallback 渲染."""
    known = _get_known_snps()
    snp_static = known.get(rsid)
    if not snp_static:
        return None

    # 找用户命中
    profile = _resolve_active_profile(db, user_id)
    user_item: Dict[str, Any] = {
        "hit": False,
        "genotype": None,
        "raw_genotype": None,
        "result_label": None,
        "risk_level": None,
        "raw_risk_level": None,
        "mapping_source": None,
        "evidence_level": None,
        "clinical_status": None,
        "health_implications": None,
    }
    related_cards: List[Dict[str, Any]] = []
    if profile is not None:
        variants = (
            db.query(GeneticVariant)
            .filter(
                GeneticVariant.profile_id == profile.id,
            )
            .all()
        )
        v = _match_variant_for_snp(variants, snp_static)
        if v is not None:
            raw_risk = v.risk_level or "info"
            user_item = {
                "hit": True,
                "genotype": v.genotype,
                "raw_genotype": getattr(v, "raw_genotype", None),
                "result_label": v.result_label,
                "risk_level": effective_risk_level(
                    raw_risk,
                    v.category,
                    getattr(v, "evidence_level", None),
                    v.health_implications,
                ),
                "raw_risk_level": raw_risk,
                "mapping_source": getattr(v, "mapping_source", None),
                "evidence_level": getattr(v, "evidence_level", None),
                "clinical_status": clinical_status(
                    v.category,
                    getattr(v, "evidence_level", None),
                    v.health_implications,
                ),
                "health_implications": v.health_implications,
            }
            user_cards = _fetch_related_cards(db, user_id)
            keys = _gene_to_card_match_keys(snp_static["gene"], snp_static["variant"])
            related_cards = [
                _card_to_dict(c) for c in user_cards if _card_matches_gene(c, keys)
            ][:_RELATED_CARDS_LIMIT]

    static_block = {
        "rsid": rsid,
        "gene": snp_static["gene"],
        "variant_name": snp_static["variant"],
        "category": snp_static["category"],
        "description": snp_static["desc"],
        "genotype_meanings": [
            {"genotype": gt, "display": meaning[0], "label": meaning[1], "risk": meaning[2]}
            for gt, meaning in snp_static.get("map", {}).items()
        ],
    }

    # cluster siblings (同 category 其它 SNP, 已命中靠前)
    siblings: List[Dict[str, Any]] = []
    for r2, s2 in known.items():
        if r2 == rsid or s2["category"] != snp_static["category"]:
            continue
        siblings.append({
            "rsid": r2,
            "gene": s2["gene"],
            "variant_name": s2["variant"],
        })
    siblings = siblings[:8]

    # LLM 个性化建议 (cached)
    cache_key = _snp_cache_key(user_id, rsid, user_item.get("genotype"))
    actions: Optional[Dict[str, Any]] = None
    try:
        from app.utils.redis_cache import RedisCache
        cached = RedisCache.get(cache_key)
        if isinstance(cached, dict) and cached.get("actions"):
            actions = cached["actions"]
    except Exception:
        pass

    if actions is None:
        # 抓用户差异化上下文
        user_context: Dict[str, Any] = {}
        try:
            from app.twin import build_twin
            twin = build_twin(db, user_id)
            user_context["flagged_labs"] = [
                a.get("item_name") for a in (twin.labs.flagged_abnormal or [])
                if a.get("item_name")
            ][:8]
            user_context["active_supplements"] = [
                s.get("name") for s in (twin.supplement.active_supplements or [])
                if s.get("name")
            ][:8]
            user_context["active_conditions"] = list(twin.chronic.active_conditions or [])
        except Exception as e:
            logger.debug(f"[snp_detail] twin context 获取失败: {e}")

        prompt = _build_snp_detail_prompt(snp_static, user_item, user_context)
        try:
            from app.services.llm import get_llm_provider
            provider = get_llm_provider()
            import asyncio
            import json as _json

            async def _call():
                result = await provider.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=700,
                )
                return result if isinstance(result, str) else (result or {}).get("content", "")

            try:
                raw = asyncio.run(_call())
            except RuntimeError:
                import nest_asyncio
                nest_asyncio.apply()
                raw = asyncio.get_event_loop().run_until_complete(_call())

            if raw:
                # 提 JSON (LLM 偶尔加 ```json 包裹)
                t = raw.strip()
                if t.startswith("```"):
                    t = t.strip("`").lstrip("json").strip()
                actions = _json.loads(t)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[snp_detail] LLM 失败 user={user_id} rsid={rsid}: {e}")
            actions = None

        if actions:
            try:
                from app.utils.redis_cache import RedisCache
                RedisCache.set(cache_key, {"actions": actions}, ttl=_SNP_DETAIL_TTL_SECONDS)
            except Exception:
                pass

    return {
        **static_block,
        "user": user_item,
        "actions": actions,
        "related_cards": related_cards,
        "siblings": siblings,
    }
