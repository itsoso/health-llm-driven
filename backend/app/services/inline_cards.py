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
from urllib.parse import quote, urlencode

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.services import agenda_service
from app.services.atomic_capability_registry import attach_action_policy_metadata
from app.services.health_operating_review import build_health_operating_review
from app.services.intake_intent_classifier import classify_intake_intent
from app.services.metric_chart_cards import build_metric_chart
from app.utils.number_format import format_card_numbers

logger = logging.getLogger(__name__)

MAX_CARDS = 3

def attach_card_action_policy_metadata(
    card_type: str,
    actions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Compatibility export for existing inline-card callers and tests."""
    return attach_action_policy_metadata(card_type, actions)


def _is_record_intent(q: str) -> bool:
    return bool(re.search(r"记录|打卡|吃了|喝了|服药|刚吃|刚喝", q))


def _looks_like_food_ui_text(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        value = " ".join(str(item) for item in value if item is not None)
    normalized = re.sub(r"\s+", "", str(value)).lower()
    if not normalized:
        return False
    if re.fullmatch(r"(?:和)?(?:早餐|午餐|晚餐|加餐|餐食)?(?:食品?)?营养卡", normalized):
        return True
    return any(marker in normalized for marker in (
        "营养卡",
        "保存并确认",
        "确认记录",
        "今日饮食",
        "待确认",
        "完成修正",
        "去饮食页修正",
        "看下一餐建议",
    ))


def _runtime_agenda_presentation_mode(q: str) -> Optional[str]:
    """Split an immediate action request from an explicit multi-day horizon.

    "加入今天计划" is a write intent owned by the client confirmation flow.  It
    must not be reinterpreted as a request to synthesize another seven-day plan.
    """
    ql = re.sub(r"\s+", "", q.lower())
    normalized_query = re.sub(r"[？?！!。,.，;；:：]+$", "", ql)
    add_verbs = r"加入|添加|放到|放进|放入|纳入|存到|加到|加进|列入|列到|排进|排到"
    today_targets = r"(?:今天|今日).{0,6}(?:计划|安排|待办)"
    add_to_today = bool(
        re.search(rf"(?:{add_verbs}).{{0,12}}{today_targets}", ql)
        or re.search(rf"{today_targets}.{{0,12}}(?:{add_verbs})", ql)
    )
    if add_to_today:
        return None

    # 运行时卡片只接受明确健康语境，或极短的上下文承接句。不能依赖不断扩张的
    # 非健康黑名单，否则“红烧肉/论文写作”等新对象会持续误触发。
    has_health_context = bool(re.search(
        r"健康(?!类?(?:科技)?产品|科技|产业|行业|项目|会议|论坛|大会)|"
        r"运动(?!会|员|服|赛事|项目|品牌|产品|产业|行业|会议|论坛)|"
        r"睡眠(?!产品|科技|产业|行业|会议|论坛)|恢复|"
        r"康复(?!产品|产业|行业|会议|论坛)|锻炼|训练|步行|跑步|拉伸|冥想|"
        r"呼吸训练|休息(?!室)|饮食|营养(?!产品|产业|行业|会议|论坛)|"
        r"血压|血糖|心率|hrv|体重|腰围|用药|服药|补剂",
        ql,
    ))
    has_non_personal_planning_context = bool(re.search(
        r"产品|品牌|产业|行业|科技|会议|论坛|发布会|赛事|运动员|运动服|休息室",
        ql,
    ))
    has_specific_personal_health_context = bool(re.search(
        r"服药|用药|血压|血糖|心率|hrv|体重|腰围|症状|疼痛|锻炼|训练|"
        r"跑步|步行|拉伸|冥想|呼吸训练|我的(?:睡眠|恢复|康复|饮食|营养)",
        ql,
    ))
    if has_non_personal_planning_context and not has_specific_personal_health_context:
        has_health_context = False
    contextual_short_queries = {
        "下一步",
        "我下一步该做什么",
        "我现在下一步该做什么",
        "现在该做什么",
        "该做什么",
        "今天怎么安排",
        "今日怎么安排",
        "今天的重点",
        "今日重点",
    }
    if not has_health_context and normalized_query not in contextual_short_queries:
        return None

    if re.search(
        r"7天|七天|(?:未来|接下来|接下去).{0,4}(?:天|一周|7|七)|这周|本周|一周|周计划|未来节奏|运行时(?:计划|编排)",
        ql,
    ):
        return "horizon"
    if re.search(
        r"下一步|现在.{0,5}(?:做什么|该做|怎么做)|该做什么|今天.{0,8}(?:怎么|如何|做什么|安排|计划|行动|重点)|今日.{0,8}(?:怎么|如何|做什么|安排|计划|行动|重点)|今天怎么样|今日如何|健康状况|健康状态|健康行动|健康怎么改善|当前重点",
        ql,
    ):
        return "today"
    return None


def _is_runtime_agenda_query(q: str) -> bool:
    return _runtime_agenda_presentation_mode(q) is not None


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


def _normalize_daily_plan_action_source(source: Any) -> Optional[str]:
    if not isinstance(source, dict) or source.get("object_type") != "daily_plan_action":
        return None
    action_id = str(source.get("object_id") or "").strip()
    if not action_id or len(action_id) > 160:
        return None
    if not re.fullmatch(r"[A-Za-z0-9._:-]+", action_id):
        return None
    return action_id


def _runtime_agenda_actions(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    action = data.get("next_action") if isinstance(data.get("next_action"), dict) else {}
    title = action.get("title") if isinstance(action.get("title"), str) else "当前行动"
    source = _normalize_agenda_source(action.get("source"))
    daily_plan_action_id = _normalize_daily_plan_action_source(action.get("source"))
    actions: List[Dict[str, Any]] = []

    if source:
        actions.append({
            "id": "complete-runtime-action",
            "label": "完成这一步",
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
    elif daily_plan_action_id:
        endpoint = f"/daily-plan/actions/{quote(daily_plan_action_id, safe='._-')}/events"
        actions.append({
            "id": "complete-daily-plan-action",
            "label": "完成这一步",
            "action": "daily_plan_action.complete",
            "endpoint": endpoint,
            "requires_manual_confirm": True,
            "payload": {
                "action_id": daily_plan_action_id,
                "event_type": "completed",
            },
            "style": "primary",
            "confirmation": {
                "title": f"完成：{title}？",
                "detail": "将写入今天的行动记录，并从待执行列表移除。",
                "confirm_label": "确认完成",
                "cancel_label": "再看看",
            },
            "optimistic": True,
        })

    presentation_mode = data.get("presentation_mode")
    actions.append({
        "id": "open-runtime-agenda",
        "label": "管理今日行动" if presentation_mode == "today" else "查看完整计划",
        "action": "route.open",
        "payload": {"route": "/alerts" if presentation_mode == "today" else "/agenda"},
        "style": "secondary" if (source or daily_plan_action_id) else "primary",
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
    actions = [
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
    ]
    next_meal_detail = data.get("next_meal_detail")
    if isinstance(next_meal_detail, dict) and next_meal_detail:
        actions.append({
            "id": "expand-next-meal",
            "label": "看下一餐建议",
            "action": "ui.inline.expand",
            "payload": {
                "target": "diet_draft",
                "patch": {
                    "expanded_sections": ["next_meal"],
                    "next_meal_detail": next_meal_detail,
                },
            },
            "style": "secondary",
        })
    actions.append({
        "id": "open-diet-edit",
        "label": "去饮食页修正",
        "action": "route.open",
        "payload": {"route": _diet_draft_route(data)},
        "style": "secondary",
    })
    return actions


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
    params = {"draft": "medication", "name": name}
    dose = data.get("dose") if isinstance(data.get("dose"), str) else ""
    if dose:
        params["dose"] = dose
    prompt = f"请帮我核对{name}的用药记录，不要建议我自行停药、换药或改剂量。" if name else "请帮我核对刚才的用药记录。"
    return [
        {
            "id": "open-medication-draft",
            "label": "去用药页记录",
            "action": "route.open",
            "payload": {
                "route": f"/medications?{urlencode(params)}",
            },
            "style": "primary",
        },
        {
            "id": "ask-medication-draft",
            "label": "问小巴",
            "action": "route.open",
            "payload": {
                "route": f"/chat?{urlencode({'prompt': prompt})}",
            },
            "style": "secondary",
        },
    ]


def _supplement_draft_actions(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    name = data.get("supplement_name") if isinstance(data.get("supplement_name"), str) else ""
    prompt = (
        f"请帮我核对{name}的补剂记录，注意剂量、服用时间和与药物/疾病的相互作用。"
        if name
        else "请帮我核对刚才的补剂记录。"
    )
    return [
        {
            "id": "open-supplement-draft",
            "label": "去补剂页记录",
            "action": "route.open",
            "payload": {
                "route": f"/supplement-inventory?{urlencode({'draft': 'supplement', 'name': name})}",
            },
            "style": "primary",
        },
        {
            "id": "ask-supplement-draft",
            "label": "问小巴",
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
    presentation_mode = _runtime_agenda_presentation_mode(q)
    if _is_record_intent(q) or presentation_mode is None:
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
        "presentation_mode": presentation_mode,
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


def _estimate_nutrition_from_table(db: Session, food_items: str) -> Optional[Dict[str, Any]]:
    """单品 + 显式克数时查营养表折算;多品/无克数返回 None(诚实留空)。"""
    text = (food_items or "").strip()
    if not text or "+" in text or "、" in text:
        return None
    m = re.search(r"(?:约)?(\d+(?:\.\d+)?)\s*(?:g|克)", text)
    if not m:
        return None
    grams = float(m.group(1))
    name = re.split(r"[\s\d(（]", text, 1)[0].strip()
    if len(name) < 1:
        return None
    try:
        from app.services.food_nutrition_lookup import enrich_food_from_table
        food: Dict[str, Any] = {"name": name, "quantity": grams, "unit": "g"}
        enriched = enrich_food_from_table(db, food)
    except Exception as e:  # noqa: BLE001
        logger.warning("[inline_cards] nutrition table estimate failed: %s", e)
        return None
    keys = ("calories", "protein", "carbs", "fat", "fiber")
    out = {k: enriched.get(k) for k in keys if enriched.get(k) is not None}
    return out or None


def _build_next_meal_detail(data: Dict[str, Any]) -> Dict[str, Any]:
    protein = data.get("protein")
    calories = data.get("calories")
    protein_num = float(protein) if isinstance(protein, (int, float)) else None
    calories_num = float(calories) if isinstance(calories, (int, float)) else None

    if protein_num is not None and protein_num >= 35:
        summary = "下一餐保持蛋白和蔬菜,避免连续高油高糖。"
        option_primary = "鱼/鸡胸/瘦牛肉 120-150g + 熟蔬菜 + 半份主食"
        rationale_primary = "这餐蛋白已较充足,下一餐重点是稳定纤维和总热量。"
    else:
        summary = "下一餐优先补足蛋白和蔬菜,避免连续高油高糖。"
        option_primary = "鱼/鸡胸/瘦牛肉 150-200g + 熟蔬菜 + 半份主食"
        rationale_primary = "这餐已有明确热量和蛋白估算,下一餐重点是补齐蛋白和纤维。"

    rationale = [rationale_primary]
    if calories_num is not None and calories_num >= 650:
        rationale.append("餐后轻走 10 分钟作为低打扰代谢行动。")
    else:
        rationale.append("如果晚些时候饥饿,优先加蛋白或酸奶,不要靠甜饮补能量。")

    return {
        "title": "下一餐建议",
        "summary": summary,
        "context": "基于本餐营养估算和今日饮食闭环生成,确认记录后会纳入今日进度。",
        "options": [
            option_primary,
            "豆腐/鸡蛋 + 希腊酸奶或牛奶,补足蛋白缺口",
        ],
        "rationale": rationale,
        "continue_prompt": "基于这餐和今天目标,帮我安排下一餐",
    }


def _build_diet_draft(db: Session, user_id: int, q: str) -> Optional[Dict[str, Any]]:
    intent = classify_intake_intent(q)
    if intent.kind != "diet":
        return None
    food_items = intent.text or _extract_food_items(q)
    if not food_items:
        return None
    if _looks_like_food_ui_text(food_items):
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
    # 原话没数字 → 接营养表估算(与记录管线同源 food_nutrition_lookup),
    # 单品且带克数才预填; 拿不准宁可留空(——)也不猜(founder 截图: 油桃草稿空数据)。
    table_filled = False
    if calories is None and all(x is None for x in (protein, carbs, fat, fiber)):
        est = _estimate_nutrition_from_table(db, food_items)
        if est:
            calories = est.get("calories")
            protein = est.get("protein")
            carbs = est.get("carbs")
            fat = est.get("fat")
            fiber = est.get("fiber")
            table_filled = calories is not None
    confidence = 0.82 if (calories is not None and not table_filled) or sum(x is not None for x in (protein, carbs, fat, fiber)) >= 2 and not table_filled else (0.72 if table_filled else 0.62)

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
    data["next_meal_detail"] = _build_next_meal_detail(data)
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


def _build_supplement_draft(db: Session, user_id: int, q: str) -> Optional[Dict[str, Any]]:
    intent = classify_intake_intent(q)
    if intent.kind != "supplement":
        return None
    supplement_name = intent.text.strip()
    if not supplement_name:
        return None
    return {
        "supplement_name": supplement_name,
        "confidence": intent.confidence,
        "source": "chat",
        "suggestions": [
            "确认前核对补剂名、剂量和服用时间",
            "如正在用药或有慢病, 先核对相互作用",
        ],
        "boundary": "确认后记录为已服用; 如正在用药或有慢病, 先核对相互作用。",
    }


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
        from app.utils.blood_pressure_classify import blood_pressure_display

        s, d = r.systolic, r.diastolic
        display = blood_pressure_display(s, d)
        m = r.measured_at
        return {
            "systolic": s, "diastolic": d,
            "pulse": getattr(r, "pulse", None),
            "measured_at": m.strftime("%m-%d %H:%M") if isinstance(m, datetime) else None,
            **display,
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
    ("supplement_draft", _build_supplement_draft),
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


_DRAFT_KIND_BY_CARD = {
    "diet_draft": "diet",
    "medication_draft": "medication",
    "supplement_draft": "supplement",
}

# 单日「快照卡」:纯按 query 关键词触发,拉当天单日快照。适合直接单指标速查
# (「我昨晚睡得怎么样」——卡即答案),但在**分析轮**(LLM 已在正文里给出自己的
# 多日对照表/可视化)就是冗余且常错配(founder 截图:问"上周睡眠不好吗", 却贴
# 今晚单晚 8h 快照)。分析轮由调用方 suppress_snapshot_cards 压掉整类。
# 草稿卡(*_draft)/图表(metric_chart)/复盘/议程不在此列——它们是结构化产物。
_SNAPSHOT_CARD_TYPES = {
    "sleep", "weight", "blood_pressure", "supplement_status", "diet", "vitals",
}


def recorded_intake_kinds(*card_lists: Any) -> set:
    """本轮已完成写入的摄入类 kind 集合(diet/medication/supplement)。

    从 executor 已附的 record / record_quality 卡推断: record 用 data.type,
    record_quality 用 data.domain。用于压制同轮 query 派生的 *_draft 卡 ——
    否则「已记录 + 再确认草稿」并存, 用户点确认会把同一笔写两次
    (founder 截图实锤: 油桃加餐已记录 40kcal, 下面又冒空数据草稿)。
    """
    kinds: set = set()
    for cards in card_lists:
        if not isinstance(cards, list):
            continue
        for c in cards:
            if not isinstance(c, dict):
                continue
            data = c.get("data") if isinstance(c.get("data"), dict) else {}
            t = c.get("type")
            raw = ""
            if t == "record":
                raw = str(data.get("type") or "")
            elif t == "record_quality":
                raw = str(data.get("domain") or "")
            else:
                continue
            if raw in {"diet", "meal", "snack", "food"}:
                kinds.add("diet")
            elif raw in {"medication", "med"}:
                kinds.add("medication")
            elif raw == "supplement":
                kinds.add("supplement")
    return kinds


def build_cards(
    db: Session,
    user_id: int,
    query: str,
    *,
    suppress_intake_kinds: Optional[set] = None,
    suppress_snapshot_cards: bool = False,
) -> List[Dict[str, Any]]:
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
    suppressed = suppress_intake_kinds or set()
    for card_type, builder in _BUILDERS:
        if card_type == "record_intent_skip":
            continue
        if _DRAFT_KIND_BY_CARD.get(card_type) in suppressed:
            dropped.append({"type": card_type, "reason": "already_recorded_this_turn"})
            continue
        if suppress_snapshot_cards and card_type in _SNAPSHOT_CARD_TYPES:
            dropped.append({"type": card_type, "reason": "analysis_turn_llm_owns_visualization"})
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
            if card_type == "supplement_draft":
                card["actions"] = _supplement_draft_actions(data)
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
            if "actions" in card:
                card["actions"] = attach_card_action_policy_metadata(
                    card_type,
                    card["actions"],
                )
            # 展示精度统一(AGENTS.md §14): 面向用户的卡片数字最多 2 位小数(整数保持整数)。
            # 在 actions 已构建之后才格式化 data —— actions 的写入 payload 保留原始精度,
            # 只有 data(展示层)被规范。单一 choke point 覆盖所有卡片所有字段。
            card["data"] = format_card_numbers(card.get("data"))
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
