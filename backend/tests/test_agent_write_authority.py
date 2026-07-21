"""Only deterministic user intent may authorize Agent health mutations."""

import json

import pytest

from app.services.agent_executor import AgentExecutor, _confirm_or_describe


@pytest.mark.asyncio
async def test_model_confirmation_fields_are_removed_before_dispatch(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录刚吃了替普瑞酮"
    captured = {}

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {"error": None, "data": args},
    )

    async def fake_exec(_base, _headers, args):
        captured.update(args)
        return '{"id": 1, "resource_type": "medication_log"}'

    monkeypatch.setattr(executor, "_exec_health_record", fake_exec)

    result = await executor._execute_tool(
        "health_record",
        {
            "record_type": "medication",
            "confirmed": True,
            "data": {"medication_name": "替普瑞酮", "confirm": True},
        },
        None,
    )

    assert "confirmed" not in captured
    assert "confirm" not in captured["data"]
    assert '"id": 1' in result


@pytest.mark.asyncio
async def test_standalone_confirmation_cannot_authorize_model_write(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "是的"

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {"error": None, "data": args},
    )

    async def should_not_run(*_args, **_kwargs):
        raise AssertionError("model-authored confirmation reached the write adapter")

    monkeypatch.setattr(executor, "_exec_health_record", should_not_run)

    result = await executor._execute_tool(
        "health_record",
        {
            "record_type": "medication",
            "confirmed": True,
            "data": {"medication_name": "替普瑞酮"},
        },
        None,
    )

    rejection = json.loads(result)
    assert rejection["status"] == "rejected"
    assert rejection["error_code"] == "ambiguous_intent_requires_clarification"
    assert rejection["dispatch_started"] is False
    assert rejection["message"].startswith("[NEEDS_CLARIFICATION]")
    assert "write_tool_without_write_intent" in result or "ambiguous_intent" in result


def test_confirmation_gate_ignores_model_flags_without_server_authority():
    args = {"confirmed": True}
    data = {"confirm": True}

    result = _confirm_or_describe(
        args,
        data,
        preview="服用替普瑞酮",
        authorized=False,
    )

    assert result is not None
    assert result.startswith("[NEEDS_CONFIRMATION]")
    assert args == {}
    assert data == {}


def test_confirmation_gate_accepts_server_authority():
    args = {"confirmed": True}
    data = {"confirm": True}

    result = _confirm_or_describe(
        args,
        data,
        preview="服用替普瑞酮",
        authorized=True,
    )

    assert result is None
    assert args == {}
    assert data == {}
