"""Inline chat cards service

在对话 SSE `done` 事件里附加 `cards: [{type, data}]`, 前端 Web/iPad + Expo iPhone 自动渲染.

设计原则:
- 纯查询, 不改写数据; 失败静默降级 (空列表)
- 关键词 + Twin 数据双门限, 两者都命中才推卡片
- 单次最多 3 张卡, 避免过度干扰阅读
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MAX_CARDS = 3


def _is_record_intent(q: str) -> bool:
    return bool(re.search(r"记录|打卡|吃了|喝了|服药|刚吃|刚喝", q))


# ── individual builders ────────────────────────────────────────────

def _build_vitals(db: Session, user_id: int, q: str) -> Optional[Dict[str, Any]]:
    if _is_record_intent(q):
        return None
    kw_any = re.search(r"综合|整体|今日如何|健康如何|今天怎么样", q)
    multi_hits = sum(1 for k in ["睡眠", "心率", "hrv", "电量", "步数", "压力"] if k in q.lower())
    if not kw_any and multi_hits < 2:
        return None
    try:
        from app.models.daily_health import GarminData
        today_str = date.today().isoformat()
        g = (db.query(GarminData)
               .filter(GarminData.user_id == user_id, GarminData.record_date == today_str)
               .first())
        if not g:
            return None
        d: Dict[str, Any] = {}
        if g.total_sleep_duration: d["sleep"] = f"{g.total_sleep_duration/60:.1f}h"
        if g.resting_heart_rate: d["hr"] = f"{g.resting_heart_rate}bpm"
        if getattr(g, "hrv", None) is not None: d["hrv"] = f"{float(g.hrv):.1f}ms"
        if g.body_battery_most_charged: d["battery"] = str(g.body_battery_most_charged)
        if g.steps: d["steps"] = f"{g.steps:,}"
        if getattr(g, "stress_level", None) is not None:
            d["stress"] = str(g.stress_level)
        return d or None
    except Exception as e:
        logger.debug("vitals card failed: %s", e)
        return None


def _build_sleep(db: Session, user_id: int, q: str) -> Optional[Dict[str, Any]]:
    if not re.search(r"睡眠|深睡|rem|浅睡|睡得|入睡", q.lower()):
        return None
    try:
        from app.models.daily_health import GarminData
        today_str = date.today().isoformat()
        g = (db.query(GarminData)
               .filter(GarminData.user_id == user_id, GarminData.record_date == today_str)
               .first())
        if not g: return None
        d: Dict[str, Any] = {}
        if getattr(g, "sleep_score", None) is not None: d["score"] = g.sleep_score
        if g.total_sleep_duration: d["duration_h"] = g.total_sleep_duration / 60
        if getattr(g, "deep_sleep_duration", None) is not None: d["deep_min"] = round(g.deep_sleep_duration)
        if getattr(g, "rem_sleep_duration", None) is not None: d["rem_min"] = round(g.rem_sleep_duration)
        if getattr(g, "light_sleep_duration", None) is not None: d["light_min"] = round(g.light_sleep_duration)
        awake = getattr(g, "awake_duration", None)
        if awake is not None: d["awake_min"] = round(awake)
        return d or None
    except Exception as e:
        logger.debug("sleep card failed: %s", e)
        return None


def _build_weight(db: Session, user_id: int, q: str) -> Optional[Dict[str, Any]]:
    if not re.search(r"体重|bmi|胖|瘦|减肥|减脂", q.lower()):
        return None
    if _is_record_intent(q) and not re.search(r"趋势|变化|多少|现在", q):
        return None
    try:
        from app.models.weight import WeightRecord
        recs = (db.query(WeightRecord)
                  .filter(WeightRecord.user_id == user_id)
                  .order_by(desc(WeightRecord.record_date))
                  .limit(7).all())
        if not recs: return None
        recs_asc = list(reversed(recs))
        vals = [float(r.weight) for r in recs_asc if getattr(r, "weight", None) is not None]
        if not vals: return None
        out: Dict[str, Any] = {"current_kg": vals[-1], "trend_7d": vals}
        if len(vals) >= 2: out["change_7d_kg"] = round(vals[-1] - vals[0], 2)
        bmi = getattr(recs_asc[-1], "bmi", None)
        if bmi is not None: out["bmi"] = float(bmi)
        return out
    except Exception as e:
        logger.debug("weight card failed: %s", e)
        return None


def _build_bp(db: Session, user_id: int, q: str) -> Optional[Dict[str, Any]]:
    if not re.search(r"血压|bp|收缩压|舒张压|高压|低压", q.lower()):
        return None
    try:
        from app.models.blood_pressure import BloodPressureRecord
        r = (db.query(BloodPressureRecord)
               .filter(BloodPressureRecord.user_id == user_id)
               .order_by(desc(BloodPressureRecord.measured_at))
               .first())
        if not r or r.systolic is None or r.diastolic is None: return None
        s, d = r.systolic, r.diastolic
        if s >= 180 or d >= 120: cat, col = "高血压急症", "#AF52DE"
        elif s >= 140 or d >= 90: cat, col = "高血压 2 期", "#FF453A"
        elif s >= 130 or d >= 80: cat, col = "高血压 1 期", "#FF6723"
        elif s >= 120 and d < 80: cat, col = "血压升高", "#FF9F0A"
        elif s < 90 or d < 60:    cat, col = "偏低", "#5AC8FA"
        else:                     cat, col = "正常", "#30D158"
        m = r.measured_at
        return {
            "systolic": s, "diastolic": d,
            "pulse": getattr(r, "pulse", None),
            "measured_at": m.strftime("%m-%d %H:%M") if isinstance(m, datetime) else None,
            "category": cat, "category_color": col,
        }
    except Exception as e:
        logger.debug("bp card failed: %s", e)
        return None


def _build_supplement(db: Session, user_id: int, q: str) -> Optional[Dict[str, Any]]:
    if not re.search(r"补剂吃了吗|补剂进度|今天吃了什么补剂|补剂状态|补剂打卡|未吃的补剂", q):
        return None
    try:
        from app.models.supplement import SupplementDefinition, SupplementRecord
        defs = (db.query(SupplementDefinition)
                  .filter(SupplementDefinition.user_id == user_id,
                          SupplementDefinition.is_active == True)
                  .all())
        if not defs: return None
        today_str = date.today().isoformat()
        taken_ids = set(r.supplement_id for r in (db.query(SupplementRecord)
                                                    .filter(SupplementRecord.user_id == user_id,
                                                            SupplementRecord.record_date == today_str,
                                                            SupplementRecord.taken == True)
                                                    .all()))
        checked = sum(1 for s in defs if s.id in taken_ids)
        pending_names = [s.name for s in defs if s.id not in taken_ids]
        return {"checked": checked, "total": len(defs), "pending_names": pending_names}
    except Exception as e:
        logger.debug("supplement card failed: %s", e)
        return None


def _build_weather(db: Session, user_id: int, q: str) -> Optional[Dict[str, Any]]:
    # 环境卡片由前端用已缓存的 weather/aqi 兜底, 后端不重复拉
    return None


def _build_diet(db: Session, user_id: int, q: str) -> Optional[Dict[str, Any]]:
    if _is_record_intent(q):
        return None
    if not re.search(r"饮食|吃了什么|今日吃|今天吃|热量|卡路里|蛋白|碳水|脂肪|营养|calories", q.lower()):
        return None
    try:
        from app.models.daily_health import DietRecord
        today = date.today()
        recs = (db.query(DietRecord)
                  .filter(DietRecord.user_id == user_id, DietRecord.record_date == today)
                  .all())
        if not recs:
            return {
                "calories": 0, "meals_count": 0, "meals_by_type": {},
            }
        total_cal = sum((r.calories or 0) for r in recs)
        total_p = round(sum((r.protein or 0) for r in recs), 1)
        total_c = round(sum((r.carbs or 0) for r in recs), 1)
        total_f = round(sum((r.fat or 0) for r in recs), 1)
        total_fi = round(sum((r.fiber or 0) for r in recs), 1)
        by_type: Dict[str, float] = {}
        for r in recs:
            k = r.meal_type or "snack"
            by_type[k] = by_type.get(k, 0) + (r.calories or 0)
        return {
            "calories": int(total_cal),
            "protein": total_p,
            "carbs": total_c,
            "fat": total_f,
            "fiber": total_fi,
            "meals_count": len(recs),
            "meals_by_type": {k: int(v) for k, v in by_type.items()},
        }
    except Exception as e:
        logger.debug("diet card failed: %s", e)
        return None


# ── public dispatcher ──────────────────────────────────────────────

_BUILDERS = [
    ("record_intent_skip", lambda db, uid, q: None),
    ("sleep",        _build_sleep),
    ("weight",       _build_weight),
    ("blood_pressure", _build_bp),
    ("supplement_status", _build_supplement),
    ("diet",         _build_diet),
    ("vitals",       _build_vitals),   # 兜底
]


def build_cards(db: Session, user_id: int, query: str) -> List[Dict[str, Any]]:
    """根据用户输入和 Twin 数据, 构造动态卡片列表

    返回 list[{type, data}], 前端直接塞进 SSE done 事件.
    单次 ≤ MAX_CARDS. 任何异常都降级为空列表.
    """
    if not query or len(query) > 500:
        return []
    out: List[Dict[str, Any]] = []
    for card_type, builder in _BUILDERS:
        if card_type == "record_intent_skip":
            continue
        try:
            data = builder(db, user_id, query)
            if data:
                out.append({"type": card_type, "data": data})
                if len(out) >= MAX_CARDS:
                    break
        except Exception as e:
            logger.debug("[inline_cards] builder %s raised: %s", card_type, e)
    return out
