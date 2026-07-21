import json

import pytest

from app.models.agent_conversation import AgentMessage
from app.services.agent_executor import AgentExecutor


def _stream_from(fake_call_llm):
    async def fake_call_llm_stream(messages, tools):
        result = await fake_call_llm(messages, tools)
        content = result.get("content") or ""
        if content:
            yield {"type": "content", "text": content}
        if result.get("tool_calls"):
            yield {"type": "tool_calls", "tool_calls": result["tool_calls"]}
        yield {"type": "finish", "finish_reason": result.get("finish_reason")}

    return fake_call_llm_stream


def test_system_prompt_does_not_turn_sleep_advice_into_an_implicit_write(db):
    prompt = AgentExecutor(db)._build_system_prompt(
        user_id=1,
        conv_id=1,
        user_auth_token="test-token",
    )

    assert "同时请求建议、分析或提问时，只回答问题，不自动记录" in prompt
    assert "除非用户另外明确说“记录”“记一下”或“打卡”" in prompt


@pytest.mark.asyncio
async def test_advice_turn_recovers_from_model_selected_write_tool_without_user_retry(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    checkpoint_statuses = []
    original_persist_write_state = executor._persist_turn_write_state

    def track_write_state(user_message, **kwargs):
        checkpoint_statuses.append(kwargs["status"])
        return original_persist_write_state(user_message, **kwargs)

    monkeypatch.setattr(executor, "_persist_turn_write_state", track_write_state)

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tools": tools})
        if len(calls) == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call_mistaken_event_write",
                        "type": "function",
                        "function": {
                            "name": "health_record",
                            "arguments": json.dumps(
                                {
                                    "record_type": "event",
                                    "data": {"description": "准备睡觉"},
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            }
        assert tools == []
        return {
            "content": "睡前先调暗灯光，停止摄入咖啡因，并把室温调整到舒适范围。",
            "finish_reason": "stop",
        }

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def should_not_dispatch(*_args, **_kwargs):
        raise AssertionError("policy-blocked health_record must not dispatch")

    monkeypatch.setattr(executor, "_exec_health_record", should_not_dispatch)
    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="我准备睡觉了，给我一些建议。",
            user_auth_token="test-token",
        )
    ]

    visible_text = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    done = events[-1]

    assert len(calls) == 2
    assert "睡前先调暗灯光" in visible_text
    assert "写入回执" not in visible_text
    assert "状态暂时无法确认" not in visible_text
    assert done["event"] == "done"
    assert done["data"]["completion_status"] == "complete"

    saved = db.query(AgentMessage).filter_by(role="assistant").one()
    assert saved.content == visible_text
    assert saved.meta["turn_outcome"]["category"] == "success"
    saved_user = db.query(AgentMessage).filter_by(role="user").one()
    assert saved_user.meta["write_state"]["status"] == "rejected"
    assert "in_flight" not in checkpoint_statuses


@pytest.mark.asyncio
async def test_write_checkpoint_is_durable_before_policy_approved_dispatch(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tools": tools})
        if len(calls) == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [{
                    "id": "call_water_write",
                    "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "water",
                            "data": {"amount": 500},
                        }),
                    },
                }],
            }
        return {"content": "已记录饮水 500ml。", "finish_reason": "stop"}

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def assert_checkpoint_before_dispatch(*_args, **_kwargs):
        source = db.query(AgentMessage).filter_by(role="user").one()
        db.refresh(source)
        assert source.meta["write_state"]["status"] == "in_flight"
        return json.dumps({"id": 42, "amount": 500})

    monkeypatch.setattr(executor, "_exec_health_record", assert_checkpoint_before_dispatch)
    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="记录饮水500ml",
            user_auth_token="test-token",
        )
    ]

    assert events[-1]["event"] == "done"
    source = db.query(AgentMessage).filter_by(role="user").one()
    assert source.meta["write_state"]["status"] == "verified"
