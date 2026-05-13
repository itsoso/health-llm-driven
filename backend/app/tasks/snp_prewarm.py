"""snp_prewarm —— SNP 详情 LLM 缓存预热 (A 优化, 2026-05-13).

问题: 用户首次点 /snp/{rsid} 详情页 LLM 调用 ~15 秒, 体感慢.
方案: daily 02:30 给活跃用户的 top 10 高/中风险命中 SNP 提前调一次 LLM 写入
Redis 24h 缓存 (key 含 user_id + rsid + genotype). 用户次日点开 ~50ms.

只跑活跃用户 (近 7 天有 GarminData 或 ActionCard 决策) 避免全量 LLM 浪费.
"""

import logging
from datetime import datetime, timedelta, timezone

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.action_card import ActionCard
from app.models.daily_health import GarminData
from app.models.genetic_data import GeneticVariant

logger = logging.getLogger(__name__)

PREWARM_TOP_N = 10  # 每用户预热前 N 个 SNP


def _active_user_ids(db, since) -> list:
    """近 7 天有 ActionCard 决策 OR Garmin 同步 = 活跃 (避免给僵尸用户调 LLM)."""
    a = {r[0] for r in db.query(ActionCard.user_id).filter(
        ActionCard.created_at >= since
    ).distinct().all()}
    g = {r[0] for r in db.query(GarminData.user_id).filter(
        GarminData.record_date >= since.date()
    ).distinct().all()}
    return sorted(a | g)


@celery_app.task
def prewarm_snp_details_for_active_users():
    """daily 02:30 北京. Celery beat 入口."""
    return _impl()


def _impl(force_user_ids: list = None):
    """force_user_ids 给单测/手动触发用."""
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        users = force_user_ids or _active_user_ids(db, cutoff)
        if not users:
            logger.info("[snp_prewarm] 0 个活跃用户, 跳过")
            return {"users": 0, "snps": 0}

        from app.api.genetic_data import KNOWN_SNPS
        from app.services.genetic_report import get_snp_detail, _resolve_active_profile

        # gene → rsid 反查 (KNOWN_SNPS 是 rsid → {gene, ...})
        gene_to_rsid: dict = {}
        for rsid, snp in KNOWN_SNPS.items():
            gene_to_rsid.setdefault(snp["gene"], rsid)

        total_snps = 0
        for uid in users:
            try:
                profile = _resolve_active_profile(db, uid)
                if not profile:
                    continue
                variants = (
                    db.query(GeneticVariant)
                    .filter(GeneticVariant.profile_id == profile.id)
                    .all()
                )
                if not variants:
                    continue
                # 按 risk_level 排序 high → medium → low → info
                risk_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
                variants.sort(key=lambda v: risk_order.get((v.risk_level or "info").lower(), 9))

                seen = 0
                for v in variants:
                    if seen >= PREWARM_TOP_N:
                        break
                    rsid = gene_to_rsid.get(v.gene_name)
                    if not rsid:
                        continue
                    try:
                        # get_snp_detail 内部已写 Redis 24h cache
                        get_snp_detail(db, uid, rsid)
                        seen += 1
                        total_snps += 1
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"[snp_prewarm] user={uid} rsid={rsid} 失败: {e}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[snp_prewarm] user={uid} 整体失败: {e}")

        logger.info(f"[snp_prewarm] 完成 — 用户 {len(users)} 个, SNP 预热 {total_snps} 次")
        return {"users": len(users), "snps": total_snps}
    finally:
        db.close()
