import json

from app.services.telegram_inbound import classify_intent


def test_telegram_record_noun_query_is_not_record_route():
    assert classify_intent("今天我的饮食的记录，帮我列个表格出来。") == "query"


def test_telegram_contrastive_correction_is_query_route():
    assert classify_intent("不是记录，是列出我今天吃的所有东西。") == "query"


def test_telegram_clear_record_command_still_records():
    assert classify_intent("记录午餐吃了牛肉面") == "record"


async def test_telegram_execute_record_uses_agent_tool_gateway(db, monkeypatch):
    from app.services.agent_executor import AgentExecutor
    from app.services.telegram_inbound import execute_health_record

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, **kwargs: {"error": None, "data": args},
    )

    async def should_not_dispatch(self, base, headers, args):
        raise AssertionError("telegram must not bypass _execute_tool")

    monkeypatch.setattr(AgentExecutor, "_exec_health_record", should_not_dispatch)

    result = await execute_health_record(
        db,
        1,
        {"record_type": "diet", "data": {"food_items": "米饭"}},
        source_text="今天我的饮食的记录，帮我列个表格出来。",
    )

    payload = json.loads(result)
    assert payload["status"] == "rejected"
    assert payload["error_code"] == "write_tool_without_write_intent"
    assert payload["dispatch_started"] is False


async def test_telegram_empty_tool_result_never_becomes_success(db, monkeypatch):
    from app.services.agent_executor import AgentExecutor
    from app.services.telegram_inbound import execute_health_record

    async def empty_result(self, tool_name, args, token, **_kwargs):
        return ""

    monkeypatch.setattr(AgentExecutor, "_execute_tool", empty_result)

    result = await execute_health_record(
        db,
        1,
        {"record_type": "water", "data": {"amount": 500}},
        source_text="记录饮水500ml",
    )

    payload = json.loads(result)
    assert payload["status"] == "uncertain"
    assert payload["error_code"] == "empty_tool_result"
    assert "✅" not in result


async def test_telegram_structured_rejection_is_not_rendered_as_success(db, monkeypatch):
    from app.services import telegram_inbound

    monkeypatch.setattr(
        telegram_inbound,
        "llm_extract_record",
        lambda _text: _async_value({
            "record_type": "diet",
            "data": {"food_items": "米饭"},
        }),
    )
    monkeypatch.setattr(
        telegram_inbound,
        "execute_health_record",
        lambda *_args, **_kwargs: _async_value(
            '{"status":"rejected","error_code":"write_tool_without_write_intent",'
            '"dispatch_started":false}'
        ),
    )

    reply = await telegram_inbound.handle_inbound_text(
        db,
        1,
        "记录午餐吃了米饭",
        source_message_id="provider-rejected-1",
        source_conversation_id="chat-1",
    )

    assert "未写入" in reply
    assert not reply.startswith("✅")


async def test_telegram_uncertain_write_requires_reconciliation(db, monkeypatch):
    from app.services import telegram_inbound

    monkeypatch.setattr(
        telegram_inbound,
        "llm_extract_record",
        lambda _text: _async_value({
            "record_type": "water",
            "data": {"amount": 500},
        }),
    )
    monkeypatch.setattr(
        telegram_inbound,
        "execute_health_record",
        lambda *_args, **_kwargs: _async_value(
            '{"status":"uncertain","dispatch_started":true}'
        ),
    )

    reply = await telegram_inbound.handle_inbound_text(
        db,
        1,
        "记录饮水500ml",
        source_message_id="provider-uncertain-1",
        source_conversation_id="chat-1",
    )

    assert "待核对" in reply
    assert not reply.startswith("✅")


async def test_telegram_info_log_does_not_include_raw_health_text(db, monkeypatch, caplog):
    from app.services import telegram_inbound

    sensitive_text = "记录我的胃痛和体重71.2公斤"
    monkeypatch.setattr(
        telegram_inbound,
        "llm_extract_record",
        lambda _text: _async_value(None),
    )

    with caplog.at_level("INFO"):
        await telegram_inbound.handle_inbound_text(db, 1, sensitive_text)

    assert sensitive_text not in caplog.text
    assert "text_length=" in caplog.text


async def test_telegram_direct_record_is_settled_in_runtime(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.config import settings
    from app.models.agent_runtime import AgentRun
    from app.services.agent_executor import AgentExecutor
    from app.services.telegram_inbound import execute_health_record

    user, _headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")

    async def verified_tool(*_args, **_kwargs):
        return json.dumps({
            "status": "verified",
            "success": True,
            "record_id": 91,
            "resource_type": "water_record",
            "resource_id": "91",
        })

    monkeypatch.setattr(AgentExecutor, "_execute_tool", verified_tool)

    await execute_health_record(
        db,
        user.id,
        {"record_type": "water", "data": {"amount": 500}},
        source_text="记录饮水500ml",
        client_turn_id="telegram-runtime-1",
    )

    run = db.query(AgentRun).filter_by(
        user_id=user.id,
        client_turn_id="telegram-runtime-1",
    ).one()
    assert run.status == "succeeded"


async def test_telegram_query_uses_agent_runtime_and_continuous_conversation(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_conversation import AgentConversation
    from app.services.agent_runtime_facade import CloudAgentRuntimeFacade
    from app.services.telegram_inbound import handle_inbound_text

    user, _headers = auth_user_and_headers
    captured = {}

    async def fake_stream(_self, **kwargs):
        captured.update(kwargs)
        yield {"event": "token", "data": {"content": "最近睡眠稳定"}}
        yield {"event": "done", "data": {"completion_status": "complete"}}

    monkeypatch.setattr(CloudAgentRuntimeFacade, "run_stream", fake_stream)

    reply = await handle_inbound_text(
        db,
        user.id,
        "最近睡眠如何",
        source_message_id="telegram-message-9",
    )

    assert reply == "最近睡眠稳定"
    assert captured["origin"] == "telegram"
    assert captured["channel"] == "typed"
    assert captured["client_turn_id"].startswith("telegram-")
    conversation = db.query(AgentConversation).filter_by(
        id=captured["conversation_id"]
    ).one()
    assert conversation.session_key == f"external-telegram-{user.id}"


async def test_telegram_directive_write_uses_runtime_and_hashed_source_id(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services import telegram_inbound
    from app.services.agent_runtime_facade import CloudAgentRuntimeFacade

    user, _headers = auth_user_and_headers
    captured = {}

    async def fake_execute(_self, **kwargs):
        captured.update(kwargs)
        return json.dumps({
            "status": "verified",
            "success": True,
            "resource_type": "user_directive",
            "resource_id": "91",
        })

    monkeypatch.setattr(CloudAgentRuntimeFacade, "execute_tool", fake_execute)

    reply = await telegram_inbound.handle_inbound_text(
        db,
        user.id,
        "严格戒酒30天",
        source_message_id="provider-message-77",
    )

    assert reply.startswith("✅")
    assert captured["tool_name"] == "user_directive"
    assert captured["client_turn_id"].startswith("telegram-")
    assert captured["arguments"]["source_message_id"].startswith("telegram-")
    assert "provider-message-77" not in repr(captured)


def test_telegram_message_identity_is_keyed_and_context_bound(
    monkeypatch,
):
    from app.config import settings
    from app.services.telegram_inbound import _telegram_client_turn_id

    monkeypatch.setattr(settings, "secret_key", "a" * 32)
    first = _telegram_client_turn_id(
        "message-10",
        user_id=7,
        conversation_id="chat-1",
    )
    repeated = _telegram_client_turn_id(
        "message-10",
        user_id=7,
        conversation_id="chat-1",
    )
    other_user = _telegram_client_turn_id(
        "message-10",
        user_id=8,
        conversation_id="chat-1",
    )

    assert first == repeated
    assert first != other_user
    assert "message-10" not in first


async def test_telegram_duplicate_directive_delivery_writes_once(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.config import settings
    from app.models.agent_runtime import AgentRun
    from app.models.user_directive import UserDirective
    from app.services import directive_parser, telegram_inbound

    user, _headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    parse_calls = 0

    async def fake_parse(_text):
        nonlocal parse_calls
        parse_calls += 1
        return [{
            "kind": "lifestyle",
            "instruction": "严格戒酒30天",
            "severity": "strong",
        }]

    monkeypatch.setattr(directive_parser, "_parse_with_llm_async", fake_parse)

    first = await telegram_inbound.handle_inbound_text(
        db,
        user.id,
        "严格戒酒30天",
        source_message_id="provider-message-88",
        source_conversation_id="chat-9",
    )
    replay = await telegram_inbound.handle_inbound_text(
        db,
        user.id,
        "严格戒酒30天",
        source_message_id="provider-message-88",
        source_conversation_id="chat-9",
    )

    assert first.startswith("✅")
    assert replay.startswith("✅")
    assert parse_calls == 1
    assert db.query(UserDirective).filter_by(user_id=user.id).count() == 1
    assert db.query(AgentRun).filter_by(user_id=user.id).count() == 1


async def test_telegram_multi_directive_replay_preserves_complete_receipt(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.config import settings
    from app.models.user_directive import UserDirective
    from app.services import directive_parser, telegram_inbound

    user, _headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")

    async def fake_parse(_text):
        return [
            {
                "kind": "lifestyle",
                "instruction": "严格戒酒30天",
                "severity": "strong",
            },
            {
                "kind": "target_override",
                "instruction": "LDL控制在2.6以下",
                "severity": "strong",
            },
        ]

    monkeypatch.setattr(directive_parser, "_parse_with_llm_async", fake_parse)
    kwargs = {
        "source_message_id": "provider-message-89",
        "source_conversation_id": "chat-9",
    }

    first = await telegram_inbound.handle_inbound_text(
        db, user.id, "严格戒酒30天，LDL控制在2.6以下", **kwargs
    )
    replay = await telegram_inbound.handle_inbound_text(
        db, user.id, "严格戒酒30天，LDL控制在2.6以下", **kwargs
    )

    assert "已录入 2 条" in first
    assert "已录入 2 条" in replay
    assert db.query(UserDirective).filter_by(user_id=user.id).count() == 2


async def _async_value(value):
    return value
