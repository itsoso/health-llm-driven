"""语音食物解析(Apple Watch Companion P-back / R5)。

把一段语音转写文本 → 结构化食物草稿(**只产草稿,不写库**;确认走 /diet/records)。
分层(产品文档 §7):
1. 规则层(确定性):餐次推断、酒精/甜饮风险标签。
2. 食物表:命中已审核食物营养表时,先补全可追溯营养。
3. 记忆层:用户常吃食物(近 60 天中位营养)补全缺失营养。
4. LLM 层:自由文本 → 结构化 foods[](可注入,便于测试;不可用时降级)。

诚实边界:不追克级精确;LLM 不确定的营养留 None,不编造。低置信 → needs_confirmation
+ 腕上最多 1 个澄清问题。不做诊断、不开方。
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.schemas.diet import MealType
from app.services.food_nutrition_lookup import enrich_foods_from_table

logger = logging.getLogger(__name__)

PARSER_VERSION = "voice-1.0"
_BEIJING_TZ = timezone(timedelta(hours=8))

# 规则层
_MEAL_BY_KEYWORD = [
    (("早餐", "早饭", "早上吃"), MealType.BREAKFAST.value),
    (("午餐", "午饭", "中午吃"), MealType.LUNCH.value),
    (("晚餐", "晚饭", "晚上吃"), MealType.DINNER.value),
    (("夜宵", "宵夜", "加餐", "零食", "下午茶"), MealType.SNACK.value),
]
_MEAL_LABELS = {
    MealType.BREAKFAST.value: "早餐",
    MealType.LUNCH.value: "午餐",
    MealType.DINNER.value: "晚餐",
    MealType.SNACK.value: "加餐",
    MealType.EXTRA.value: "其他",
}
_ALCOHOL_KW = ("啤酒", "白酒", "红酒", "黄酒", "清酒", "鸡尾酒", "威士忌", "伏特加", "梅酒")
_SWEET_KW = ("可乐", "雪碧", "奶茶", "果汁", "甜饮", "含糖", "蛋糕", "甜品", "冰淇淋", "巧克力")


def infer_meal_type(raw_text: str, hour: int) -> str:
    """先看文本关键词,无则按本地时刻兜底。返回 /diet/records 可直接写库的 MealType enum。"""
    for kws, meal in _MEAL_BY_KEYWORD:
        if any(k in raw_text for k in kws):
            return meal
    if 5 <= hour < 10:
        return MealType.BREAKFAST.value
    if 10 <= hour < 14:
        return MealType.LUNCH.value
    if 16 <= hour < 21:
        return MealType.DINNER.value
    return MealType.SNACK.value


def meal_type_label(meal_type: str) -> str:
    return _MEAL_LABELS.get(meal_type, meal_type)


def detect_risk_tags(raw_text: str) -> List[str]:
    tags = []
    if any(k in raw_text for k in _ALCOHOL_KW):
        tags.append("alcohol")
    if any(k in raw_text for k in _SWEET_KW):
        tags.append("sweet_drink")
    return tags


def _frequent_index(db: Session, user_id: int, days: int = 60) -> Dict[str, Dict[str, Any]]:
    """近 days 天常吃食物 → {food_name: 中位营养}(记忆层,复用 /frequent 同口径)。"""
    from app.models.daily_health import DietRecord

    start = datetime.now(_BEIJING_TZ).date() - timedelta(days=days)
    rows = db.query(DietRecord).filter(
        DietRecord.user_id == user_id,
        DietRecord.record_date >= start,
        DietRecord.food_name.isnot(None),
    ).all()
    groups: Dict[str, list] = {}
    for r in rows:
        for name in {(r.food_name or "").strip(), (r.food_items or "").strip()}:
            if name:
                groups.setdefault(name, []).append(r)

    out: Dict[str, Dict[str, Any]] = {}
    for name, rs in groups.items():
        if not name or len(rs) < 2:   # 至少出现 2 次才算"常吃"
            continue
        out[name] = {
            "calories": _median([r.calories for r in rs]),
            "protein": _median([r.protein for r in rs]),
            "carbs": _median([r.carbs for r in rs]),
            "fat": _median([r.fat for r in rs]),
            "quantity": _median([r.quantity for r in rs]),
            "unit": next((r.unit for r in rs if r.unit), None),
        }
    return out


def _median(vals: list[Any]) -> float | None:
    values = [v for v in vals if v is not None]
    return float(median(values)) if values else None


async def _llm_parse_foods(db: Session, user_id: int, raw_text: str):
    """LLM 层:自由文本 → (foods[], confidence)。不可用/失败 → ([], None)。"""
    from app.services.ai.food_recognition import extract_json_from_text
    from app.services.llm.factory import create_provider_for_user

    try:
        provider = create_provider_for_user(user_id, db)
        content = await provider.chat(messages=[
            {"role": "system", "content": (
                "你把用户语音记录的食物解析成 JSON。只输出 JSON,格式:"
                '{"foods":[{"name":"","quantity":数字或null,"unit":"g/ml/份","calories":数字或null,'
                '"protein":数字或null,"carbs":数字或null,"fat":数字或null}],"confidence":0到1}。'
                "不确定的营养值一律 null,禁止编造精确克数;confidence 反映整体把握。"
            )},
            {"role": "user", "content": raw_text},
        ])
        data = json.loads(extract_json_from_text(content))
        foods = data.get("foods") or []
        return foods, data.get("confidence")
    except Exception as e:  # noqa: BLE001 — LLM 不可用/解析失败 → 降级,不抛
        logger.warning("[diet_voice] LLM 解析失败,降级: %s", e)
        return [], None


async def parse_voice_food(
    db: Session, user_id: int, raw_text: str, meal_type: Optional[str | MealType] = None,
    *, llm_parse: Optional[Callable[..., Awaitable]] = None,
) -> Dict[str, Any]:
    """语音食物草稿(不写库)。llm_parse 可注入(默认走 _llm_parse_foods)。"""
    raw_text = (raw_text or "").strip()
    hour = datetime.now(_BEIJING_TZ).hour
    meal = _normalize_meal_type(meal_type) or infer_meal_type(raw_text, hour)
    tags = detect_risk_tags(raw_text)

    fn = llm_parse or _llm_parse_foods
    foods, llm_conf = await fn(db, user_id, raw_text)

    # 食物表优先:LLM 没给营养的,先用可追溯的 per-100g 表补空值
    enrich_foods_from_table(db, foods)

    # 记忆层补全:食物表未命中/未能补全的,用常吃中位值兜
    freq = _frequent_index(db, user_id)
    for f in foods:
        mem = freq.get((f.get("name") or "").strip())
        if mem:
            filled_from_memory = False
            for k in ("calories", "protein", "carbs", "fat"):
                if f.get(k) is None and mem.get(k) is not None:
                    f[k] = mem[k]
                    filled_from_memory = True
            if f.get("quantity") is None and mem.get("quantity") is not None:
                f["quantity"], f["unit"] = mem["quantity"], mem.get("unit")
                filled_from_memory = True
            if filled_from_memory and f.get("source") is None:
                f["source"] = "diet_history"

    # 降级:LLM 没解析出任何食物 → 整段当一个待确认食物,低置信
    if not foods and raw_text:
        foods = [{"name": raw_text[:50], "quantity": None, "unit": None}]
        llm_conf = 0.2

    confidence = round(float(llm_conf), 2) if llm_conf is not None else 0.3
    missing_qty = [f for f in foods if f.get("quantity") is None]
    needs_confirmation = confidence < 0.7 or bool(missing_qty) or not foods
    question = None
    if missing_qty:
        question = f"「{missing_qty[0].get('name')}」大概多少量?"
    elif confidence < 0.7 and foods:
        question = f"记录的是「{foods[0].get('name')}」对吗?"

    return {
        "raw_text": raw_text,
        "meal_type": meal,
        "meal_type_label": meal_type_label(meal),
        "foods": foods,
        "risk_tags": tags,
        "confidence": confidence,
        "needs_confirmation": needs_confirmation,
        "clarifying_question": question,
        "parser_version": PARSER_VERSION,
    }


def _normalize_meal_type(value: Optional[str | MealType]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, MealType):
        return value.value
    text = str(value).strip()
    return text if text in _MEAL_LABELS else None
