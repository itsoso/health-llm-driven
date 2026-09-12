"""Read/sync outcome regressions through real Pi and the production gateway.

Only provider output and data dispatch are scripted. No external calls or real
health mutations are allowed, including sockets hidden by fallback handlers.
"""
import json
from datetime import date, timedelta

import pytest

from app.models.agent_conversation import AgentMessage
from app.services.agent_executor import AgentExecutor


@pytest.fixture(autouse=True)
def _isolate_twin_cache(isolated_agent_protocol_transport):
    """Keep real Pi subprocess transport, prohibit external network access."""


async def _run_scripted(db, user, monkeypatch, *, query, first_tool, first_args, dispatch, reply, turn_id, forbidden_tool_text=None, actual_sync=False, required_context_text=None, answer_finish_reason="stop"):
    executor = AgentExecutor(db)
    rounds = []
    dispatched = []
    leaked_tool_data = []
    dispatch_errors = []

    async def provider(messages, tools):
        rounds.append(messages)
        if len(rounds) == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "requested-tool", "type": "function", "function": {
                    "name": first_tool, "arguments": json.dumps(first_args),
                },
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            if required_context_text and not any(
                required_context_text in str(m.get("content", "")) for m in messages if m.get("role") == "system"
            ):
                dispatch_errors.append(AssertionError("Verified summary context missing"))
            if forbidden_tool_text and any(
                forbidden_tool_text in str(message.get("content", ""))
                for message in messages if message.get("role") == "tool"
            ):
                leaked_tool_data.append(True)
            yield {"type": "content", "text": reply}
            yield {"type": "finish", "finish_reason": answer_finish_reason}

    async def data_dispatch(request, token):
        dispatched.append(request)
        try:
            if actual_sync:
                return await executor._trigger_garmin_sync()
            return json.dumps(dispatch(request), ensure_ascii=False)
        except Exception as error:
            dispatch_errors.append(error)
            raise

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "Use tools to read data.")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_dispatch_tool_request", data_dispatch)
    events = [event async for event in executor.run_stream(
        user.id, query, client_turn_id=turn_id, client_caps=["genui-table-v1"],
    )]
    assert not dispatch_errors, f"Scripted dispatcher failed: {dispatch_errors!r}"
    assert not leaked_tool_data, "Unattested tool data must not reach the model"
    done = events[-1]["data"]
    assert done["perf"]["agent_kernel"] == "pi"
    persisted = db.query(AgentMessage).filter(AgentMessage.id == done["message_id"]).one()
    assert persisted.meta["turn_outcome"] == done["turn_outcome"]
    assert persisted.meta["completion_status"] == done["completion_status"]
    assert persisted.meta["generation_status"] == done["generation_status"]
    public_text = "".join(event.get("data", {}).get("content", "") for event in events if event.get("event") == "token")
    return executor, done, persisted, public_text, dispatched


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,args", [
    ("health_record", {"record_type": "weight", "data": {"weight": 70}}),
    ("health_query", {"dimension": "sleep", "days": 1}),
])
async def test_existing_data_or_rejected_record_never_proves_sync(db, auth_user_and_headers, monkeypatch, tool, args):
    user, _ = auth_user_and_headers
    executor, done, persisted, public_text, dispatched = await _run_scripted(
        db, user, monkeypatch,
        query=("查询昨天的睡眠记录，再同步佳明数据" if tool == "health_query" else "对昨天的佳明的数据进行同步。"),
        first_tool=tool, first_args=args,
        dispatch=lambda request: {"records": [{"sleep_score": 80}], "availability": "available"},
        reply="已自动同步昨天的数据，所有记录已经更新。", turn_id=f"sync-false-{tool}",
    )
    assert executor._turn_sync_queued is False
    assert not done["write_receipts"]
    assert done["completion_status"] == "error"
    assert done["turn_outcome"]["status"] in {"blocked", "failed"}
    assert "同步" in persisted.content and "没有" in persisted.content
    assert "已自动同步" not in persisted.content
    assert "已自动同步" not in public_text
    if tool == "health_record":
        assert not dispatched, "The gateway must reject the unrelated write before dispatch"
    else:
        assert dispatched, "Exercise successful existing-data lookup, not only a rejected read"


def _calendar_payload(request, *, records, availability="available", window=None):
    return {
        "dimension": request.arguments["dimension"],
        "window": window or {key: request.arguments[key] for key in ("start_date", "end_date", "timezone")},
        "records": records, "count": len(records), "availability": availability,
    }


@pytest.mark.asyncio
async def test_daily_summary_partial_read_keeps_diet_evidence_and_card(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers

    def dispatch(request):
        if request.arguments["dimension"] == "sleep":
            return {"status": "failed", "error": "lookup_failed", "records": []}
        return _calendar_payload(request, records=[{
            "record_date": request.arguments["start_date"], "meal_type": "breakfast",
            "food_items": "燕麦", "calories": 200,
        }])

    _, done, persisted, public_text, dispatched = await _run_scripted(
        db, user, monkeypatch, query="给我今天总结", first_tool="health_analysis",
        first_args={"analysis_type": "orchestrator"}, dispatch=dispatch,
        reply="饮食已查到燕麦；睡眠查询失败，本次未完成。", turn_id="daily-partial",
    )
    assert {request.arguments["dimension"] for request in dispatched} == {"diet", "sleep"}
    assert done["turn_outcome"]["status"] == "partial"
    assert done["completion_status"] == "error"
    assert done["generation_status"] == "complete"
    assert {goal["goal_id"]: goal["status"] for goal in done["turn_outcome"]["goals"]} == {
        "diet": "verified", "sleep": "failed",
    }
    assert "燕麦" in persisted.content and "燕麦" in public_text
    assert "metric_table" in persisted.content, "Verified diet card must survive partial task completion"
    assert "metric_table" in public_text


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [False, True])
async def test_empty_dataset_is_distinct_from_failed_lookup(db, auth_user_and_headers, monkeypatch, failed):
    user, _ = auth_user_and_headers

    def dispatch(request):
        if failed:
            return {"status": "failed", "error": "lookup_failed", "records": []}
        return _calendar_payload(request, records=[], availability="no_data")

    _, done, _, _, _ = await _run_scripted(
        db, user, monkeypatch, query="给我今天总结", first_tool="health_analysis",
        first_args={"analysis_type": "orchestrator"}, dispatch=dispatch,
        reply="本次没有可用记录。", turn_id=f"daily-empty-{failed}",
    )
    assert done["turn_outcome"]["status"] == ("failed" if failed else "complete")
    assert {goal["status"] for goal in done["turn_outcome"]["goals"]} == ({"failed"} if failed else {"verified"})


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["record_date", "window", "dimension"])
async def test_daily_goal_rejects_result_outside_requested_calendar_window(db, auth_user_and_headers, monkeypatch, mismatch):
    user, _ = auth_user_and_headers

    def dispatch(request):
        wrong_date = (date.fromisoformat(request.arguments["start_date"]) - timedelta(days=1)).isoformat()
        result = _calendar_payload(request, records=[{
            "record_date": wrong_date if mismatch == "record_date" else request.arguments["start_date"],
            "food_items": "禁止进入回答的错范围记录", "meal_type": "dinner",
        }])
        if mismatch == "window":
            result["window"].update(start_date=wrong_date, end_date=wrong_date)
        if mismatch == "dimension":
            result["dimension"] = "sleep"
        return result

    _, done, persisted, public_text, _ = await _run_scripted(
        db, user, monkeypatch, query="今天我吃了啥", first_tool="health_query",
        first_args={"dimension": "diet"}, dispatch=dispatch,
        reply="本次查询没有完成。", turn_id=f"daily-wrong-{mismatch}",
        forbidden_tool_text="禁止进入回答的错范围记录",
    )
    assert done["turn_outcome"]["status"] == "failed"
    assert done["turn_outcome"]["goals"][0]["status"] == "failed"
    assert "禁止进入回答的错范围记录" not in persisted.content + public_text


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["meal_type", "record_date"])
async def test_dinner_query_rejects_mismatched_rows_before_model_card_or_reference(db, auth_user_and_headers, monkeypatch, mismatch):
    user, _ = auth_user_and_headers

    def dispatch(request):
        assert request.tool_name == "health_manage"
        wrong_date = (date.fromisoformat(request.arguments["date"]) - timedelta(days=1)).isoformat()
        return {"records": [{
            "id": 42, "record_date": wrong_date if mismatch == "record_date" else request.arguments["date"],
            "meal_type": "dinner" if mismatch == "record_date" else "breakfast",
            "food_items": "禁止进入晚餐回答的早餐记录",
        }]}

    executor, done, persisted, public_text, _ = await _run_scripted(
        db, user, monkeypatch, query="今天晚上我吃了什么？", first_tool="health_query",
        first_args={"dimension": "diet"}, dispatch=dispatch,
        reply="本次晚餐查询没有完成。", turn_id=f"daily-wrong-meal-{mismatch}",
        forbidden_tool_text="禁止进入晚餐回答的早餐记录",
    )
    assert done["turn_outcome"]["status"] == "failed"
    assert "禁止进入晚餐回答的早餐记录" not in persisted.content + public_text

    assert "diet" not in executor._agent_kernel_manage_list_references


@pytest.mark.asyncio
async def test_queued_sync_never_claims_data_updated_in_stream_or_history(db, auth_user_and_headers, monkeypatch):
    import app.tasks.garmin_sync as garmin_task
    from app.models.user import GarminCredential
    user, _ = auth_user_and_headers
    db.add(GarminCredential(user_id=user.id, garmin_email="synthetic@example.test",
                           encrypted_password="synthetic", sync_enabled=True,
                           credentials_valid=True, requires_mfa=False))
    db.commit()
    enqueued = []
    monkeypatch.setattr(garmin_task.sync_user_garmin_data, "delay", lambda *a, **k: enqueued.append((a, k)))
    executor, done, persisted, public_text, dispatched = await _run_scripted(
        db, user, monkeypatch, query="帮我同步佳明数据", first_tool="health_record",
        first_args={"record_type": "garmin_sync", "data": {}}, dispatch=lambda request: {},
        reply="同步完成，所有数据已更新。", turn_id="sync-queued-honesty", actual_sync=True,
    )
    assert executor._turn_sync_queued and len(enqueued) == 1
    assert "已提交" in public_text and "尚未确认" in public_text
    assert "所有数据已更新" not in public_text
    assert "尚未确认" in persisted.content


@pytest.mark.asyncio
async def test_real_dinner_list_reaches_answer_evidence_without_table_capability(
    db, client, auth_user_and_headers, monkeypatch,
):
    from datetime import datetime
    from urllib.parse import urlsplit
    from zoneinfo import ZoneInfo
    from app.models.daily_health import DietRecord

    user, headers = auth_user_and_headers
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    db.add_all([
        DietRecord(user_id=user.id, record_date=today, meal_type="dinner", food_name="合成晚餐番茄", food_items="合成晚餐番茄", calories=200),
        DietRecord(user_id=user.id, record_date=today, meal_type="breakfast", food_name="不应混入的早餐", food_items="不应混入的早餐", calories=100),
        DietRecord(user_id=user.id, record_date=today - timedelta(days=1), meal_type="dinner", food_name="不应混入的旧晚餐", food_items="不应混入的旧晚餐", calories=100),
    ])
    db.commit()
    executor = AgentExecutor(db)
    provider_rounds, api_calls, api_failures = [], [], []

    async def provider(messages, tools):
        provider_rounds.append(messages)
        if len(provider_rounds) == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "dinner-list", "type": "function", "function": {
                    "name": "health_manage", "arguments": json.dumps({"record_type": "diet", "operation": "list"}),
                },
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "今天晚餐记录了番茄。建议根据记录回顾饮食。"}
            yield {"type": "finish", "finish_reason": "stop"}

    async def local_api_get(url, request_headers):
        parsed = urlsplit(url)
        api_calls.append(parsed.path)
        response = client.get(parsed.path + "?" + parsed.query, headers=request_headers)
        if response.status_code != 200 or parsed.path != "/api/v1/diet/records/me":
            api_failures.append((parsed.path, response.status_code))
        return response.text

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "Use tools to read data.")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_api_get", local_api_get)
    events = [event async for event in executor.run_stream(
        user.id, "今天晚上我吃了什么？给我一些建议。",
        user_auth_token=headers["Authorization"].removeprefix("Bearer "),
        client_turn_id="real-dinner-evidence", client_caps=[],
    )]
    assert not api_failures
    assert api_calls == ["/api/v1/diet/records/me"]
    done = events[-1]["data"]
    assert done["perf"]["agent_kernel"] == "pi"
    assert done["turn_outcome"]["status"] == "complete"
    assert done["turn_outcome"]["goals"][0]["status"] == "verified"
    evidence = done.get("answer_evidence") or {}
    assert evidence.get("basis"), "The real executor must collect diet-list evidence independently of table capability"
    basis_text = json.dumps(evidence["basis"], ensure_ascii=False)
    assert "合成晚餐番茄" in basis_text
    assert str(today) in basis_text and "晚餐" in basis_text
    assert "不应混入" not in basis_text
    persisted = db.query(AgentMessage).filter(AgentMessage.id == done["message_id"]).one()
    assert persisted.meta["answer_evidence"] == evidence
    assert db.query(DietRecord).filter(DietRecord.user_id == user.id).count() == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("advice", [False, True])
async def test_daily_summary_keeps_duplicate_rows_and_uses_verified_arithmetic(db, auth_user_and_headers, monkeypatch, advice):
    user, _ = auth_user_and_headers
    def dispatch(request):
        day = request.arguments["start_date"]
        if request.arguments["dimension"] == "diet":
            rows = [{"id": index, "record_date": day, "meal_type": "breakfast" if index < 3 else "lunch", "food_name": "燕麦" if index < 3 else "番茄蛋饭", "calories": calories} for index, calories in [(1, 300), (2, 300), (3, 420)]]
        else:
            rows = [{"record_date": day, "sleep_score": 80, "total_sleep_duration": 420}]
        return _calendar_payload(request, records=rows)
    _, done, persisted, public, _ = await _run_scripted(
        db, user, monkeypatch, query="给我今天总结" + ("，给我建议" if advice else ""),
        first_tool="health_analysis", first_args={"analysis_type": "orchestrator"}, dispatch=dispatch,
        reply="建议：根据已记录数据规律安排饮食与睡眠。" if advice else "今天只吃了720千卡，睡眠正常。",
        turn_id=f"summary-duplicate-{advice}", required_context_text="1020",
    )
    assert done["turn_outcome"]["status"] == "complete"
    assert "1020" in public and "1020" in persisted.content
    assert "720" not in public
    assert "已记录" in public and "睡眠" in public
    assert "7" in public and "80" in public
    assert "今天只吃了" not in public
    if advice:
        assert "建议" in public


@pytest.mark.asyncio
async def test_summary_advice_cannot_publish_contradictory_total(db,auth_user_and_headers,monkeypatch):
    user,_=auth_user_and_headers
    def dispatch(request):
        day=request.arguments['start_date']
        if request.arguments['dimension']=='diet':
            rows=[{'id':index,'record_date':day,'meal_type':'breakfast' if index<3 else 'dinner','food_name':'燕麦' if index<3 else '番茄蛋饭','calories':calories} for index,calories in [(1,300),(2,300),(3,420)]]
        else:
            rows=[{'record_date':day,'sleep_score':80,'total_sleep_duration':420}]
        return _calendar_payload(request,records=rows)
    _,done,persisted,public,_=await _run_scripted(db,user,monkeypatch,query='给我今天总结，给我建议',first_tool='health_analysis',first_args={'analysis_type':'orchestrator'},dispatch=dispatch,reply='建议：今天只吃了720千卡，摄入不足，明天增加一餐。',turn_id='independent-summary-advice-wrongtotal',required_context_text='1020')
    assert done['turn_outcome']['status'] == 'partial'
    assert done['completion_status'] == 'error'
    assert '1020' in persisted.content
    assert '摄入不足' not in public
    assert any(goal['goal_id'] == 'summary_advice' and goal['status'] == 'failed' for goal in done['turn_outcome']['goals'])
    assert '720' not in public and '720' not in persisted.content
    assert '今天只吃了' not in public


@pytest.mark.asyncio
async def test_daily_facts_do_not_turn_provider_error_into_success(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    def dispatch(request):
        return _calendar_payload(request, records=[], availability="no_data")
    _, done, persisted, public, _ = await _run_scripted(
        db, user, monkeypatch, query="给我今天总结", first_tool="health_analysis",
        first_args={"analysis_type": "orchestrator"}, dispatch=dispatch,
        reply="本轮生成失败，请重试。", turn_id="summary-generation-error",
        answer_finish_reason="error",
    )
    assert done["generation_status"] == "error"
    assert done["completion_status"] == "error"
    assert done["turn_outcome"]["status"] != "complete"
    assert "本轮生成失败" in public and "本轮生成失败" in persisted.content
