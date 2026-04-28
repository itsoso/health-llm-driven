"""
Memory Extractor — 从现有事件源自动产出 MemoryFact.

旁路: orchestrator/outcome_grader/medical_exam_parser 跑完之后调用,
不发起额外 LLM 调用 (省成本), 主要靠确定性规则提取.

来源 → fact 映射:
1. specialist Finding raw → fact (e.g. {zone: "rest", score: 35} → '当前 readiness=rest')
2. ActionCard outcome (graded) → fact (干预成功/失败的 procedural memory)
3. clinical_journal entry → 部分字段抽出来作为 semantic fact
4. medical_exam item (异常) → fact ('LDL is_above 3.4')
5. user_directive → fact (硬性约束作为 high-confidence semantic)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[memory_extractor] 单步失败 (跳过): {e}")
        return None


def extract_from_specialist_finding(
    db: Session, user_id: int, finding, source_specialist: str,
) -> List[int]:
    """从 SpecialistFinding 抽 facts. 返回创建的 fact id 列表."""
    from app.services.memory_service import write_fact

    created: List[int] = []
    raw = finding.raw or {}
    fname = source_specialist
    src = {"type": "specialist_finding", "id": fname, "weight": 0.5}

    # Recovery: zone + score → fact
    if fname == "recovery_coach":
        zone = raw.get("zone")
        score = raw.get("score")
        if zone:
            f = _safe_call(
                write_fact, db,
                user_id=user_id, tier="working",
                subject="当前 readiness",
                predicate="equals",
                object_value=str(zone),
                confidence=0.7, source=src, tags=["recovery"],
                decay_rate=0.1,  # 状态级, 1-2 天就该衰减
            )
            if f: created.append(f.id)
        if score is not None:
            f = _safe_call(
                write_fact, db,
                user_id=user_id, tier="working",
                subject="readiness 分数",
                predicate="is_value",
                object_value=str(score), object_unit="分",
                confidence=0.7, source=src, tags=["recovery"],
                decay_rate=0.1,
            )
            if f: created.append(f.id)

    # Movement: ACWR → fact
    if fname == "movement_coach":
        acwr = raw.get("acwr")
        status = raw.get("status")
        if acwr is not None:
            f = _safe_call(
                write_fact, db,
                user_id=user_id, tier="working",
                subject="当前 ACWR",
                predicate="is_value",
                object_value=f"{acwr:.2f}",
                confidence=0.6, source=src, tags=["movement", "training_load"],
                decay_rate=0.07,
            )
            if f: created.append(f.id)
        if status:
            f = _safe_call(
                write_fact, db,
                user_id=user_id, tier="working",
                subject="训练负荷状态",
                predicate="equals",
                object_value=str(status),
                confidence=0.6, source=src, tags=["movement"],
                decay_rate=0.07,
            )
            if f: created.append(f.id)

    # Hypertension: stage → fact
    if fname == "hypertension_specialist":
        stage = raw.get("stage")
        sys_bp = raw.get("systolic")
        if stage and stage not in {"unknown", "normal"}:
            f = _safe_call(
                write_fact, db,
                user_id=user_id, tier="semantic",
                subject="血压分级",
                predicate="equals",
                object_value=str(stage),
                confidence=0.8, source=src, tags=["hypertension"],
                decay_rate=0.005,  # 慢病诊断, 长持久
            )
            if f: created.append(f.id)

    # Metabolic: 代谢综合征 detected → fact
    if fname == "metabolic_specialist":
        if raw.get("metabolic_syndrome"):
            f = _safe_call(
                write_fact, db,
                user_id=user_id, tier="semantic",
                subject="代谢综合征",
                predicate="equals",
                object_value="positive",
                confidence=0.85, source=src, tags=["metabolic"],
                decay_rate=0.005,
            )
            if f: created.append(f.id)

    return created


def extract_from_action_card_outcome(
    db: Session, card,
) -> Optional[int]:
    """评分后的 ActionCard → procedural memory fact.

    '干预 X (减重 protocol) 在 14 天后 accuracy=85, 用户对其响应良好' →
    procedural memory, 下次类似情况 specialist 可参考.
    """
    if card.accuracy_score is None:
        return None
    from app.services.memory_service import write_fact

    score = card.accuracy_score
    metric = card.metric_key
    specialist = card.creator_specialist or "unknown"

    if score >= 70:
        predicate = "responds_to"
        obj = f"{specialist} 的 {metric} 干预 ({card.title[:50]})"
        # accuracy 越高, confidence 越高, 但因为是单次样本所以不超 0.8
        confidence = min(0.8, 0.5 + score / 200)
        decay = 0.005  # 长记忆, 慢衰减
    else:
        predicate = "does_not_respond_to"
        obj = f"{specialist} 的 {metric} 干预 ({card.title[:50]})"
        confidence = min(0.8, 0.5 + (100 - score) / 200)
        decay = 0.005

    f = _safe_call(
        write_fact, db,
        user_id=card.user_id, tier="procedural",
        subject=f"用户对 {metric}",
        predicate=predicate,
        object_value=obj,
        confidence=confidence,
        source={
            "type": "action_card_outcome",
            "id": card.id,
            "weight": 0.7,
        },
        tags=[metric, specialist] if metric else [specialist],
        decay_rate=decay,
    )
    return f.id if f else None


def extract_from_medical_exam_item(
    db: Session, user_id: int, item,
) -> Optional[int]:
    """异常化验项 → semantic fact.

    item: app.models.family_health.MedicalIndicator
    例: name='LDL', value=4.2, is_abnormal=True →
        ('用户 LDL', 'is_above', '4.2 mmol/L', conf=0.9, tier='semantic')
    """
    if not getattr(item, "is_abnormal", False):
        return None
    from app.services.memory_service import write_fact

    name = item.name or "未知化验项"
    value = item.value
    if value is None:
        return None
    unit = item.unit or ""

    # 判断方向 (is_above / is_below) 基于 reference_high
    ref_high = getattr(item, "reference_high", None)
    ref_low = getattr(item, "reference_low", None)
    if ref_high is not None and value > ref_high:
        predicate = "is_above"
    elif ref_low is not None and value < ref_low:
        predicate = "is_below"
    else:
        predicate = "is_value"

    f = _safe_call(
        write_fact, db,
        user_id=user_id, tier="semantic",
        subject=f"用户 {name}",
        predicate=predicate,
        object_value=str(value),
        object_unit=unit,
        confidence=0.85,
        source={
            "type": "medical_exam_item",
            "id": item.id,
            "weight": 0.9,
        },
        tags=[name.lower()],
        decay_rate=0.01,  # 化验值缓慢衰减, 6 月内仍有参考意义
        is_sensitive=False,
    )
    return f.id if f else None


def extract_kg_from_medication(
    db: Session, user_id: int, medication,
) -> Optional[int]:
    """Medication → HealthEntity (type=medication) + relation owns.

    medication: app.models.medication.Medication
    """
    from app.services.kg_service import upsert_entity, create_relation

    name = getattr(medication, "name", None) or getattr(medication, "medication_name", None)
    if not name:
        return None

    # User node (type=condition 'self')
    user_ent = upsert_entity(
        db, user_id=user_id, type="condition",
        canonical_name="self_user", aliases=["我", "用户"],
        confidence=1.0, source={"type": "system"},
    )
    med_ent = upsert_entity(
        db, user_id=user_id, type="medication",
        canonical_name=name,
        attributes={
            "dosage": getattr(medication, "dosage", None),
            "schedule": getattr(medication, "schedule", None),
        },
        source={"type": "medication", "id": getattr(medication, "id", None)},
    )
    if user_ent and med_ent:
        create_relation(
            db, user_id=user_id,
            subject_id=user_ent.id, predicate="owns",
            object_id=med_ent.id, confidence=0.95,
            source={"type": "medication", "id": getattr(medication, "id", None)},
        )
        return med_ent.id
    return None


def extract_kg_from_lab(
    db: Session, user_id: int, item,
) -> Optional[int]:
    """MedicalIndicator (异常项) → HealthEntity (type=lab_value) + 'self_user owns lab_value'."""
    from app.services.kg_service import upsert_entity, create_relation

    name = item.name or "未知化验项"
    user_ent = upsert_entity(
        db, user_id=user_id, type="condition",
        canonical_name="self_user", aliases=["我", "用户"],
        confidence=1.0, source={"type": "system"},
    )
    lab_ent = upsert_entity(
        db, user_id=user_id, type="lab_value",
        canonical_name=name,
        attributes={
            "latest": item.value,
            "unit": item.unit,
            "is_abnormal": getattr(item, "is_abnormal", False),
        },
        source={"type": "medical_indicator", "id": getattr(item, "id", None)},
    )
    if user_ent and lab_ent:
        create_relation(
            db, user_id=user_id,
            subject_id=user_ent.id, predicate="owns",
            object_id=lab_ent.id, confidence=0.9,
            source={"type": "medical_indicator", "id": getattr(item, "id", None)},
        )
        return lab_ent.id
    return None


def extract_from_directive(
    db: Session, directive,
) -> Optional[int]:
    """User Directive → high-confidence semantic fact."""
    from app.services.memory_service import write_fact

    predicate_map = {
        "medication_change": "takes_medication",
        "target_override": "has_target",
        "lifestyle": "follows_protocol",
        "watch_metric": "monitors",
        "skip_recommendation": "does_not_want",
    }
    predicate = predicate_map.get(directive.kind, "directive")

    f = _safe_call(
        write_fact, db,
        user_id=directive.user_id, tier="semantic",
        subject="用户",
        predicate=predicate,
        object_value=directive.instruction[:300],
        confidence=0.95,  # directive 是硬性指令, 高置信
        source={
            "type": "user_directive",
            "id": directive.id,
            "weight": 1.0,
        },
        tags=[t for t in [directive.kind, directive.metric_key] if t],
        decay_rate=0.0,  # 永不衰减直到 directive 被 revoke
    )
    return f.id if f else None
