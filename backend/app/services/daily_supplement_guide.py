"""每日补剂动态指南 — 基于整合医学评估的规则引擎

根据用户的身体状况、环境因素、运动记录、鼻炎症状等，
生成个性化的每日补剂服用提醒和调整建议。

规则来源：用户的整合医学功能医学评估报告
"""
import logging
from datetime import date, timedelta, datetime
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.medication import Medication, MedicationLog
from app.models.daily_health import GarminData, ExerciseRecord
from app.models.health_checkin import HealthCheckin

logger = logging.getLogger(__name__)


def get_daily_supplement_guide(
    db: Session, user_id: int, target_date: Optional[date] = None
) -> Dict[str, Any]:
    """生成每日补剂动态指南"""
    today = target_date or date.today()

    # ── 1. 获取基础数据 ──────────────────────────
    active_supps = (
        db.query(SupplementDefinition)
        .filter(
            SupplementDefinition.user_id == user_id,
            SupplementDefinition.is_active == True,
        )
        .order_by(SupplementDefinition.timing, SupplementDefinition.sort_order)
        .all()
    )

    taken_records = {
        r.supplement_id: r
        for r in db.query(SupplementRecord)
        .filter(
            SupplementRecord.user_id == user_id,
            SupplementRecord.record_date == today,
        )
        .all()
    }

    # 今日 Garmin 数据（睡眠、HRV）
    garmin = (
        db.query(GarminData)
        .filter(GarminData.user_id == user_id, GarminData.record_date == today)
        .first()
    )
    # 昨日 Garmin（用于昨晚睡眠）
    garmin_yesterday = (
        db.query(GarminData)
        .filter(
            GarminData.user_id == user_id,
            GarminData.record_date == today - timedelta(days=1),
        )
        .first()
    )

    # 今日运动
    exercises = (
        db.query(ExerciseRecord)
        .filter(
            ExerciseRecord.user_id == user_id,
            ExerciseRecord.record_date == today,
        )
        .all()
    )

    # 今日鼻炎/症状签到
    checkins = (
        db.query(HealthCheckin)
        .filter(
            HealthCheckin.user_id == user_id,
            HealthCheckin.checkin_date == today,
        )
        .all()
    )

    # 活跃药物（查注射类）
    active_meds = (
        db.query(Medication)
        .filter(
            Medication.user_id == user_id,
            Medication.is_active == True,
        )
        .all()
    )

    # 今日药物记录
    med_logs = (
        db.query(MedicationLog)
        .filter(
            MedicationLog.user_id == user_id,
            MedicationLog.taken_date == today,
        )
        .all()
    )
    med_log_ids = {ml.medication_id for ml in med_logs}

    # ── 2. 构建上下文 ─────────────────────────────
    ctx = _build_context(garmin, garmin_yesterday, exercises, checkins, active_meds, med_log_ids)

    # ── 3. 生成时间段补剂列表 + 动态提示 ──────────
    slots = _build_slots(active_supps, taken_records, ctx)
    alerts = _generate_alerts(ctx, active_supps)
    medications = _build_medication_section(active_meds, med_log_ids, today)

    # ── 4. 动态推荐（基于上下文强调/调整） ─────────
    recommendations = _generate_recommendations(ctx, active_supps, taken_records)

    return {
        "date": today.isoformat(),
        "slots": slots,
        "alerts": alerts,
        "recommendations": recommendations,
        "medications": medications,
        "context": {
            "sleep_quality": ctx.get("sleep_quality"),
            "sleep_score": ctx.get("sleep_score"),
            "hrv_status": ctx.get("hrv_status"),
            "hrv_value": ctx.get("hrv_value"),
            "has_exercise": ctx.get("has_exercise", False),
            "exercise_types": ctx.get("exercise_types", []),
            "rhinitis_active": ctx.get("rhinitis_active", False),
            "sneeze_count": ctx.get("sneeze_count", 0),
            "is_injection_day": ctx.get("is_injection_day", False),
        },
        "summary": _build_summary(active_supps, taken_records),
    }


def _build_context(
    garmin, garmin_yesterday, exercises, checkins, active_meds, med_log_ids
) -> Dict[str, Any]:
    """从各数据源提取规则引擎需要的上下文"""
    ctx: Dict[str, Any] = {}

    # 睡眠质量（用今日或昨日数据）
    sleep_data = garmin or garmin_yesterday
    if sleep_data and sleep_data.sleep_score:
        score = sleep_data.sleep_score
        if score >= 80:
            ctx["sleep_quality"] = "good"
        elif score >= 60:
            ctx["sleep_quality"] = "fair"
        else:
            ctx["sleep_quality"] = "poor"
        ctx["sleep_score"] = score

    # HRV
    if garmin and garmin.hrv:
        ctx["hrv_value"] = garmin.hrv
        ctx["hrv_status"] = garmin.hrv_status or "unknown"
        if garmin.hrv_7day_avg and garmin.hrv:
            ctx["hrv_below_avg"] = garmin.hrv < garmin.hrv_7day_avg * 0.85

    # 运动
    ctx["has_exercise"] = len(exercises) > 0
    ctx["exercise_types"] = [e.exercise_type for e in exercises]
    ctx["high_intensity"] = any(
        e.exercise_type in ("running", "hiit", "cycling", "swimming")
        for e in exercises
    )

    # 鼻炎症状（HealthCheckin 有 sneeze_count 字段）
    for c in checkins:
        if c.sneeze_count and c.sneeze_count > 0:
            ctx["rhinitis_active"] = True
            ctx["sneeze_count"] = c.sneeze_count
            break
    if not ctx.get("rhinitis_active"):
        rhinitis_keywords = {"喷嚏", "鼻塞", "流涕", "鼻痒", "rhinitis", "sneeze"}
        for c in checkins:
            notes = (c.notes or "").lower()
            if any(k in notes for k in rhinitis_keywords):
                ctx["rhinitis_active"] = True
                break

    # 注射日（如睾酮注射）
    injection_meds = [
        m for m in active_meds
        if any(kw in (m.name or "").lower() for kw in ("注射", "injection", "睾酮", "testosterone"))
        or any(kw in (m.category or "").lower() for kw in ("注射", "injection"))
    ]
    ctx["is_injection_day"] = any(m.id in med_log_ids for m in injection_meds)
    ctx["injection_meds"] = [m.name for m in injection_meds]

    return ctx


TIMING_LABELS = {
    "morning": "☀️ 早晨",
    "noon": "🌤️ 午间",
    "evening": "🌇 晚间",
    "bedtime": "🌙 睡前",
}

TIMING_ORDER = ["morning", "noon", "evening", "bedtime"]


def _build_slots(
    supps: list, taken_records: dict, ctx: dict
) -> List[Dict[str, Any]]:
    """按时间段组织补剂，附加动态提示"""
    slots = []
    grouped: Dict[str, list] = {}

    for s in supps:
        timing = s.timing or "morning"
        grouped.setdefault(timing, []).append(s)

    for timing in TIMING_ORDER:
        items = grouped.get(timing, [])
        if not items:
            continue

        slot_items = []
        for s in items:
            record = taken_records.get(s.id)
            taken = record.taken if record else False
            tips = _get_item_tips(s, ctx)

            slot_items.append({
                "id": s.id,
                "name": s.name,
                "dosage": s.dosage or "",
                "taken": taken,
                "taken_time": (
                    record.taken_time.strftime("%H:%M") if record and record.taken_time else None
                ),
                "tips": tips,
                "category": s.category or "",
            })

        slots.append({
            "timing": timing,
            "label": TIMING_LABELS.get(timing, timing),
            "items": slot_items,
        })

    return slots


def _get_item_tips(supp, ctx: dict) -> List[str]:
    """为单个补剂生成上下文相关提示"""
    tips = []
    name_lower = (supp.name or "").lower()
    category_lower = (supp.category or "").lower()

    # 规则0: 益生菌空腹
    if any(k in name_lower for k in ("益生菌", "probio", "乳酸菌")):
        tips.append("🫙 早餐前空腹服用，胃酸最低时活菌存活率最高")

    # 规则0b: 甲基化组合
    if any(k in name_lower for k in ("叶酸", "mthf", "folate")):
        tips.append("🧬 活性叶酸，随餐与甲基B12+B6同服效果最佳")
    if any(k in name_lower for k in ("甲基b12", "methyl b12", "methylcobalamin")):
        tips.append("🧬 甲基化循环核心底物，也可舌下含服提高吸收率")

    # 规则1: 脂溶性维生素随餐服用
    fat_soluble = any(k in name_lower for k in ("vitamin d", "维生素d", "d3", "vitamin a", "维生素a",
                                                   "vitamin e", "维生素e", "vitamin k", "维生素k",
                                                   "omega", "鱼油", "coq10", "辅酶"))
    if fat_soluble:
        tips.append("🍳 随餐服用，脂溶性需油脂辅助吸收")

    # 规则2: 锌/镁随餐避免胃不适
    if any(k in name_lower for k in ("zinc", "锌", "magnesium", "镁")):
        tips.append("🍚 随餐服用，减少胃部不适")

    # 规则3: 注射日窗口（如睾酮注射后避免大量抗氧化剂）
    if ctx.get("is_injection_day"):
        is_antioxidant = any(k in name_lower for k in (
            "抗氧化", "antioxidant", "vitamin c", "维生素c", "vc",
            "glutathione", "谷胱甘肽", "nac"
        ))
        if is_antioxidant:
            tips.append("💉 注射日：大剂量抗氧化剂可能影响药效，建议间隔4h+")

    # 规则4: 高强度运动后不宜立即服用抗氧化剂（影响运动适应）
    if ctx.get("high_intensity"):
        is_antioxidant = any(k in name_lower for k in (
            "vitamin c", "维生素c", "vc", "vitamin e", "维生素e",
            "nac", "glutathione", "谷胱甘肽"
        ))
        if is_antioxidant:
            tips.append("🏃 高强度运动后2h内避免服用，以保留运动适应信号")

    # 规则5: 睡眠差 / HRV低 → 强调镁和B族
    if ctx.get("sleep_quality") == "poor" or ctx.get("hrv_below_avg"):
        if any(k in name_lower for k in ("magnesium", "镁", "mag")):
            tips.append("😴 睡眠欠佳，镁有助放松和睡眠改善")
        if any(k in name_lower for k in ("b6", "b12", "b族", "b-complex", "甲基b")):
            tips.append("😴 HRV偏低，B族支持神经修复")

    # 规则6: 鼻炎发作 → 强调槲皮素/VC/益生菌
    if ctx.get("rhinitis_active"):
        if any(k in name_lower for k in ("quercetin", "槲皮素")):
            tips.append("👃 鼻炎活跃期，槲皮素是天然抗组胺")
        if any(k in name_lower for k in ("vitamin c", "维生素c", "vc")):
            tips.append("👃 鼻炎期间VC支持免疫，可适当加量")
        if any(k in name_lower for k in ("probio", "益生菌", "乳酸菌")):
            tips.append("👃 益生菌调节免疫平衡，对过敏有辅助作用")

    # 规则7: 铁剂与钙/茶/咖啡间隔
    if any(k in name_lower for k in ("iron", "铁")):
        tips.append("☕ 与咖啡/茶/钙间隔2h，搭配VC促进吸收")

    # 规则8: 褪黑素仅睡前
    if any(k in name_lower for k in ("melatonin", "褪黑素")):
        if supp.timing != "bedtime":
            tips.append("⚠️ 建议调整到睡前30分钟服用")

    return tips


def _generate_alerts(ctx: dict, supps: list) -> List[Dict[str, str]]:
    """生成全局提醒/预警"""
    alerts = []

    if ctx.get("sleep_quality") == "poor":
        score = ctx.get("sleep_score", "")
        alerts.append({
            "level": "warning",
            "icon": "😴",
            "message": f"昨晚睡眠质量差{f'（{score}分）' if score else ''}，今天注意镁和B族的补充，避免咖啡因过量",
        })

    if ctx.get("hrv_below_avg"):
        alerts.append({
            "level": "info",
            "icon": "💓",
            "message": "HRV低于7日均值，身体可能需要更多恢复，确保补剂按时服用",
        })

    if ctx.get("is_injection_day"):
        meds = ctx.get("injection_meds", [])
        med_name = meds[0] if meds else "注射药物"
        alerts.append({
            "level": "important",
            "icon": "💉",
            "message": f"今日为{med_name}注射日，大剂量抗氧化剂(VC/NAC/谷胱甘肽)建议间隔4小时",
        })

    if ctx.get("rhinitis_active"):
        alerts.append({
            "level": "info",
            "icon": "👃",
            "message": "鼻炎症状活跃，加强槲皮素/VC/益生菌，注意避免过敏原",
        })

    if ctx.get("high_intensity"):
        alerts.append({
            "level": "info",
            "icon": "🏃",
            "message": "今日有高强度运动，运动后2小时内避免大剂量抗氧化剂",
        })

    return alerts


def _build_medication_section(
    active_meds: list, med_log_ids: set, today: date
) -> List[Dict[str, Any]]:
    """构建今日用药提醒"""
    meds = []
    for m in active_meds:
        meds.append({
            "id": m.id,
            "name": m.name,
            "dosage": m.dosage or "",
            "frequency": m.frequency or "",
            "purpose": m.purpose or "",
            "taken_today": m.id in med_log_ids,
            "reminder_times": m.reminder_times or [],
        })
    return meds


def _build_summary(supps: list, taken_records: dict) -> Dict[str, Any]:
    """生成完成摘要"""
    total = len(supps)
    taken = sum(
        1 for s in supps
        if s.id in taken_records and taken_records[s.id].taken
    )
    return {
        "total": total,
        "taken": taken,
        "remaining": total - taken,
        "completion_rate": round(taken / total * 100) if total > 0 else 0,
    }


# ── 动态推荐引擎 ─────────────────────────────────────
# 基于整合医学评估报告的服用顺序和交互规则

def _generate_recommendations(
    ctx: dict, supps: list, taken_records: dict
) -> List[Dict[str, Any]]:
    """基于当前身体状况生成动态服用建议"""
    recs = []
    supp_names = {(s.name or "").lower() for s in supps}
    hour = datetime.now().hour

    # ── 服用顺序建议（基于当前时间段） ──
    if hour < 11:
        recs.append({
            "type": "order",
            "icon": "📋",
            "title": "早晨服用顺序",
            "message": "空腹先服益生菌 → 等15min → MitoQ+NAC → 早餐随餐：叶酸+B12+D3K2+鱼油+肌酸+槲皮素+VC+B6",
            "priority": "high",
        })
    elif 17 <= hour < 20:
        recs.append({
            "type": "order",
            "icon": "📋",
            "title": "晚餐服用提醒",
            "message": "锌随晚餐服用，不要与早晨的钙/铁同时",
            "priority": "medium",
        })
    elif hour >= 21:
        recs.append({
            "type": "order",
            "icon": "📋",
            "title": "睡前提醒",
            "message": "甘氨酸镁在睡前30-60分钟服用，促进深度睡眠",
            "priority": "medium",
        })

    # ── 交互提醒 ──
    has_nac = any("nac" in n for n in supp_names)
    has_vc = any(k in n for n in supp_names for k in ("维生素c", "vitamin c"))
    if has_nac and has_vc:
        recs.append({
            "type": "interaction",
            "icon": "⚠️",
            "title": "NAC 与 VC 交互",
            "message": "NAC 和维生素C 建议间隔1小时服用，NAC 空腹先服",
            "priority": "medium",
        })

    # ── 甲基化通路强调 ──
    has_folate = any(k in n for n in supp_names for k in ("叶酸", "mthf", "folate"))
    has_b12 = any(k in n for n in supp_names for k in ("b12", "甲基b"))
    if has_folate and has_b12:
        recs.append({
            "type": "synergy",
            "icon": "🧬",
            "title": "甲基化协同",
            "message": "5-MTHF + 甲基B12 + B6 是甲基化循环三驾马车，一起随餐服用效果最佳",
            "priority": "low",
        })

    # ── 基于身体状态的动态调整 ──
    if ctx.get("sleep_quality") == "poor":
        recs.append({
            "type": "adjust",
            "icon": "😴",
            "title": "睡眠恢复方案",
            "message": f"睡眠评分 {ctx.get('sleep_score', '偏低')}，今晚甘氨酸镁可加至3粒，B6支持GABA合成帮助入睡",
            "priority": "high",
        })

    if ctx.get("rhinitis_active"):
        sneezes = ctx.get("sneeze_count", 0)
        msg = "鼻炎活跃"
        if sneezes:
            msg = f"今日已打喷嚏{sneezes}次"
        recs.append({
            "type": "adjust",
            "icon": "👃",
            "title": "鼻炎应对加强",
            "message": f"{msg}，建议：①槲皮素今日可加至1000mg ②VC加至1000mg ③确保益生菌已服用 ④需要时服用西替利嗪",
            "priority": "high",
        })

    if ctx.get("has_exercise"):
        types = ctx.get("exercise_types", [])
        ex_str = "、".join(types[:3]) if types else "运动"
        if ctx.get("high_intensity"):
            recs.append({
                "type": "adjust",
                "icon": "🏋️",
                "title": "运动后恢复",
                "message": f"今日{ex_str}（高强度），运动后2h再服VC/NAC；肌酸今日尤其重要，确保已服用",
                "priority": "high",
            })
        else:
            recs.append({
                "type": "adjust",
                "icon": "💪",
                "title": "运动日营养",
                "message": f"今日{ex_str}，肌酸+Omega-3支持肌肉恢复，确保已随餐服用",
                "priority": "medium",
            })

    if ctx.get("hrv_below_avg"):
        hrv_val = ctx.get("hrv_value")
        recs.append({
            "type": "adjust",
            "icon": "💓",
            "title": "HRV恢复建议",
            "message": f"HRV {hrv_val}ms 低于均值，Omega-3+镁+B族是改善HRV的核心三件套",
            "priority": "high",
        })

    if ctx.get("is_injection_day"):
        recs.append({
            "type": "timing",
            "icon": "💉",
            "title": "注射日时间规划",
            "message": "注射前正常服用补剂，注射后4小时内避免大剂量VC/NAC/MitoQ",
            "priority": "high",
        })

    # 排序: high > medium > low
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: priority_order.get(r.get("priority", "low"), 2))

    return recs
