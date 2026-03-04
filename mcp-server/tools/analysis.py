"""健康数据分析工具 - 3 个分析端点"""
import json
import logging
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


async def get_health_analysis(question: Optional[str] = None) -> str:
    """获取健康问题分析，基于用户历史数据识别潜在健康风险和改善建议。

    Args:
        question: 具体的健康问题（可选），例如 "我最近睡眠质量如何？"
    """
    client = get_client()
    params = {}
    if question:
        params["question"] = question
    data = await client.get("/analysis/me/issues", params=params or None)
    return _json(data)


async def get_daily_recommendation() -> str:
    """获取今日个性化健康建议，基于最新的健康数据由 AI 生成。"""
    client = get_client()
    data = await client.post(
        "/daily-recommendation/me/refresh", params={"use_llm": True}
    )
    return _json(data)


async def get_health_trends(dimension: str = "overall") -> str:
    """获取健康趋势预测，分析过去30天数据并预测未来走势。

    Args:
        dimension: 分析维度，可选值: "overall"(综合), "sleep"(睡眠), "activity"(运动), "heart"(心率)
    """
    client = get_client()
    params = {"days": 30}
    if dimension != "overall":
        params["dimension"] = dimension
    data = await client.get("/health-trend/me/prediction", params=params)
    return _json(data)
