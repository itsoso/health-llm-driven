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


async def _async_value(value):
    return value
