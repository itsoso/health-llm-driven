"""思考流可视化: qwen reasoning_content 增量 → 节流的 thinking status 事件填死气。

零质量风险的感知延迟优化(纯 UI, 答案 byte-identical)。合成/答案轮首个可见 token 之前
有 ~20-34s 纯 reasoning 死气(探针 scripts/probe_qwen_thinking_budget.py)。executor 把
provider 产出的 {"type":"reasoning",...} 增量节流成既有 thinking status 事件的 detail。

锁死不变量:
  (a) reasoning 增量 → 节流的 stage='thinking' + snippet detail, **首个可见 token 后停发**;
  (b) reasoning 文本绝不进 token 流 / full_reply / 持久化 assistant 消息内容;
  (c) 无 reasoning 的模型 → 零 reasoning-derived 事件(byte-identical 路径);
  (d) 长得像工具结果 JSON 的 reasoning 片段被 _streaming_leak_forming 跳过。
"""
import pytest

from app.services import agent_executor as ae
from app.services.agent_executor import AgentExecutor


def _wire_min(executor, monkeypatch):
    """最小接线,让 run_stream 走到 round 循环而不碰真 LLM/provider。"""
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [{
        "type": "function",
        "function": {"name": "health_query", "description": "x",
                     "parameters": {"type": "object", "properties": {}}},
    }])
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")


async def _run(executor, message, user_id):
    return [
        event
        async for event in executor.run_stream(
            user_id=user_id,
            message=message,
            user_auth_token="test-token",
        )
    ]


def _thinking_details(events):
    """所有 stage='thinking' 且 detail 非空的 status 事件的 detail(reasoning-derived)。"""
    out = []
    for e in events:
        if e.get("event") == "status":
            d = e.get("data") or {}
            if d.get("stage") == "thinking" and d.get("detail"):
                out.append(d["detail"])
    return out


def _tokens(events):
    return "".join(
        e["data"].get("content", "")
        for e in events
        if e.get("event") == "token"
    )


@pytest.mark.asyncio
async def test_reasoning_throttled_into_thinking_status_and_absent_from_answer(
    db, auth_user_and_headers, monkeypatch
):
    """(a) + (b): reasoning → thinking status(首 token 前停),且绝不进答案/持久化。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    # 关掉节流阈值,让每个 reasoning delta 都能发,精确断言逐条。
    monkeypatch.setattr(ae, "_REASONING_STATUS_MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(ae, "_REASONING_STATUS_MIN_CHARS", 0)

    async def fake_stream(messages, round_tools):
        yield {"type": "reasoning", "text": "先看 HRV 夜间下滑"}
        yield {"type": "reasoning", "text": "再对比睡眠结构偏浅"}
        yield {"type": "content", "text": "综合来看,"}
        # 首个可见 token 之后的 reasoning 必须被忽略(答案流已接管)。
        yield {"type": "reasoning", "text": "这段绝不该surface给用户"}
        yield {"type": "content", "text": "建议早餐补蛋白。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(executor, "分析我的状态", user_id=user.id)

    details = _thinking_details(events)
    # (a) reasoning 片段以 thinking status 出现,首 token 后的 late reasoning 不出现。
    assert any("HRV" in d for d in details)
    assert any("睡眠结构" in d for d in details)
    assert not any("surface" in d for d in details), "首个可见 token 后 reasoning 必须停发"

    # (b) 答案 token 流 = 纯 content,绝不含 reasoning 文本。
    tokens = _tokens(events)
    assert tokens == "综合来看,建议早餐补蛋白。"
    for leaked in ("HRV", "睡眠结构", "surface"):
        assert leaked not in tokens

    # (b) 持久化 assistant 消息内容 = 纯答案,无 reasoning。
    from app.models.agent_conversation import AgentMessage

    done = next(e for e in events if e.get("event") == "done")
    msg = (
        db.query(AgentMessage)
        .filter(AgentMessage.id == done["data"]["message_id"])
        .first()
    )
    assert msg is not None
    assert msg.content == "综合来看,建议早餐补蛋白。"
    assert "HRV" not in (msg.content or "") and "睡眠结构" not in (msg.content or "")


@pytest.mark.asyncio
async def test_reasoning_status_is_throttled_by_char_budget(
    db, auth_user_and_headers, monkeypatch
):
    """(a) 节流: 默认 120 字预算下,300 字 reasoning 分 10 个 30 字 delta → 恰 2 条 status。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    # 只放开时间闸,保留默认字符预算(120),验证 whichever-later 的字符节流。
    monkeypatch.setattr(ae, "_REASONING_STATUS_MIN_INTERVAL_S", 0.0)

    async def fake_stream(messages, round_tools):
        for _ in range(10):
            yield {"type": "reasoning", "text": "分析" * 15}  # 30 字/条,共 300 字
        yield {"type": "content", "text": "结论。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(executor, "分析", user_id=user.id)

    details = [d for d in _thinking_details(events) if "分析" in d]
    # 累积到 120 / 240 各发一次,300 收尾差 60<120 不发 → 恰 2 条。
    assert len(details) == 2


@pytest.mark.asyncio
async def test_no_reasoning_model_emits_zero_reasoning_events(
    db, auth_user_and_headers, monkeypatch
):
    """(c) 无 reasoning 增量 → 零 stage='thinking'+detail 事件(byte-identical 路径)。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "直接回答。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(executor, "你好", user_id=user.id)

    # 无 reasoning → 无 thinking-with-detail 事件;答案照旧。
    assert _thinking_details(events) == []
    assert _tokens(events) == "直接回答。"


@pytest.mark.asyncio
async def test_reasoning_snippet_that_looks_like_tool_result_json_is_skipped(
    db, auth_user_and_headers, monkeypatch
):
    """(d) reasoning 片段形成工具结果 JSON 泄漏形态 → _streaming_leak_forming 跳过。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    monkeypatch.setattr(ae, "_REASONING_STATUS_MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(ae, "_REASONING_STATUS_MIN_CHARS", 0)

    json_like = '[{"record_date":"2026-07-12","meal_type":"lunch","calories":700}]'

    async def fake_stream(messages, round_tools):
        yield {"type": "reasoning", "text": json_like}
        yield {"type": "content", "text": "已了解。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(executor, "看看我的饮食", user_id=user.id)

    details = _thinking_details(events)
    assert all("record_date" not in d and "meal_type" not in d for d in details)
    # 泄漏形态的 reasoning 一条 status 都不发。
    assert details == []
    assert _tokens(events) == "已了解。"


@pytest.mark.asyncio
async def test_internal_process_content_is_never_streamed_or_persisted(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    leaked = (
        "I need to get the actual sleep data for last night. Let me query it properly. "
        "The sleep query failed due to a window parameter issue. "
        "I'll try health_query with the sleep dimension."
    )

    async def fake_stream(messages, round_tools):
        # 单字符增量锁死最坏情况：不能先漏出 "I" / "I need" 再开始缓冲。
        for char in leaked:
            yield {"type": "content", "text": char}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(executor, "昨晚我睡得怎么样？今天是否适合锻炼？", user_id=user.id)

    tokens = _tokens(events)
    assert "I need to" not in tokens
    assert "health_query" not in tokens
    assert tokens == "这次没有完成数据查询，因此没有生成可靠回答。请点“重试”重新查询。"

    done = next(event for event in events if event.get("event") == "done")
    assert done["data"]["completion_status"] == "error"
    assert done["data"]["turn_outcome"]["retryable"] is True

    from app.models.agent_conversation import AgentMessage

    message = (
        db.query(AgentMessage)
        .filter(AgentMessage.id == done["data"]["message_id"])
        .first()
    )
    assert message is not None
    assert message.content == tokens
