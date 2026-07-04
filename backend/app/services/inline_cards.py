"""Inline chat cards service

在对话 SSE `done` 事件里附加 `cards: [{type, data}]`, 前端 Web/iPad + Expo iPhone 自动渲染.

设计原则:
- 纯查询, 不改写数据; 单 builder 失败降级跳过, 但绝不静默 —— 组装后输出
  telemetry: builder 真异常 (卡片被 DROP) 走 WARNING, gate 未命中 (正常) 走 DEBUG
- 关键词 + Twin 数据双门限, 两者都命中才推卡片
- 单次最多 3 张卡, 避免过度干扰阅读
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.services import agenda_service
from app.services.health_operating_review import build_health_operating_review
from app.services.intake_intent_classifier import classify_intake_intent
from app.services.metric_chart_cards import build_metric_chart

logger = logging.getLogger(__name__)

MAX_CARDS = 3


def _is_record_intent(q: str) -> bool:
    return bool(re.search(r"记录|打卡|吃了|喝了|服药|刚吃|刚喝", q))


def _is_runtime_agenda_query(q: str) -> bool:
    ql = q.lower()
    if re.search(r"7天|七天|未来|接下来|接下去|这周|一周|计划|安排|编排|运行时|下一步|该做|重点", ql):
        return True
    if re.search(r"今天怎么样|今日如何|健康状况|健康行动|怎么改善|怎么做", ql):
        return True
    return False


def _is_operating_review_query(q: str) -> bool:
    ql = q.lower()
    if _is_record_intent(ql):
        return False
    return bool(re.search(r"复盘|回测|预测.*实际|预测.*结果|效果怎么样|有没有改善|有没有变好|进展|成果|本周效果|这周效果", ql))


def _review_window_days(q: str) -> int:
    ql = q.lower()
    if re.search(r"90天|九十天|三个月|3个月|长期", ql):
        return 90
    if re.search(r"30天|三十天|一个月|月度|最近一月", ql):
        return 30
    return 7


def _compact_runtime_day(day: Dict[str, Any]) -> Dict[str, Any]:
    next_action = day.get("next_action") if isinstance(day.get("next_action"), dict) else None
    item_count = 0
    for window in day.get("time_windows") or []:
        if isinstance(window, dict) and isinstance(window.get("items"), list):
            item_count += len(window["items"])
    return {
        "date": day.get("date"),
        "next_action_title": next_action.get("title") if next_action else None,
        "items_count": item_count,
    }


def _compact_metric_changes(metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(metrics, dict):
        return out
    for metric, change in metrics.items():
        if not isinstance(change, dict):
            continue
        if change.get("status") != "present" or change.get("delta") is None:
            continue
        out.append({
            "metric": metric,
            "count": change.get("count"),
            "current": change.get("current"),
            "current_date": change.get("current_date"),
            "delta": change.get("delta"),
        })
    return out[:4]


def _compact_prediction_backtest(backtest: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(backtest, dict):
        return {}
    results = [
        result
        for result in (backtest.get("results") or [])
        if isinstance(result, dict)
    ][:2]
    return {
        "version": backtest.get("version"),
        "status": backtest.get("status"),
        "reason": backtest.get("reason"),
        "ready_candidate_count": backtest.get("ready_candidate_count"),
        "candidate_count": backtest.get("candidate_count"),
        "summary": backtest.get("summary") if isinstance(backtest.get("summary"), dict) else None,
        "confidence_summary": (
            backtest.get("confidence_summary")
            if isinstance(backtest.get("confidence_summary"), dict)
            else None
        ),
        "results": results,
        "boundary": backtest.get("boundary"),
    }


def _compact_causal_memory(memory: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(memory, dict):
        return {"notes": [], "claim_boundary": None}
    notes = [note for note in (memory.get("notes") or []) if isinstance(note, dict)][:2]
    return {
        "notes": notes,
        "claim_boundary": memory.get("claim_boundary"),
    }


def _metric_history_route_type(metric: Optional[str]) -> str:
    return {
        "resting_heart_rate": "heart_rate",
    }.get(metric or "", metric or "hrv")


def _metric_history_label(data: Dict[str, Any]) -> str:
    metric = data.get("metric")
    label = data.get("label")
    if metric == "hrv":
        return "查看HRV历史"
    if isinstance(label, str) and label.strip():
        return f"查看{label.strip()}历史"
    return "查看指标历史"


_AGENDA_COMPLETE_SOURCE_TYPES = {"health_protocol", "medication", "supplement"}
_MEAL_LABELS = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "snack": "加餐",
}


def _normalize_agenda_source(source: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(source, dict):
        return None
    object_type = source.get("object_type")
    object_id = source.get("object_id")
    if not isinstance(object_type, str) or object_type not in _AGENDA_COMPLETE_SOURCE_TYPES:
        return None
    try:
        oid = int(object_id)
    except (TypeError, ValueError):
        return None
    if oid <= 0:
        return None
    return {"object_type": object_type, "object_id": oid}


def _runtime_agenda_actions(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    action = data.get("next_action") if isinstance(data.get("next_action"), dict) else {}
    title = action.get("title") if isinstance(action.get("title"), str) else "当前行动"
    source = _normalize_agenda_source(action.get("source"))
    actions: List[Dict[str, Any]] = []

    if source:
        actions.append({
            "id": "complete-runtime-action",
            "label": "完成",
            "action": "agenda.complete",
            "endpoint": "/agenda/complete",
            "requires_manual_confirm": True,
            "payload": {
                "source": source,
                "status": "done",
                "track": "manual",
            },
            "style": "primary",
            "confirmation": {
                "title": f"完成：{title}？",
                "detail": "将写入今天的健康运行时执行记录。",
                "confirm_label": "确认完成",
                "cancel_label": "再看看",
            },
            "optimistic": True,
        })
    else:
        actions.append({
            "id": "complete-runtime-action",
            "label": "完成",
            "action": "agenda.complete",
            "endpoint": "/agenda/complete",
            "requires_manual_confirm": True,
            "payload": {},
            "style": "primary",
            "disabled_reason": "当前行动缺少可完成的来源,请进入7天计划处理",
        })

    actions.append({
        "id": "open-runtime-agenda",
        "label": "查看7天计划",
        "action": "route.open",
        "payload": {"route": "/agenda"},
        "style": "secondary",
    })
    return actions


def _is_water_only_record(q: str) -> bool:
    return bool(re.search(r"(喝水|饮水|温水|白水|矿泉水|纯净水|喝了?\s*\d+\s*(?:ml|毫升).{0,4}水)", q, re.I))


def _looks_like_diet_record(q: str) -> bool:
    return classify_intake_intent(q).kind == "diet"


def _infer_meal_type_from_query(q: str) -> str:
    if re.search(r"早餐|早饭|早上", q):
        return "breakfast"
    if re.search(r"午餐|中饭|中午", q):
        return "lunch"
    if re.search(r"晚餐|晚饭|晚上", q):
        return "dinner"
    if re.search(r"加餐|零食|夜宵|下午茶", q):
        return "snack"
    hour = datetime.now().hour
    if hour < 10:
        return "breakfast"
    if hour < 14:
        return "lunch"
    if hour < 20:
        return "dinner"
    return "snack"


def _as_payload_number(value: float) -> int | float:
    rounded = round(float(value), 1)
    return int(rounded) if rounded.is_integer() else rounded


def _extract_number(q: str, *patterns: str) -> Optional[int | float]:
    for pattern in patterns:
        m = re.search(pattern, q, re.I)
        if not m:
            continue
        try:
            return _as_payload_number(float(m.group(1)))
        except (TypeError, ValueError):
            continue
    return None


def _strip_nutrition_tokens(q: str) -> str:
    cleaned = re.sub(r"(?:热量|约|大约|总共)?\s*\d+(?:\.\d+)?\s*(?:kcal|千卡|大卡|卡路里)", " ", q, flags=re.I)
    cleaned = re.sub(r"(?:蛋白质?|protein)\s*\d+(?:\.\d+)?\s*(?:g|克)?", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"(?:碳水|carbs?|碳水化合物)\s*\d+(?:\.\d+)?\s*(?:g|克)?", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"(?:脂肪|fat)\s*\d+(?:\.\d+)?\s*(?:g|克)?", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"(?:纤维|fiber|膳食纤维)\s*\d+(?:\.\d+)?\s*(?:g|克)?", " ", cleaned, flags=re.I)
    return cleaned


def _extract_food_items(q: str) -> Optional[str]:
    cleaned = _strip_nutrition_tokens(q)
    cleaned = re.sub(r"[，,;；。]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    patterns = [
        r"(?:早餐|早饭|午餐|中饭|晚餐|晚饭|加餐|夜宵|零食)?\s*(?:吃了|吃的是|吃|点了)\s*(.+)",
        r"(?:早餐|早饭|午餐|中饭|晚餐|晚饭|加餐|夜宵|零食)\s*[:：]?\s*(.+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, cleaned)
        if not m:
            continue
        food = m.group(1).strip(" ：:，,;；。")
        food = re.sub(r"^(?:一份|一个|一碗|一杯|了)\s*", "", food)
        food = re.sub(r"\s+", " ", food).strip()
        if food:
            return food[:160]
    return None


def _diet_draft_actions(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    meal_type = data.get("meal_type") if isinstance(data.get("meal_type"), str) else "snack"
    meal_label = _MEAL_LABELS.get(meal_type, "餐食")
    record: Dict[str, Any] = {
        "meal_type": meal_type,
        "food_items": data.get("food_items"),
    }
    for key in ("calories", "protein", "carbs", "fat", "fiber"):
        if data.get(key) is not None:
            record[key] = data[key]
    confidence = data.get("confidence")
    if isinstance(confidence, (int, float)):
        record["notes"] = f"来源: chat; 置信度 {round(float(confidence) * 100)}%"
    return [
        {
            "id": "confirm-diet-draft",
            "label": "确认记录",
            "action": "diet_record.create",
            "endpoint": "/diet/records",
            "requires_manual_confirm": True,
            "payload": {"record": record},
            "style": "primary",
            "confirmation": {
                "title": f"记录这顿{meal_label}？",
                "detail": "确认后会写入今天的饮食记录，可稍后在饮食页修正。",
                "confirm_label": "确认记录",
                "cancel_label": "再看看",
            },
            "optimistic": True,
        },
        {
            "id": "open-diet-edit",
            "label": "去饮食页修正",
            "action": "route.open",
            "payload": {"route": _diet_draft_route(data)},
            "style": "secondary",
        },
    ]


def _diet_draft_route(data: Dict[str, Any]) -> str:
    params: Dict[str, Any] = {
        "draft": "diet",
        "meal_type": data.get("meal_type") or "snack",
        "food_items": data.get("food_items") or "",
    }
    for key in ("calories", "protein", "carbs", "fat"):
        if data.get(key) is not None:
            params[key] = data[key]
    return f"/diet?{urlencode(params)}"


def _medication_draft_actions(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    name = data.get("medication_name") if isinstance(data.get("medication_name"), str) else ""
    prompt = f"请帮我核对{name}的用药记录，不要建议我自行停药、换药或改剂量。" if name else "请帮我核对刚才的用药记录。"
    return [
        {
            "id": "open-medication-draft",
            "label": "去用药页记录",
            "action": "route.open",
            "payload": {
                "route": f"/medications?{urlencode({'draft': 'medication', 'name': name})}",
            },
            "style": "primary",
        },
        {
            "id": "ask-medication-draft",
            "label": "问阿衡",
            "action": "route.open",
            "payload": {
                "route": f"/chat?{urlencode({'prompt': prompt})}",
            },
            "style": "secondary",
        },
    ]


# ── individual builders ────────────────────────────────────────────

def _build_metric_chart(db: Session, user_id: int, q: str) -> Optional[Dict[str, Any]]:
    return build_metric_chart(db, user_id=user_id, query=q)


def _build_operating_review(db: Session, user_id: int, q: str) -> Optional[Dict[str, Any]]:
    if not _is_operating_review_query(q):
        return None
    window_days = _review_window_days(q)
    try:
        payload = build_health_operating_review(
            db,
            user_id=user_id,
            window_days=window_days,
        )
    except Exception as e:
        logger.debug("operating review card failed: %s", e)
        return None
    if not isinstance(payload, dict):
        return None

    execution = payload.get("execution") if isinstance(payload.get("execution"), dict) else {}
    backtest = _compact_prediction_backtest(payload.get("prediction_backtest") or {})
    metrics = _compact_metric_changes(payload.get("metrics") or {})
    memory = _compact_causal_memory(payload.get("causal_memory") or {})

    return {
        "window_days": payload.get("window_days") or window_days,
        "start_date": payload.get("start_date"),
        "end_date": payload.get("end_date"),
        "execution": {
            "total_events": execution.get("total_events", 0),
            "completed_events": execution.get("completed_events", 0),
            "completion_rate": execution.get("completion_rate", 0),
        },
        "metrics": metrics,
        "prediction_backtest": backtest,
        "causal_memory": memory,
    }


def _build_runtime_agenda(db: Session, user_id: int, q: str) -> Optional[Dict[str, Any]]:
    if _is_record_intent(q) or not _is_runtime_agenda_query(q):
        return None
    try:
        payload = agenda_service.runtime_range_view(
            db,
            user_id,
            days=7,
            max_items_per_day=3,
        )
    except Exception as e:
        logger.debug("runtime agenda card failed: %s", e)
        return None

    if not isinstance(payload, dict):
        return None
    action = payload.get("next_action")
    if not isinstance(action, dict):
        for day in payload.get("days") or []:
            if isinstance(day, dict) and isinstance(day.get("next_action"), dict):
                action = day["next_action"]
                break
    if not isinstance(action, dict):
        return None

    runtime_context = action.get("runtime_context")
    if not isinstance(runtime_context, dict):
        runtime_context = {}
    root_context = payload.get("runtime_context")
    if not isinstance(root_context, dict):
        root_context = {}
    verification_window = runtime_context.get("verification_window")
    if not isinstance(verification_window, dict):
        verification_window = {}
    metrics = [
        str(metric)
        for metric in verification_window.get("metrics") or []
        if isinstance(metric, (str, int, float)) and str(metric).strip()
    ][:3]

    return {
        "mode": payload.get("mode"),
        "generated_by": payload.get("generated_by"),
        "horizon_days": payload.get("horizon_days"),
        "start": payload.get("start"),
        "end": payload.get("end"),
        "safety_boundary": (
            root_context.get("safety_boundary")
            or runtime_context.get("safety_boundary")
        ),
        "next_action": {
            "id": action.get("id"),
            "title": action.get("title"),
            "kind": action.get("type"),
            "source": action.get("source") if isinstance(action.get("source"), dict) else None,
            "time_window": action.get("time_window"),
            "priority_tier": action.get("priority_tier"),
            "current_state_summary": runtime_context.get("current_state_summary"),
            "replan_reason": runtime_context.get("replan_reason"),
            "verification_metrics": metrics,
            "verification_window_days": verification_window.get("window_days"),
        },
        "days": [
            _compact_runtime_day(day)
            for day in (payload.get("days") or [])[:7]
            if isinstance(day, dict)
        ],
    }


def _build_diet_draft(db: Session, user_id: int, q: str) -> Optional[Dict[str, Any]]:
    intent = classify_intake_intent(q)
    if intent.kind != "diet":
        return None
    food_items = intent.text or _extract_food_items(q)
    if not food_items:
        return None
    meal_type = intent.slots.get("meal_type") if isinstance(intent.slots.get("meal_type"), str) else _infer_meal_type_from_query(q)
    calories = _extract_number(
        q,
        r"(?:热量|约|大约|总共)?\s*(\d+(?:\.\d+)?)\s*(?:kcal|千卡|大卡|卡路里)",
    )
    protein = _extract_number(q, r"(?:蛋白质?|protein)\s*(\d+(?:\.\d+)?)\s*(?:g|克)?")
    carbs = _extract_number(q, r"(?:碳水|carbs?|碳水化合物)\s*(\d+(?:\.\d+)?)\s*(?:g|克)?")
    fat = _extract_number(q, r"(?:脂肪|fat)\s*(\d+(?:\.\d+)?)\s*(?:g|克)?")
    fiber = _extract_number(q, r"(?:纤维|fiber|膳食纤维)\s*(\d+(?:\.\d+)?)\s*(?:g|克)?")
    confidence = 0.82 if calories is not None or sum(x is not None for x in (protein, carbs, fat, fiber)) >= 2 else 0.62

    data: Dict[str, Any] = {
        "meal_type": meal_type,
        "food_items": food_items,
        "confidence": confidence,
        "source": "chat",
        "suggestions": [
            "确认后更新今日饮食进度",
            "如估算不准，可去饮食页修正",
        ],
        "boundary": "营养为估算值,确认后写入今日饮食记录。",
    }
    for key, value in {
        "calories": calories,
        "protein": protein,
        "carbs": carbs,
        "fat": fat,
        "fiber": fiber,
    }.items():
        if value is not None:
            data[key] = value
    if meal_type in {"lunch", "dinner"} or (isinstance(calories, (int, float)) and calories >= 300):
        data["post_meal_walk"] = {"recommended": True, "minutes": 10}
    return data


def _build_medication_draft(db: Session, user_id: int, q: str) -> Optional[Dict[str, Any]]:
    intent = classify_intake_intent(q)
    if intent.kind != "medication":
        return None
    medication_name = intent.text.strip()
    if not medication_name:
        return None
    data: Dict[str, Any] = {
        "medication_name": medication_name,
        "confidence": intent.confidence,
        "source": "chat",
        "suggestions": [
            "确认前核对药名、剂量和服用时间",
            "如药品不在清单中, 先添加到用药管理",
        ],
        "boundary": "确认后记录为已服用; 不替代医嘱, 不调整剂量。",
    }
    if intent.slots.get("dose"):
        data["dose"] = intent.slots["dose"]
    if intent.slots.get("taken_time"):
        data["taken_time"] = intent.slots["taken_time"]
    return data


def _build_vitals(db: Session, user_id: int, q: str) -> Optional[Dict[str, Any]]:
    if _is_record_intent(q):
        return None
    kw_any = re.search(r"综合|整体|今日如何|健康如何|今天怎么样", q)
    multi_hits = sum(1 for k in ["睡眠", "心率", "hrv", "电量", "步数", "压力"] if k in q.lower())
    if not kw_any and multi_hits < 2:
        return None
    try:
        from app.services.garmin_daily_merged import merged_daily_rows
        _t = date.today()
        _rows = merged_daily_rows(db, user_id, since=_t, until=_t)
        g = _rows[0] if _rows else None
        if not g:
            return None
        d: Dict[str, Any] = {}
        if g.total_sleep_duration:
            d["sleep"] = f"{g.total_sleep_duration/60:.1f}h"
        if g.resting_heart_rate:
            d["hr"] = f"{g.resting_heart_rate}bpm"
        if getattr(g, "hrv", None) is not None:
            d["hrv"] = f"{float(g.hrv):.1f}ms"
        if g.body_battery_most_charged:
            d["battery"] = str(g.body_battery_most_charged)
        if g.steps:
            d["steps"] = f"{g.steps:,}"
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
        from app.services.garmin_daily_merged import merged_daily_rows
        _t = date.today()
        _rows = merged_daily_rows(db, user_id, since=_t, until=_t)
        g = _rows[0] if _rows else None
        if not g:
            return None
        d: Dict[str, Any] = {}
        if getattr(g, "sleep_score", None) is not None:
            d["score"] = g.sleep_score
        if g.total_sleep_duration:
            d["duration_h"] = g.total_sleep_duration / 60
        if getattr(g, "deep_sleep_duration", None) is not None:
            d["deep_min"] = round(g.deep_sleep_duration)
        if getattr(g, "rem_sleep_duration", None) is not None:
            d["rem_min"] = round(g.rem_sleep_duration)
        if getattr(g, "light_sleep_duration", None) is not None:
            d["light_min"] = round(g.light_sleep_duration)
        awake = getattr(g, "awake_duration", None)
        if awake is not None:
            d["awake_min"] = round(awake)
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
        if not recs:
            return None
        recs_asc = list(reversed(recs))
        vals = [float(r.weight) for r in recs_asc if getattr(r, "weight", None) is not None]
        if not vals:
            return None
        out: Dict[str, Any] = {"current_kg": vals[-1], "trend_7d": vals}
        if len(vals) >= 2:
            out["change_7d_kg"] = round(vals[-1] - vals[0], 2)
        bmi = getattr(recs_asc[-1], "bmi", None)
        if bmi is not None:
            out["bmi"] = float(bmi)
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
        if not r or r.systolic is None or r.diastolic is None:
            return None
        s, d = r.systolic, r.diastolic
        if s >= 180 or d >= 120:
            cat, col = "高血压急症", "#AF52DE"
        elif s >= 140 or d >= 90:
            cat, col = "高血压 2 期", "#FF453A"
        elif s >= 130 or d >= 80:
            cat, col = "高血压 1 期", "#FF6723"
        elif s >= 120 and d < 80:
            cat, col = "血压升高", "#FF9F0A"
        elif s < 90 or d < 60:
            cat, col = "偏低", "#5AC8FA"
        else:
            cat, col = "正常", "#30D158"
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
                          SupplementDefinition.is_active)
                  .all())
        if not defs:
            return None
        today_str = date.today().isoformat()
        taken_ids = set(r.supplement_id for r in (db.query(SupplementRecord)
                                                    .filter(SupplementRecord.user_id == user_id,
                                                            SupplementRecord.record_date == today_str,
                                                            SupplementRecord.taken)
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
    ("medication_draft", _build_medication_draft),
    ("diet_draft", _build_diet_draft),
    ("metric_chart", _build_metric_chart),
    ("operating_review", _build_operating_review),
    ("runtime_agenda", _build_runtime_agenda),
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
    单次 ≤ MAX_CARDS. 单 builder 异常不阻塞其他卡片, 返回 shape 不变;
    但组装后必须输出 telemetry —— builder 真异常 (卡片被 DROP, 与"当天本来就没数据"
    是两回事) 走 WARNING 带 builder 名 + 异常 repr, gate 未命中 (正常) 走 DEBUG。
    """
    if not query or len(query) > 500:
        return []
    out: List[Dict[str, Any]] = []
    considered: List[str] = []
    emitted: List[str] = []
    gate_miss: List[str] = []
    dropped: List[Dict[str, str]] = []
    for card_type, builder in _BUILDERS:
        if card_type == "record_intent_skip":
            continue
        considered.append(card_type)
        try:
            data = builder(db, user_id, query)
            if not data:
                gate_miss.append(card_type)
                continue
            card: Dict[str, Any] = {"type": card_type, "data": data}
            if card_type == "runtime_agenda":
                card["actions"] = _runtime_agenda_actions(data)
            if card_type == "medication_draft":
                card["actions"] = _medication_draft_actions(data)
            if card_type == "diet_draft":
                card["actions"] = _diet_draft_actions(data)
            if card_type == "operating_review":
                card["actions"] = [
                    {
                        "id": "open-operating-review",
                        "label": "查看复盘详情",
                        "action": "route.open",
                        "payload": {"route": "/my-progress"},
                        "style": "primary",
                    }
                ]
            if card_type == "metric_chart":
                metric = data.get("metric") if isinstance(data, dict) else None
                route_type = _metric_history_route_type(metric)
                card["actions"] = [
                    {
                        "id": f"open-{metric or 'metric'}-history",
                        "label": _metric_history_label(data) if isinstance(data, dict) else "查看指标历史",
                        "action": "route.open",
                        "payload": {
                            "route": f"/indicator-history?type={route_type}",
                        },
                        "style": "secondary",
                    }
                ]
            out.append(card)
            emitted.append(card_type)
            if len(out) >= MAX_CARDS:
                break
        except Exception as e:
            logger.debug("[inline_cards] builder %s raised: %s", card_type, e)
            dropped.append({"builder": card_type, "reason": repr(e)})
    # 组装 telemetry: 有 builder 真异常 → WARNING (fail-loud, 历史上此类静默丢卡
    # 造成过多次线上事故); 全部正常 (含 gate 未命中) → DEBUG。不记 query 原文 (隐私)。
    if dropped:
        logger.warning(
            "[inline_cards] user=%s composition dropped=%s considered=%s emitted=%s gate_miss=%s",
            user_id, dropped, considered, emitted, gate_miss,
        )
    else:
        logger.debug(
            "[inline_cards] user=%s composition considered=%s emitted=%s gate_miss=%s",
            user_id, considered, emitted, gate_miss,
        )
    return out


# ── LLM-emitted card extraction ────────────────────────────────────
# LLM 在回复里主动输出 fenced ```menu_share JSON 块 → 提取成结构化卡片下发前端

_FENCED_CARD_RE = re.compile(
    r"```(menu_share)\s*\n(\{[\s\S]*?\})\s*\n```",
    re.MULTILINE,
)

# 允许 LLM 主动输出的 card 类型白名单
_LLM_CARD_TYPES = {"menu_share"}


def _validate_menu_share(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """校验 + 清洗 menu_share schema. 防止 LLM 漏字段崩前端."""
    if not isinstance(d, dict):
        return None
    title = (d.get("title") or "").strip()
    items_raw = d.get("items")
    if not title or not isinstance(items_raw, list) or not items_raw:
        return None
    norm_items: List[Dict[str, Any]] = []
    for it in items_raw:
        if not isinstance(it, dict):
            continue
        name = it.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        entry: Dict[str, Any] = {"name": name.strip()}
        if isinstance(it.get("qty"), str):
            entry["qty"] = it["qty"]
        for k in ("kcal", "protein", "carbs", "fat", "fiber"):
            v = it.get(k)
            if isinstance(v, (int, float)):
                entry[k] = v
        norm_items.append(entry)
    if not norm_items:
        return None
    out: Dict[str, Any] = {"title": title, "items": norm_items}
    if isinstance(d.get("reason"), str):
        out["reason"] = d["reason"]
    totals = d.get("totals")
    if isinstance(totals, dict):
        norm_totals: Dict[str, Any] = {}
        for k in ("kcal", "protein", "carbs", "fat", "fiber"):
            v = totals.get(k)
            if isinstance(v, (int, float)):
                norm_totals[k] = v
        if norm_totals:
            out["totals"] = norm_totals
    sl = d.get("shopping_list")
    if isinstance(sl, list):
        norm_sl = [s for s in sl if isinstance(s, str) and s.strip()]
        if norm_sl:
            out["shopping_list"] = norm_sl
    return out


_VALIDATORS = {
    "menu_share": _validate_menu_share,
}


def extract_inline_card_blocks(text: str) -> List[Dict[str, Any]]:
    """从 LLM 完整回复里提取 fenced ```menu_share 之类 JSON 卡片.

    返回 list[{type, data}], 校验失败的块跳过 (静默, 不抛).
    """
    if not text or not isinstance(text, str):
        return []
    out: List[Dict[str, Any]] = []
    try:
        for m in _FENCED_CARD_RE.finditer(text):
            ctype = m.group(1)
            if ctype not in _LLM_CARD_TYPES:
                continue
            raw_json = m.group(2)
            try:
                parsed = json.loads(raw_json)
            except Exception:
                continue
            validator = _VALIDATORS.get(ctype)
            if not validator:
                continue
            data = validator(parsed)
            if data:
                out.append({"type": ctype, "data": data})
    except Exception as e:
        logger.debug("[inline_cards] extract_inline_card_blocks failed: %s", e)
    return out
