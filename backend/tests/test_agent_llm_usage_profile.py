from app.api.agent import (
    _append_thinking_step,
    _persist_done_llm_usage,
    _persist_done_thinking_steps,
    _thought_step_from_agent_event,
)
from app.models.agent_conversation import AgentConversation, AgentMessage


def test_persist_done_llm_usage_preserves_existing_meta(db):
    conv = AgentConversation(user_id=1, title="usage profile")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    msg = AgentMessage(
        conversation_id=conv.id,
        role="assistant",
        content="ok",
        meta={"cards": [{"type": "record", "data": {"x": 1}}]},
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    usage = {
        "calls": 1,
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "total_tokens": 20,
        "cost_usd": 0.00001,
        "latency_ms": 234,
        "models": ["qwen3.7-plus"],
        "providers": ["tokenplan"],
        "items": [
            {
                "provider": "tokenplan",
                "model": "qwen3.7-plus",
                "caller": "agent.answer",
                "prompt_tokens": 12,
                "completion_tokens": 8,
                "total_tokens": 20,
                "cost_usd": 0.00001,
                "latency_ms": 234,
                "success": True,
            }
        ],
    }

    _persist_done_llm_usage(db, msg.id, usage)
    db.refresh(msg)

    assert msg.meta["cards"] == [{"type": "record", "data": {"x": 1}}]
    assert msg.meta["llm_usage"]["prompt_tokens"] == 12
    assert msg.meta["llm_usage"]["completion_tokens"] == 8
    assert msg.meta["llm_usage"]["items"][0]["model"] == "qwen3.7-plus"


def test_persist_done_thinking_steps_preserves_existing_meta(db):
    conv = AgentConversation(user_id=1, title="thinking profile")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    msg = AgentMessage(
        conversation_id=conv.id,
        role="assistant",
        content="ok",
        meta={"cards": [{"type": "record", "data": {"x": 1}}]},
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    _persist_done_thinking_steps(
        db,
        msg.id,
        ["正在理解你的问题", "读取健康数据", "已取得健康数据", "读取健康数据"],
    )
    db.refresh(msg)

    assert msg.meta["cards"] == [{"type": "record", "data": {"x": 1}}]
    assert msg.meta["thinking_steps"] == ["正在理解你的问题", "读取健康数据", "已取得健康数据"]
    assert msg.meta["thinking_steps_kind"] == "safe_progress_summary"


def test_agent_event_thinking_steps_are_safe_progress_summaries():
    steps = []
    events = [
        {"event": "agent_start", "data": {"message": "多模型综合分析中…", "conversation_id": 7}},
        {"event": "tool_call", "data": {"tool": "health_query", "args": "{\"private\":\"raw\"}"}},
        {"event": "tool_result", "data": {"tool": "health_query", "success": True, "preview": "raw result"}},
        {"event": "status", "data": {"stage": "tool", "detail": "查饮食数据", "round": 2}},
    ]

    for event in events:
        steps = _append_thinking_step(steps, _thought_step_from_agent_event(event))

    assert steps == [
        "正在理解你的问题",
        "读取健康数据",
        "已取得健康数据",
        "正在查饮食数据",
    ]
