from app.api.agent import _persist_done_llm_usage
from app.models.openclaw import OpenClawConversation, OpenClawMessage


def test_persist_done_llm_usage_preserves_existing_meta(db):
    conv = OpenClawConversation(user_id=1, title="usage profile")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    msg = OpenClawMessage(
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
