"""多轮承诺记忆回归 —— 镜像 evals/comparative battery 的 multi_turn_endoscopy_recheck。

钉死的运行时保证:同一 conversation 的追问轮,传给 LLM 的 messages 必须带上
首轮 assistant 给出的时间承诺原文(如"8月中旬复查胃镜")+ 首轮用户问题,且轮次
顺序正确。防未来回归面:build_messages limit 被调小、fast-route 扩围剥历史、
历史注入点被挪到保存本轮 user 消息之前等。

不触发真 LLM:_call_llm/_call_llm_stream 全注入。
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.agent_conversation import AgentMessage
from app.services.agent_executor import AgentExecutor

FIRST_TURN_PROMPT = "我的胃溃疡什么时候该复查胃镜?给点建议。"
FIRST_TURN_REPLY = "建议在 8月中旬 疗程结束时复查胃镜(常规 6-8 周),具体以医生意见为准。"
FOLLOW_UP_PROMPT = "那按你上面说的复查时间,到现在到了吗?"


def _stream_from(fake_call_llm):
    """把 fake_call_llm(messages, tools) -> dict 适配成 _call_llm_stream 事件流。"""

    async def fake_call_llm_stream(messages, tools):
        result = await fake_call_llm(messages, tools)
        content = (result.get("content") or "") if isinstance(result, dict) else str(result or "")
        if content:
            yield {"type": "content", "text": content}
        finish = result.get("finish_reason") if isinstance(result, dict) else "stop"
        yield {"type": "finish", "finish_reason": finish or "stop"}

    return fake_call_llm_stream


def _executor_with(db, fake_call_llm) -> AgentExecutor:
    ex = AgentExecutor(db)
    ex._call_llm = fake_call_llm
    ex._call_llm_stream = _stream_from(fake_call_llm)
    return ex


@pytest.mark.asyncio
async def test_followup_turn_llm_messages_carry_first_turn_time_commitment(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    llm_calls: list[list[dict]] = []

    async def fake_call_llm(messages, tools):
        llm_calls.append([dict(m) for m in messages])
        if len(llm_calls) == 1:
            return {"content": FIRST_TURN_REPLY, "finish_reason": "stop"}
        return {"content": "还没到。", "finish_reason": "stop"}

    # 第一轮:新会话,拿到 conversation_id
    events1 = [
        e
        async for e in _executor_with(db, fake_call_llm).run_stream(
            user_id=user.id, message=FIRST_TURN_PROMPT, user_auth_token="test-token"
        )
    ]
    done1 = events1[-1]
    assert done1["event"] == "done"
    conv_id = done1["data"]["conversation_id"]

    # 第二轮:同一会话追问(新 executor 实例,镜像生产每请求新建)
    events2 = [
        e
        async for e in _executor_with(db, fake_call_llm).run_stream(
            user_id=user.id,
            message=FOLLOW_UP_PROMPT,
            conversation_id=conv_id,
            user_auth_token="test-token",
        )
    ]
    assert events2[-1]["event"] == "done"
    assert events2[-1]["data"]["conversation_id"] == conv_id

    # 追问轮传给 LLM 的 messages:首轮时间承诺 + 首轮问题必须在场,顺序正确
    second = llm_calls[-1]
    assert len(llm_calls) >= 2, "追问轮没有走到 LLM"
    non_system = [(m.get("role"), m.get("content") or "") for m in second if m.get("role") != "system"]
    assert [r for r, _ in non_system] == ["user", "assistant", "user"], non_system
    assert FIRST_TURN_PROMPT in non_system[0][1]
    assert "8月中旬" in non_system[1][1], f"首轮时间锚点丢失: {non_system[1][1][:200]}"
    assert FOLLOW_UP_PROMPT in non_system[2][1]


def test_build_messages_stable_order_when_created_at_ties(db, auth_user_and_headers):
    """created_at 同刻(同毫秒并写/时钟回拨)时按 id 决胜,user/assistant 轮次不得翻转。"""
    from app.services.agent_conversation_service import AgentConversationService

    user, _headers = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="tie")

    same_instant = datetime.now(UTC)
    for role, content in (("user", "首问"), ("assistant", "首答"), ("user", "追问")):
        msg = AgentMessage(conversation_id=conv.id, role=role, content=content, created_at=same_instant)
        db.add(msg)
    db.commit()

    got = svc.build_messages(conv.id, limit=15)
    assert [(m["role"], m["content"]) for m in got] == [
        ("user", "首问"),
        ("assistant", "首答"),
        ("user", "追问"),
    ]
