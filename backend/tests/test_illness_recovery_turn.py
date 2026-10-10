"""Self recovery statements must update an owned episode, never broaden reads."""
import json
from datetime import date

import pytest

from app.models.illness import IllnessEpisode
from app.models.user import User
from app.services.agent_executor import AgentExecutor, _normalize_goal_guarded_tool_calls
from app.services.agent_kernel.goal_spec import compile_goal_spec
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext
from app.services.write_intent_scope import has_explicit_authorizing_update_request

MESSAGES = ("我感冒痊愈了", "更新我的感冒状态：已经痊愈", "我的感冒已经康复了", "请更新我的感冒状态:已康复")


def _goal(message):
    context = ExecutionContext.for_test(user_id=1, channel="typed")
    envelope = AgentEnvelope(user_id=1, channel="typed", text=message)
    intent = build_intent_frame(envelope, context)
    return intent, compile_goal_spec(envelope=envelope, context=context, intent=intent)


@pytest.mark.parametrize("message", MESSAGES)
def test_recovery_is_typed_owned_update_not_a_history_query(message):
    intent, goal = _goal(message)
    assert has_explicit_authorizing_update_request(message)
    assert (intent.primary, intent.operation, intent.domain, intent.is_write) == ("mutate", "update", "illness", True)
    assert goal.kind == "health_manage_mutation"
    assert dict(goal.target_values) == {"name": "感冒"}
    proposed = [{"id": "model-query", "type": "function", "function": {"name": "health_query", "arguments": '{"dimension":"illness"}'}}]
    normalized = _normalize_goal_guarded_tool_calls(proposed, goal, original_user_message=message)
    assert normalized[0]["function"]["name"] == "health_manage"
    assert json.loads(normalized[0]["function"]["arguments"]) == {"record_type": "illness", "operation": "list", "limit": 20}


@pytest.mark.parametrize("message", (
    "我朋友感冒痊愈了", "我的朋友的感冒已经痊愈了", "我妈妈感冒痊愈了",
    "更新妈妈的感冒状态：已经痊愈", "更新我的朋友的感冒状态：已经痊愈",
    "我感冒可能痊愈了", "我感冒痊愈了吗？", "我感冒痊愈了？",
    "我感冒痊愈了，但今天又复发", "如果我感冒痊愈了", "等我感冒痊愈了",
    "我感冒痊愈了，不要更新", "例子：我感冒痊愈了", "他说：我感冒痊愈了",
    "“我感冒痊愈了”", "更新我的感冒状态：已经痊愈，不对，还没好",
    "我的感冒和鼻炎已经痊愈了", "我感冒痊愈了，顺便删除全部记录",
))
def test_quoted_uncertain_nonself_or_retracted_recovery_has_no_mutation_authority(message):
    _, goal = _goal(message)
    assert not has_explicit_authorizing_update_request(message)
    assert goal.kind != "health_manage_mutation"


def _seed(db, *, duplicates=1):
    users = [User(username=f"recovery-{i}", email=f"recovery-{i}@example.test", hashed_password="synthetic", name="Synthetic recovery", is_active=True, is_approved=True) for i in range(2)]
    db.add_all(users)
    db.flush()
    other = IllnessEpisode(user_id=users[1].id, name="感冒", start_date=date.today(), status="active")
    own = [IllnessEpisode(user_id=users[0].id, name="感冒", start_date=date.today(), status="active") for _ in range(duplicates)]
    db.add_all([other, *own])
    db.commit()
    return users[0], own, other


@pytest.mark.asyncio
@pytest.mark.parametrize("message", MESSAGES[:2])
@pytest.mark.parametrize("duplicates", (0, 1, 2))
@pytest.mark.parametrize("historical", (False, True))
async def test_real_gateway_and_api_persist_only_unique_owned_recovery(db, client, monkeypatch, message, duplicates, historical):
    user, own, other = _seed(db, duplicates=duplicates)
    old = None
    if historical:
        old = IllnessEpisode(user_id=user.id, name="感冒", start_date=date(2025, 1, 1), end_date=date(2025, 1, 5), status="resolved")
        db.add(old)
        db.commit()
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._turn_channel = "typed"
    executor._current_turn_user_message = message
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(user.id)})
    calls = []

    async def request(method, url, headers, payload=None):
        path = "/api/v1" + url.split("/api/v1", 1)[1]
        calls.append((method, path))
        response = client.request(method, path, headers=headers, **({"json": payload} if payload is not None else {}))
        assert response.status_code == 200
        return json.dumps(response.json(), ensure_ascii=False)

    async def get(url, headers):
        return await request("GET", url, headers)

    async def put(url, headers, payload):
        return await request("PUT", url, headers, payload)

    monkeypatch.setattr(executor, "_api_get", get)
    monkeypatch.setattr(executor, "_api_put", put)
    lookup = await executor._execute_tool("health_manage", {"record_type": "illness", "operation": "list"}, token)
    assert not lookup.startswith("Error:"), lookup
    assert {row["id"] for row in json.loads(lookup)} == {row.id for row in [*own, *([old] if old else [])]}
    result = await executor._execute_tool("health_manage", {"record_type": "illness", "operation": "update", "record_id": own[0].id if own else (old.id if old else other.id), "data": {"status": "resolved"}}, token)
    for row in [*own, other]:
        db.refresh(row)
    assert other.status == "active"
    if old:
        db.refresh(old)
        assert old.status == "resolved" and old.end_date == date(2025, 1, 5)
    if duplicates == 1:
        assert own[0].status == "resolved"
        assert own[0].end_date == date.today()
        assert json.loads(result)["id"] == own[0].id
        assert [method for method, _ in calls] == ["GET", "PUT"]
    else:
        assert all(row.status == "active" for row in own)
        assert json.loads(result)["success"] is False
        assert json.loads(result)["error_category"] == "clarification_required"
        assert [method for method, _ in calls] == ["GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize("message", MESSAGES[:2])
async def test_screenshot_statement_reaches_pi_saved_answer_and_verified_receipt(
    db, client, isolated_agent_protocol_transport, monkeypatch, message,
):
    from datetime import datetime, timezone
    from app.models.agent_conversation import AgentMessage
    from app.services.auth import auth_service
    from app.twin.schema import HealthTwin, TwinMeta

    user, own, other = _seed(db)
    now = datetime.now(timezone.utc)
    monkeypatch.setattr("app.twin.builder.build_twin", lambda _db, uid, **kwargs:
        HealthTwin(meta=TwinMeta(user_id=uid, generated_at=now)))
    executor = AgentExecutor(db)
    rounds, http_calls = [], []

    async def provider(messages, tools):
        rounds.append(tools)
        if len(rounds) <= 2:
            name, args = (("health_query", {"dimension": "illness"}) if len(rounds) == 1 else
                          ("health_manage", {"record_type": "illness", "operation": "update",
                                             "record_id": own[0].id, "data": {"status": "resolved"}}))
            yield {"type": "tool_calls", "tool_calls": [{"id": f"recovery-{len(rounds)}", "type": "function",
                   "function": {"name": name, "arguments": json.dumps(args)}}]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "已根据你的报告更新感冒状态。"}
            yield {"type": "finish", "finish_reason": "stop"}

    async def request(method, url, headers, payload=None):
        path = "/api/v1" + url.split("/api/v1", 1)[1]
        http_calls.append((method, path))
        response = client.request(method, path, headers=headers, **({"json": payload} if payload is not None else {}))
        assert response.status_code == 200
        return json.dumps(response.json(), ensure_ascii=False)

    async def get(url, headers):
        return await request("GET", url, headers)

    async def put(url, headers, payload):
        return await request("PUT", url, headers, payload)

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "依据本人报告与真实回执回答。")
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *a, **k: "")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_api_get", get)
    monkeypatch.setattr(executor, "_api_put", put)
    events = [event async for event in executor.run_stream(
        user.id, message, user_auth_token=auth_service.create_access_token({"sub": str(user.id)}),
        channel="typed", client_turn_id=f"self-recovery-{MESSAGES.index(message)}")]
    done = next(event["data"] for event in reversed(events) if event.get("event") == "done")
    saved = db.get(AgentMessage, done["message_id"])
    db.refresh(own[0])
    db.refresh(other)
    assert done["perf"]["agent_kernel"] == "pi"
    assert own[0].status == "resolved" and other.status == "active"
    assert [method for method, _ in http_calls] == ["GET", "PUT"]
    assert len(done["write_receipts"]) == 1
    receipt = done["write_receipts"][0]
    assert str(receipt["resource_id"]) == str(own[0].id)
    assert (receipt["resource_type"], receipt["action"], receipt["status"], receipt["verified"]) == ("illness_episode", "update", "verified", True)
    assert saved.meta["write_receipts"] == done["write_receipts"]
    assert "这次查询未执行" not in saved.content
    assert "没有授权" not in saved.content
