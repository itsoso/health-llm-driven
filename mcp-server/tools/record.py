"""健康数据记录工具 - 5 个写入端点"""
import json
import logging
from datetime import date
from typing import Optional

from client import HealthAPIClient
from config import Config

logger = logging.getLogger(__name__)

_client: Optional[HealthAPIClient] = None


def get_client() -> HealthAPIClient:
    """获取单例 HealthAPIClient 实例（懒初始化）"""
    global _client
    if _client is None:
        _client = HealthAPIClient()
    return _client


def _json(data) -> str:
    """将数据序列化为 JSON 字符串"""
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _today() -> str:
    """返回今天的日期字符串 (YYYY-MM-DD)"""
    return date.today().isoformat()


# 餐类型映射：支持中英文
_MEAL_TYPE_MAP = {
    "breakfast": "BREAKFAST",
    "lunch": "LUNCH",
    "dinner": "DINNER",
    "extra": "EXTRA",
    "早餐": "BREAKFAST",
    "午餐": "LUNCH",
    "晚餐": "DINNER",
    "加餐": "EXTRA",
}


async def record_water(amount_ml: int = 250) -> str:
    """快速记录饮水量。

    Args:
        amount_ml: 饮水量（毫升），默认250ml
    """
    client = get_client()
    data = await client.post("/water/records/quick", params={"amount": amount_ml})
    return _json(data)


async def record_weight(weight_kg: float) -> str:
    """记录体重。

    Args:
        weight_kg: 体重（公斤），例如 72.5
    """
    client = get_client()
    body = {
        "record_date": _today(),
        "weight": weight_kg,
    }
    data = await client.post("/weight/records", data=body)
    return _json(data)


async def record_blood_pressure(
    systolic: int, diastolic: int, heart_rate: Optional[int] = None
) -> str:
    """记录血压。

    Args:
        systolic: 收缩压（高压），例如 120
        diastolic: 舒张压（低压），例如 80
        heart_rate: 心率（可选），例如 72
    """
    client = get_client()
    body = {
        "record_date": _today(),
        "systolic": systolic,
        "diastolic": diastolic,
    }
    if heart_rate is not None:
        body["pulse"] = heart_rate
    data = await client.post("/blood-pressure/records", data=body)
    return _json(data)


async def record_checkin(template_name: str, value: Optional[float] = None) -> str:
    """快速打卡。先按名称查找打卡模板，然后提交打卡记录。

    Args:
        template_name: 打卡模板名称，例如 "跑步"、"俯卧撑"
        value: 打卡数值（可选），例如 5.0（公里）或 30（个）
    """
    client = get_client()

    # 1. 获取模板列表，按名称匹配
    templates = await client.get("/checkin/templates")
    if isinstance(templates, dict) and "error" in templates:
        return _json(templates)

    template_id = None
    for t in templates:
        if t.get("name") == template_name:
            template_id = t.get("id")
            break

    if template_id is None:
        return _json({"error": f"找不到名为 '{template_name}' 的打卡模板"})

    # 2. 提交打卡
    body = {"template_id": template_id}
    if value is not None:
        body["value"] = value
    data = await client.post("/checkin/records/quick", data=body)
    return _json(data)


async def record_diet(
    meal_type: str, foods: str, calories: Optional[int] = None
) -> str:
    """记录饮食。

    Args:
        meal_type: 餐类型，支持英文(breakfast/lunch/dinner/extra)或中文(早餐/午餐/晚餐/加餐)
        foods: 食物描述，例如 "鸡胸肉沙拉、全麦面包"
        calories: 估算热量（可选），单位千卡
    """
    client = get_client()

    # 映射餐类型
    mapped = _MEAL_TYPE_MAP.get(meal_type.lower() if meal_type.isascii() else meal_type)
    if mapped is None:
        return _json({"error": f"不支持的餐类型 '{meal_type}'，请使用: breakfast/lunch/dinner/extra 或 早餐/午餐/晚餐/加餐"})

    body = {
        "record_date": _today(),
        "meal_type": mapped,
        "food_items": foods,
    }
    if calories is not None:
        body["calories"] = calories
    data = await client.post("/diet/records", data=body)
    return _json(data)
