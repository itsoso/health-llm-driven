# -*- coding: utf-8 -*-
"""Deterministic post-record answer quality layer.

This module turns confirmed writes into concise guidance + dynamic card data.
It deliberately avoids diagnosis, prescriptions, and hidden writes.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote

from sqlalchemy.orm import Session

BEIJING_TZ = timezone(timedelta(hours=8))
logger = logging.getLogger(__name__)

_MEAL_TYPE_ZH = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "snack": "加餐",
}
_FAST_RECORD_KIND_ALIASES = {
    "bp": "blood_pressure",
    "blood-pressure": "blood_pressure",
    "bloodpressure": "blood_pressure",
}
_BOUNDARY = "健康管理建议，不替代医生诊断、处方或治疗。"


@dataclass(frozen=True)
class PersonalContextPack:
    conditions: list[str] = field(default_factory=list)
    allergies: list[str] = field(default_factory=list)
    medications: list[str] = field(default_factory=list)
    primary_goal: Optional[str] = None
    target_water_ml: Optional[int] = None
    weight_kg: Optional[float] = None
    protein_target_g: int = 80
    wearable_recovery_state: Optional[str] = None
    wearable_meal_biases: list[str] = field(default_factory=list)
    wearable_summary: Optional[str] = None

    def has_condition(self, *keywords: str) -> bool:
        text = " ".join(self.conditions)
        return any(keyword and keyword in text for keyword in keywords)


@dataclass(frozen=True)
class DietDayTotals:
    record_date: date
    meals_count: int
    calories: float
    protein: float
    carbs: float
    fat: float
    fiber: float
    protein_target_g: int

    @property
    def remaining_protein_g(self) -> int:
        return max(0, round(self.protein_target_g - self.protein))


def _normalize_kind(raw: Any) -> str:
    kind = str(raw or "").strip().lower()
    return _FAST_RECORD_KIND_ALIASES.get(kind, kind)


def _number_or_none(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        raw = value.strip()
        if raw:
            try:
                return float(raw)
            except ValueError:
                return None
    return None


def _clean_items(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, dict):
            value = value.get("name") or value.get("title") or value.get("value")
        raw = str(value).strip()
        if not raw:
            continue
        for item in re.split(r"[,，、/]\s*", raw):
            item = item.strip()
            if item and item not in seen:
                seen.add(item)
                out.append(item)
    return out


def _is_meaningful_diet_caution_item(value: Any) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    normalized = re.sub(r"\s+", "", raw)
    lower = normalized.lower()
    if lower in {"无", "暂无", "没有", "none", "null", "nil", "n/a", "na"}:
        return False
    if re.fullmatch(r"\d+(?:\.\d+)?", normalized):
        return False
    if re.fullmatch(r"[\W_]+", normalized, re.UNICODE):
        return False
    return True


def _context_line_items(personal_context: str, label: str) -> list[str]:
    m = re.search(rf"{re.escape(label)}[:：]\s*([^\n]+)", personal_context or "")
    return _clean_items([m.group(1)]) if m else []


def _short_food_label(value: Any, limit: int = 34) -> str:
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = str(item.get("name") or item.get("food") or "").strip()
            else:
                text = str(item or "").strip()
            if text:
                parts.append(text)
        raw = "、".join(parts)
    else:
        raw = str(value or "").strip()
    raw = re.sub(r"\s+", " ", raw).strip(" ,，、")
    if len(raw) > limit:
        return raw[:limit].rstrip(" ,，、") + "…"
    return raw


def _macro_metrics(record_data: dict) -> list[dict[str, str]]:
    metrics: list[dict[str, str]] = []
    values = [
        ("热量", record_data.get("calories") or record_data.get("kcal"), "kcal"),
        ("蛋白", record_data.get("protein"), "g"),
        ("碳水", record_data.get("carbs") or record_data.get("carbohydrates"), "g"),
        ("脂肪", record_data.get("fat"), "g"),
        ("纤维", record_data.get("fiber"), "g"),
    ]
    for label, raw, unit in values:
        n = _number_or_none(raw)
        if n is not None:
            metrics.append({"label": label, "value": f"{n:.0f}{unit}"})
    return metrics


def _macro_summary(record_data: dict) -> str:
    return " · ".join(f"{m['label']} {m['value']}" for m in _macro_metrics(record_data))


def _extract_target_water(personal_context: str) -> Optional[int]:
    m = re.search(r"(?:饮水|喝水)[^\d]{0,8}(\d{3,5})\s*ml", personal_context or "", re.I)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _protein_target_from_weight(weight_kg: Optional[float]) -> int:
    if weight_kg and weight_kg > 0:
        return max(60, round(weight_kg * 1.6))
    return 80


def extract_personal_context_pack(
    personal_context: str = "",
    *,
    db: Optional[Session] = None,
    user_id: Optional[int] = None,
) -> PersonalContextPack:
    conditions = _context_line_items(personal_context, "慢性病")
    allergies = _context_line_items(personal_context, "过敏/禁忌")
    medications = _context_line_items(personal_context, "用药")
    target_water_ml = _extract_target_water(personal_context)
    primary_goal: Optional[str] = None
    weight_kg: Optional[float] = None
    wearable_recovery_state: Optional[str] = None
    wearable_meal_biases: list[str] = []
    wearable_summary: Optional[str] = None

    if db is not None and user_id is not None:
        try:
            from app.models.user_profile import UserProfile

            profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
            if profile:
                conditions.extend(_clean_items(list(profile.chronic_conditions or [])))
                allergies.extend(_clean_items(list(profile.allergies or [])))
                medications.extend(_clean_items(list(profile.current_medications or [])))
                primary_goal = profile.primary_goal or primary_goal
                target_water_ml = profile.target_water_ml or target_water_ml
                weight_kg = _number_or_none(profile.current_weight_kg)
        except Exception as exc:
            logger.warning(
                "[post_record_quality] profile lookup failed user_id=%s error=%s",
                user_id,
                exc,
            )
        try:
            from app.services.health_context_summary import build_wearable_context_summary

            summary = build_wearable_context_summary(db, user_id, days=7)
            meal_context = summary.get("meal_guidance_context") if isinstance(summary, dict) else None
            if isinstance(meal_context, dict) and summary.get("status") == "present":
                wearable_recovery_state = str(meal_context.get("recovery_state") or "") or None
                wearable_meal_biases = _clean_items(list(meal_context.get("meal_advice_bias") or []))
                wearable_summary = str(meal_context.get("summary") or "").strip() or None
        except Exception as exc:
            logger.warning(
                "[post_record_quality] wearable context lookup failed user_id=%s error=%s",
                user_id,
                exc,
            )

    return PersonalContextPack(
        conditions=_clean_items(conditions),
        allergies=_clean_items(allergies),
        medications=_clean_items(medications),
        primary_goal=primary_goal,
        target_water_ml=target_water_ml,
        weight_kg=weight_kg,
        protein_target_g=_protein_target_from_weight(weight_kg),
        wearable_recovery_state=wearable_recovery_state,
        wearable_meal_biases=wearable_meal_biases,
        wearable_summary=wearable_summary,
    )


def fetch_today_diet_totals(
    *,
    db: Optional[Session],
    user_id: Optional[int],
    context: PersonalContextPack,
    record_date: Optional[date] = None,
) -> Optional[DietDayTotals]:
    if db is None or user_id is None:
        return None
    target_date = record_date or datetime.now(BEIJING_TZ).date()
    try:
        from app.models.daily_health import DietRecord

        rows = (
            db.query(DietRecord)
            .filter(DietRecord.user_id == user_id, DietRecord.record_date == target_date)
            .all()
        )
    except Exception as exc:
        logger.warning(
            "[post_record_quality] diet totals lookup failed user_id=%s date=%s error=%s",
            user_id,
            target_date,
            exc,
        )
        return None
    if not rows:
        return None
    return DietDayTotals(
        record_date=target_date,
        meals_count=len(rows),
        calories=sum(float(r.calories or 0) for r in rows),
        protein=sum(float(r.protein or 0) for r in rows),
        carbs=sum(float(r.carbs or 0) for r in rows),
        fat=sum(float(r.fat or 0) for r in rows),
        fiber=sum(float(r.fiber or 0) for r in rows),
        protein_target_g=context.protein_target_g,
    )


def _record_date(record_data: dict) -> Optional[date]:
    raw = record_data.get("record_date")
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw.strip()):
        try:
            return date.fromisoformat(raw.strip())
        except ValueError:
            return None
    return None


def _diet_personal_cautions(record_data: dict, context: PersonalContextPack) -> list[str]:
    food_text = str(record_data.get("food_items") or record_data.get("food") or "")
    combined = f"{food_text}\n{' '.join(context.conditions)}"
    cautions: list[str] = []
    if context.has_condition("胃溃疡", "胃炎", "胃病", "反流", "GERD", "消化道") and any(
        word in food_text for word in ("柠檬", "酸", "维C", "维生素C", "姜黄", "咖啡", "酒", "辣", "冰", "冷")
    ):
        cautions.append("胃溃疡记录在案，冷饮/酸性饮品可能刺激胃，建议观察耐受。")
    carbs = _number_or_none(record_data.get("carbs") or record_data.get("carbohydrates"))
    if context.has_condition("糖尿病", "血糖", "糖耐量", "胰岛素抵抗") and carbs is not None and carbs >= 80:
        cautions.append("控糖背景下这餐碳水偏高，餐后可轻走 10-15 分钟并关注血糖。")
    if context.has_condition("高血压", "血压") and any(word in combined for word in ("咸", "盐", "酱", "汤", "腌", "外卖")):
        cautions.append("有血压管理目标时，留意这餐钠盐和汤汁摄入。")
    for item in context.allergies:
        if not _is_meaningful_diet_caution_item(item):
            continue
        if item and item in food_text:
            cautions.append(f"你的禁忌里包含「{item}」，请确认这餐没有误食。")
            break
    return cautions[:2]


def _diet_primary_judgement(record_data: dict, totals: Optional[DietDayTotals]) -> str:
    protein = _number_or_none(record_data.get("protein"))
    kcal = _number_or_none(record_data.get("calories") or record_data.get("kcal"))
    if protein is not None and protein >= 25:
        base = f"本餐蛋白质到位（{protein:.0f}g）"
    elif protein is not None:
        base = f"本餐蛋白偏低（{protein:.0f}g）"
    elif kcal is not None:
        base = f"本餐热量约 {kcal:.0f} kcal"
    else:
        base = "这餐已经进入今日饮食账本"
    if totals:
        return f"{base}；今日蛋白 {totals.protein:.0f}/{totals.protein_target_g}g。"
    if kcal is not None and protein is not None:
        return f"{base}，热量约 {kcal:.0f} kcal。"
    return base + "。"


def _diet_headline_sentence(
    meal: str,
    record_data: dict,
    totals: Optional[DietDayTotals] = None,
) -> str:
    """一句话确认 + 单个头条数字(热量/蛋白)。

    移动端已用结构化饮食卡渲染完整食材/宏量/进度 —— 这行文本只为无卡客户端
    (Siri 朗读 / watch 纯文本) 兜底自立。缺失的数字直接省略,绝不编造:
    两者都在 → "已记录午餐:770 kcal,蛋白 30g。"; 只有热量/只有蛋白 → 只带那一个;
    都没有 → "已记录午餐。"(founder 截图的多段墙由此收敛)。
    """
    kcal = _number_or_none(record_data.get("calories") or record_data.get("kcal"))
    protein = _number_or_none(record_data.get("protein"))
    bits: list[str] = []
    if kcal is not None:
        bits.append(f"{kcal:.0f} kcal")
    if protein is not None:
        bits.append(f"蛋白 {protein:.0f}g")
    if totals:
        bits.append(f"今日累计 {totals.calories:.0f} kcal / {totals.meals_count} 餐")
    if bits:
        return f"已记录{meal}：{'，'.join(bits)}。"
    return f"已记录{meal}。"


def _diet_next_action(record_data: dict, context: PersonalContextPack, totals: Optional[DietDayTotals]) -> str:
    protein = _number_or_none(record_data.get("protein"))
    if context.wearable_recovery_state == "strained":
        if totals and totals.remaining_protein_g > 0:
            amount = min(40, max(25, totals.remaining_protein_g))
            if context.has_condition("胃溃疡", "胃炎", "胃病", "反流", "GERD"):
                return f"恢复状态偏紧，下一餐补约 {amount:.0f}g 蛋白，选温热少刺激，别用大热量缺口硬扛。"
            return f"恢复状态偏紧，下一餐补约 {amount:.0f}g 蛋白和水分，避免高油高糖与过晚进食。"
        if context.has_condition("胃溃疡", "胃炎", "胃病", "反流", "GERD"):
            return "恢复状态偏紧，下一餐选温热少刺激、足蛋白但别太撑。"
        return "恢复状态偏紧，下一餐选易消化蛋白、熟蔬菜和水分，不建议继续制造大热量缺口。"
    if context.wearable_recovery_state == "recovered":
        if totals and totals.remaining_protein_g > 0:
            amount = min(45, max(25, totals.remaining_protein_g))
            return f"恢复状态不错，下一餐按计划补约 {amount:.0f}g 蛋白，配蔬菜和适量主食。"
        return "恢复状态不错，下一餐保持一份蛋白、两拳蔬菜和适量主食。"
    if totals and totals.remaining_protein_g > 0:
        amount = min(45, max(25, totals.remaining_protein_g))
        if context.has_condition("胃溃疡", "胃炎", "胃病", "反流", "GERD"):
            return f"下一餐补约 {amount:.0f}g 蛋白，少油少刺激，饮品尽量温和。"
        return f"下一餐优先补约 {amount:.0f}g 蛋白，并配蔬菜和主食。"
    if context.has_condition("胃溃疡", "胃炎", "胃病", "反流", "GERD"):
        return "晚餐少油少刺激，饮品尽量温和，观察餐后胃部体感。"
    if protein is not None and protein < 25:
        return "下一餐优先补 30-40g 蛋白，比如鱼/鸡胸/豆腐加蔬菜。"
    return "下一餐继续补足蔬菜和水，避免把热量集中到夜间。"


def _diet_progress_data(totals: Optional[DietDayTotals]) -> Optional[dict[str, Any]]:
    if not totals:
        return None
    return {
        "record_date": totals.record_date.isoformat(),
        "meals_count": totals.meals_count,
        "calories_total": round(totals.calories),
        "protein_total_g": round(totals.protein),
        "protein_target_g": totals.protein_target_g,
        "remaining_protein_g": totals.remaining_protein_g,
    }


def _route_action(action_id: str, label: str, route: str, *, style: str = "secondary") -> dict[str, Any]:
    return {
        "id": action_id,
        "label": label,
        "action": "route.open",
        "payload": {"route": route},
        "style": style,
    }


def _inline_expand_action(
    action_id: str,
    label: str,
    target: str,
    patch: dict[str, Any],
    *,
    style: str = "secondary",
) -> dict[str, Any]:
    return {
        "id": action_id,
        "label": label,
        "action": "ui.inline.expand",
        "payload": {
            "target": target,
            "patch": patch,
        },
        "style": style,
    }


def _chat_prompt_action(action_id: str, label: str, prompt: str, *, badge: str = "记录建议") -> dict[str, Any]:
    prompt_text = re.sub(r"\s+", " ", prompt).strip()[:240]
    route = (
        f"/(tabs)/chat?prompt={quote(prompt_text, safe='')}"
        f"&badge={quote(badge, safe='')}"
    )
    return _route_action(action_id, label, route)


def _diet_next_meal_detail(
    *,
    meal: str,
    food_label: str,
    record_data: dict,
    context: PersonalContextPack,
    totals: Optional[DietDayTotals],
    next_action: str,
) -> dict[str, Any]:
    protein = _number_or_none(record_data.get("protein"))
    remaining = totals.remaining_protein_g if totals else None
    if context.wearable_recovery_state == "strained":
        options = [
            "温热鱼/鸡蛋/豆腐 + 熟蔬菜 + 少量主食，先稳住恢复。",
            "低油鸡胸/瘦肉粥 + 青菜 + 温水，避免夜间高糖高油。",
        ]
    elif context.has_condition("胃溃疡", "胃炎", "胃病", "反流", "GERD"):
        options = [
            "温热鱼/豆腐 + 熟蔬菜 + 少量米饭，少油少辣。",
            "鸡胸/鸡蛋 + 南瓜或土豆 + 绿叶菜，饮品选温水。",
        ]
    elif context.wearable_recovery_state == "recovered":
        options = [
            "鱼/鸡胸/瘦牛肉 150-200g + 熟蔬菜 + 适量主食。",
            "豆腐/鸡蛋 + 深色蔬菜 + 米饭或土豆，按训练日结构补足。",
        ]
    elif remaining and remaining >= 35:
        options = [
            "鱼/鸡胸/瘦牛肉 150-200g + 熟蔬菜 + 半份主食。",
            "豆腐/鸡蛋 + 希腊酸奶或牛奶，补足蛋白但别堆夜宵。",
        ]
    elif protein is not None and protein < 25:
        options = [
            "下一餐先放一份明确蛋白：鱼、鸡胸、豆腐或鸡蛋。",
            "主食减半，搭配深色蔬菜，避免只吃碳水。",
        ]
    else:
        options = [
            "保持一份蛋白 + 两拳蔬菜 + 一小份主食。",
            "晚些如果饿，优先无糖酸奶/鸡蛋/豆腐，避免高糖零食。",
        ]
    rationale: list[str] = []
    if context.wearable_summary:
        rationale.append(f"恢复状态依据: {context.wearable_summary}")
    if totals:
        rationale.append(
            f"今日已记录 {totals.meals_count} 餐，蛋白 {totals.protein:.0f}/{totals.protein_target_g}g，"
            f"还差约 {totals.remaining_protein_g}g。"
        )
    if context.has_condition("胃溃疡", "胃炎", "胃病", "反流", "GERD"):
        rationale.append("你的胃部/反流背景下，下一餐优先温和、少刺激。")
    if protein is not None:
        rationale.append(f"刚记录的{meal}蛋白约 {protein:.0f}g，可据此安排下一餐。")
    if not rationale:
        rationale.append("基于刚记录的饮食，下一餐优先补齐结构而不是继续加热量。")
    context_line = f"刚记录{meal}：{food_label}"
    macro = _macro_summary(record_data)
    if macro:
        context_line += f"；{macro}"
    return {
        "title": "下一餐建议",
        "summary": next_action,
        "context": context_line,
        "options": options,
        "rationale": rationale[:3],
        "continue_prompt": "可以继续在这里问小巴：如果只能外卖，下一餐怎么选。",
    }


def _exercise_record_summary(record_data: dict) -> tuple[str, str]:
    exercise = str(
        record_data.get("exercise_type")
        or record_data.get("type")
        or record_data.get("name")
        or "运动"
    ).strip()
    reps = _number_or_none(record_data.get("reps"))
    sets = _number_or_none(record_data.get("sets"))
    duration = _number_or_none(record_data.get("duration") or record_data.get("minutes"))
    bits: list[str] = []
    if sets is not None:
        bits.append(f"{sets:.0f}组")
    if reps is not None:
        bits.append(f"{reps:.0f}次")
    if duration is not None:
        bits.append(f"{duration:.0f}分钟")
    return exercise, " · ".join(bits) if bits else "已完成"


def _result_is_failed(result: str) -> bool:
    if not result:
        return False
    from app.services.agent_write_outcome import classify_explicit_write_execution

    outcome = classify_explicit_write_execution(result)
    return bool(
        result.startswith("Error")
        or result.startswith("[NEEDS_CONFIRMATION]")
        or bool(outcome and outcome.status in {"rejected", "failed", "uncertain"})
    )


def _record_id_from_write(result: str, record_data: dict) -> Optional[int]:
    """写入后的记录 id 来源: 工具 result 是持久化后的 DietRecordResponse JSON(含 id)。

    record_data 是 LLM 的入参(food/meal/macros),不含 DB 分配的 id ——
    故先解析 result JSON 的 ``id``,再兜底 record_data.get("id")(某些直调路径会回填)。
    """
    parsed = parse_tool_record_result(result)
    for source in (parsed, record_data):
        raw = source.get("id") if isinstance(source, dict) else None
        if isinstance(raw, bool):  # True/False 不是合法 id
            continue
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and raw.strip().isdigit():
            return int(raw.strip())
    return None


def _diet_meal_type_value(record_data: dict) -> str:
    """归一 meal_type 到 breakfast/lunch/dinner/snack(mobile 编辑器按此渲染)。

    _exec_health_record 已把中文映射成 english,但直调/降级路径可能仍是中文,
    故这里再收口一次;无法识别时回退 snack(与写入端 setdefault 一致)。
    """
    raw = str(record_data.get("meal_type") or "").strip().lower()
    if raw in _MEAL_TYPE_ZH:
        return raw
    zh_map = {"早餐": "breakfast", "午餐": "lunch", "晚餐": "dinner", "加餐": "snack", "夜宵": "snack"}
    return zh_map.get(raw, "snack")


def _diet_adjust_record_seed(record_id: int, record_data: dict) -> dict[str, Any]:
    """就地调整器的种子: 取 record_data 原始值,None 保留 None(不格式化展示串)。"""
    food_raw = record_data.get("food_items") or record_data.get("food")
    if isinstance(food_raw, list):
        food_items = "、".join(
            (str(f.get("name") or f) if isinstance(f, dict) else str(f)).strip()
            for f in food_raw
            if f is not None
        )
    else:
        food_items = str(food_raw or "").strip()
    return {
        "record_id": record_id,
        "meal_type": _diet_meal_type_value(record_data),
        "food_items": food_items,
        "calories": _number_or_none(record_data.get("calories") or record_data.get("kcal")),
        "protein": _number_or_none(record_data.get("protein")),
        "carbs": _number_or_none(record_data.get("carbs") or record_data.get("carbohydrates")),
        "fat": _number_or_none(record_data.get("fat")),
    }


def build_post_record_quality_response(
    record_type: Any,
    record_data: Any,
    result: str = "",
    personal_context: str = "",
    *,
    db: Optional[Session] = None,
    user_id: Optional[int] = None,
    write_verified: Optional[bool] = None,
) -> Optional[dict[str, Any]]:
    if (
        write_verified is False
        or _result_is_failed(result)
        or not isinstance(record_data, dict)
    ):
        return None
    kind = _normalize_kind(record_type)
    context = extract_personal_context_pack(personal_context, db=db, user_id=user_id)

    if kind == "diet":
        meal = _MEAL_TYPE_ZH.get(str(record_data.get("meal_type") or "").lower(), "饮食")
        food_label = _short_food_label(record_data.get("food_items") or record_data.get("food"))
        if not food_label:
            return None
        totals = fetch_today_diet_totals(
            db=db,
            user_id=user_id,
            context=context,
            record_date=_record_date(record_data),
        )
        judgement = _diet_primary_judgement(record_data, totals)
        cautions = _diet_personal_cautions(record_data, context)
        next_action = _diet_next_action(record_data, context, totals)
        progress = _diet_progress_data(totals)
        next_meal_detail = _diet_next_meal_detail(
            meal=meal,
            food_label=food_label,
            record_data=record_data,
            context=context,
            totals=totals,
            next_action=next_action,
        )
        # 回复文本压到最多 2 句:头条确认 + 一句人话备注。完整食材/宏量/进度/判断
        # 由移动端结构化饮食卡承载,文本不再复述那堵墙(founder 截图投诉)。备注优先
        # 用个人提醒(过敏/慢病更值得无卡客户端听见),否则用确定性的下一步建议;两者
        # 皆为当前代码已确定性产出的字段,并同样在卡上呈现,不新增/不臆造。
        note = cautions[0] if cautions else next_action
        headline = _diet_headline_sentence(meal, record_data, totals)
        reply = f"{headline}{note}" if note else headline
        card_data: dict[str, Any] = {
            "domain": "diet",
            "title": f"{meal}已记录",
            "summary": food_label,
            "metrics": _macro_metrics(record_data),
            "primary_judgement": judgement,
            "personal_cautions": cautions,
            "next_action": next_action,
            "boundary": _BOUNDARY,
        }
        if progress:
            card_data["progress"] = progress
        record_id = _record_id_from_write(result, record_data)
        if record_id is not None:
            adjust_action = _inline_expand_action(
                "adjust-record",
                "调整记录",
                "adjust_record",
                {
                    "expanded_sections": ["adjust_record"],
                    "adjust_record": _diet_adjust_record_seed(record_id, record_data),
                },
            )
        else:
            # 拿不到 id 无法就地调整 → 至少跳真正的饮食页(不再去通用记录 tab)。
            adjust_action = _route_action("open-diet", "去饮食页调整", "/diet")
        return {
            "reply": re.sub(r"\s+", " ", reply).strip()[:280],
            "cards": [{
                "type": "record_quality",
                "data": card_data,
                "actions": [
                    _inline_expand_action(
                        "show-next-meal",
                        "看下一餐建议",
                        "next_meal",
                        {
                            "expanded_sections": ["next_meal"],
                            "next_meal_detail": next_meal_detail,
                        },
                        style="primary",
                    ),
                    adjust_action,
                ],
            }],
        }

    if kind == "exercise":
        exercise, detail = _exercise_record_summary(record_data)
        if context.has_condition("高血压", "心脏病", "胸闷", "胸痛"):
            caution = "有心血管/血压背景时，训练中若胸闷头晕要停止并观察。"
        else:
            caution = "留意心率和疲劳感，避免连续高强度堆叠。"
        next_action = "补水并做 3-5 分钟拉伸，晚些再看恢复状态。"
        reply = f"已记录运动：{exercise} {detail}。{caution} 下一步：{next_action}"
        return {
            "reply": reply[:220],
            "cards": [{
                "type": "record_quality",
                "data": {
                    "domain": "exercise",
                    "title": "运动已记录",
                    "summary": f"{exercise} · {detail}",
                    "metrics": [{"label": "运动", "value": detail}],
                    "primary_judgement": "已进入今日活动记录。",
                    "personal_cautions": [caution],
                    "next_action": next_action,
                    "boundary": _BOUNDARY,
                },
                "actions": [
                    _route_action("open-workouts", "查看运动记录", "/workout-list", style="primary"),
                    _route_action("open-record", "继续记录", "/(tabs)/record"),
                    _chat_prompt_action(
                        "ask-recovery",
                        "问小巴恢复",
                        (
                            f"基于我刚记录的运动（{exercise} · {detail}），结合最近恢复、睡眠和心率数据，"
                            "给我今天剩余时间的恢复建议。"
                        ),
                        badge="运动记录",
                    ),
                ],
            }],
        }

    return None


def combine_post_record_quality_responses(
    responses: list[Optional[dict[str, Any]]],
) -> Optional[dict[str, Any]]:
    valid = [r for r in responses if isinstance(r, dict)]
    if not valid:
        return None
    if len(valid) == 1:
        return valid[0]
    cards: list[dict[str, Any]] = []
    labels: list[str] = []
    next_actions: list[str] = []
    for response in valid:
        for card in response.get("cards") or []:
            if not isinstance(card, dict):
                continue
            cards.append(card)
            data = card.get("data") if isinstance(card.get("data"), dict) else {}
            domain = str(data.get("domain") or "").strip()
            title = str(data.get("title") or "").strip()
            summary = str(data.get("summary") or "").strip()
            if domain == "exercise" and summary:
                labels.append(summary)
            elif title:
                labels.append(title)
            elif summary:
                labels.append(summary)
            next_action = str(data.get("next_action") or "").strip()
            if next_action:
                next_actions.append(next_action)
    label_text = "、".join(labels[:3])
    reply = f"已记录 {len(valid)} 项"
    if label_text:
        reply += f"：{label_text}"
    if next_actions:
        reply += f"。接下来：{next_actions[0]}"
    return {"reply": reply[:260], "cards": cards}


def parse_tool_record_result(result: str) -> dict[str, Any]:
    """Best-effort parse for tests and future card enrichment."""
    try:
        parsed = json.loads(result)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}
