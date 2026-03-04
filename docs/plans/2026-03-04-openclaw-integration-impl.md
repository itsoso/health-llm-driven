# OpenClaw 深度集成 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Health MCP Server + OpenClaw Skills to expose health system capabilities to any AI client and all OpenClaw channels, then migrate the frontend AI chat from regex-based action parsing to Function Calling.

**Architecture:** A standalone MCP Server (FastMCP, Python) calls the health backend API over HTTP. OpenClaw Skills (SKILL.md files) provide native Gateway integration. The LLM Provider base class gets `tools` parameter support for Function Calling, and chat_service migrates from `<<<ACTIONS:` regex to structured tool_calls.

**Tech Stack:** FastMCP (Python MCP framework), httpx (HTTP client), OpenAI function calling format, OpenClaw Skills (YAML+Markdown)

---

### Task 1: MCP Server — Project Scaffold + HTTP Client

**Files:**
- Create: `mcp-server/requirements.txt`
- Create: `mcp-server/config.py`
- Create: `mcp-server/client.py`
- Create: `mcp-server/server.py`
- Test: `mcp-server/tests/test_client.py`

**Step 1: Create project structure**

```bash
mkdir -p mcp-server/tools mcp-server/tests
```

**Step 2: Write requirements.txt**

Create `mcp-server/requirements.txt`:
```
fastmcp>=2.0.0
httpx>=0.27.0
pydantic>=2.0.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

**Step 3: Write config.py**

Create `mcp-server/config.py`:
```python
"""Health MCP Server 配置"""
import os


class Config:
    HEALTH_API_URL = os.environ.get("HEALTH_API_URL", "http://localhost:8000/api/v1")
    HEALTH_API_TOKEN = os.environ.get("HEALTH_API_TOKEN", "")
    MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio")  # stdio | sse
    MCP_SSE_PORT = int(os.environ.get("MCP_SSE_PORT", "8808"))
```

**Step 4: Write the failing test for client.py**

Create `mcp-server/tests/test_client.py`:
```python
"""测试 Health API Client"""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from client import HealthAPIClient


@pytest.fixture
def client():
    return HealthAPIClient(
        base_url="http://test-api:8000/api/v1",
        token="test-token-123"
    )


@pytest.mark.asyncio
async def test_client_get_headers(client):
    """测试请求头包含认证信息"""
    headers = client._get_headers()
    assert headers["Authorization"] == "Bearer test-token-123"
    assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_client_get_success(client):
    """测试 GET 请求成功"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": "test"}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        MockClient.return_value = mock_instance

        result = await client.get("/water/records/me/date/2024-01-01")
        assert result == {"data": "test"}


@pytest.mark.asyncio
async def test_client_post_success(client):
    """测试 POST 请求成功"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": 1, "amount": 250}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        MockClient.return_value = mock_instance

        result = await client.post("/water/records/quick", params={"amount": 250})
        assert result["amount"] == 250


@pytest.mark.asyncio
async def test_client_error_handling(client):
    """测试错误处理"""
    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = Exception("Connection refused")
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        MockClient.return_value = mock_instance

        result = await client.get("/nonexistent")
        assert "error" in result
```

**Step 5: Run test to verify it fails**

Run: `cd mcp-server && pip install -r requirements.txt && python -m pytest tests/test_client.py -v`
Expected: FAIL (module `client` not found)

**Step 6: Write client.py**

Create `mcp-server/client.py`:
```python
"""Health API HTTP 客户端"""
import logging
from typing import Any, Dict, Optional

import httpx

from config import Config

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0


class HealthAPIClient:
    """健康系统 API 客户端"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
    ):
        self.base_url = (base_url or Config.HEALTH_API_URL).rstrip("/")
        self.token = token or Config.HEALTH_API_TOKEN

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def get(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """GET 请求"""
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.get(url, headers=self._get_headers(), params=params)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"GET {path} failed: {e}")
            return {"error": str(e)}

    async def post(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST 请求"""
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.post(
                    url, headers=self._get_headers(), json=data, params=params
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"POST {path} failed: {e}")
            return {"error": str(e)}
```

**Step 7: Run test to verify it passes**

Run: `cd mcp-server && python -m pytest tests/test_client.py -v`
Expected: 4 passed

**Step 8: Write minimal server.py entry point**

Create `mcp-server/server.py`:
```python
"""Health MCP Server 入口"""
from fastmcp import FastMCP

from config import Config

mcp = FastMCP(
    "Health Management",
    description="AI-powered health management system - query health data, record measurements, and get health analysis",
)


if __name__ == "__main__":
    transport = Config.MCP_TRANSPORT
    if transport == "sse":
        mcp.run(transport="sse", port=Config.MCP_SSE_PORT)
    else:
        mcp.run(transport="stdio")
```

**Step 9: Commit**

```bash
git add mcp-server/
git commit -m "feat: MCP Server scaffold with HTTP client and config"
```

---

### Task 2: MCP Server — Query Tools (10 tools)

**Files:**
- Create: `mcp-server/tools/query.py`
- Modify: `mcp-server/server.py`
- Test: `mcp-server/tests/test_query_tools.py`

**Step 1: Write the failing test**

Create `mcp-server/tests/test_query_tools.py`:
```python
"""测试数据查询 Tools"""
import pytest
from unittest.mock import AsyncMock, patch
from tools.query import (
    get_health_summary,
    get_weight_history,
    get_blood_pressure_history,
    get_water_intake,
    get_sleep_data,
    get_heart_rate,
    get_workout_history,
    get_diet_records,
    get_checkin_status,
    get_achievements,
)


@pytest.fixture
def mock_client():
    with patch("tools.query.get_client") as mock:
        client = AsyncMock()
        mock.return_value = client
        yield client


@pytest.mark.asyncio
async def test_get_health_summary_today(mock_client):
    mock_client.get.return_value = {
        "sleep": {"average_sleep_hours": 7.5},
        "heart_rate": {"average_rhr": 62},
        "activity": {"average_daily_steps": 8500},
    }
    result = await get_health_summary(period="today")
    assert "sleep" in result or "步" in result or "average" in str(result)
    mock_client.get.assert_called()


@pytest.mark.asyncio
async def test_get_weight_history(mock_client):
    mock_client.get.return_value = [
        {"record_date": "2024-01-01", "weight": 72.5},
        {"record_date": "2024-01-02", "weight": 72.3},
    ]
    result = await get_weight_history(days=7)
    assert "72" in str(result)


@pytest.mark.asyncio
async def test_get_water_intake(mock_client):
    mock_client.get.return_value = {
        "total_amount": 1500,
        "target_amount": 2000,
        "progress_percentage": 75.0,
    }
    result = await get_water_intake(date="2024-01-01")
    assert "1500" in str(result)


@pytest.mark.asyncio
async def test_get_checkin_status(mock_client):
    mock_client.get.return_value = {
        "date": "2024-01-01",
        "total_templates": 10,
        "completed_templates": 5,
        "completion_rate": 50.0,
    }
    result = await get_checkin_status()
    assert "50" in str(result) or "completed" in str(result).lower()


@pytest.mark.asyncio
async def test_get_achievements(mock_client):
    mock_client.get.return_value = {
        "total": 15,
        "unlocked": 3,
        "achievements": [{"name": "三天坚持", "unlocked": True}],
    }
    result = await get_achievements()
    assert "三天坚持" in str(result) or "unlocked" in str(result).lower()


@pytest.mark.asyncio
async def test_get_blood_pressure_history(mock_client):
    mock_client.get.return_value = [
        {"systolic": 120, "diastolic": 80, "record_date": "2024-01-01"}
    ]
    result = await get_blood_pressure_history(days=7)
    assert "120" in str(result)


@pytest.mark.asyncio
async def test_get_sleep_data(mock_client):
    mock_client.get.return_value = {
        "sleep": {"average_sleep_hours": 7.2, "sleep_quality_score": 78}
    }
    result = await get_sleep_data(days=7)
    assert "7.2" in str(result) or "sleep" in str(result).lower()


@pytest.mark.asyncio
async def test_get_heart_rate(mock_client):
    mock_client.get.return_value = {
        "heart_rate": {"average_rhr": 62, "hrv_avg": 45}
    }
    result = await get_heart_rate(days=7)
    assert "62" in str(result) or "heart" in str(result).lower()


@pytest.mark.asyncio
async def test_get_workout_history(mock_client):
    mock_client.get.return_value = [
        {"workout_type": "running", "distance_meters": 5000, "duration_seconds": 1800}
    ]
    result = await get_workout_history(days=7)
    assert "running" in str(result) or "5000" in str(result)


@pytest.mark.asyncio
async def test_get_diet_records(mock_client):
    mock_client.get.return_value = [
        {"meal_type": "LUNCH", "food_items": "鸡胸肉沙拉", "calories": 400}
    ]
    result = await get_diet_records(days=3)
    assert "鸡胸肉" in str(result) or "400" in str(result)
```

**Step 2: Run test to verify it fails**

Run: `cd mcp-server && python -m pytest tests/test_query_tools.py -v`
Expected: FAIL (no module `tools.query`)

**Step 3: Write query tools**

Create `mcp-server/tools/__init__.py` (empty file).

Create `mcp-server/tools/query.py`:
```python
"""数据查询类 MCP Tools"""
import json
from datetime import date
from typing import Optional

from client import HealthAPIClient
from config import Config

_client: Optional[HealthAPIClient] = None


def get_client() -> HealthAPIClient:
    global _client
    if _client is None:
        _client = HealthAPIClient()
    return _client


async def get_health_summary(period: str = "today") -> str:
    """获取健康概览数据，包含步数、心率、睡眠、压力等

    Args:
        period: 时间范围 - today(今天), week(本周), month(本月)
    """
    days = {"today": 1, "week": 7, "month": 30}.get(period, 1)
    client = get_client()
    data = await client.get("/garmin-analysis/me/comprehensive", params={"days": days})
    return json.dumps(data, ensure_ascii=False, indent=2)


async def get_weight_history(days: int = 7) -> str:
    """查询体重历史记录

    Args:
        days: 查询天数，默认7天
    """
    client = get_client()
    data = await client.get("/weight/records/me", params={"limit": days})
    return json.dumps(data, ensure_ascii=False, indent=2)


async def get_blood_pressure_history(days: int = 7) -> str:
    """查询血压历史记录

    Args:
        days: 查询天数，默认7天
    """
    client = get_client()
    data = await client.get("/blood-pressure/records/me", params={"limit": days})
    return json.dumps(data, ensure_ascii=False, indent=2)


async def get_water_intake(date: Optional[str] = None) -> str:
    """查询饮水记录

    Args:
        date: 日期，格式YYYY-MM-DD，不传则为今天
    """
    client = get_client()
    from datetime import date as date_type
    query_date = date or date_type.today().isoformat()
    data = await client.get(f"/water/records/me/date/{query_date}")
    return json.dumps(data, ensure_ascii=False, indent=2)


async def get_sleep_data(days: int = 7) -> str:
    """查询睡眠数据，包含睡眠时长、质量评分、深睡比例等

    Args:
        days: 查询天数，默认7天
    """
    client = get_client()
    data = await client.get("/garmin-analysis/me/sleep", params={"days": days})
    return json.dumps(data, ensure_ascii=False, indent=2)


async def get_heart_rate(days: int = 7) -> str:
    """查询心率数据，包含静息心率、HRV、压力水平等

    Args:
        days: 查询天数，默认7天
    """
    client = get_client()
    data = await client.get("/garmin-analysis/me/heart-rate", params={"days": days})
    return json.dumps(data, ensure_ascii=False, indent=2)


async def get_workout_history(days: int = 7, workout_type: Optional[str] = None) -> str:
    """查询运动记录

    Args:
        days: 查询天数，默认7天
        workout_type: 运动类型筛选，如 running/cycling/swimming
    """
    client = get_client()
    params = {"days": days}
    if workout_type:
        params["workout_type"] = workout_type
    data = await client.get("/workout/me", params=params)
    return json.dumps(data, ensure_ascii=False, indent=2)


async def get_diet_records(days: int = 3) -> str:
    """查询饮食记录

    Args:
        days: 查询天数，默认3天
    """
    client = get_client()
    # Diet API uses user/{user_id} path, but we'll use the me variant
    # The actual endpoint needs the user_id, so we get it from /auth/me first
    user_data = await client.get("/auth/me")
    user_id = user_data.get("id", 0)
    if not user_id:
        return json.dumps({"error": "无法获取用户信息"}, ensure_ascii=False)
    data = await client.get(f"/diet/records/user/{user_id}", params={"limit": days * 3})
    return json.dumps(data, ensure_ascii=False, indent=2)


async def get_checkin_status(date: Optional[str] = None) -> str:
    """查询打卡状态，包含今日完成情况和各模板状态

    Args:
        date: 日期，不传则为今天
    """
    client = get_client()
    data = await client.get("/checkin/records/today")
    return json.dumps(data, ensure_ascii=False, indent=2)


async def get_achievements() -> str:
    """查询成就徽章，包含已解锁和进度"""
    client = get_client()
    data = await client.get("/achievements/me")
    return json.dumps(data, ensure_ascii=False, indent=2)
```

**Step 4: Register tools in server.py**

Modify `mcp-server/server.py`:
```python
"""Health MCP Server 入口"""
from fastmcp import FastMCP

from config import Config
from tools.query import (
    get_health_summary,
    get_weight_history,
    get_blood_pressure_history,
    get_water_intake,
    get_sleep_data,
    get_heart_rate,
    get_workout_history,
    get_diet_records,
    get_checkin_status,
    get_achievements,
)

mcp = FastMCP(
    "Health Management",
    description="AI-powered health management system - query health data, record measurements, and get health analysis",
)

# 注册查询工具
mcp.tool()(get_health_summary)
mcp.tool()(get_weight_history)
mcp.tool()(get_blood_pressure_history)
mcp.tool()(get_water_intake)
mcp.tool()(get_sleep_data)
mcp.tool()(get_heart_rate)
mcp.tool()(get_workout_history)
mcp.tool()(get_diet_records)
mcp.tool()(get_checkin_status)
mcp.tool()(get_achievements)


if __name__ == "__main__":
    transport = Config.MCP_TRANSPORT
    if transport == "sse":
        mcp.run(transport="sse", port=Config.MCP_SSE_PORT)
    else:
        mcp.run(transport="stdio")
```

**Step 5: Run tests**

Run: `cd mcp-server && python -m pytest tests/test_query_tools.py -v`
Expected: 10 passed

**Step 6: Commit**

```bash
git add mcp-server/tools/ mcp-server/server.py
git commit -m "feat: MCP Server query tools - 10 data query endpoints"
```

---

### Task 3: MCP Server — Record Tools (5 tools)

**Files:**
- Create: `mcp-server/tools/record.py`
- Modify: `mcp-server/server.py`
- Test: `mcp-server/tests/test_record_tools.py`

**Step 1: Write the failing test**

Create `mcp-server/tests/test_record_tools.py`:
```python
"""测试记录写入 Tools"""
import pytest
from unittest.mock import AsyncMock, patch
from tools.record import (
    record_water,
    record_weight,
    record_blood_pressure,
    record_checkin,
    record_diet,
)


@pytest.fixture
def mock_client():
    with patch("tools.record.get_client") as mock:
        client = AsyncMock()
        mock.return_value = client
        yield client


@pytest.mark.asyncio
async def test_record_water(mock_client):
    mock_client.post.return_value = {"id": 1, "amount": 250}
    result = await record_water(amount_ml=250)
    assert "250" in result
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_record_weight(mock_client):
    mock_client.post.return_value = {"id": 1, "weight": 72.5}
    result = await record_weight(weight_kg=72.5)
    assert "72.5" in result


@pytest.mark.asyncio
async def test_record_blood_pressure(mock_client):
    mock_client.post.return_value = {"id": 1, "systolic": 120, "diastolic": 80}
    result = await record_blood_pressure(systolic=120, diastolic=80)
    assert "120" in result


@pytest.mark.asyncio
async def test_record_blood_pressure_with_heart_rate(mock_client):
    mock_client.post.return_value = {"id": 1, "systolic": 120, "diastolic": 80, "pulse": 72}
    result = await record_blood_pressure(systolic=120, diastolic=80, heart_rate=72)
    assert "72" in result


@pytest.mark.asyncio
async def test_record_checkin(mock_client):
    mock_client.get.return_value = {
        "templates": [{"id": 1, "name": "俯卧撑"}]
    }
    mock_client.post.return_value = {"id": 1, "template_name": "俯卧撑", "value": 30}
    result = await record_checkin(template_name="俯卧撑", value=30)
    assert "俯卧撑" in result


@pytest.mark.asyncio
async def test_record_diet(mock_client):
    mock_client.post.return_value = {"id": 1, "food_items": "鸡胸肉沙拉", "calories": 400}
    result = await record_diet(meal_type="lunch", foods="鸡胸肉沙拉", calories=400)
    assert "鸡胸肉" in result
```

**Step 2: Run test to verify it fails**

Run: `cd mcp-server && python -m pytest tests/test_record_tools.py -v`
Expected: FAIL

**Step 3: Write record tools**

Create `mcp-server/tools/record.py`:
```python
"""记录写入类 MCP Tools"""
import json
from datetime import date
from typing import Optional

from client import HealthAPIClient
from config import Config

_client: Optional[HealthAPIClient] = None


def get_client() -> HealthAPIClient:
    global _client
    if _client is None:
        _client = HealthAPIClient()
    return _client


async def record_water(amount_ml: int = 250) -> str:
    """记录饮水量

    Args:
        amount_ml: 饮水量，单位毫升，默认250ml（一杯水）
    """
    client = get_client()
    data = await client.post("/water/records/quick", params={"amount": amount_ml})
    if "error" in data:
        return f"记录失败: {data['error']}"
    return json.dumps(data, ensure_ascii=False, indent=2)


async def record_weight(weight_kg: float) -> str:
    """记录体重

    Args:
        weight_kg: 体重，单位千克
    """
    client = get_client()
    data = await client.post("/weight/records", data={
        "record_date": date.today().isoformat(),
        "weight": weight_kg,
    })
    if "error" in data:
        return f"记录失败: {data['error']}"
    return json.dumps(data, ensure_ascii=False, indent=2)


async def record_blood_pressure(
    systolic: int, diastolic: int, heart_rate: Optional[int] = None
) -> str:
    """记录血压

    Args:
        systolic: 收缩压（高压）
        diastolic: 舒张压（低压）
        heart_rate: 心率（可选）
    """
    client = get_client()
    body = {
        "record_date": date.today().isoformat(),
        "systolic": systolic,
        "diastolic": diastolic,
    }
    if heart_rate is not None:
        body["pulse"] = heart_rate
    data = await client.post("/blood-pressure/records", data=body)
    if "error" in data:
        return f"记录失败: {data['error']}"
    return json.dumps(data, ensure_ascii=False, indent=2)


async def record_checkin(template_name: str, value: Optional[float] = None) -> str:
    """快速打卡

    Args:
        template_name: 打卡模板名称，如"俯卧撑"、"深蹲"、"洗鼻"
        value: 打卡数值（可选），如俯卧撑30个
    """
    client = get_client()
    # 先查找模板ID
    templates_data = await client.get("/checkin/templates")
    templates = templates_data.get("templates", [])
    template_id = None
    for t in templates:
        if t.get("name") == template_name:
            template_id = t.get("id")
            break
    if template_id is None:
        return f"未找到名为 '{template_name}' 的打卡模板"

    body = {"template_id": template_id}
    if value is not None:
        body["value"] = value
    data = await client.post("/checkin/records/quick", data=body)
    if "error" in data:
        return f"打卡失败: {data['error']}"
    return json.dumps(data, ensure_ascii=False, indent=2)


async def record_diet(
    meal_type: str, foods: str, calories: Optional[int] = None
) -> str:
    """记录饮食

    Args:
        meal_type: 餐次 - breakfast(早餐), lunch(午餐), dinner(晚餐), extra(加餐)
        foods: 食物描述，如"鸡胸肉沙拉、一碗米饭"
        calories: 估算卡路里（可选）
    """
    client = get_client()
    meal_map = {
        "breakfast": "BREAKFAST", "lunch": "LUNCH",
        "dinner": "DINNER", "extra": "EXTRA",
        "早餐": "BREAKFAST", "午餐": "LUNCH",
        "晚餐": "DINNER", "加餐": "EXTRA",
    }
    body = {
        "record_date": date.today().isoformat(),
        "meal_type": meal_map.get(meal_type.lower(), "LUNCH"),
        "food_items": foods,
    }
    if calories is not None:
        body["calories"] = calories
    data = await client.post("/diet/records", data=body)
    if "error" in data:
        return f"记录失败: {data['error']}"
    return json.dumps(data, ensure_ascii=False, indent=2)
```

**Step 4: Register record tools in server.py**

Add to `mcp-server/server.py` after query tool imports:
```python
from tools.record import (
    record_water,
    record_weight,
    record_blood_pressure,
    record_checkin,
    record_diet,
)

# 注册记录工具（在查询工具注册之后）
mcp.tool()(record_water)
mcp.tool()(record_weight)
mcp.tool()(record_blood_pressure)
mcp.tool()(record_checkin)
mcp.tool()(record_diet)
```

**Step 5: Run tests**

Run: `cd mcp-server && python -m pytest tests/test_record_tools.py -v`
Expected: 6 passed

**Step 6: Commit**

```bash
git add mcp-server/
git commit -m "feat: MCP Server record tools - water, weight, BP, checkin, diet"
```

---

### Task 4: MCP Server — Analysis Tools (3 tools)

**Files:**
- Create: `mcp-server/tools/analysis.py`
- Modify: `mcp-server/server.py`
- Test: `mcp-server/tests/test_analysis_tools.py`

**Step 1: Write the failing test**

Create `mcp-server/tests/test_analysis_tools.py`:
```python
"""测试分析报告 Tools"""
import pytest
from unittest.mock import AsyncMock, patch
from tools.analysis import (
    get_health_analysis,
    get_daily_recommendation,
    get_health_trends,
)


@pytest.fixture
def mock_client():
    with patch("tools.analysis.get_client") as mock:
        client = AsyncMock()
        mock.return_value = client
        yield client


@pytest.mark.asyncio
async def test_get_health_analysis(mock_client):
    mock_client.get.return_value = {
        "issues": [{"name": "sleep_quality", "severity": "warning"}]
    }
    result = await get_health_analysis()
    assert "sleep" in result.lower() or "warning" in result.lower()


@pytest.mark.asyncio
async def test_get_daily_recommendation(mock_client):
    mock_client.post.return_value = {
        "status": "success",
        "recommendations": {"exercise": "建议慢跑30分钟"}
    }
    result = await get_daily_recommendation()
    assert "慢跑" in result or "recommendation" in result.lower()


@pytest.mark.asyncio
async def test_get_health_trends(mock_client):
    mock_client.get.return_value = {
        "predictions": [
            {"metric": "sleep_quality", "trend": "up", "confidence": 0.85}
        ]
    }
    result = await get_health_trends(dimension="sleep")
    assert "sleep" in result.lower() or "up" in result
```

**Step 2: Run test to verify it fails**

Run: `cd mcp-server && python -m pytest tests/test_analysis_tools.py -v`
Expected: FAIL

**Step 3: Write analysis tools**

Create `mcp-server/tools/analysis.py`:
```python
"""分析报告类 MCP Tools"""
import json
from typing import Optional

from client import HealthAPIClient
from config import Config

_client: Optional[HealthAPIClient] = None


def get_client() -> HealthAPIClient:
    global _client
    if _client is None:
        _client = HealthAPIClient()
    return _client


async def get_health_analysis(question: Optional[str] = None) -> str:
    """获取 AI 健康分析，检测潜在健康问题并提供建议

    Args:
        question: 具体的健康问题（可选），如"我最近睡眠怎么样"
    """
    client = get_client()
    data = await client.get("/analysis/me/issues")
    return json.dumps(data, ensure_ascii=False, indent=2)


async def get_daily_recommendation() -> str:
    """获取今日健康推荐，包含运动、饮食、作息建议"""
    client = get_client()
    data = await client.post("/daily-recommendation/me/refresh", params={"use_llm": True})
    return json.dumps(data, ensure_ascii=False, indent=2)


async def get_health_trends(dimension: str = "overall") -> str:
    """获取健康趋势预测

    Args:
        dimension: 分析维度 - weight(体重), sleep(睡眠), exercise(运动), overall(综合)
    """
    client = get_client()
    data = await client.get("/health-trend/me/prediction", params={"days": 30})
    return json.dumps(data, ensure_ascii=False, indent=2)
```

**Step 4: Register in server.py and run all tests**

Add to `mcp-server/server.py`:
```python
from tools.analysis import (
    get_health_analysis,
    get_daily_recommendation,
    get_health_trends,
)

# 注册分析工具
mcp.tool()(get_health_analysis)
mcp.tool()(get_daily_recommendation)
mcp.tool()(get_health_trends)
```

**Step 5: Run all MCP Server tests**

Run: `cd mcp-server && python -m pytest tests/ -v`
Expected: 23 passed (4 client + 10 query + 6 record + 3 analysis)

**Step 6: Commit**

```bash
git add mcp-server/
git commit -m "feat: MCP Server analysis tools - health analysis, recommendations, trends"
```

---

### Task 5: MCP Server — Dockerfile + Docker Compose Integration

**Files:**
- Create: `mcp-server/Dockerfile`
- Modify: `docker-compose.yml`

**Step 1: Create Dockerfile**

Create `mcp-server/Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8808

CMD ["python", "server.py"]
```

**Step 2: Add mcp-server service to docker-compose.yml**

Add the following service to the existing `docker-compose.yml` (after the `backend` service):
```yaml
  mcp-server:
    build:
      context: ./mcp-server
      dockerfile: Dockerfile
    environment:
      HEALTH_API_URL: http://backend:8000/api/v1
      HEALTH_API_TOKEN: ${MCP_API_TOKEN:-}
      MCP_TRANSPORT: sse
      MCP_SSE_PORT: "8808"
    ports:
      - "8808:8808"
    depends_on:
      backend:
        condition: service_healthy
    restart: unless-stopped
```

**Step 3: Add MCP_API_TOKEN to .env.example**

Add to the root `.env.example`:
```env
# === MCP Server ===
MCP_API_TOKEN=           # Health API JWT token for MCP Server authentication
```

**Step 4: Commit**

```bash
git add mcp-server/Dockerfile docker-compose.yml .env.example
git commit -m "feat: MCP Server Docker setup + Compose integration"
```

---

### Task 6: OpenClaw Skills — 3 SKILL.md Files

**Files:**
- Create: `openclaw-skills/health-query/SKILL.md`
- Create: `openclaw-skills/health-record/SKILL.md`
- Create: `openclaw-skills/health-analysis/SKILL.md`
- Create: `openclaw-skills/README.md`

**Step 1: Create skill directories**

```bash
mkdir -p openclaw-skills/health-query openclaw-skills/health-record openclaw-skills/health-analysis
```

**Step 2: Write health-query skill**

Create `openclaw-skills/health-query/SKILL.md`:
```yaml
---
name: health-query
description: Query health data from the Health Management System - steps, heart rate, sleep, weight, blood pressure, workouts, diet, checkin status, and achievements.
requires:
  env:
    - HEALTH_API_URL
    - HEALTH_API_TOKEN
---

You have access to a Health Management System API. Use curl to query health data.

## Authentication
- URL: ${HEALTH_API_URL}
- Header: `Authorization: Bearer ${HEALTH_API_TOKEN}`

## Available Endpoints

### 综合健康数据（Garmin）
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/garmin-analysis/me/comprehensive?days=7"
```
返回：步数、心率、睡眠、压力、Body Battery 综合分析

### 睡眠数据
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/garmin-analysis/me/sleep?days=7"
```

### 心率数据
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/garmin-analysis/me/heart-rate?days=7"
```

### 活动数据
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/garmin-analysis/me/activity?days=7"
```

### 体重记录
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/weight/records/me?limit=7"
```

### 血压记录
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/blood-pressure/records/me?limit=7"
```

### 今日饮水
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/water/records/me/date/$(date +%Y-%m-%d)"
```

### 饮水统计
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/water/records/me/stats?days=7"
```

### 今日打卡
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/checkin/records/today"
```

### 打卡统计
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/checkin/stats"
```

### 运动记录
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/workout/me?days=7"
```

### 成就徽章
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/achievements/me"
```

### 健康评分
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/health-score/daily/me"
```

## Response Rules
- Always format responses in readable Chinese
- Include units (步, bpm, 分, kg, mmHg, ml)
- Highlight anomalies or notable changes
- Compare with targets when available
```

**Step 3: Write health-record skill**

Create `openclaw-skills/health-record/SKILL.md`:
```yaml
---
name: health-record
description: Record health data - water intake, weight, blood pressure, checkins, and diet entries.
requires:
  env:
    - HEALTH_API_URL
    - HEALTH_API_TOKEN
---

You can record health data via the Health Management System API.

## Authentication
- URL: ${HEALTH_API_URL}
- Header: `Authorization: Bearer ${HEALTH_API_TOKEN}`
- Content-Type: `application/json`

## Available Actions

### 记录饮水（快速）
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/water/records/quick?amount=250"
```
默认250ml，可修改 amount 参数。

### 记录体重
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/weight/records" \
  -d '{"record_date":"'$(date +%Y-%m-%d)'","weight":72.5}'
```

### 记录血压
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/blood-pressure/records" \
  -d '{"record_date":"'$(date +%Y-%m-%d)'","systolic":120,"diastolic":80,"pulse":72}'
```

### 快速打卡
先查询可用模板：
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/checkin/templates"
```
然后打卡（用模板ID）：
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/checkin/records/quick" \
  -d '{"template_id":1,"value":30}'
```

### 记录饮食
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/diet/records" \
  -d '{"record_date":"'$(date +%Y-%m-%d)'","meal_type":"LUNCH","food_items":"鸡胸肉沙拉","calories":400}'
```
meal_type: BREAKFAST / LUNCH / DINNER / EXTRA

## Rules
- Confirm the action with the user before recording
- After successful recording, report what was saved
- Parse natural language: "喝了一杯水" → 250ml, "喝了两杯" → 500ml
- Parse weight: "体重72公斤" → 72.0, "72.5kg" → 72.5
- Parse blood pressure: "血压120/80" → systolic=120, diastolic=80
- Always respond in Chinese
```

**Step 4: Write health-analysis skill**

Create `openclaw-skills/health-analysis/SKILL.md`:
```yaml
---
name: health-analysis
description: Get AI health analysis, daily recommendations, health trend predictions, and health scores.
requires:
  env:
    - HEALTH_API_URL
    - HEALTH_API_TOKEN
---

You can request health analysis and recommendations from the Health Management System.

## Authentication
- URL: ${HEALTH_API_URL}
- Header: `Authorization: Bearer ${HEALTH_API_TOKEN}`

## Available Endpoints

### 健康问题检测
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/analysis/me/issues"
```
返回潜在健康问题及严重程度。

### 今日推荐（刷新）
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/daily-recommendation/me/refresh?use_llm=true"
```
AI 生成个性化运动、饮食、作息建议。

### 健康趋势预测
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/health-trend/me/prediction?days=30"
```
预测未来7天的睡眠、心率、压力等趋势。

### 健康风险因素
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/health-trend/me/risk-factors"
```

### 今日健康评分
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/health-score/daily/me"
```
返回0-100综合评分及各维度（运动、睡眠、营养、水分、压力）。

### 健康评分趋势
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/health-score/trend/me?days=7"
```

## Response Rules
- Present analysis in structured, readable format
- Use severity levels: 🟢 正常, 🟡 注意, 🔴 警告
- Highlight important trends and anomalies
- Provide actionable suggestions
- Always respond in Chinese
```

**Step 5: Write README**

Create `openclaw-skills/README.md`:
```markdown
# Health Management OpenClaw Skills

三个 OpenClaw Skills，让你在任何 OpenClaw 连接的渠道（Telegram、Discord、微信等）管理健康数据。

## 安装

将 skill 目录复制到 OpenClaw 的 skills 目录：

```bash
cp -r health-query health-record health-analysis ~/.openclaw/skills/
```

## 配置

在 `~/.openclaw/openclaw.json` 中添加：

```json
{
  "skills": {
    "entries": {
      "health-query": {
        "env": {
          "HEALTH_API_URL": "https://your-health-api.com/api/v1",
          "HEALTH_API_TOKEN": "your-jwt-token"
        }
      },
      "health-record": {
        "env": {
          "HEALTH_API_URL": "https://your-health-api.com/api/v1",
          "HEALTH_API_TOKEN": "your-jwt-token"
        }
      },
      "health-analysis": {
        "env": {
          "HEALTH_API_URL": "https://your-health-api.com/api/v1",
          "HEALTH_API_TOKEN": "your-jwt-token"
        }
      }
    }
  }
}
```

## 使用示例

- "查一下我今天的步数"
- "最近一周的睡眠数据"
- "记录喝水250ml"
- "体重72公斤"
- "血压120/80"
- "俯卧撑打卡30个"
- "分析我的健康趋势"
- "今天的健康建议"
```

**Step 6: Commit**

```bash
git add openclaw-skills/
git commit -m "feat: OpenClaw Skills - health-query, health-record, health-analysis"
```

---

### Task 7: LLM Provider — Add `tools` Parameter Support

**Files:**
- Modify: `backend/app/services/llm/base.py`
- Modify: `backend/app/services/llm/providers/openai_provider.py`
- Modify: `backend/app/services/llm/providers/openclaw_provider.py`
- Test: `backend/tests/test_llm_provider.py` (add new tests)

**Step 1: Write the failing test**

Add to `backend/tests/test_llm_provider.py`:
```python
# ---- Function Calling / Tools Tests ----

class TestOpenAIProviderTools:
    """OpenAI Provider tools 参数测试"""

    @pytest.fixture
    def provider(self):
        return OpenAIProvider(api_key="test-key", model="gpt-4o-mini")

    @pytest.fixture
    def sample_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "record_water",
                    "description": "记录饮水量",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "amount_ml": {"type": "integer", "description": "饮水量(毫升)"}
                        },
                        "required": ["amount_ml"],
                    },
                },
            }
        ]

    @patch("app.services.llm.providers.openai_provider.asyncio.to_thread")
    @pytest.mark.asyncio
    async def test_chat_with_tools_passes_to_sdk(self, mock_to_thread, provider, sample_tools):
        """tools 参数应透传给 OpenAI SDK"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "已记录"
        mock_response.choices[0].message.tool_calls = None
        mock_to_thread.return_value = mock_response

        with patch.object(provider, "_get_client") as mock_client:
            mock_client.return_value = MagicMock()
            result = await provider.chat(
                messages=[{"role": "user", "content": "喝水250"}],
                tools=sample_tools,
            )
            # tools 应通过 **kwargs 透传
            call_kwargs = mock_to_thread.call_args
            assert "tools" in str(call_kwargs)


class TestOpenClawProviderTools:
    """OpenClaw Provider tools 参数测试"""

    @pytest.fixture
    def provider(self):
        return OpenClawProvider(
            base_url="https://test.com/v1",
            api_key="test-key",
        )

    @pytest.fixture
    def sample_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "record_water",
                    "description": "记录饮水量",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "amount_ml": {"type": "integer"}
                        },
                        "required": ["amount_ml"],
                    },
                },
            }
        ]

    @pytest.mark.asyncio
    async def test_chat_with_tools_includes_in_payload(self, provider, sample_tools):
        """tools 参数应包含在 HTTP payload 中"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "已记录", "tool_calls": None}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            result = await provider.chat(
                messages=[{"role": "user", "content": "喝水250"}],
                tools=sample_tools,
            )
            # 验证 POST payload 包含 tools
            post_call = mock_instance.post.call_args
            payload = post_call.kwargs.get("json", {})
            assert "tools" in payload
            assert payload["tools"] == sample_tools

    @pytest.mark.asyncio
    async def test_chat_with_tool_calls_returns_dict(self, provider):
        """当 LLM 返回 tool_calls 时，chat 应返回包含 tool_calls 的结构"""
        tool_calls_data = [
            {
                "id": "call_123",
                "type": "function",
                "function": {"name": "record_water", "arguments": '{"amount_ml": 250}'},
            }
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": tool_calls_data,
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            result = await provider.chat(
                messages=[{"role": "user", "content": "喝水250"}],
                tools=[{"type": "function", "function": {"name": "record_water"}}],
            )
            # tool_calls 时返回 dict 而非 str
            assert isinstance(result, dict)
            assert "tool_calls" in result
            assert result["tool_calls"][0]["function"]["name"] == "record_water"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_llm_provider.py -k "Tools" -v`
Expected: FAIL

**Step 3: Modify OpenClaw Provider to support tools**

In `backend/app/services/llm/providers/openclaw_provider.py`, modify the `chat()` method:

1. Accept `tools` from `**kwargs`
2. Include `tools` in the HTTP payload when present
3. When the response contains `tool_calls` instead of `content`, return a dict with `tool_calls`

```python
# In chat() method, after building payload:
tools = kwargs.get("tools")
if tools:
    payload["tools"] = tools

# After getting response, before return:
message = data.get("choices", [{}])[0].get("message", {})
tool_calls = message.get("tool_calls")
if tool_calls:
    return {
        "content": message.get("content"),
        "tool_calls": tool_calls,
    }
content = message.get("content", "")
return content.strip()
```

**Step 4: Modify OpenAI Provider**

The OpenAI provider already passes `**kwargs` to `client.chat.completions.create()`, which naturally supports `tools`. But we need to handle the `tool_calls` response similarly:

In the `chat()` method's non-streaming branch, after getting response:
```python
message = response.choices[0].message
if message.tool_calls:
    return {
        "content": message.content,
        "tool_calls": [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ],
    }
content = message.content or ""
return content.strip()
```

**Step 5: Update base.py docstring**

Update the `chat()` method docstring in base.py to mention tools:
```python
"""
...
    **kwargs: 额外参数（如 tools 用于 function calling）

Returns:
    stream=False: 返回完整的响应字符串，或当 LLM 返回 tool_calls 时返回 dict
    stream=True: 返回 AsyncIterator[str]，逐 token yield
"""
```

**Step 6: Run tests**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_llm_provider.py -v`
Expected: All tests pass (existing + 3 new)

**Step 7: Commit**

```bash
git add backend/app/services/llm/ backend/tests/test_llm_provider.py
git commit -m "feat: LLM Provider tools/function calling support"
```

---

### Task 8: Chat Service — Define Health Tools Schema

**Files:**
- Create: `backend/app/services/chat_tools.py`
- Test: `backend/tests/test_chat_tools.py`

**Step 1: Write the failing test**

Create `backend/tests/test_chat_tools.py`:
```python
"""测试 Chat Tools Schema 定义"""
import json
import pytest
from app.services.chat_tools import HEALTH_TOOLS, get_tool_by_name, execute_tool


def test_health_tools_format():
    """所有工具都符合 OpenAI function calling 格式"""
    assert len(HEALTH_TOOLS) >= 5
    for tool in HEALTH_TOOLS:
        assert tool["type"] == "function"
        func = tool["function"]
        assert "name" in func
        assert "description" in func
        assert "parameters" in func
        assert func["parameters"]["type"] == "object"


def test_get_tool_by_name():
    """能通过名称查找工具"""
    tool = get_tool_by_name("record_water")
    assert tool is not None
    assert tool["function"]["name"] == "record_water"


def test_get_tool_by_name_not_found():
    """查找不存在的工具返回 None"""
    tool = get_tool_by_name("nonexistent_tool")
    assert tool is None


def test_tool_names_unique():
    """工具名称唯一"""
    names = [t["function"]["name"] for t in HEALTH_TOOLS]
    assert len(names) == len(set(names))
```

**Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_chat_tools.py -v`
Expected: FAIL

**Step 3: Write chat_tools.py**

Create `backend/app/services/chat_tools.py`:
```python
"""Chat Function Calling Tools 定义

定义健康系统的 tools schema，供 LLM Function Calling 使用。
"""
from typing import Optional, Dict, Any, List


HEALTH_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "record_water",
            "description": "记录用户饮水量",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount_ml": {
                        "type": "integer",
                        "description": "饮水量，单位毫升，默认250",
                    }
                },
                "required": ["amount_ml"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_weight",
            "description": "记录用户体重",
            "parameters": {
                "type": "object",
                "properties": {
                    "weight_kg": {
                        "type": "number",
                        "description": "体重，单位千克",
                    }
                },
                "required": ["weight_kg"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_blood_pressure",
            "description": "记录用户血压",
            "parameters": {
                "type": "object",
                "properties": {
                    "systolic": {"type": "integer", "description": "收缩压（高压）"},
                    "diastolic": {"type": "integer", "description": "舒张压（低压）"},
                    "heart_rate": {"type": "integer", "description": "心率（可选）"},
                },
                "required": ["systolic", "diastolic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_checkin",
            "description": "快速打卡",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_name": {
                        "type": "string",
                        "description": "打卡模板名称，如'俯卧撑'、'深蹲'、'洗鼻'",
                    },
                    "value": {
                        "type": "number",
                        "description": "打卡数值（可选），如俯卧撑30个",
                    },
                },
                "required": ["template_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_diet",
            "description": "记录饮食",
            "parameters": {
                "type": "object",
                "properties": {
                    "meal_type": {
                        "type": "string",
                        "enum": ["breakfast", "lunch", "dinner", "extra"],
                        "description": "餐次：早餐/午餐/晚餐/加餐",
                    },
                    "foods": {
                        "type": "string",
                        "description": "食物描述",
                    },
                    "calories": {
                        "type": "integer",
                        "description": "估算卡路里（可选）",
                    },
                },
                "required": ["meal_type", "foods"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_plan",
            "description": "为用户创建健康周计划",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_week": {
                        "type": "string",
                        "enum": ["current", "next"],
                        "description": "目标周：本周或下周",
                    },
                    "user_focus": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "用户关注重点",
                    },
                },
                "required": ["target_week"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workout_analyze",
            "description": "分析用户最近完成的运动",
            "parameters": {
                "type": "object",
                "properties": {
                    "workout_type": {
                        "type": "string",
                        "description": "运动类型：running/cycling/swimming/hiit/strength/yoga/other",
                    }
                },
                "required": ["workout_type"],
            },
        },
    },
]


def get_tool_by_name(name: str) -> Optional[Dict[str, Any]]:
    """根据名称查找工具定义"""
    for tool in HEALTH_TOOLS:
        if tool["function"]["name"] == name:
            return tool
    return None


async def execute_tool(name: str, arguments: Dict[str, Any], db, user) -> Dict[str, Any]:
    """执行工具调用，返回结果

    这个函数会在 chat_service.py 中被调用，替代原来的 <<<ACTIONS: 解析逻辑。
    """
    # 将在 Task 9 中实现具体逻辑
    return {"status": "not_implemented", "tool": name}
```

**Step 4: Run tests**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_chat_tools.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add backend/app/services/chat_tools.py backend/tests/test_chat_tools.py
git commit -m "feat: Chat tools schema for function calling"
```

---

### Task 9: Chat Service — Implement Tool Executor

**Files:**
- Modify: `backend/app/services/chat_tools.py`
- Modify: `backend/tests/test_chat_tools.py`

**Step 1: Write the failing test for execute_tool**

Add to `backend/tests/test_chat_tools.py`:
```python
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = 1
    return user


@pytest.mark.asyncio
async def test_execute_record_water(mock_db, mock_user):
    """测试执行饮水记录工具"""
    with patch("app.services.chat_tools._record_water") as mock_fn:
        mock_fn.return_value = {"success": True, "amount": 250}
        result = await execute_tool("record_water", {"amount_ml": 250}, mock_db, mock_user)
        assert result["success"] is True
        assert result["amount"] == 250


@pytest.mark.asyncio
async def test_execute_record_weight(mock_db, mock_user):
    """测试执行体重记录工具"""
    with patch("app.services.chat_tools._record_weight") as mock_fn:
        mock_fn.return_value = {"success": True, "weight": 72.5}
        result = await execute_tool("record_weight", {"weight_kg": 72.5}, mock_db, mock_user)
        assert result["success"] is True


@pytest.mark.asyncio
async def test_execute_unknown_tool(mock_db, mock_user):
    """测试执行未知工具返回错误"""
    result = await execute_tool("unknown_tool", {}, mock_db, mock_user)
    assert result.get("error") is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_chat_tools.py -k "execute" -v`
Expected: FAIL

**Step 3: Implement execute_tool with handlers**

Modify `backend/app/services/chat_tools.py` — add tool executor functions:

```python
import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)


async def _record_water(args: Dict, db, user) -> Dict[str, Any]:
    """执行饮水记录"""
    from app.models.water import WaterRecord
    amount = args.get("amount_ml", 250)
    record = WaterRecord(
        user_id=user.id,
        record_date=date.today(),
        amount=amount,
    )
    db.add(record)
    db.commit()
    return {"success": True, "amount": amount, "message": f"已记录饮水 {amount}ml"}


async def _record_weight(args: Dict, db, user) -> Dict[str, Any]:
    """执行体重记录"""
    from app.models.weight import WeightRecord
    weight = args["weight_kg"]
    today = date.today()
    existing = db.query(WeightRecord).filter(
        WeightRecord.user_id == user.id,
        WeightRecord.record_date == today,
    ).first()
    if existing:
        existing.weight = weight
    else:
        record = WeightRecord(user_id=user.id, record_date=today, weight=weight)
        db.add(record)
    db.commit()
    return {"success": True, "weight": weight, "message": f"已记录体重 {weight}kg"}


async def _record_blood_pressure(args: Dict, db, user) -> Dict[str, Any]:
    """执行血压记录"""
    from app.models.blood_pressure import BloodPressureRecord
    record = BloodPressureRecord(
        user_id=user.id,
        record_date=date.today(),
        systolic=args["systolic"],
        diastolic=args["diastolic"],
        pulse=args.get("heart_rate"),
    )
    db.add(record)
    db.commit()
    return {
        "success": True,
        "message": f"已记录血压 {args['systolic']}/{args['diastolic']}",
    }


async def _record_checkin(args: Dict, db, user) -> Dict[str, Any]:
    """执行打卡"""
    from app.models.checkin import CheckinTemplate, CheckinRecord
    template_name = args["template_name"]
    template = db.query(CheckinTemplate).filter(
        CheckinTemplate.user_id == user.id,
        CheckinTemplate.name == template_name,
    ).first()
    if not template:
        return {"success": False, "message": f"未找到打卡模板: {template_name}"}
    record = CheckinRecord(
        user_id=user.id,
        template_id=template.id,
        checkin_date=date.today(),
        value=args.get("value"),
    )
    db.add(record)
    db.commit()
    return {"success": True, "message": f"已完成打卡: {template_name}"}


async def _record_diet(args: Dict, db, user) -> Dict[str, Any]:
    """执行饮食记录"""
    from app.models.diet import DietRecord
    meal_map = {"breakfast": "BREAKFAST", "lunch": "LUNCH", "dinner": "DINNER", "extra": "EXTRA"}
    record = DietRecord(
        user_id=user.id,
        record_date=date.today(),
        meal_type=meal_map.get(args.get("meal_type", "lunch"), "LUNCH"),
        food_items=args["foods"],
        calories=args.get("calories"),
    )
    db.add(record)
    db.commit()
    return {"success": True, "message": f"已记录饮食: {args['foods']}"}


# 工具名称 → 执行函数映射
TOOL_EXECUTORS = {
    "record_water": _record_water,
    "record_weight": _record_weight,
    "record_blood_pressure": _record_blood_pressure,
    "record_checkin": _record_checkin,
    "record_diet": _record_diet,
}


async def execute_tool(name: str, arguments: Dict[str, Any], db, user) -> Dict[str, Any]:
    """执行工具调用"""
    executor = TOOL_EXECUTORS.get(name)
    if not executor:
        # create_plan 和 workout_analyze 返回特殊标记，由 chat_service 处理
        if name in ("create_plan", "workout_analyze"):
            return {"action_type": name, "arguments": arguments}
        return {"error": f"未知工具: {name}"}
    try:
        return await executor(arguments, db, user)
    except Exception as e:
        logger.error(f"执行工具 {name} 失败: {e}")
        return {"error": str(e)}
```

**Step 4: Run tests**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_chat_tools.py -v`
Expected: All passed

**Step 5: Commit**

```bash
git add backend/app/services/chat_tools.py backend/tests/test_chat_tools.py
git commit -m "feat: Chat tool executor for function calling"
```

---

### Task 10: Chat Service — Migrate to Function Calling

**Files:**
- Modify: `backend/app/services/chat_service.py`

This is the most impactful task. The goal is to add Function Calling support alongside the existing `<<<ACTIONS:` pattern (not replace it yet), so both approaches work during the transition.

**Step 1: Add tool calling to non-streaming chat**

In `chat_service.py`, find the `send_message()` method (non-streaming path). After the LLM call, check if the response is a dict with `tool_calls`:

```python
# In the send_message method, after calling provider.chat():
from app.services.chat_tools import HEALTH_TOOLS, execute_tool

# Add tools to the LLM call
reply_content = await self._call_openclaw(messages, tools=HEALTH_TOOLS)

# Check for tool_calls response
if isinstance(reply_content, dict) and reply_content.get("tool_calls"):
    tool_results = []
    for tc in reply_content["tool_calls"]:
        func_name = tc["function"]["name"]
        func_args = json.loads(tc["function"]["arguments"])
        result = await execute_tool(func_name, func_args, self.db, self.user)
        tool_results.append(result)

    # Send tool results back to LLM for natural language response
    messages.append({"role": "assistant", "content": None, "tool_calls": reply_content["tool_calls"]})
    for i, tc in enumerate(reply_content["tool_calls"]):
        messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": json.dumps(tool_results[i], ensure_ascii=False),
        })
    # Get final response from LLM
    reply_content = await self._call_openclaw(messages)
```

**Step 2: Update _call_openclaw to accept tools**

```python
async def _call_openclaw(self, messages, tools=None):
    provider = get_llm_provider()
    kwargs = {}
    if tools:
        kwargs["tools"] = tools
    return await provider.chat(messages=messages, **kwargs)
```

**Step 3: Keep <<<ACTIONS: as fallback**

The existing `_parse_actions()` method stays as fallback. If the LLM doesn't use tool_calls (e.g., when using a model that doesn't support function calling), the regex parsing still works.

**Step 4: Test manually by running the backend**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/ -x --timeout=30 -q`
Expected: All existing tests pass

**Step 5: Commit**

```bash
git add backend/app/services/chat_service.py
git commit -m "feat: chat service function calling support (alongside <<<ACTIONS: fallback)"
```

---

### Task 11: Integration Verification + README

**Files:**
- Create: `mcp-server/README.md`
- Modify: root `README.md` or create integration docs

**Step 1: Run all MCP Server tests**

```bash
cd mcp-server && python -m pytest tests/ -v
```
Expected: 23+ passed

**Step 2: Run all backend tests**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/ -x -q
```
Expected: All tests pass (150+)

**Step 3: Write MCP Server README**

Create `mcp-server/README.md`:
```markdown
# Health MCP Server

A Model Context Protocol (MCP) server that exposes health management capabilities to any AI client.

## Quick Start

### Local (stdio mode)
```bash
export HEALTH_API_URL=https://your-health-api.com/api/v1
export HEALTH_API_TOKEN=your-jwt-token
pip install -r requirements.txt
python server.py
```

### Remote (SSE mode)
```bash
export MCP_TRANSPORT=sse
export MCP_SSE_PORT=8808
python server.py
```

### Docker
```bash
docker compose up mcp-server
```

## Available Tools

### Query Tools (10)
- `get_health_summary` - Health overview (steps, heart rate, sleep)
- `get_weight_history` - Weight records
- `get_blood_pressure_history` - Blood pressure records
- `get_water_intake` - Water intake
- `get_sleep_data` - Sleep analysis
- `get_heart_rate` - Heart rate & HRV
- `get_workout_history` - Workout records
- `get_diet_records` - Diet records
- `get_checkin_status` - Checkin status
- `get_achievements` - Badges & achievements

### Record Tools (5)
- `record_water` - Log water intake
- `record_weight` - Log weight
- `record_blood_pressure` - Log blood pressure
- `record_checkin` - Quick checkin
- `record_diet` - Log diet

### Analysis Tools (3)
- `get_health_analysis` - AI health analysis
- `get_daily_recommendation` - Daily health tips
- `get_health_trends` - Health trend predictions

## Claude Desktop Configuration

Add to `~/.claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "health": {
      "command": "python",
      "args": ["path/to/mcp-server/server.py"],
      "env": {
        "HEALTH_API_URL": "https://your-health-api.com/api/v1",
        "HEALTH_API_TOKEN": "your-jwt-token"
      }
    }
  }
}
```
```

**Step 4: Commit**

```bash
git add mcp-server/README.md
git commit -m "docs: MCP Server and OpenClaw Skills documentation"
```

---

### Task 12: Deploy and Test on Production

**Step 1: Commit all remaining changes and push**

```bash
git push
```

**Step 2: Deploy backend (for function calling changes)**

```bash
./deploy.sh -b
```

**Step 3: Copy OpenClaw Skills to Gateway**

```bash
scp -r openclaw-skills/health-query openclaw-skills/health-record openclaw-skills/health-analysis root@39.98.206.178:~/.openclaw/skills/
```

**Step 4: Configure OpenClaw Gateway**

SSH into the server and update `~/.openclaw/openclaw.json` with the API credentials:
```json
{
  "skills": {
    "entries": {
      "health-query": {
        "env": {
          "HEALTH_API_URL": "https://health-api.executor.life/api/v1",
          "HEALTH_API_TOKEN": "<generate-a-long-lived-jwt>"
        }
      },
      "health-record": {
        "env": {
          "HEALTH_API_URL": "https://health-api.executor.life/api/v1",
          "HEALTH_API_TOKEN": "<same-token>"
        }
      },
      "health-analysis": {
        "env": {
          "HEALTH_API_URL": "https://health-api.executor.life/api/v1",
          "HEALTH_API_TOKEN": "<same-token>"
        }
      }
    }
  }
}
```

**Step 5: Restart OpenClaw Gateway**

```bash
openclaw restart
```

**Step 6: Test via OpenClaw channel**

Send test messages through Telegram or Web UI:
- "查一下我今天的步数"
- "记录喝水250ml"
- "分析我的健康趋势"

**Step 7: Final commit**

```bash
git commit -m "chore: production deployment for OpenClaw integration"
```
