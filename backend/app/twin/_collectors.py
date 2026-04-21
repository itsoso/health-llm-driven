"""
Twin 层的薄数据收集器 —— 过渡期。

为什么存在：
  理想状态下，twin/builder.py 只调用 service 层函数，不直接读 model。
  但当前 service 层对几个领域（water/checkin/supplement/BP/medical_exam）
  还没有聚合函数。与其阻塞 Phase 0，不如把这些直接查询隔离到这里，
  下一阶段逐步上提到各自的 service 模块。

约束：
  - 每个函数只做一件事：取"最新/今日"状态并返回简单 dict
  - 不做任何计算/LLM/告警
  - 失败返回空字典或 None，不抛异常
  - 异常后 rollback，防止污染事务影响后续 collector
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

DEFAULT_WATER_GOAL_ML = 2000


def _safe_rollback(db: Session) -> None:
    """静默回滚，防止一个失败的查询污染整个事务。"""
    try:
        db.rollback()
    except Exception:  # noqa: BLE001
        pass


# ─────────────────────────────── water ────────────────────────────────


def fetch_water_today(db: Session, user_id: int) -> Dict[str, Any]:
    """今日饮水总量。"""
    try:
        from app.models.daily_health import WaterIntake

        today = date.today()
        records = (
            db.query(WaterIntake)
            .filter(
                WaterIntake.user_id == user_id,
                WaterIntake.record_date == today,
            )
            .all()
        )
        total_ml = sum(int(getattr(r, "amount_ml", 0) or 0) for r in records)
        return {
            "total_ml": total_ml,
            "entries_count": len(records),
            "goal_ml": DEFAULT_WATER_GOAL_ML,
            "progress_pct": round(total_ml / DEFAULT_WATER_GOAL_ML * 100, 1) if total_ml else 0.0,
        }
    except Exception as e:
        logger.warning(f"[twin.collectors] water 失败: {e}")
        _safe_rollback(db)
        return {"total_ml": 0, "entries_count": 0, "goal_ml": DEFAULT_WATER_GOAL_ML, "progress_pct": 0.0}


# ─────────────────────────── health_checkin (rhinitis) ────────────────


def fetch_health_checkin_today(db: Session, user_id: int) -> Dict[str, Any]:
    """今日健康打卡 —— 含鼻炎字段。"""
    try:
        from app.models.health_checkin import HealthCheckin

        today = date.today()
        record = (
            db.query(HealthCheckin)
            .filter(
                HealthCheckin.user_id == user_id,
                HealthCheckin.checkin_date == today,
            )
            .first()
        )
        if not record:
            return {}
        return {
            "nasal_wash_count": record.nasal_wash_count or 0,
            "sneeze_count": record.sneeze_count or 0,
            "daily_score": record.daily_score,
            "running_distance_km": record.running_distance,
            "squats_count": record.squats_count or 0,
        }
    except Exception as e:
        logger.warning(f"[twin.collectors] health_checkin 失败: {e}")
        _safe_rollback(db)
        return {}


# ─────────────────────────── supplement ───────────────────────────────


def fetch_supplement_today(db: Session, user_id: int) -> Dict[str, Any]:
    """今日补剂打卡状态。单次 LEFT JOIN 查询代替两次独立查询。"""
    try:
        from app.models.supplement import SupplementDefinition, SupplementRecord

        today = date.today()

        # LEFT JOIN: active supplements + today's taken records
        rows = (
            db.query(
                SupplementDefinition.id,
                SupplementDefinition.name,
                SupplementDefinition.dosage,
                SupplementDefinition.timing,
                SupplementRecord.taken,
            )
            .outerjoin(
                SupplementRecord,
                (SupplementRecord.supplement_id == SupplementDefinition.id)
                & (SupplementRecord.user_id == user_id)
                & (SupplementRecord.record_date == today)
                & (SupplementRecord.taken == True),  # noqa: E712
            )
            .filter(
                SupplementDefinition.user_id == user_id,
                SupplementDefinition.is_active == True,  # noqa: E712
            )
            .order_by(SupplementDefinition.sort_order)
            .all()
        )

        items = [
            {
                "id": row[0],
                "name": row[1],
                "dosage": row[2],
                "timing": row[3],
                "taken": row[4] is True,
            }
            for row in rows
        ]

        return {
            "active_supplements": items,
            "taken_today_count": sum(1 for i in items if i["taken"]),
            "total_active_count": len(items),
        }
    except Exception as e:
        logger.warning(f"[twin.collectors] supplement 失败: {e}")
        _safe_rollback(db)
        return {"active_supplements": [], "taken_today_count": 0, "total_active_count": 0}


# ─────────────────────────── blood pressure ───────────────────────────


def fetch_blood_pressure_latest(db: Session, user_id: int) -> Optional[Dict[str, Any]]:
    """最近一次血压。"""
    try:
        from app.models.blood_pressure import BloodPressureRecord

        record = (
            db.query(BloodPressureRecord)
            .filter(BloodPressureRecord.user_id == user_id)
            .order_by(desc(BloodPressureRecord.record_date))
            .first()
        )
        if not record:
            return None
        return {
            "systolic": record.systolic,
            "diastolic": record.diastolic,
            "pulse": record.pulse,
            "record_date": record.record_date,
        }
    except Exception as e:
        logger.warning(f"[twin.collectors] blood_pressure 失败: {e}")
        _safe_rollback(db)
        return None


# ─────────────────────────── medical exam abnormal ────────────────────


def fetch_medical_exam_abnormal(
    db: Session, user_id: int, limit: int = 10
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """最近体检中的异常指标 — 从统一的 medical_indicators 表读取。"""
    try:
        from app.models.family_health import MedicalIndicator

        indicators = (
            db.query(MedicalIndicator)
            .filter(
                MedicalIndicator.user_id == user_id,
                MedicalIndicator.is_abnormal == True,
            )
            .order_by(desc(MedicalIndicator.record_date))
            .limit(limit)
            .all()
        )
        if not indicators:
            return [], {}

        latest_meta = {
            "exam_date": indicators[0].record_date,
            "exam_type": indicators[0].category,
        }
        result: List[Dict[str, Any]] = [
            {
                "item_name": ind.name,
                "value": ind.value if ind.value is not None else ind.value_text,
                "unit": ind.unit,
                "reference_range": ind.reference_range or (
                    f"{ind.reference_low}-{ind.reference_high}"
                    if ind.reference_low is not None and ind.reference_high is not None
                    else None
                ),
                "result": ind.result,
                "exam_date": ind.record_date,
                "exam_type": ind.category,
            }
            for ind in indicators
        ]
        return result, latest_meta
    except Exception as e:
        logger.warning(f"[twin.collectors] medical_indicators 失败: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return [], {}


# fetch_latest_exam_meta 已合并到 fetch_medical_exam_abnormal 中（Phase 3.2）
# 保留旧签名供外部调用者向后兼容
def fetch_latest_exam_meta(db: Session, user_id: int) -> Dict[str, Any]:
    """最近一份化验单的元信息。已合并入 fetch_medical_exam_abnormal。"""
    try:
        from app.models.medical_exam import MedicalExam

        exam = (
            db.query(MedicalExam)
            .filter(MedicalExam.user_id == user_id)
            .order_by(desc(MedicalExam.exam_date))
            .first()
        )
        if not exam:
            return {}
        return {"exam_date": exam.exam_date, "exam_type": exam.exam_type}
    except Exception as e:
        logger.warning(f"[twin.collectors] latest_exam_meta 失败: {e}")
        _safe_rollback(db)
        return {}


# ─────────────────────────── genetic variants (categorized) ───────────


def fetch_genetic_variants_categorized(db: Session, user_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """按类别分组的基因变异。"""
    try:
        from app.models.genetic_data import GeneticVariant

        variants = (
            db.query(GeneticVariant)
            .filter(GeneticVariant.user_id == user_id)
            .all()
        )

        # 按 gene_name + variant_name 去重，保留首条（risk_level desc 排序后优先高风险）
        seen = {}
        for v in variants:
            key = (v.gene_name, getattr(v, "variant_name", None))
            if key not in seen:
                seen[key] = v
        unique_variants = list(seen.values())

        drug_sens: List[Dict[str, Any]] = []
        risk: List[Dict[str, Any]] = []
        protective: List[Dict[str, Any]] = []
        by_category: Dict[str, List[Dict[str, Any]]] = {
            "cognition": [], "personality": [], "sleep": [],
            "recovery": [], "exercise": [], "nutrition": [],
        }

        for v in unique_variants:
            item = {
                "gene_name": v.gene_name,
                "variant_name": getattr(v, "variant_name", None),
                "genotype": getattr(v, "genotype", None),
                "result_label": getattr(v, "result_label", None),
                "risk_level": getattr(v, "risk_level", None),
                "category": getattr(v, "category", None),
            }
            category = (getattr(v, "category", "") or "").lower()
            nature = (getattr(v, "variant_nature", "") or "").lower()
            if "drug" in category:
                drug_sens.append(item)
            elif nature == "protective":
                protective.append(item)
            elif nature == "risk":
                risk.append(item)

            if category in by_category:
                by_category[category].append(item)

        return {
            "total": len(unique_variants),
            "drug_sensitivity": drug_sens[:10],
            "risk": risk[:10],
            "protective": protective[:10],
            **{f"{k}_variants": v[:15] for k, v in by_category.items()},
        }
    except Exception as e:
        logger.warning(f"[twin.collectors] genetic 失败: {e}")
        _safe_rollback(db)
        return {"total": 0, "drug_sensitivity": [], "risk": [], "protective": []}
