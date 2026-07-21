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
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

DEFAULT_WATER_GOAL_ML = 2000


def _safe_rollback(db: Session) -> None:
    """静默回滚，防止一个失败的查询污染整个事务。"""
    try:
        db.rollback()
    except Exception as e:  # noqa: BLE001
        logger.debug("[twin] rollback failed (continuing): %s", e)


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


def fetch_supplement_today(
    db: Session,
    user_id: int,
    *,
    raise_on_error: bool = False,
) -> Dict[str, Any]:
    """今日补剂打卡状态。单次 LEFT JOIN 查询代替两次独立查询。

    ``raise_on_error`` is reserved for safety-critical callers that own the
    surrounding transaction.  Those callers must be allowed to contain a
    failed read in a SAVEPOINT; rolling back their whole session here could
    erase already-flushed health writes.
    """
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

        # "在服"分段:近 14 天有 taken=true 打卡的才算正在服用;库里其余
        # active 定义只是"已登记"。防 LLM 把补剂库存量当当前摄入负担
        # (实测:24 种库存被说成"你目前有 24 种补剂,再加红参会增加负担")。
        taking_window_days = 14
        window_start = today - timedelta(days=taking_window_days - 1)
        taken_id_rows = (
            db.query(SupplementRecord.supplement_id)
            .filter(
                SupplementRecord.user_id == user_id,
                SupplementRecord.record_date >= window_start,
                SupplementRecord.taken == True,  # noqa: E712
            )
            .distinct()
            .all()
        )
        taken_ids = {r[0] for r in taken_id_rows}
        taking_names = [i["name"] for i in items if i["id"] in taken_ids]

        return {
            "active_supplements": items,
            "taken_today_count": sum(1 for i in items if i["taken"]),
            "total_active_count": len(items),
            "taking_recent_count": len(taking_names),
            "taking_recent_names": taking_names,
            "taking_window_days": taking_window_days,
        }
    except Exception as e:
        logger.warning(f"[twin.collectors] supplement 失败: {e}")
        if raise_on_error:
            raise
        _safe_rollback(db)
        return {"active_supplements": [], "taken_today_count": 0, "total_active_count": 0}


# ─────────────────────────── blood pressure ───────────────────────────


def fetch_waist_latest(db: Session, user_id: int) -> Optional[Dict[str, Any]]:
    """最近一次腰围."""
    try:
        from app.models.user import User
        from app.models.user_profile import UserProfile
        from app.models.basic_health import BasicHealthData
        from app.models.waist import WaistRecord

        record = (
            db.query(WaistRecord)
            .filter(WaistRecord.user_id == user_id)
            .order_by(desc(WaistRecord.record_date))
            .first()
        )
        if not record:
            return None

        user = db.query(User).filter(User.id == user_id).first()
        gender = (getattr(user, "gender", None) or "").lower()
        is_male = gender in {"男", "male", "m", "man"} or gender.startswith("男")
        threshold = 90 if is_male else 80

        height_cm = None
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if profile and profile.height_cm:
            height_cm = float(profile.height_cm)
        if height_cm is None:
            basic = (
                db.query(BasicHealthData.height)
                .filter(BasicHealthData.user_id == user_id, BasicHealthData.height.isnot(None))
                .order_by(desc(BasicHealthData.record_date))
                .first()
            )
            if basic:
                height_cm = float(basic[0])

        return {
            "waist_cm": record.waist_cm,
            "record_date": record.record_date,
            "waist_to_height_ratio": round(record.waist_cm / height_cm, 3) if height_cm else None,
            "central_obesity_flag": record.waist_cm >= threshold,
        }
    except Exception as e:
        logger.warning(f"[twin.collectors] waist 失败: {e}")
        _safe_rollback(db)
        return None


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


def fetch_ecg_latest(db: Session, user_id: int) -> Optional[Dict[str, Any]]:
    """最近一次 Apple Watch ECG 观测 (筛查信号非诊断)。

    afib_recent 判定: 最近一次分类为 AtrialFibrillation, 或其 afib_event_count>=1。
    缺失/未知分类不当作房颤。recorded_at 为 NULL 的记录排在最后取。"""
    try:
        from app.models.ecg_observation import EcgObservation

        record = (
            db.query(EcgObservation)
            .filter(EcgObservation.user_id == user_id)
            .order_by(desc(EcgObservation.recorded_at), desc(EcgObservation.id))
            .first()
        )
        if not record:
            return None
        afib_count = record.afib_event_count or 0
        is_afib = record.classification == "AtrialFibrillation" or afib_count >= 1
        return {
            "ecg_classification": record.classification,
            "ecg_recorded_at": record.recorded_at,
            "afib_event_count": afib_count,
            "afib_recent": is_afib,
        }
    except Exception as e:
        logger.warning(f"[twin.collectors] ecg 失败: {e}")
        _safe_rollback(db)
        return None


# ─────────────────────────── medical exam abnormal ────────────────────


def fetch_latest_labs(db: Session, user_id: int) -> Dict[str, float]:
    """从 MedicalIndicator 抓最新一次的常用化验项数值.

    返回 {key: value}, key 与 LabsContext 字段名对齐:
      ldl / hdl / total_cholesterol / triglycerides / blood_glucose / hba1c
      alt / ast / ggt / creatinine / egfr / uric_acid
      血常规 CBC: hemoglobin / hematocrit / rbc / platelet / mch / mchc / neutrophil_pct

    每个 key 取该用户该指标的最新一次记录 (按 record_date desc).
    """
    out: Dict[str, float] = {}
    try:
        from app.models.family_health import MedicalIndicator
        from sqlalchemy import func

        # 字段名/中文名/英文缩写到 key 的映射
        # 形如: 'creatinine' 关键字 → key='creatinine'
        # 用 ilike 模糊匹配, 一个 key 命中多个 candidate, 取最新
        KEY_PATTERNS = {
            "ldl": ["LDL", "低密度脂蛋白"],
            "hdl": ["HDL", "高密度脂蛋白"],
            "total_cholesterol": ["TC", "总胆固醇"],
            "triglycerides": ["TG", "甘油三酯"],
            "blood_glucose": ["FBG", "空腹血糖"],
            "hba1c": ["HBA1C", "HbA1c", "糖化血红蛋白"],
            "alt": ["ALT", "谷丙转氨酶"],
            "ast": ["AST", "谷草转氨酶"],
            "ggt": ["GGT", "γ-谷氨酰", "谷氨酰转肽酶"],
            "creatinine": ["CREA", "肌酐"],
            "egfr": ["eGFR", "肾小球滤过率"],
            "uric_acid": ["UA", "尿酸"],
            # PhenoAge 输入项 (单位见 LabsContext 字段注释):
            "albumin": ["ALB", "白蛋白"],
            "crp": ["hs-CRP", "hsCRP", "CRP", "C反应蛋白", "C-反应蛋白"],
            "mcv": ["MCV", "红细胞平均体积", "平均红细胞体积"],
            "rdw": ["RDW", "红细胞分布宽度"],
            "alp": ["ALP", "碱性磷酸酶"],
            # 注: wbc / lymphocyte_pct 以及全部血常规 CBC analyte 不在此 substring-loop,
            # 改走下方 cbc_analyte_of 锚定白名单 (防 白细胞酯酶/网织血红蛋白/MPV 等复合名污染)。
        }

        from sqlalchemy import or_
        from app.biomarkers.definitions import resolve_code

        for key, patterns in KEY_PATTERNS.items():
            # 构建 OR 条件: name_en/name/item_code 任一匹配关键字
            cond = or_(*[
                MedicalIndicator.name.ilike(f"%{p}%") |
                MedicalIndicator.name_en.ilike(f"%{p}%") |
                MedicalIndicator.item_code.ilike(f"%{p}%")
                for p in patterns
            ])
            base_q = (
                db.query(MedicalIndicator.value, MedicalIndicator.name)
                .filter(
                    MedicalIndicator.user_id == user_id,
                    MedicalIndicator.value.isnot(None),
                    cond,
                )
                .order_by(desc(MedicalIndicator.record_date))
            )
            # hba1c 医疗敏感: 子串「糖化血红蛋白」会吞下「糖化血红蛋白A1」(总糖化 HbA1,
            # 与标准 A1c 是不同指标, 参考 6.3–9.0%)。该总糖化值喂进 twin.labs.hba1c →
            # 污染 SafetyGuardian 糖尿病阈值规则的 fallback。用 canonical resolve_code 校验:
            # 只接受解析为 glucose_hba1c(标准 A1c)的行, 逐条向旧回退直到命中。
            if key == "hba1c":
                row = None
                for cand_value, cand_name in base_q.limit(20).all():
                    if resolve_code(cand_name or "") == "glucose_hba1c":
                        row = (cand_value,)
                        break
            else:
                row = base_q.first()
            if row and row[0] is not None:
                try:
                    out[key] = float(row[0])
                except (TypeError, ValueError):
                    pass

        # ── 血常规 CBC: 锚定白名单 (cbc_analyte_of) ──
        # resolve_code 最长子串回退把任何含「血红蛋白」名 → hemoglobin (黑名单打地鼠会漏
        # 网织血红蛋白/还原血红蛋白/血红蛋白A2/电泳); 血小板/白细胞同病 (MPV/PDW/白细胞酯酶)。
        # 这里只接受「规范化整串恰好等于规范名」的行 → 复合名结构性拒绝, 防 red_cell_elevation
        # 等安全规则 under-alarm。SQL 宽前缀仅缩小扫描, 每行最终走 cbc_analyte_of 锚定校验。
        from app.services.blood_routine import (
            cbc_analyte_of, _CBC_SQL_PREFILTER,
        )
        _CBC_KEYS = (
            "hemoglobin", "hematocrit", "rbc", "platelet",
            "wbc", "neutrophil_pct", "lymphocyte_pct", "mch", "mchc",
        )
        # mch/mchc 不在 _CBC_SQL_PREFILTER (它只列 blood_routine 需要的); 给一份本地前缀。
        _CBC_PREFILTER = dict(_CBC_SQL_PREFILTER)
        _CBC_PREFILTER.setdefault("mch", ["平均血红蛋白量", "MCH"])
        _CBC_PREFILTER.setdefault("mchc", ["平均血红蛋白浓度", "MCHC"])
        for key in _CBC_KEYS:
            prefilters = _CBC_PREFILTER.get(key) or []
            if not prefilters:
                continue
            cond = or_(*[
                MedicalIndicator.name.ilike(f"%{p}%") |
                MedicalIndicator.name_en.ilike(f"%{p}%") |
                MedicalIndicator.item_code.ilike(f"%{p}%")
                for p in prefilters
            ])
            rows = (
                db.query(MedicalIndicator.value, MedicalIndicator.name)
                .filter(
                    MedicalIndicator.user_id == user_id,
                    MedicalIndicator.value.isnot(None),
                    cond,
                )
                .order_by(desc(MedicalIndicator.record_date))
                .limit(30)
                .all()
            )
            for cand_value, cand_name in rows:  # newest-first; 取首个锚定命中
                if cbc_analyte_of(cand_name) == key:
                    try:
                        out[key] = float(cand_value)
                    except (TypeError, ValueError):
                        pass
                    break
        return out
    except Exception as e:
        logger.warning(f"[twin.collectors] fetch_latest_labs 失败: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return {}


def fetch_medical_exam_abnormal(
    db: Session,
    user_id: int,
    limit: int = 10,
    *,
    raise_on_error: bool = False,
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
        if raise_on_error:
            raise
        try:
            db.rollback()
        except Exception:
            pass
        return [], {}


# fetch_latest_exam_meta 已合并到 fetch_medical_exam_abnormal 中（Phase 3.2）
# 保留旧签名供外部调用者向后兼容
def fetch_user_age(db: Session, user_id: int) -> Optional[int]:
    """用户实足年龄(整数岁)。

    取数优先级:User.birth_date (canonical) → UserProfile.birth_date (fallback)。
    User 模型是仓库里大部分 service 算年龄的来源 (sleep / exercise / doctor_report),
    UserProfile 仅在用户主动填了"我的资料"时才有。两边都缺 → 返回 None。
    """
    try:
        from app.models.user import User

        birth_date = (
            db.query(User.birth_date)
            .filter(User.id == user_id)
            .scalar()
        )
        if birth_date is None:
            from app.models.user_profile import UserProfile

            profile = (
                db.query(UserProfile)
                .filter(UserProfile.user_id == user_id)
                .first()
            )
            if profile is None or profile.birth_date is None:
                return None
            birth_date = profile.birth_date

        today = date.today()
        return today.year - birth_date.year - (
            (today.month, today.day) < (birth_date.month, birth_date.day)
        )
    except Exception as e:
        logger.warning(f"[twin.collectors] fetch_user_age 失败: {e}")
        _safe_rollback(db)
        return None


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


def fetch_genetic_variants_categorized(
    db: Session,
    user_id: int,
    *,
    raise_on_error: bool = False,
) -> Dict[str, List[Dict[str, Any]]]:
    """按类别分组的基因变异。

    Safety-critical callers opt into propagation so their SAVEPOINT, rather
    than this collector, controls rollback scope.
    """
    try:
        from app.models.genetic_data import GeneticVariant
        from app.services.genetic_report import _resolve_active_profile
        from app.services.genetic_risk import clinical_status, effective_risk_level

        profile = _resolve_active_profile(db, user_id)
        if profile is None:
            return {"total": 0, "drug_sensitivity": [], "risk": [], "protective": []}
        variants = (
            db.query(GeneticVariant)
            .filter(
                GeneticVariant.user_id == user_id,
                GeneticVariant.profile_id == profile.id,
            )
            .order_by(GeneticVariant.id.asc())
            .all()
        )

        # 按 rsid 优先去重；老数据无 rsid 时退回 gene + variant + category。
        # 只读取活跃 profile，避免历史上传结果污染 Agent/Twin。
        seen = {}
        for v in variants:
            key = (
                (getattr(v, "rsid", None) or "").lower()
                or f"{v.gene_name}:{getattr(v, 'variant_name', None)}:{getattr(v, 'category', None)}"
            )
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
            raw_risk = getattr(v, "risk_level", None) or "info"
            display_risk = effective_risk_level(
                raw_risk,
                getattr(v, "category", None),
                getattr(v, "evidence_level", None),
                getattr(v, "health_implications", None),
            )
            item = {
                "rsid": getattr(v, "rsid", None),
                "gene_name": v.gene_name,
                "variant_name": getattr(v, "variant_name", None),
                "genotype": getattr(v, "genotype", None),
                "result_label": getattr(v, "result_label", None),
                "risk_level": display_risk,
                "raw_risk_level": raw_risk,
                "category": getattr(v, "category", None),
                "evidence_level": getattr(v, "evidence_level", None),
                "mapping_source": getattr(v, "mapping_source", None),
                "clinical_status": clinical_status(
                    getattr(v, "category", None),
                    getattr(v, "evidence_level", None),
                    getattr(v, "health_implications", None),
                ),
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
        if raise_on_error:
            raise
        _safe_rollback(db)
        return {"total": 0, "drug_sensitivity": [], "risk": [], "protective": []}
