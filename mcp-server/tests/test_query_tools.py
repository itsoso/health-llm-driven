"""测试 10 个健康数据查询工具"""
import json
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.query import (
    get_achievements,
    get_blood_pressure_history,
    get_checkin_status,
    get_diet_records,
    get_health_summary,
    get_heart_rate,
    get_sleep_data,
    get_water_intake,
    get_weight_history,
    get_workout_history,
)


@pytest.fixture
def mock_client():
    """Mock get_client() 返回一个带有 AsyncMock get/post 方法的客户端"""
    with patch("tools.query.get_client") as mock_get_client:
        client = AsyncMock()
        mock_get_client.return_value = client
        yield client


# ---- 1. get_health_summary ----

@pytest.mark.asyncio
async def test_get_health_summary(mock_client):
    mock_client.get.return_value = {
        "sleep": {"score": 82, "duration_hours": 7.5},
        "heart_rate": {"resting": 58, "avg": 65},
        "stress": {"avg": 32},
        "body_battery": {"current": 75},
        "activity": {"steps": 8500, "calories": 2100},
    }

    result = await get_health_summary("today")
    data = json.loads(result)

    assert data["sleep"]["score"] == 82
    assert data["heart_rate"]["resting"] == 58
    assert data["activity"]["steps"] == 8500
    mock_client.get.assert_called_once_with(
        "/garmin-analysis/me/comprehensive", params={"days": 1}
    )


@pytest.mark.asyncio
async def test_get_health_summary_week(mock_client):
    mock_client.get.return_value = {"summary": "week"}

    result = await get_health_summary("week")
    json.loads(result)

    mock_client.get.assert_called_once_with(
        "/garmin-analysis/me/comprehensive", params={"days": 7}
    )


# ---- 2. get_weight_history ----

@pytest.mark.asyncio
async def test_get_weight_history(mock_client):
    mock_client.get.return_value = [
        {"id": 1, "weight": 72.5, "record_date": "2026-03-04", "bmi": 23.1},
        {"id": 2, "weight": 72.8, "record_date": "2026-03-03", "bmi": 23.2},
    ]

    result = await get_weight_history(7)
    data = json.loads(result)

    assert len(data) == 2
    assert data[0]["weight"] == 72.5
    mock_client.get.assert_called_once_with(
        "/weight/records/me", params={"limit": 7}
    )


# ---- 3. get_blood_pressure_history ----

@pytest.mark.asyncio
async def test_get_blood_pressure_history(mock_client):
    mock_client.get.return_value = [
        {
            "id": 1,
            "systolic": 120,
            "diastolic": 78,
            "heart_rate": 68,
            "record_date": "2026-03-04",
        },
    ]

    result = await get_blood_pressure_history(7)
    data = json.loads(result)

    assert data[0]["systolic"] == 120
    assert data[0]["diastolic"] == 78
    mock_client.get.assert_called_once_with(
        "/blood-pressure/records/me", params={"limit": 7}
    )


# ---- 4. get_water_intake ----

@pytest.mark.asyncio
async def test_get_water_intake(mock_client):
    mock_client.get.return_value = {
        "date": "2026-03-04",
        "total_ml": 1750,
        "goal_ml": 2000,
        "records": [
            {"id": 1, "amount_ml": 250, "record_time": "08:00"},
            {"id": 2, "amount_ml": 500, "record_time": "10:30"},
        ],
    }

    result = await get_water_intake("2026-03-04")
    data = json.loads(result)

    assert data["total_ml"] == 1750
    assert len(data["records"]) == 2
    mock_client.get.assert_called_once_with("/water/records/me/date/2026-03-04")


# ---- 5. get_sleep_data ----

@pytest.mark.asyncio
async def test_get_sleep_data(mock_client):
    mock_client.get.return_value = {
        "days": [
            {
                "date": "2026-03-03",
                "duration_hours": 7.2,
                "deep_sleep_pct": 22,
                "light_sleep_pct": 50,
                "rem_pct": 20,
                "awake_pct": 8,
                "score": 78,
            }
        ],
        "avg_duration": 7.2,
        "avg_score": 78,
    }

    result = await get_sleep_data(7)
    data = json.loads(result)

    assert data["avg_score"] == 78
    assert len(data["days"]) == 1
    mock_client.get.assert_called_once_with(
        "/garmin-analysis/me/sleep", params={"days": 7}
    )


# ---- 6. get_heart_rate ----

@pytest.mark.asyncio
async def test_get_heart_rate(mock_client):
    mock_client.get.return_value = {
        "days": [
            {
                "date": "2026-03-03",
                "resting_hr": 56,
                "avg_hr": 64,
                "max_hr": 145,
                "hrv": 52,
            }
        ],
        "avg_resting_hr": 56,
    }

    result = await get_heart_rate(7)
    data = json.loads(result)

    assert data["avg_resting_hr"] == 56
    assert data["days"][0]["hrv"] == 52
    mock_client.get.assert_called_once_with(
        "/garmin-analysis/me/heart-rate", params={"days": 7}
    )


# ---- 7. get_workout_history ----

@pytest.mark.asyncio
async def test_get_workout_history(mock_client):
    mock_client.get.return_value = [
        {
            "id": 1,
            "workout_date": "2026-03-03",
            "workout_type": "running",
            "duration_seconds": 1800,
            "distance_meters": 5000,
            "calories": 350,
        },
    ]

    result = await get_workout_history(days=7, workout_type="running")
    data = json.loads(result)

    assert data[0]["workout_type"] == "running"
    assert data[0]["distance_meters"] == 5000
    mock_client.get.assert_called_once_with(
        "/workout/me", params={"days": 7, "workout_type": "running"}
    )


@pytest.mark.asyncio
async def test_get_workout_history_no_type(mock_client):
    mock_client.get.return_value = []

    await get_workout_history(days=30)

    mock_client.get.assert_called_once_with(
        "/workout/me", params={"days": 30}
    )


# ---- 8. get_diet_records ----

@pytest.mark.asyncio
async def test_get_diet_records(mock_client):
    mock_client.get.return_value = [
        {
            "id": 1,
            "record_date": "2026-03-04",
            "meal_type": "breakfast",
            "food_name": "燕麦粥",
            "calories": 280,
            "protein": 8,
            "carbs": 45,
            "fat": 6,
        },
        {
            "id": 2,
            "record_date": "2026-03-04",
            "meal_type": "lunch",
            "food_name": "鸡胸肉沙拉",
            "calories": 450,
            "protein": 35,
            "carbs": 20,
            "fat": 15,
        },
    ]

    result = await get_diet_records(3)
    data = json.loads(result)

    assert len(data) == 2
    assert data[0]["food_name"] == "燕麦粥"
    assert data[1]["calories"] == 450
    mock_client.get.assert_called_once_with(
        "/diet/records/me", params={"limit": 9}
    )


# ---- 9. get_checkin_status ----

@pytest.mark.asyncio
async def test_get_checkin_status(mock_client):
    mock_client.get.return_value = {
        "date": "2026-03-04",
        "templates": [
            {"name": "跑步", "completed": True, "value": "5km"},
            {"name": "饮水", "completed": False, "value": None},
        ],
        "completed_count": 1,
        "total_count": 2,
    }

    result = await get_checkin_status()
    data = json.loads(result)

    assert data["completed_count"] == 1
    assert data["templates"][0]["name"] == "跑步"
    mock_client.get.assert_called_once_with("/checkin/records/today")


# ---- 10. get_achievements ----

@pytest.mark.asyncio
async def test_get_achievements(mock_client):
    mock_client.get.return_value = {
        "badges": [
            {
                "id": 1,
                "name": "三天坚持",
                "category": "streak",
                "unlocked": True,
                "progress": 100,
            },
            {
                "id": 2,
                "name": "饮水新手",
                "category": "activity",
                "unlocked": False,
                "progress": 60,
            },
        ],
        "total_unlocked": 1,
    }

    result = await get_achievements()
    data = json.loads(result)

    assert data["total_unlocked"] == 1
    assert len(data["badges"]) == 2
    assert data["badges"][0]["unlocked"] is True
    mock_client.get.assert_called_once_with("/achievements/me")
