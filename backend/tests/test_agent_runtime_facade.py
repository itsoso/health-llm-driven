from __future__ import annotations

import asyncio
import json
import plistlib

import pytest
from sqlalchemy import inspect

from app.config import settings


class _FakeExecutor:
    calls = 0

    def __init__(self, db):
        self.db = db

    async def run_stream(
        self,
        *,
        user_id,
        message,
        client_turn_id=None,
        run_id=None,
        attempt_id=None,
        **_kwargs,
    ):
        from app.models.agent_conversation import AgentConversation, AgentMessage

        type(self).calls += 1
        conversation = AgentConversation(
            user_id=user_id,
            title="runtime facade test",
            session_key=f"facade-{client_turn_id}",
        )
        self.db.add(conversation)
        self.db.flush()
        source = AgentMessage(
            conversation_id=conversation.id,
            role="user",
            content=message,
            client_turn_id=client_turn_id,
        )
        self.db.add(source)
        self.db.commit()
        yield {
            "event": "request_persisted",
            "data": {
                "conversation_id": conversation.id,
                "user_message_id": source.id,
                "client_turn_id": client_turn_id,
            },
        }
        yield {"event": "token", "data": {"content": "已处理"}}
        assistant = AgentMessage(
            conversation_id=conversation.id,
            role="assistant",
            content="已处理",
            client_turn_id=client_turn_id,
            meta={
                "completion_status": "complete",
                "client_turn_finalized": True,
            },
        )
        self.db.add(assistant)
        self.db.commit()
        yield {
            "event": "done",
            "data": {
                "conversation_id": conversation.id,
                "message_id": assistant.id,
                "completion_status": "complete",
                "client_turn_id": client_turn_id,
            },
        }


async def _collect(stream):
    return [event async for event in stream]


async def test_cloud_facade_tracks_and_replays_one_logical_turn(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_runtime import AgentRun
    from app.services.agent_runtime_facade import CloudAgentRuntimeFacade

    user, _headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    monkeypatch.setattr(settings, "agent_runtime_deadline_seconds", 300)
    _FakeExecutor.calls = 0
    facade = CloudAgentRuntimeFacade(db, executor_factory=_FakeExecutor)

    first = await _collect(
        facade.run_stream(
            user_id=user.id,
            message="private health text",
            client_turn_id="facade-turn-1",
            origin="siri",
            channel="siri",
        )
    )
    replay = await _collect(
        facade.run_stream(
            user_id=user.id,
            message="private health text",
            client_turn_id="facade-turn-1",
            origin="siri",
            channel="siri",
        )
    )

    assert _FakeExecutor.calls == 1
    assert [event["event"] for event in first] == [
        "request_persisted",
        "token",
        "done",
    ]
    assert [event["event"] for event in replay] == [
        "request_persisted",
        "token",
        "done",
    ]
    assert replay[-1]["data"]["replayed"] is True
    assert first[-1]["data"]["run_id"] == replay[-1]["data"]["run_id"]
    run = db.query(AgentRun).one()
    assert run.status == "succeeded"
    assert run.source_message_id is not None
    assert run.assistant_message_id is not None
    assert run.runtime_contract_version == "agent-runtime-v1"
    assert len(run.tool_registry_digest or "") == 64
    assert len(run.capability_policy_digest or "") == 64
    serialized = repr(run.__dict__)
    assert "private health text" not in serialized


async def test_cloud_facade_preserves_legacy_execution_when_runtime_is_off(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_runtime import AgentRun
    from app.services.agent_runtime_facade import CloudAgentRuntimeFacade

    user, _headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "off")
    _FakeExecutor.calls = 0

    events = await _collect(
        CloudAgentRuntimeFacade(db, executor_factory=_FakeExecutor).run_stream(
            user_id=user.id,
            message="legacy",
            client_turn_id="facade-legacy-1",
            origin="wechat",
            channel="typed",
        )
    )

    assert _FakeExecutor.calls == 1
    assert events[-1]["event"] == "done"
    assert "run_id" not in events[-1]["data"]
    assert db.query(AgentRun).count() == 0


async def test_cloud_facade_maintains_runtime_lease_until_stream_finishes(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services import agent_runtime_facade as facade_module
    from app.services.agent_runtime_facade import CloudAgentRuntimeFacade

    user, _headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    calls = []

    async def dormant_heartbeat():
        await __import__("asyncio").Event().wait()

    def fake_start(**kwargs):
        calls.append(("start", kwargs))
        return __import__("asyncio").create_task(dormant_heartbeat())

    async def fake_stop(task, *, run_id):
        calls.append(("stop", {"run_id": run_id}))
        task.cancel()
        try:
            await task
        except __import__("asyncio").CancelledError:
            pass

    monkeypatch.setattr(
        facade_module,
        "start_agent_runtime_heartbeat",
        fake_start,
        raising=False,
    )
    monkeypatch.setattr(
        facade_module,
        "stop_agent_runtime_heartbeat",
        fake_stop,
        raising=False,
    )

    await _collect(
        CloudAgentRuntimeFacade(db, executor_factory=_FakeExecutor).run_stream(
            user_id=user.id,
            message="lease protected",
            client_turn_id="facade-heartbeat-1",
            origin="wechat",
            channel="typed",
        )
    )

    assert [name for name, _payload in calls] == ["start", "stop"]
    assert calls[0][1]["managed"] is True
    assert calls[0][1]["worker_id"].startswith("attempt_")
    assert calls[1][1]["run_id"] == calls[0][1]["context"].run_id


async def test_cloud_facade_blocks_duplicate_write_and_reconciles_cancelled_dispatch(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_runtime import AgentRun, AgentToolOperation
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_runtime_facade import CloudAgentRuntimeFacade

    user, _headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )
    executor = AgentExecutor(db)
    dispatch_started = asyncio.Event()
    dispatch_count = 0

    async def blocked_write(_base_url, _headers, _args):
        nonlocal dispatch_count
        dispatch_count += 1
        dispatch_started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(executor, "_exec_health_record", blocked_write)
    facade = CloudAgentRuntimeFacade(db)
    arguments = {
        "record_type": "diet",
        "data": {"food_items": "牛肉面"},
    }
    first = asyncio.create_task(
        facade.execute_tool(
            user_id=user.id,
            message="记录午餐吃了牛肉面",
            origin="voice_command",
            channel="voice",
            tool_name="health_record",
            arguments=arguments,
            client_turn_id="facade-concurrent-write-1",
            executor=executor,
            source="voice_command",
        )
    )
    await dispatch_started.wait()

    duplicate = await facade.execute_tool(
        user_id=user.id,
        message="记录午餐吃了牛肉面",
        origin="voice_command",
        channel="voice",
        tool_name="health_record",
        arguments=arguments,
        client_turn_id="facade-concurrent-write-1",
        executor=AgentExecutor(db),
        source="voice_command",
    )
    duplicate_payload = json.loads(duplicate)
    assert duplicate_payload["status"] == "uncertain"
    assert duplicate_payload["error_code"] == "duplicate_in_flight"
    assert dispatch_count == 1

    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    run = db.query(AgentRun).one()
    operation = db.query(AgentToolOperation).one()
    assert run.status == "reconciliation_required"
    assert operation.status == "reconciliation_required"
    assert operation.error_code == "write_uncertain"


def test_siri_uses_first_party_agent_conversation(db, auth_user_and_headers):
    from app.api.siri import get_or_create_siri_conversation
    from app.models.agent_conversation import AgentConversation
    from app.models.chat import ChatConversation

    user, _headers = auth_user_and_headers

    first = get_or_create_siri_conversation(user.id, db)
    repeated = get_or_create_siri_conversation(user.id, db)

    assert first == repeated
    assert db.query(AgentConversation).filter_by(id=first).one().user_id == user.id
    assert db.query(ChatConversation).count() == 0


def test_wechat_message_identity_is_deterministic_and_content_free():
    import pytest

    from app.services.agent_runtime_identity import MissingExternalMessageIdentity
    from app.services.wechat_bot import _wechat_client_turn_id

    first = _wechat_client_turn_id({
        "wechat_openid": "private-open-id",
        "msg_id": "private-message-id",
    })
    repeated = _wechat_client_turn_id({
        "wechat_openid": "private-open-id",
        "msg_id": "private-message-id",
    })

    assert first == repeated
    assert first.startswith("wechat-")
    assert "private-open-id" not in first
    assert "private-message-id" not in first
    with pytest.raises(MissingExternalMessageIdentity):
        _wechat_client_turn_id({"wechat_openid": "private-open-id"})


async def test_cloud_facade_fails_closed_for_write_when_runtime_circuit_is_paused(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.config import settings
    from app.services.agent_runtime_facade import CloudAgentRuntimeFacade
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    AgentRuntimeRolloutService(db).pause(
        actor_kind="admin",
        reason_code="manual_pause",
        actor_user_id=user.id,
    )

    result = await CloudAgentRuntimeFacade(db).execute_tool(
        user_id=user.id,
        message="记录饮水500ml",
        origin="voice_command",
        channel="voice",
        tool_name="health_record",
        arguments={"record_type": "water", "data": {"amount": 500}},
        client_turn_id="facade-paused-write-1",
        source="voice_command",
    )

    payload = json.loads(result)
    assert payload["status"] == "failed"
    assert payload["error_code"] == "runtime_control_unavailable"
    assert payload["dispatch_started"] is False


async def test_executor_blocks_dynamic_write_when_runtime_circuit_is_unavailable(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services.agent_executor import AgentExecutor

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = "记录饮水500ml"
    executor._runtime_write_block_reason = "circuit_unavailable"
    dispatch_count = 0

    async def should_not_dispatch(_base_url, _headers, _args):
        nonlocal dispatch_count
        dispatch_count += 1
        return '{"success": true, "record_id": 1}'

    monkeypatch.setattr(executor, "_exec_health_record", should_not_dispatch)
    result = await executor._execute_tool(
        "health_record",
        {"record_type": "water", "data": {"amount": 500}},
        None,
    )

    payload = json.loads(result)
    assert payload["status"] == "failed"
    assert payload["error_code"] == "runtime_control_unavailable"
    assert dispatch_count == 0
    assert executor._agent_kernel_event_bus is not None
    tool_result = next(
        event
        for event in executor._agent_kernel_event_bus.events
        if event.name == "agent.tool_result"
    )
    assert tool_result.data["success"] is False


async def test_cloud_facade_allows_read_when_runtime_circuit_is_paused(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_runtime_facade import CloudAgentRuntimeFacade
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    AgentRuntimeRolloutService(db).pause(
        actor_kind="admin",
        reason_code="manual_pause",
        actor_user_id=user.id,
    )
    executor = AgentExecutor(db)
    dispatch_count = 0

    async def read_result(_base_url, _headers, _args):
        nonlocal dispatch_count
        dispatch_count += 1
        return '{"records":[]}'

    monkeypatch.setattr(executor, "_exec_health_query", read_result)
    result = await CloudAgentRuntimeFacade(db).execute_tool(
        user_id=user.id,
        message="查询今天饮水",
        origin="voice_command",
        channel="voice",
        tool_name="health_query",
        arguments={"query_type": "water", "date": "today"},
        client_turn_id="facade-paused-read-1",
        executor=executor,
        source="voice_command",
    )

    assert json.loads(result) == {"records": []}
    assert dispatch_count == 1


async def test_wechat_api_contract_accepts_and_forwards_provider_message_id(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.api.family_health import WeChatMessageRequest
    from app.services.wechat_bot import WeChatBotHandler

    user, _headers = auth_user_and_headers
    request = WeChatMessageRequest(
        msg_type="text",
        content="记录饮水500ml",
        wechat_openid="private-open-id",
        msg_id="provider-message-42",
    )
    captured = {}

    async def fake_call(_self, *_args, **kwargs):
        captured.update(kwargs)
        return "已处理"

    monkeypatch.setattr(WeChatBotHandler, "_call_agent", fake_call)
    assert request.msg_id == "provider-message-42"
    payload = request.model_dump()
    payload["user_id"] = user.id
    await WeChatBotHandler(db).handle_message(payload)
    assert captured["client_turn_id"].startswith("wechat-")


def test_wechat_api_rejects_missing_provider_message_id(
    client,
    auth_user_and_headers,
):
    _user, headers = auth_user_and_headers

    response = client.post(
        "/api/v1/family-health/wechat-bot/message",
        headers=headers,
        json={
            "msg_type": "text",
            "content": "记录饮水500ml",
            "wechat_openid": "private-open-id",
        },
    )

    assert response.status_code == 422
    assert "消息 ID" in response.json()["detail"]


def test_siri_api_rejects_missing_idempotency_key(
    client,
    auth_user_and_headers,
):
    _user, headers = auth_user_and_headers

    response = client.post(
        "/api/v1/siri/say",
        headers=headers,
        json={"message": "记录饮水500ml"},
    )

    assert response.status_code == 422
    assert "唯一标识" in response.json()["detail"]


def test_siri_shortcuts_send_a_fresh_idempotency_key_per_invocation():
    from app.api.siri import (
        _generate_generic_shortcut_plist,
        _generate_shortcut_plist,
    )

    for raw in (
        _generate_generic_shortcut_plist(),
        _generate_shortcut_plist("private-token"),
    ):
        shortcut = plistlib.loads(raw)
        actions = shortcut["WFWorkflowActions"]
        uuid_action = next(
            action
            for action in actions
            if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.getuuid"
        )
        uuid_output = uuid_action["WFWorkflowActionParameters"]["UUID"]
        request_action = next(
            action
            for action in actions
            if action["WFWorkflowActionIdentifier"]
            == "is.workflow.actions.downloadurl"
        )
        header_items = request_action["WFWorkflowActionParameters"][
            "WFHTTPHeaders"
        ]["Value"]["WFDictionaryFieldValueItems"]
        idempotency_header = next(
            item
            for item in header_items
            if item["WFKey"]["Value"]["string"] == "Idempotency-Key"
        )
        attachment = idempotency_header["WFValue"]["Value"][
            "attachmentsByRange"
        ]["{0, 1}"]
        assert attachment["OutputUUID"] == uuid_output


def test_external_channel_conversation_has_database_uniqueness(db):
    indexes = {
        index["name"]: index
        for index in inspect(db.get_bind()).get_indexes("agent_conversations")
    }
    assert indexes["uq_agent_conv_user_session_key"]["unique"] == 1


def test_external_channel_conversation_is_reused(db, auth_user_and_headers):
    from app.models.agent_conversation import AgentConversation
    from app.services.agent_runtime_facade import (
        get_or_create_channel_conversation,
    )

    user, _headers = auth_user_and_headers

    first = get_or_create_channel_conversation(
        db,
        user_id=user.id,
        channel="wechat",
        title="微信对话",
    )
    repeated = get_or_create_channel_conversation(
        db,
        user_id=user.id,
        channel="wechat",
        title="微信对话",
    )

    assert first == repeated
    conversation = db.query(AgentConversation).filter_by(id=first).one()
    assert conversation.session_key == f"external-wechat-{user.id}"


async def test_wechat_handler_reuses_channel_conversation(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_conversation import AgentConversation
    from app.services.wechat_bot import WeChatBotHandler

    user, _headers = auth_user_and_headers
    captured = {}

    async def fake_call(_self, user_id, message, *_args, **kwargs):
        captured.update(
            user_id=user_id,
            message=message,
            conversation_id=kwargs.get("conversation_id"),
        )
        return "已处理"

    monkeypatch.setattr(WeChatBotHandler, "_call_agent", fake_call)
    result = await WeChatBotHandler(db).handle_message({
        "msg_type": "text",
        "content": "继续刚才的话题",
        "wechat_openid": "private-open-id",
        "msg_id": "message-2",
        "user_id": user.id,
    })

    assert result["reply"] == "已处理"
    conversation = db.query(AgentConversation).filter_by(
        id=captured["conversation_id"]
    ).one()
    assert conversation.session_key == f"external-wechat-{user.id}"
