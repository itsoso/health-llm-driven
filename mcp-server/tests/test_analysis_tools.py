"""测试 3 个健康数据分析工具"""
import json
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.analysis import (
    get_daily_recommendation,
    get_health_analysis,
    get_health_trends,
)


@pytest.fixture
def mock_client():
    """Mock get_client() 返回一个带有 AsyncMock get/post 方法的客户端"""
    with patch("tools.analysis.get_client") as mock_get_client:
        client = AsyncMock()
        mock_get_client.return_value = client
        yield client


# ---- 1. get_health_analysis ----

@pytest.mark.asyncio
async def test_get_health_analysis(mock_client):
    mock_client.get.return_value = {
        "issues": [
            {
                "type": "sleep",
                "severity": "warning",
                "message": "最近3天睡眠评分持续低于60分",
                "suggestion": "建议调整作息时间，避免睡前使用电子设备",
            }
        ],
        "overall_score": 72,
    }

    result = await get_health_analysis("我最近睡眠如何？")
    data = json.loads(result)

    assert data["overall_score"] == 72
    assert len(data["issues"]) == 1
    assert data["issues"][0]["type"] == "sleep"
    mock_client.get.assert_called_once_with(
        "/analysis/me/issues", params={"question": "我最近睡眠如何？"}
    )


# ---- 2. get_daily_recommendation ----

@pytest.mark.asyncio
async def test_get_daily_recommendation(mock_client):
    mock_client.post.return_value = {
        "date": "2026-03-04",
        "recommendations": [
            {"category": "exercise", "content": "今天建议进行30分钟轻度有氧运动"},
            {"category": "diet", "content": "注意补充蛋白质，推荐鸡胸肉或鱼类"},
            {"category": "sleep", "content": "昨晚睡眠不足，今晚尝试提前30分钟入睡"},
        ],
    }

    result = await get_daily_recommendation()
    data = json.loads(result)

    assert data["date"] == "2026-03-04"
    assert len(data["recommendations"]) == 3
    mock_client.post.assert_called_once_with(
        "/daily-recommendation/me/refresh", params={"use_llm": True}
    )


# ---- 3. get_health_trends ----

@pytest.mark.asyncio
async def test_get_health_trends(mock_client):
    mock_client.get.return_value = {
        "dimension": "overall",
        "period_days": 30,
        "trends": {
            "sleep_score": {"direction": "improving", "change_pct": 5.2},
            "resting_hr": {"direction": "stable", "change_pct": -0.8},
            "activity_level": {"direction": "declining", "change_pct": -12.3},
        },
        "prediction": "整体健康趋势平稳，运动量有所下降，建议增加运动频率。",
    }

    result = await get_health_trends("overall")
    data = json.loads(result)

    assert data["dimension"] == "overall"
    assert data["period_days"] == 30
    assert "sleep_score" in data["trends"]
    assert data["trends"]["activity_level"]["direction"] == "declining"
    mock_client.get.assert_called_once_with(
        "/health-trend/me/prediction", params={"days": 30}
    )
