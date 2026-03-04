"""测试 5 个健康数据记录工具"""
import json
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.record import (
    record_blood_pressure,
    record_checkin,
    record_diet,
    record_water,
    record_weight,
)


@pytest.fixture
def mock_client():
    """Mock get_client() 返回一个带有 AsyncMock get/post 方法的客户端"""
    with patch("tools.record.get_client") as mock_get_client:
        client = AsyncMock()
        mock_get_client.return_value = client
        yield client


# ---- 1. record_water ----

@pytest.mark.asyncio
async def test_record_water(mock_client):
    mock_client.post.return_value = {"id": 1, "amount_ml": 250, "record_time": "08:30"}

    result = await record_water(250)
    data = json.loads(result)

    assert data["amount_ml"] == 250
    mock_client.post.assert_called_once_with(
        "/water/records/quick", params={"amount": 250}
    )


# ---- 2. record_weight ----

@pytest.mark.asyncio
async def test_record_weight(mock_client):
    mock_client.post.return_value = {"id": 1, "weight": 72.5, "record_date": "2026-03-04"}

    result = await record_weight(72.5)
    data = json.loads(result)

    assert data["weight"] == 72.5
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "/weight/records"
    assert call_args[1]["data"]["weight"] == 72.5
    assert "record_date" in call_args[1]["data"]


# ---- 3. record_blood_pressure (without heart_rate) ----

@pytest.mark.asyncio
async def test_record_blood_pressure(mock_client):
    mock_client.post.return_value = {
        "id": 1, "systolic": 120, "diastolic": 80, "record_date": "2026-03-04"
    }

    result = await record_blood_pressure(120, 80)
    data = json.loads(result)

    assert data["systolic"] == 120
    assert data["diastolic"] == 80
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "/blood-pressure/records"
    body = call_args[1]["data"]
    assert body["systolic"] == 120
    assert body["diastolic"] == 80
    assert "pulse" not in body


# ---- 4. record_blood_pressure (with heart_rate) ----

@pytest.mark.asyncio
async def test_record_blood_pressure_with_heart_rate(mock_client):
    mock_client.post.return_value = {
        "id": 1, "systolic": 130, "diastolic": 85, "pulse": 72, "record_date": "2026-03-04"
    }

    result = await record_blood_pressure(130, 85, heart_rate=72)
    data = json.loads(result)

    assert data["pulse"] == 72
    call_args = mock_client.post.call_args
    body = call_args[1]["data"]
    assert body["pulse"] == 72


# ---- 5. record_checkin ----

@pytest.mark.asyncio
async def test_record_checkin(mock_client):
    # 模拟模板列表
    mock_client.get.return_value = [
        {"id": 1, "name": "跑步", "unit": "km"},
        {"id": 2, "name": "俯卧撑", "unit": "个"},
    ]
    mock_client.post.return_value = {"id": 10, "template_id": 1, "value": 5.0}

    result = await record_checkin("跑步", value=5.0)
    data = json.loads(result)

    assert data["template_id"] == 1
    assert data["value"] == 5.0
    mock_client.get.assert_called_once_with("/checkin/templates")
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "/checkin/records/quick"
    body = call_args[1]["data"]
    assert body["template_id"] == 1
    assert body["value"] == 5.0


# ---- 6. record_diet ----

@pytest.mark.asyncio
async def test_record_diet(mock_client):
    mock_client.post.return_value = {
        "id": 1, "meal_type": "LUNCH", "food_items": "鸡胸肉沙拉", "calories": 450
    }

    result = await record_diet("午餐", "鸡胸肉沙拉", calories=450)
    data = json.loads(result)

    assert data["meal_type"] == "LUNCH"
    assert data["calories"] == 450
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "/diet/records"
    body = call_args[1]["data"]
    assert body["meal_type"] == "LUNCH"
    assert body["food_items"] == "鸡胸肉沙拉"
    assert body["calories"] == 450
