import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _declare_explicit_turn_for_raw_manage_handler_contracts(monkeypatch):
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.tool_gateway import ToolGateway
    from app.services.agent_kernel.types import ToolExecutionResult

    original = AgentExecutor._execute_tool

    async def with_explicit_test_turn(self, tool_name, args_raw, user_token):
        self._current_user_id = self._current_user_id or 1
        if not getattr(self, "_current_turn_user_message", ""):
            self._current_turn_user_message = (
                "记录测试健康目标" if tool_name == "health_record" else "修改测试健康记录"
            )
        return await original(self, tool_name, args_raw, user_token)

    monkeypatch.setattr(AgentExecutor, "_execute_tool", with_explicit_test_turn)

    async def dispatch_adapter_contract(
        self,
        request,
        dispatch,
        *,
        on_decision=None,
    ):
        return ToolExecutionResult(
            tool_name=request.tool_name,
            content=await dispatch(request),
        )

    # This file verifies URL/payload adapter contracts. Capability authorization
    # and real zero-dispatch behavior are covered separately by kernel tests.
    monkeypatch.setattr(ToolGateway, "execute", dispatch_adapter_contract)


@pytest.mark.asyncio
async def test_health_manage_deletes_diet_record_by_id(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3
    executor._current_turn_user_message = "删除饮食记录 605"

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
    assert json.loads(result)["message"] == "Record deleted successfully"


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
    assert json.loads(result)["message"] == "已更新饮食：鳕鱼 50g + 鲍鱼 2个"


@pytest.mark.asyncio
async def test_health_manage_lists_diet_candidates_by_explicit_meal_type(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_get(url, headers):
        captured["url"] = url
        return '[{"id":605,"meal_type":"dinner","food_items":"原晚餐"}]'

    with patch.object(executor, "_api_get", new=AsyncMock(side_effect=fake_get)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "diet",
                "operation": "list",
                "date": "2026-07-08",
                "meal_type": "晚餐",
                "limit": 50,
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith(
        "/diet/records/me?limit=50&start_date=2026-07-08&end_date=2026-07-08&meal_type=dinner"
    )
    assert json.loads(result)[0]["id"] == 605


@pytest.mark.asyncio
async def test_health_manage_list_never_auto_deletes_numbered_diet_candidate(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3
    executor._current_turn_user_message = "删除早餐 1"

    captured = {"deleted": []}

    async def fake_get(url, headers):
        captured["list_url"] = url
        return json.dumps([
            {"id": 701, "meal_type": "breakfast", "food_items": "大米粥"},
            {"id": 702, "meal_type": "breakfast", "food_items": "咸鸭蛋"},
        ], ensure_ascii=False)

    async def fake_delete(url, headers):
        captured["deleted"].append(url)
        return '{"message":"Record deleted successfully"}'

    with (
        patch.object(executor, "_api_get", new=AsyncMock(side_effect=fake_get)),
        patch.object(executor, "_api_delete", new=AsyncMock(side_effect=fake_delete)),
    ):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "diet",
                "operation": "list",
                "date": "today",
                "meal_type": "breakfast",
            }),
            user_token="test-token",
        )

    assert "start_date=today" not in captured["list_url"]
    assert captured["deleted"] == []
    payload = json.loads(result)
    assert [item["id"] for item in payload] == [701, 702]


@pytest.mark.asyncio
async def test_health_manage_update_normalizes_zh_diet_meal_type_patch(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_put(url, headers, payload):
        captured["payload"] = payload
        return '{"id":605,"meal_type":"dinner"}'

    with patch.object(executor, "_api_put", new=AsyncMock(side_effect=fake_put)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "diet",
                "operation": "update",
                "record_id": 605,
                "data": {"meal_type": "晚餐", "food_items": "蛋黄酥 2/3"},
            }),
            user_token="test-token",
        )

    assert captured["payload"]["meal_type"] == "dinner"
    assert json.loads(result)["meal_type"] == "dinner"


@pytest.mark.asyncio
async def test_health_manage_deletes_exercise_record_by_id(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3
    executor._current_turn_user_message = "删除运动记录 42"

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
        return '[{"id":15,"supplement_id":7,"taken":true}]'

    with patch.object(executor, "_api_get", new=AsyncMock(side_effect=fake_get)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({"record_type": "supplement", "operation": "list"}),
            user_token="test-token",
        )

    assert captured["url"].endswith("/supplements/me/records?limit=20")
    assert json.loads(result)[0]["id"] == 15


@pytest.mark.asyncio
async def test_health_manage_lists_medical_exam_report_summaries(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3
    captured = {}

    async def fake_get(url, headers):
        captured["url"] = url
        captured["headers"] = headers
        return '[{"id":31,"exam_date":"2026-07-01","exam_type":"MRI","items_count":6}]'

    with patch.object(executor, "_api_get", new=AsyncMock(side_effect=fake_get)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "medical_exam",
                "operation": "list",
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/medical-exams/me/reports?limit=20")
    assert captured["headers"]["Authorization"] == "Bearer test-token"
    assert json.loads(result)[0]["id"] == 31


@pytest.mark.asyncio
async def test_health_manage_rejects_medical_exam_mutation(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    with patch.object(executor, "_api_put", new=AsyncMock()) as put_mock:
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "medical_exam",
                "operation": "update",
                "record_id": 31,
                "data": {"overall_assessment": "改写报告"},
            }),
            user_token="test-token",
        )

    put_mock.assert_not_called()
    assert "medical_exam" in result
    assert "只支持 list" in result


@pytest.mark.asyncio
async def test_health_manage_updates_and_deletes_supplement_record_by_id(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3
    captured = {}

    async def fake_put(url, headers, payload):
        captured["put_url"] = url
        captured["payload"] = payload
        return '{"id":15,"taken":false,"notes":"误记"}'

    async def fake_delete(url, headers):
        captured["delete_url"] = url
        return '{"message":"删除成功","record_id":15}'

    with patch.object(executor, "_api_put", new=AsyncMock(side_effect=fake_put)):
        updated = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "supplement",
                "operation": "update",
                "record_id": 15,
                "data": {"taken": False, "notes": "误记"},
            }),
            user_token="test-token",
        )
    with patch.object(executor, "_api_delete", new=AsyncMock(side_effect=fake_delete)):
        executor._current_turn_user_message = "删除补剂记录 15"
        deleted = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "supplement",
                "operation": "delete",
                "record_id": 15,
            }),
            user_token="test-token",
        )

    assert captured["put_url"].endswith("/supplements/records/15")
    assert captured["payload"] == {"taken": False, "notes": "误记"}
    assert json.loads(updated)["taken"] is False
    assert captured["delete_url"].endswith("/supplements/records/15")
    assert json.loads(deleted)["record_id"] == 15


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


@pytest.mark.asyncio
async def test_health_record_creates_goal(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3
    executor._current_turn_user_message = "创建目标：90天把腰围降到82cm"

    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        return json.dumps({"id": 22, **payload}, ensure_ascii=False)

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "goal",
                "data": {
                    "title": "90 天把腰围降到 82cm",
                    "goal_type": "weight",
                    "goal_period": "daily",
                    "target_value": 82,
                    "target_unit": "cm",
                    "start_date": "2026-07-05",
                },
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/goals/")
    assert captured["headers"]["Authorization"] == "Bearer test-token"
    assert captured["payload"]["title"] == "90 天把腰围降到 82cm"
    assert captured["payload"]["goal_type"] == "weight"
    assert json.loads(result)["id"] == 22


@pytest.mark.asyncio
async def test_health_manage_lists_updates_and_deletes_goals(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3
    captured = {}

    async def fake_get(url, headers):
        captured["list_url"] = url
        return '[{"id":22,"title":"每日运动30分钟"}]'

    async def fake_put(url, headers, payload):
        captured["put_url"] = url
        captured["payload"] = payload
        return json.dumps({"id": 22, **payload}, ensure_ascii=False)

    async def fake_delete(url, headers):
        captured["delete_url"] = url
        return '{"message":"删除成功","record_id":22}'

    with patch.object(executor, "_api_get", new=AsyncMock(side_effect=fake_get)):
        listed = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({"record_type": "goal", "operation": "list"}),
            user_token="test-token",
        )
    with patch.object(executor, "_api_put", new=AsyncMock(side_effect=fake_put)):
        updated = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "goal",
                "operation": "update",
                "record_id": 22,
                "data": {"status": "paused", "notes": "膝盖恢复期暂停"},
            }),
            user_token="test-token",
        )
    with patch.object(executor, "_api_delete", new=AsyncMock(side_effect=fake_delete)):
        executor._current_turn_user_message = "删除目标记录 22"
        deleted = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "goal",
                "operation": "delete",
                "record_id": 22,
            }),
            user_token="test-token",
        )

    assert captured["list_url"].endswith("/goals/me")
    assert json.loads(listed)[0]["id"] == 22
    assert captured["put_url"].endswith("/goals/22")
    assert captured["payload"] == {"status": "paused", "notes": "膝盖恢复期暂停"}
    assert json.loads(updated)["status"] == "paused"
    assert captured["delete_url"].endswith("/goals/22")
    assert json.loads(deleted)["record_id"] == 22


@pytest.mark.asyncio
async def test_health_manage_resolves_illness_normalizes_relative_end_date(db):
    """病症痊愈: data.end_date='昨天' 必须在工具边界折算成 ISO。

    否则相对词字面命中 IllnessEpisodePatch.end_date: date → 422 → 失败标记 →
    写入回执守卫误报「没取得可验证写入回执」(founder 实测「舌尖溃疡昨天好了,
    修改记录」失败根因)。顶层 args['date'] 早已归一,data 内 date 字段之前没有。
    """
    from app.services.agent_executor import AgentExecutor, _normalize_relative_date

    executor = AgentExecutor(db)
    executor._current_user_id = 3

    captured = {}

    async def fake_put(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return json.dumps({
            "id": 71, "name": "舌尖溃疡", "start_date": "2026-07-10",
            "end_date": payload.get("end_date"), "status": "resolved", "severity": 2,
        }, ensure_ascii=False)

    with patch.object(executor, "_api_put", new=AsyncMock(side_effect=fake_put)):
        result = await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "illness",
                "operation": "update",
                "record_id": 71,
                "data": {"status": "resolved", "end_date": "昨天"},
            }),
            user_token="test-token",
        )

    assert captured["url"].endswith("/illness/episodes/71")
    # 关键: 相对词被折算成 ISO, 绝不原样发出(否则 422)
    assert captured["payload"]["end_date"] == _normalize_relative_date("昨天")
    assert captured["payload"]["end_date"] != "昨天"
    assert captured["payload"]["status"] == "resolved"
    parsed = json.loads(result)
    assert parsed["id"] == 71 and parsed["status"] == "resolved"


@pytest.mark.asyncio
async def test_health_manage_resolve_illness_drops_unparseable_end_date(db):
    """折不出的相对词字段丢弃(降级到后端默认: resolved 自动补 today), 绝不发垃圾串 422。"""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 3
    captured = {}

    async def fake_put(url, headers, payload):
        captured["payload"] = payload
        return json.dumps({
            "id": 9, "name": "口腔溃疡", "start_date": "2026-07-08",
            "status": "resolved", "severity": 1,
        }, ensure_ascii=False)

    with patch.object(executor, "_api_put", new=AsyncMock(side_effect=fake_put)):
        await executor._execute_tool(
            tool_name="health_manage",
            args_raw=json.dumps({
                "record_type": "illness", "operation": "update", "record_id": 9,
                "data": {"status": "resolved", "end_date": "过一阵子"},
            }),
            user_token="test-token",
        )

    assert "end_date" not in captured["payload"]   # 丢弃, 不触发 422
    assert captured["payload"]["status"] == "resolved"


def test_illness_update_result_recognized_as_write_receipt():
    """成功的病症痊愈 update 必须被识别为可验证写入回执。

    否则即使真写成功, 写入诚实守卫(_write_tool_completed→_unverified_write_message)
    也会误报『没取得写入回执』, 就是截图那句兜底文案。这是回执层的回归护栏。
    """
    from app.services.agent_executor import (
        _write_tool_completed, _write_receipt_from_tool_result,
    )

    args = json.dumps({
        "record_type": "illness", "operation": "update", "record_id": 71,
        "data": {"status": "resolved"},
    })
    result = json.dumps({
        "id": 71, "name": "舌尖溃疡", "start_date": "2026-07-10",
        "end_date": "2026-07-15", "status": "resolved", "severity": 2,
    }, ensure_ascii=False)

    assert _write_tool_completed("health_manage", args, result) is True
    receipt = _write_receipt_from_tool_result("health_manage", "illness", result)
    assert receipt is not None
    assert receipt["resource_type"] == "illness_episode"
    assert receipt["resource_id"] == "71"
    assert receipt["verified"] is True


def test_illness_guidance_routes_local_healing_conditions():
    """回归护栏: 口腔溃疡这类"有起病→痊愈周期的局部病灶"指引必须落在 illness(可 resolve),
    不在 symptom catch-all; health_manage 必须有痊愈→resolve 的流程指引。
    (根因: 指引把口腔溃疡推向无 status/end_date 的 SymptomEntry → 无对象可标痊愈。)
    """
    from app.services.tool_schema_registry import get_health_tools

    tools = get_health_tools()
    # record_type/data 指引在嵌套 property description 里, 全量序列化后再断言
    by_name = {t["function"]["name"]: json.dumps(t, ensure_ascii=False) for t in tools}
    rec = by_name["health_record"]
    mng = by_name["health_manage"]

    # 局部愈合病灶明确锚定到 illness 段
    assert "口腔溃疡" in rec
    assert "局部会愈合的病灶" in rec
    # symptom 不再是"任何偶发症状都走这个"的 catch-all
    assert "任何偶发症状都走这个" not in rec
    # 安全加固: 急性危险症状硬分流护栏(绝不因"会不会好"误归 illness)
    assert "急性危险症状永远走 symptom" in rec
    # health_manage 有痊愈/resolve 的显式流程指引
    assert "病症痊愈/好转" in mng
    assert "resolved" in mng
