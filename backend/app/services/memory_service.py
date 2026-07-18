"""
Memory Service — 事实级记忆的写入/检索/lifecycle 管理.

核心 API:
- write_fact(...)            创建新事实, 自动检测重复 → reinforce 而非新建
- reinforce_fact(fact_id, source)  追加来源, 提升 confidence
- supersede_fact(old_id, new_id)   建立版本链 (旧 → 新)
- get_active_facts(user_id, **filters)  取该 user 当前 active facts
- decay_all_facts(user_id=None)    cron 用, 应用遗忘曲线
- detect_contradictions(user_id, new_fact)  写入前检测矛盾

外部调用方:
- orchestrator: 跑完后从 findings 抽 facts
- outcome_grader: 评分结果落地为 fact ('用户对干预 X 响应良好')
- medical_exam parser: 化验异常项 → fact
- soap_writer: SOAP entry 同时产出 facts (decompose semantic 抽出来)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models.memory_fact import MemoryFact

logger = logging.getLogger(__name__)


CAUSAL_EFFECT_PREDICATES = frozenset({
    "responds_to",
    "does_not_respond_to",
    "partially_responds_to",
})


def effective_memory_predicate(
    predicate: str,
    *,
    subject: str = "",
    object_value: str = "",
    tags: Optional[List[str]] = None,
) -> str:
    """Return the safe presentation predicate for a stored memory fact.

    Old rows may predate the clinician-confounding guard. Every presentation
    surface calls this helper, so those rows cannot re-enter prompts or user
    views as efficacy claims before the data migration is applied.
    """
    if predicate not in CAUSAL_EFFECT_PREDICATES:
        return predicate
    from app.services.personal_models.intervention_priors import gate_text_for_clinician

    context = " ".join([subject or "", object_value or "", *(tags or [])])
    return "observed_change" if gate_text_for_clinician(context) else predicate


def effective_memory_confidence(
    confidence: float,
    *,
    predicate: str,
    subject: str = "",
    object_value: str = "",
    tags: Optional[List[str]] = None,
) -> float:
    """Cap presentation confidence for a confounded historical effect claim."""
    safe_predicate = effective_memory_predicate(
        predicate, subject=subject, object_value=object_value, tags=tags,
    )
    return min(float(confidence), 0.4) if safe_predicate == "observed_change" and predicate in CAUSAL_EFFECT_PREDICATES else float(confidence)


# 标准 predicates — LLM extraction 应优先使用这些
STANDARD_PREDICATES = {
    # 度量值
    "is_value", "is_above", "is_below", "equals",
    # 因果
    "causes", "treats", "improves", "worsens", "triggers",
    # 关系
    "interacts_with", "contradicts", "depends_on", "supersedes",
    # 用户态
    "has_history", "takes_medication", "has_genotype",
    "responds_to", "does_not_respond_to", "partially_responds_to",
    "observed_change",
    # ActionCard outcome
    "intervention_succeeded", "intervention_failed",
}


# decay_rate 默认值 by predicate
PREDICATE_DECAY_DEFAULTS = {
    # 永不衰减 (硬性事实)
    "has_genotype": 0.0,
    "has_history": 0.0,
    # 慢衰减 (慢病诊断, 长期患者特征)
    "takes_medication": 0.005,  # 半年衰减一半
    "treats": 0.005,
    "responds_to": 0.01,
    # 中等衰减 (近期状态)
    "is_value": 0.03,
    "is_above": 0.03,
    "is_below": 0.03,
    "equals": 0.03,
    # 快衰减 (临时症状/触发)
    "triggers": 0.05,
    "worsens": 0.05,
    "improves": 0.05,
}


def _decay_for(predicate: str) -> float:
    return PREDICATE_DECAY_DEFAULTS.get(predicate, 0.02)


def _normalize_value(s: str) -> str:
    """规范化 object_value 用于重复检测."""
    return (s or "").strip().lower()


def write_fact(
    db: Session,
    *,
    user_id: int,
    tier: str,
    subject: str,
    predicate: str,
    object_value: str,
    object_unit: Optional[str] = None,
    confidence: float = 0.5,
    source: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    is_sensitive: bool = False,
    decay_rate: Optional[float] = None,
) -> Optional[MemoryFact]:
    """写入一条事实. 已存在同三元组 → reinforce 而非新建.

    返回 (新建或被 reinforce 的 fact). 出错返回 None.
    """
    if tier not in {"working", "episodic", "semantic", "procedural"}:
        logger.warning(f"[memory] 未知 tier: {tier}, 跳过写入")
        return None
    if not subject or not predicate or not object_value:
        return None

    try:
        # 1) 看是否已有同三元组的 active fact
        norm_obj = _normalize_value(object_value)
        existing = db.query(MemoryFact).filter(
            MemoryFact.user_id == user_id,
            MemoryFact.subject == subject,
            MemoryFact.predicate == predicate,
            MemoryFact.superseded_at.is_(None),
        ).all()
        match = next(
            (f for f in existing if _normalize_value(f.object_value) == norm_obj),
            None,
        )
        if match:
            return reinforce_fact(db, match.id, source=source)

        # 2) 新建
        fact = MemoryFact(
            user_id=user_id,
            tier=tier,
            subject=subject[:200],
            predicate=predicate[:80],
            object_value=str(object_value)[:1000],
            object_unit=(object_unit or None),
            confidence=max(0.0, min(1.0, confidence)),
            sources=[source] if source else [],
            last_reinforced_at=datetime.now(timezone.utc),
            reinforcement_count=1,
            decay_rate=decay_rate if decay_rate is not None else _decay_for(predicate),
            tags=tags or [],
            is_sensitive=is_sensitive,
        )
        db.add(fact)
        db.commit()
        db.refresh(fact)
        logger.info(f"[memory] 新事实 #{fact.id} {subject}.{predicate}={object_value} "
                   f"conf={confidence:.2f} tier={tier}")
        return fact
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[memory] write_fact 失败: {e}")
        return None


def reinforce_fact(
    db: Session,
    fact_id: int,
    source: Optional[Dict[str, Any]] = None,
    confidence_boost: float = 0.05,
) -> Optional[MemoryFact]:
    """追加来源 + 提升 confidence + 重置 last_reinforced_at."""
    try:
        fact = db.query(MemoryFact).filter(MemoryFact.id == fact_id).first()
        if not fact:
            return None
        if source:
            sources = list(fact.sources or [])
            sources.append({**source, "ingested_at": datetime.now(timezone.utc).isoformat()})
            fact.sources = sources
        fact.confidence = min(1.0, fact.confidence + confidence_boost)
        fact.last_reinforced_at = datetime.now(timezone.utc)
        fact.reinforcement_count = (fact.reinforcement_count or 0) + 1
        db.commit()
        db.refresh(fact)
        logger.info(f"[memory] reinforce #{fact_id} → conf={fact.confidence:.2f}, "
                   f"count={fact.reinforcement_count}")
        return fact
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[memory] reinforce_fact 失败: {e}")
        return None


def supersede_fact(
    db: Session, old_id: int, new_id: int,
) -> bool:
    """旧 fact 被新 fact 替代. 双向链接."""
    try:
        now = datetime.now(timezone.utc)
        old = db.query(MemoryFact).filter(MemoryFact.id == old_id).first()
        new = db.query(MemoryFact).filter(MemoryFact.id == new_id).first()
        if not old or not new:
            return False
        old.superseded_at = now
        old.superseded_by_id = new.id
        new.supersedes_id = old.id
        db.commit()
        logger.info(f"[memory] supersede: #{old_id} → #{new_id}")
        return True
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[memory] supersede 失败: {e}")
        return False


def dismiss_fact(db: Session, fact_id: int, reason: str = "user_dismissed") -> bool:
    """用户标记'这条不对' — 纯 soft-delete, 不挂 new_id.

    设置 superseded_at=now 就能从 get_active_facts / hybrid_retrieve 里消失,
    同时保留审计痕迹 (sources 里追加一条 dismissal 记录).
    """
    try:
        now = datetime.now(timezone.utc)
        fact = db.query(MemoryFact).filter(MemoryFact.id == fact_id).first()
        if not fact or fact.superseded_at is not None:
            return False
        fact.superseded_at = now
        # sources 追加 dismissal 记录 (不覆盖, 供后续 offline eval 学习 "AI 推错了什么")
        sources = list(fact.sources or [])
        sources.append({
            "type": "user_dismissal",
            "reason": reason,
            "at": now.isoformat(),
            "weight": 0.0,
        })
        fact.sources = sources
        db.commit()
        logger.info(f"[memory] dismiss: #{fact_id} reason={reason}")
        return True
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[memory] dismiss 失败: {e}")
        return False



def get_active_facts(
    db: Session,
    user_id: int,
    *,
    tier: Optional[str] = None,
    predicate: Optional[str] = None,
    subject_contains: Optional[str] = None,
    tag: Optional[str] = None,
    min_confidence: float = 0.0,
    limit: int = 100,
) -> List[MemoryFact]:
    """取该 user 的 active facts. 按 last_reinforced_at desc."""
    q = db.query(MemoryFact).filter(
        MemoryFact.user_id == user_id,
        MemoryFact.superseded_at.is_(None),
    )
    if tier:
        q = q.filter(MemoryFact.tier == tier)
    if predicate:
        q = q.filter(MemoryFact.predicate == predicate)
    if subject_contains:
        q = q.filter(MemoryFact.subject.ilike(f"%{subject_contains}%"))
    if tag:
        # JSONB contains: tags @> '["tag"]'
        q = q.filter(MemoryFact.tags.contains([tag]))
    if min_confidence > 0:
        q = q.filter(MemoryFact.confidence >= min_confidence)
    q = q.order_by(MemoryFact.last_reinforced_at.desc()).limit(limit)
    return q.all()


def decay_all_facts(
    db: Session,
    user_id: Optional[int] = None,
    confidence_floor: float = 0.05,
) -> Dict[str, int]:
    """cron 任务: 应用遗忘曲线. 低于 floor 的 fact 自动归档为 superseded.

    实际上 effective_confidence 是动态计算的, 但低 confidence 的 fact
    最好显式归档以减少检索时的 noise.
    """
    pruned = 0
    seen = 0
    try:
        q = db.query(MemoryFact).filter(MemoryFact.superseded_at.is_(None))
        if user_id:
            q = q.filter(MemoryFact.user_id == user_id)
        # 按批处理, 避免锁定整张表
        for fact in q.yield_per(500):
            seen += 1
            # 计算 raw decayed (绕开 effective_confidence 的 floor 保底)
            if fact.decay_rate <= 0:
                continue
            ref = fact.last_reinforced_at
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - ref).total_seconds() / 86400
            import math
            raw_decayed = fact.confidence * math.exp(-fact.decay_rate * days)
            # 没反复确认 + raw decayed 已低于 floor → 归档
            if raw_decayed < confidence_floor and (fact.reinforcement_count or 0) <= 1:
                fact.superseded_at = datetime.now(timezone.utc)
                pruned += 1
        db.commit()
        logger.info(f"[memory] decay 扫描 {seen} 条, 归档 {pruned}")
        return {"seen": seen, "pruned": pruned}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[memory] decay_all_facts 失败: {e}")
        return {"seen": seen, "pruned": pruned, "error": str(e)}


def detect_contradictions(
    db: Session,
    user_id: int,
    *,
    subject: str,
    predicate: str,
    object_value: str,
) -> List[MemoryFact]:
    """写入前检测矛盾.

    返回与新事实矛盾的现有 active facts. 由调用方决定是 supersede 还是
    并存 (e.g. 多次复查值都保留, 仅看 trend).
    """
    contradicting_predicates = {
        "is_above": {"is_below", "is_value"},
        "is_below": {"is_above", "is_value"},
        "is_value": {"is_above", "is_below"},
        "responds_to": {"does_not_respond_to"},
        "does_not_respond_to": {"responds_to"},
    }
    candidates = contradicting_predicates.get(predicate, set()) | {predicate}

    # 同 subject 但 predicate 矛盾 → contradiction
    rows = db.query(MemoryFact).filter(
        MemoryFact.user_id == user_id,
        MemoryFact.subject == subject,
        MemoryFact.predicate.in_(list(candidates)),
        MemoryFact.superseded_at.is_(None),
    ).all()
    return [
        r for r in rows
        if r.predicate != predicate or _normalize_value(r.object_value) != _normalize_value(object_value)
    ]


def render_facts_for_prompt(
    facts: List[MemoryFact], max_lines: int = 10,
) -> str:
    """格式化事实给 LLM prompt 注入. 按 effective_confidence 排序."""
    if not facts:
        return ""
    sorted_facts = sorted(
        facts,
        key=lambda f: effective_memory_confidence(
            f.effective_confidence,
            predicate=f.predicate,
            subject=f.subject,
            object_value=f.object_value,
            tags=f.tags or [],
        ),
        reverse=True,
    )[:max_lines]
    lines = ["## 个人知识 (来自历史观察, 按可信度排)"]
    for f in sorted_facts:
        conf = effective_memory_confidence(
            f.effective_confidence,
            predicate=f.predicate,
            subject=f.subject,
            object_value=f.object_value,
            tags=f.tags or [],
        )
        cflag = "🟢" if conf >= 0.7 else "🟡" if conf >= 0.4 else "⚪"
        unit = f" {f.object_unit}" if f.object_unit else ""
        n_src = len(f.sources or [])
        predicate = effective_memory_predicate(
            f.predicate, subject=f.subject, object_value=f.object_value, tags=f.tags or [],
        )
        lines.append(
            f"{cflag} {f.subject} **{predicate}** {f.object_value}{unit}  "
            f"(conf={conf:.2f}, sources={n_src})"
        )
    return "\n".join(lines)
