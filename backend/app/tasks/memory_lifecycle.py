"""
Memory Lifecycle Cron — LLM Wiki v2 阶段 D.

每天 04:00 跑一次:
1. **Decay**: 应用遗忘曲线, 低 confidence 单次 fact 自动归档
2. **Crystallization**: 多次出现/被反复确认的 working facts 升级到 episodic/semantic
3. **Stale entity 标记**: 长期没 reinforced 的 entity is_active=false (软删)

设计理念 (Wiki v2):
- working memory 是临时观察, 短衰减
- 同一 working fact 反复出现 (reinforcement_count >= 3) → 升级到 episodic
- episodic fact 与多个其它 fact / entity 关联 (跨主题) → 升级到 semantic
- semantic fact 反复成功用于 specialist 决策 → 升级到 procedural

简化版 v0:
- working → episodic: reinforcement_count >= 3 OR confidence >= 0.7
- episodic → semantic: reinforcement_count >= 5 AND confidence >= 0.6
- procedural 由 outcome_grader 直接写 (绕过 working/episodic, 因为它本来就是验证后的)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import or_

from app.celery_app import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)


def _crystallize_loop(db) -> dict:
    """working → episodic → semantic 升级.

    返回 {working_to_episodic, episodic_to_semantic}.
    """
    from app.models.memory_fact import MemoryFact

    def is_clinician_review_fact(fact) -> bool:
        tags = fact.tags if isinstance(fact.tags, list) else []
        return "clinician_review" in tags

    w2e = 0
    e2s = 0

    # working → episodic: 反复 (count >= 3) OR confidence 高 (>= 0.7)
    rows = db.query(MemoryFact).filter(
        MemoryFact.tier == "working",
        MemoryFact.superseded_at.is_(None),
        or_(
            MemoryFact.reinforcement_count >= 3,
            MemoryFact.confidence >= 0.7,
        ),
    ).all()
    for f in rows:
        if is_clinician_review_fact(f):
            continue
        f.tier = "episodic"
        w2e += 1

    # episodic → semantic: 反复 + 中等以上 conf
    rows = db.query(MemoryFact).filter(
        MemoryFact.tier == "episodic",
        MemoryFact.superseded_at.is_(None),
        MemoryFact.reinforcement_count >= 5,
        MemoryFact.confidence >= 0.6,
    ).all()
    for f in rows:
        if is_clinician_review_fact(f):
            continue
        f.tier = "semantic"
        e2s += 1

    if w2e or e2s:
        db.commit()
    logger.info(f"[memory_lifecycle] crystallization: w→e={w2e}, e→s={e2s}")
    return {"working_to_episodic": w2e, "episodic_to_semantic": e2s}


def _stale_entity_loop(db, stale_days: int = 90) -> int:
    """长期没被 reinforced 的 entity → is_active=false (软删).

    判据: 最近 sources 时间戳 > stale_days 天前.
    """
    from app.models.health_kg import HealthEntity

    deactivated = 0
    cutoff = datetime.now(timezone.utc).timestamp() - stale_days * 86400

    rows = db.query(HealthEntity).filter(
        HealthEntity.is_active == True,  # noqa: E712
    ).all()
    for ent in rows:
        # 最新 source 时间戳
        last_source_ts = 0.0
        for src in (ent.sources or []):
            ts_str = src.get("added_at") or src.get("ingested_at")
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                last_source_ts = max(last_source_ts, ts.timestamp())
            except Exception:
                continue
        # 没 source 时间 → 用 created_at 兜底
        if last_source_ts == 0.0 and ent.created_at:
            ct = ent.created_at
            if ct.tzinfo is None:
                ct = ct.replace(tzinfo=timezone.utc)
            last_source_ts = ct.timestamp()

        if last_source_ts > 0 and last_source_ts < cutoff:
            ent.is_active = False
            deactivated += 1

    if deactivated:
        db.commit()
    logger.info(f"[memory_lifecycle] stale entities deactivated: {deactivated}")
    return deactivated


@celery_app.task(
    time_limit=600,
    name="app.tasks.memory_lifecycle.run_memory_lifecycle",
)
def run_memory_lifecycle():
    """每天 04:00 跑."""
    from app.services.memory_service import decay_all_facts

    with SessionLocal() as db:
        # 1. Decay: 低 conf singleton fact 自动归档
        decay_result = decay_all_facts(db, user_id=None)
        # 2. Crystallization
        cryst_result = _crystallize_loop(db)
        # 3. Stale entity 软删
        stale_count = _stale_entity_loop(db, stale_days=90)

    summary = {
        **decay_result,
        **cryst_result,
        "stale_entities_deactivated": stale_count,
    }
    logger.info(f"[memory_lifecycle] 完成: {summary}")
    return summary
