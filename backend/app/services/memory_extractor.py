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

    三段式 (仅非处方混杂指标):
      score >= 70 → responds_to        (干预有效, 下次同类优先)
      30 < score < 70 → partially_responds_to  (勉强, 可调剂量/方式再试)
      score <= 30 → does_not_respond_to (无效, 下次避开或显著改变)

    subject/object 组织:
      subject    = "用户"  (固定, 便于 BM25 "用户" 查询时命中)
      object     = "{title} → {metric_key}"  (保留具体干预 + 指标, 不同指标同建议不相互覆盖)
      tags       = [specialist, metric_key]  (per-specialist 检索用)
    """
    if card.accuracy_score is None:
        return None
    from app.services.memory_service import write_fact

    from app.services.personal_models.intervention_priors import is_clinician_gated_metric

    score = card.accuracy_score
    metric = card.metric_key or "unknown"
    specialist = card.creator_specialist or "unknown"
    title = (card.title or "")[:60]

    if is_clinician_gated_metric(metric):
        # 这类指标可能主要受处方药、激素或其他临床处理影响。评分只能说明
        # 观察到了变化，不能证明该行动对用户有效或无效。
        predicate = "observed_change"
        confidence = 0.4
    elif score >= 70:
        predicate = "responds_to"
        confidence = min(0.8, 0.5 + score / 200)
    elif score <= 30:
        predicate = "does_not_respond_to"
        confidence = min(0.8, 0.5 + (100 - score) / 200)
    else:
        predicate = "partially_responds_to"
        # 中间段信心低: 单次样本且方向不明确
        confidence = 0.4

    obj = f"{title} → {metric}" if title else metric

    tags = [specialist, metric] if metric != "unknown" else [specialist]
    if predicate == "observed_change":
        tags.append("clinician_review")

    f = _safe_call(
        write_fact, db,
        user_id=card.user_id, tier="procedural",
        subject="用户",
        predicate=predicate,
        object_value=obj,
        confidence=confidence,
        source={
            "type": "action_card_outcome",
            "id": card.id,
            "weight": 0.7,
        },
        tags=tags,
        decay_rate=0.005,  # 长记忆, 慢衰减
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


# 临床有意义的基因类别: 用药 + 营养 + 疾病风险中的 risk/protective
_GENE_CLINICAL_CATEGORIES = {
    "drug_sensitivity",
    "pharmacogenomics",
    "nutrition",
    "disease_risk",
    "exercise",
    "sleep",
}


def extract_kg_from_gene_variant(
    db: Session, user_id: int, variant,
) -> Optional[int]:
    """基因位点 → HealthEntity (type=gene_variant) + 'self_user owns gene_variant'.

    过滤规则: 只收**临床有意义**的位点, 避免 709 条 neutral/info 污染 KG:
    - risk_level in ('high', 'medium') 的 risk 位点
    - variant_nature 是 'risk' 或 'protective' 的
    - 用药相关全收 (drug_sensitivity / pharmacogenomics)
    """
    from app.services.kg_service import upsert_entity, create_relation

    category = (getattr(variant, "category", "") or "").lower()
    risk_level = (getattr(variant, "risk_level", "") or "").lower()
    nature = (getattr(variant, "variant_nature", "") or "").lower()

    # 过滤: 临床无意义的不进 KG
    is_drug = category in {"drug_sensitivity", "pharmacogenomics"}
    is_risky = risk_level in {"high", "medium"}
    is_typed = nature in {"risk", "protective"}
    if not (is_drug or is_risky or is_typed):
        return None

    gene_name = getattr(variant, "gene_name", None)
    if not gene_name:
        return None
    genotype = getattr(variant, "genotype", None)
    variant_label = getattr(variant, "variant_name", None) or gene_name
    canonical = f"{gene_name}_{genotype}" if genotype else gene_name

    # 置信度: 用药相关 0.95, 高风险 0.9, 其他 0.8
    if is_drug:
        conf = 0.95
    elif risk_level == "high":
        conf = 0.9
    else:
        conf = 0.8

    user_ent = upsert_entity(
        db, user_id=user_id, type="condition",
        canonical_name="self_user", aliases=["我", "用户"],
        confidence=1.0, source={"type": "system"},
    )
    gene_ent = upsert_entity(
        db, user_id=user_id, type="gene_variant",
        canonical_name=canonical,
        aliases=[gene_name, variant_label] if variant_label != gene_name else [gene_name],
        attributes={
            "gene_name": gene_name,
            "genotype": genotype,
            "category": category,
            "risk_level": risk_level,
            "variant_nature": nature,
            "result_label": getattr(variant, "result_label", None),
        },
        confidence=conf,
        source={"type": "genetic_variant", "id": getattr(variant, "id", None)},
    )
    if user_ent and gene_ent:
        # User has_genotype gene_variant (decay_rate=0 隐含于 predicate, KG 不显式带 decay)
        create_relation(
            db, user_id=user_id,
            subject_id=user_ent.id, predicate="has_genotype" if genotype else "owns",
            object_id=gene_ent.id, confidence=conf,
            source={"type": "genetic_variant", "id": getattr(variant, "id", None)},
        )
        return gene_ent.id
    return None


def extract_from_briefing_entry(
    db: Session, entry,
) -> List[int]:
    """ClinicalJournalEntry (briefing SOAP) → MemoryFact(s).

    从 SOAP 四字段里抽:
      - objective: 数字型 vital / lab 值 (正则挖数字+单位)
      - assessment: theme-level tag → symptom/condition entity
      - plan: 计划关键字 → intervention fact
    旁路调用, 失败不影响主链路.
    """
    import re
    from app.services.memory_service import write_fact

    created: List[int] = []
    src = {
        "type": "clinical_journal",
        "id": entry.id,
        "weight": 0.7,
    }
    tags = [entry.created_by or "briefing"]

    # 从 objective 抓数字 (HRV 72 ms, 睡眠评分 85, LDL 3.4 mmol/L 等)
    obj = entry.objective or ""
    # 模式: 词汇 + 数字 + 可选单位; 支持中文词汇
    pattern = re.compile(
        r"([A-Za-z一-龥]{1,12}?)\s*[：:=是为]?\s*"
        r"(-?\d+(?:\.\d+)?)\s*"
        r"(mmHg|bpm|%|分|ms|mmol/L|mg/dL|kg|次|小时|h|min)?",
    )
    # 只为已知健康指标建 is_value 事实 —— 否则简报 objective 里嵌的基因/补剂文案碎片
    # ("AA 9"/"基因提示 9"/"上午补充 500"/"ml 2")会被正则当成"事实",且每日简报重抽
    # 同一段文字 → reinforcement 飙到置信度 1.0,垃圾反而最"可信"(画像页根因)。
    _metric_tokens = (
        "hrv", "rhr", "心率", "血压", "收缩压", "舒张压", "spo2", "血氧", "体温",
        "压力", "电量", "battery", "readiness", "恢复", "步数", "睡眠", "深睡",
        "ldl", "hdl", "胆固醇", "甘油三酯", "hba1c", "糖化", "血糖", "alt", "ast",
        "ggt", "尿酸", "肌酐", "egfr", "白细胞", "血红蛋白", "体重", "bmi", "体脂", "腰围",
    )
    seen_subjects: set = set()
    for m in list(pattern.finditer(obj))[:15]:
        try:
            subj = m.group(1).strip()
            val = m.group(2)
            unit = m.group(3) or ""
            # 过滤: subj 过短 / 纯数字字 / 重复 / 不在已知指标白名单
            if not subj or len(subj) < 2 or subj in seen_subjects or subj.isdigit():
                continue
            if not any(tok in subj.lower() for tok in _metric_tokens):
                continue
            seen_subjects.add(subj)
            f = _safe_call(
                write_fact, db,
                user_id=entry.user_id, tier="working",
                subject=subj,
                predicate="is_value",
                object_value=val,
                object_unit=unit,
                confidence=0.6,
                source=src, tags=tags + ["briefing_snapshot"],
                decay_rate=0.05,  # 快衰减: 每日简报是瞬时快照
            )
            if f:
                created.append(f.id)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[memory_extractor] briefing regex fail (skip): {e}")
            continue

    # 从 assessment 抓"关注点": 以 · 开头的 bullet 或 "⚠️" 条目
    assess = entry.assessment or ""
    for line in assess.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("·") or line.startswith("-") or line.startswith("⚠"):
            bullet = line.lstrip("·-⚠️ ").strip()[:200]
            if len(bullet) < 4:
                continue
            f = _safe_call(
                write_fact, db,
                user_id=entry.user_id, tier="working",
                subject="本日关注点",
                predicate="mentions",
                object_value=bullet,
                confidence=0.55,
                source=src, tags=tags + ["assessment"],
                decay_rate=0.08,  # 关注点 ~10 天衰减
            )
            if f:
                created.append(f.id)

    return created


def bulk_extract_genes_for_profile(
    db: Session, user_id: int, profile_id: Optional[int] = None,
) -> int:
    """基因档案入库后一次性 extract. 返回写入 KG 的 variant 数.

    3 个基因上传入口 (TXT/PDF/batch API) 统一用此 helper. profile_id=None 时处理该 user 所有 variant.
    """
    from app.models.genetic_data import GeneticVariant
    q = db.query(GeneticVariant).filter(GeneticVariant.user_id == user_id)
    if profile_id is not None:
        q = q.filter(GeneticVariant.profile_id == profile_id)
    written = 0
    for v in q.all():
        try:
            if extract_kg_from_gene_variant(db, user_id, v):
                written += 1
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[memory_extractor] gene skip id={v.id}: {e}")
    return written
