import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_health_manage_deletes_diet_record_by_id(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_delete(url, headers):
        captured["url"] = url
        captured["headers"] = headers
        return '{"message":"Record deleted successfully"}'

    with patch.object(executor, "_api_delete", new=AsyncMock(side_effect=fake_delete)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "diet",
                "operation": "delete",
                "record_id": 605,
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/diet/records/605")
    assert captured["headers"]["Authorization"] == "Bearer test-token"
    payload = json.loads(result)
    assert payload["message"] == "Record deleted successfully"
    assert payload["record_id"] == 605
    assert payload["id"] == 605
    assert payload["resource_type"] == "diet_record"


@pytest.mark.asyncio
async def test_health_manage_updates_diet_record_by_id(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_put(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return '{"id":605,"food_items":"鳕鱼 50g + 鲍鱼 2个","calories":378}'

    with patch.object(executor, "_api_put", new=AsyncMock(side_effect=fake_put)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "diet",
                "operation": "update",
                "record_id": 605,
                "data": {"food_items": "鳕鱼 50g + 鲍鱼 2个", "calories": 378},
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/diet/records/605")
    assert captured["payload"]["calories"] == 378
    assert json.loads(result)["id"] == 605


@pytest.mark.asyncio
async def test_health_manage_lists_diet_candidates_by_explicit_meal_type(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_get(url, headers):
        captured["url"] = url
        captured["headers"] = headers
        return '[{"id":706,"meal_type":"dinner","food_items":"蛋黄酥 2/3 + 酸奶 2/3"}]'

    with patch.object(executor, "_api_get", new=AsyncMock(side_effect=fake_get)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "diet",
                "operation": "list",
                "date": "2026-07-08",
                "meal_type": "晚餐",
            }),
            user_token="test-token",
        )

    assert captured["headers"]["Authorization"] == "Bearer test-token"
    assert captured["url"].endswith(
        "/diet/records/me?start_date=2026-07-08&end_date=2026-07-08&meal_type=dinner&limit=50"
    )
    assert json.loads(result)[0]["meal_type"] == "dinner"


@pytest.mark.asyncio
async def test_health_manage_update_normalizes_zh_diet_meal_type_patch(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_put(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return json.dumps({"id": 706, **payload}, ensure_ascii=False)

    with patch.object(executor, "_api_put", new=AsyncMock(side_effect=fake_put)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "diet",
                "operation": "update",
                "record_id": 706,
                "data": {"meal_type": "晚餐", "food_items": "蛋黄酥 2/3 + 酸奶 2/3"},
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/diet/records/706")
    assert captured["payload"]["meal_type"] == "dinner"
    assert json.loads(result)["meal_type"] == "dinner"


@pytest.mark.asyncio
async def test_health_manage_deletes_exercise_record_by_id(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_delete(url, headers):
        captured["url"] = url
        return '{"message":"已删除","id":42}'

    with patch.object(executor, "_api_delete", new=AsyncMock(side_effect=fake_delete)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "exercise",
                "operation": "delete",
                "record_id": 42,
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/daily-health/exercise/42")
    assert json.loads(result)["id"] == 42


@pytest.mark.asyncio
async def test_health_manage_updates_illness_record_by_id(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_put(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return '{"id":7,"status":"resolved"}'

    with patch.object(executor, "_api_put", new=AsyncMock(side_effect=fake_put)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "illness",
                "operation": "update",
                "record_id": 7,
                "data": {"status": "resolved"},
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/illness/episodes/7")
    assert captured["payload"]["status"] == "resolved"
    assert json.loads(result)["status"] == "resolved"


@pytest.mark.asyncio
async def test_health_manage_lists_reminders(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_get(url, headers):
        captured["url"] = url
        return '[{"id":9,"title":"吃药"}]'

    with patch.object(executor, "_api_get", new=AsyncMock(side_effect=fake_get)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "reminder",
                "operation": "list",
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/reminders/me?status=all&limit=50")
    assert json.loads(result)[0]["id"] == 9


@pytest.mark.asyncio
async def test_health_manage_lists_supplement_records(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_get(url, headers):
        captured["url"] = url
        return '[{"id":9,"supplement_id":7,"taken":true}]'

    with patch.object(executor, "_api_get", new=AsyncMock(side_effect=fake_get)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "supplement",
                "operation": "list",
                "date": "2026-07-06",
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/supplements/me/records?start_date=2026-07-06&end_date=2026-07-06&limit=50")
    assert json.loads(result)[0]["id"] == 9


@pytest.mark.asyncio
async def test_health_manage_updates_supplement_record_by_id(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_put(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return '{"id":9,"taken":false,"notes":"误点"}'

    with patch.object(executor, "_api_put", new=AsyncMock(side_effect=fake_put)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "supplement",
                "operation": "update",
                "record_id": 9,
                "data": {"taken": False, "notes": "误点"},
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/supplements/records/9")
    assert captured["payload"] == {"taken": False, "notes": "误点"}
    assert json.loads(result)["taken"] is False


@pytest.mark.asyncio
async def test_health_manage_deletes_supplement_record_by_id(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_delete(url, headers):
        captured["url"] = url
        return '{"message":"删除成功","record_id":9}'

    with patch.object(executor, "_api_delete", new=AsyncMock(side_effect=fake_delete)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "supplement",
                "operation": "delete",
                "record_id": 9,
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/supplements/records/9")
    assert json.loads(result)["record_id"] == 9


@pytest.mark.asyncio
async def test_health_manage_lists_goals(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_get(url, headers):
        captured["url"] = url
        return '[{"id":21,"title":"每日运动40分钟"}]'

    with patch.object(executor, "_api_get", new=AsyncMock(side_effect=fake_get)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "goal",
                "operation": "list",
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/goals/me")
    assert json.loads(result)[0]["id"] == 21


@pytest.mark.asyncio
async def test_health_manage_updates_goal_by_id(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_put(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return '{"id":21,"title":"每日运动40分钟","target_value":40}'

    with patch.object(executor, "_api_put", new=AsyncMock(side_effect=fake_put)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "goal",
                "operation": "update",
                "record_id": 21,
                "data": {"title": "每日运动40分钟", "target_value": 40},
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/goals/21")
    assert captured["payload"]["target_value"] == 40
    assert json.loads(result)["title"] == "每日运动40分钟"


@pytest.mark.asyncio
async def test_health_manage_deletes_goal_by_id(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_delete(url, headers):
        captured["url"] = url
        return '{"message":"目标已删除","goal_id":21}'

    with patch.object(executor, "_api_delete", new=AsyncMock(side_effect=fake_delete)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "goal",
                "operation": "delete",
                "record_id": 21,
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/goals/21")
    assert json.loads(result)["goal_id"] == 21


@pytest.mark.asyncio
async def test_health_manage_lists_medical_exam_reports(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_get(url, headers):
        captured["url"] = url
        return '[{"id":42,"exam_date":"2026-06-30","exam_type":"MRI"}]'

    with patch.object(executor, "_api_get", new=AsyncMock(side_effect=fake_get)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "medical_exam",
                "operation": "list",
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/medical-exams/me?limit=20")
    assert json.loads(result)[0]["id"] == 42


@pytest.mark.asyncio
async def test_health_manage_updates_exercise_record_by_id(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_put(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return '{"id":42,"reps":20,"sets":2}'

    with patch.object(executor, "_api_put", new=AsyncMock(side_effect=fake_put)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "exercise",
                "operation": "update",
                "record_id": 42,
                "data": {"reps": 20, "sets": 2},
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/daily-health/exercise/42")
    assert captured["payload"] == {"reps": 20, "sets": 2}
    assert json.loads(result)["reps"] == 20


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("record_type", "path", "payload"),
    [
        ("symptom", "/symptoms/12", {"severity": 2, "notes": "已缓解"}),
        ("medication_log", "/medication/logs/13", {"status": "skipped", "skip_reason": "医生要求暂停"}),
        ("reminder", "/reminders/14", {"title": "明早复查血压", "priority": "high"}),
    ],
)
async def test_health_manage_updates_remaining_record_types(db, record_type, path, payload):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_put(url, headers, data):
        captured["url"] = url
        captured["payload"] = data
        return json.dumps({"id": int(path.rsplit("/", 1)[1]), **data}, ensure_ascii=False)

    with patch.object(executor, "_api_put", new=AsyncMock(side_effect=fake_put)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": record_type,
                "operation": "update",
                "record_id": int(path.rsplit("/", 1)[1]),
                "data": payload,
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith(path)
    assert captured["payload"] == payload
    assert json.loads(result)["id"] == int(path.rsplit("/", 1)[1])
