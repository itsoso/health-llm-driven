"""健康数据查询工具 - 10 个只读查询端点"""
import json
import logging
from datetime import date, datetime
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


def _period_to_days(period: str) -> int:
    """将 period 字符串转换为天数"""
    mapping = {"today": 1, "week": 7, "month": 30}
    return mapping.get(period, 1)


async def get_health_summary(period: str = "today") -> str:
    """获取健康数据综合摘要，包括睡眠、心率、压力、Body Battery、活动等。

    Args:
        period: 时间范围，可选值: "today"(今天), "week"(最近7天), "month"(最近30天)
    """
    client = get_client()
    days = _period_to_days(period)
    data = await client.get("/garmin-analysis/me/comprehensive", params={"days": days})
    return _json(data)


async def get_weight_history(days: int = 7) -> str:
    """获取体重记录历史。

    Args:
        days: 获取最近多少条记录，默认7条
    """
    client = get_client()
    data = await client.get("/weight/records/me", params={"limit": days})
    return _json(data)


async def get_blood_pressure_history(days: int = 7) -> str:
    """获取血压记录历史。

    Args:
        days: 获取最近多少条记录，默认7条
    """
    client = get_client()
    data = await client.get("/blood-pressure/records/me", params={"limit": days})
    return _json(data)


async def get_water_intake(date: Optional[str] = None) -> str:
    """获取某天的饮水记录汇总。

    Args:
        date: 日期字符串，格式 YYYY-MM-DD，默认今天
    """
    client = get_client()
    target_date = date or _today()
    data = await client.get(f"/water/records/me/date/{target_date}")
    return _json(data)


async def get_sleep_data(days: int = 7) -> str:
    """获取睡眠数据分析，包括睡眠时长、深睡/浅睡/REM 比例、睡眠评分等。

    Args:
        days: 获取最近多少天的数据，默认7天
    """
    client = get_client()
    data = await client.get("/garmin-analysis/me/sleep", params={"days": days})
    return _json(data)


async def get_heart_rate(days: int = 7) -> str:
    """获取心率数据分析，包括静息心率、平均心率、最大心率、HRV 等。

    Args:
        days: 获取最近多少天的数据，默认7天
    """
    client = get_client()
    data = await client.get("/garmin-analysis/me/heart-rate", params={"days": days})
    return _json(data)


async def get_workout_history(days: int = 7, workout_type: Optional[str] = None) -> str:
    """获取运动记录历史，包括跑步、骑行、力量训练等各类运动。

    Args:
        days: 获取最近多少天的记录，默认7天
        workout_type: 运动类型筛选，如 "running", "cycling", "strength" 等，为空则返回全部
    """
    client = get_client()
    params = {"days": days}
    if workout_type:
        params["workout_type"] = workout_type
    data = await client.get("/workout/me", params=params)
    return _json(data)


async def get_diet_records(days: int = 3) -> str:
    """获取饮食记录，包括每餐食物、热量和营养素（蛋白质、碳水、脂肪）。

    Args:
        days: 获取最近多少天的饮食记录，默认3天
    """
    client = get_client()
    # 每天最多 3 餐，用 days*3 作为 limit
    data = await client.get("/diet/records/me", params={"limit": days * 3})
    return _json(data)


async def get_checkin_status(date: Optional[str] = None) -> str:
    """获取打卡状态汇总，包括各打卡模板的完成情况。

    Args:
        date: 日期字符串，格式 YYYY-MM-DD，默认今天。目前仅支持查询今日打卡状态。
    """
    client = get_client()
    data = await client.get("/checkin/records/today")
    return _json(data)


async def get_achievements() -> str:
    """获取用户成就徽章列表，包括已解锁的徽章和各徽章的进度。"""
    client = get_client()
    data = await client.get("/achievements/me")
    return _json(data)
