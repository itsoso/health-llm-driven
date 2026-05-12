"""genetic_report —— Mobile 报告页数据源 (G-W1, 2026-05-12).

聚合:
  - GeneticProfile + GeneticVariant (实测命中)
  - KNOWN_SNPS 字典 (52 SNP 全集) - 命中 = 用户测过, 未命中 = 用户没测/数据缺失
  - LLM 生成顶部 "基因 Agent 对你说" 一段总结 (缓存 1h)

返回结构 (mobile 报告页直接渲染):
  {
    profile: {id, provider, test_date, total_known, hits, miss},
    agent_summary: "你的代谢偏向... → 优先做的事: ...",
    items: [
      {rsid, gene, variant_name, category, hit: bool,
       genotype?, result_label?, risk_level?, variant_nature?,
       description}
    ]
  }
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.genetic_data import GeneticProfile, GeneticVariant

logger = logging.getLogger(__name__)

# Risk 排序权重 — 报告页按 risk 优先, 同 risk 内按 category 字母序
_RISK_WEIGHT = {"high": 0, "medium": 1, "low": 2, "info": 3}


def _get_known_snps() -> Dict[str, Dict[str, Any]]:
    """惰性 import 避免循环依赖. KNOWN_SNPS 在 api/genetic_data.py."""
    from app.api.genetic_data import KNOWN_SNPS
    return KNOWN_SNPS


def _resolve_active_profile(db: Session, user_id: int) -> Optional[GeneticProfile]:
    """选用户的主报告 — 优先 variants 多的 (信息更全)."""
    profiles = (
        db.query(GeneticProfile)
        .filter(GeneticProfile.user_id == user_id)
        .all()
    )
    if not profiles:
        return None
    # 用 subquery 数 variants
    counts = {}
    for p in profiles:
        n = db.query(GeneticVariant).filter(GeneticVariant.profile_id == p.id).count()
        counts[p.id] = n
    profiles.sort(key=lambda p: (-counts[p.id], -p.id))
    return profiles[0]


def build_report(db: Session, user_id: int) -> Dict[str, Any]:
    """主入口: 返回报告页所需全部数据 (除 LLM 总结, 它独立 cache)."""
    profile = _resolve_active_profile(db, user_id)
    known = _get_known_snps()

    if profile is None:
        return {
            "profile": None,
            "items": [],
            "stats": {"total_known": len(known), "hits": 0, "miss": len(known)},
        }

    variants = (
        db.query(GeneticVariant)
        .filter(GeneticVariant.profile_id == profile.id)
        .all()
    )
    # 用户实测的 rsid 集合 (genetic_variants 没存 rsid, 但用 gene+variant 反查 KNOWN_SNPS)
    # 实际更可靠的反查: gene_name 在 KNOWN_SNPS 任一项里
    hit_by_gene_variant = {}
    for v in variants:
        key = (v.gene_name, v.variant_name or "")
        hit_by_gene_variant[key] = v

    items: List[Dict[str, Any]] = []
    hits = 0

    for rsid, snp in known.items():
        # 尝试匹配 (gene, variant) — variant_name 可能不完全一致, fallback 到 gene only
        v = None
        gene = snp["gene"]
        variant_label = snp["variant"]
        # 严格匹配
        v = hit_by_gene_variant.get((gene, variant_label))
        if v is None:
            # 宽松: 同 gene 的任一 variant
            for (g, _vn), gv in hit_by_gene_variant.items():
                if g == gene:
                    v = gv
                    break

        if v is not None:
            hits += 1
            items.append({
                "rsid": rsid,
                "gene": gene,
                "variant_name": variant_label,
                "category": snp["category"],
                "description": snp["desc"],
                "hit": True,
                "genotype": v.genotype,
                "result_label": v.result_label,
                "risk_level": v.risk_level or "info",
                "variant_nature": v.variant_nature or "neutral",
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
                "result_label": None,
                "risk_level": None,
                "variant_nature": None,
            })

    # 排序: 命中优先 (hit=True 先), 命中内按 risk 高→低, 未命中按 category 字母
    items.sort(key=lambda it: (
        0 if it["hit"] else 1,
        _RISK_WEIGHT.get(it.get("risk_level") or "info", 3),
        it["category"],
        it["gene"],
    ))

    return {
        "profile": {
            "id": profile.id,
            "test_provider": profile.test_provider,
            "test_date": profile.test_date.isoformat() if profile.test_date else None,
            "notes": profile.notes,
        },
        "items": items,
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
