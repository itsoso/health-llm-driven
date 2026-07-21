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

    async def empty_result(self, tool_name, args, token):
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

    reply = await telegram_inbound.handle_inbound_text(db, 1, "记录饮水500ml")

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


async def _async_value(value):
    return value
