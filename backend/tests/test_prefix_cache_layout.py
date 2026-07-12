"""Prefix-cache layout invariant (LLM token-perf plan rank #6).

Turn-scoped context (system-KB evidence block, desktop markdown instruction,
entry deeplink context, opener-quick-reply note) must be assembled into the
**last user message**, never appended to the byte-stable system prompt tail.
Keeping it out of the system prompt lets the vendor implicit prefix cache
(百炼/qwen usage.cached_tokens) match a stable prefix = system + tools + history
across consecutive turns.

These tests pin that invariant at the message-assembly seam: they capture the
exact `messages` array handed to the LLM (`_call_llm_stream`) and assert
  1. the SYSTEM message is byte-identical across two different-text /
     different-KB turns of the same intent regime, and
  2. the turn-scoped content (KB evidence + desktop instruction + entry
     context) appears only in the LAST USER message, attributed as system
     附注 (not user input), never in the system message.

Regression guard: if a future edit re-appends turn-scoped content to the system
prompt tail (the exact pre-rank-6 bug), assertion (1) or (2) fails.
"""
import pytest

from app.services.agent_executor import AgentExecutor
from tests.conftest import create_authenticated_user


def _install_message_capture(executor, monkeypatch):
    """Replace the LLM streaming call with a capture that records the assembled
    `messages` array (first positional arg) and answers "OK" with no tool call,
    so the round loop terminates in one round."""
    captured: list[list[dict]] = []

    async def _capture(messages, tools):  # noqa: ANN001 — mirrors _call_llm_stream(messages, tools)
        captured.append(messages)
        yield {"type": "content", "text": "OK"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", _capture)
    # Keep everything local: no agent_base direct path, no real provider.
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    return captured


async def _drain(executor, message, user_id, extra_context=None):
    async for _ in executor.run_stream(
        user_id=user_id,
        message=message,
        user_auth_token="test-token",
        extra_context=extra_context,
    ):
        pass


def _system_and_last_user(messages):
    assert messages[0]["role"] == "system", "messages[0] must be the system prompt"
    last_user = next(
        m for m in reversed(messages) if m.get("role") == "user"
    )
    return messages[0]["content"], last_user["content"]


@pytest.mark.asyncio
async def test_kb_evidence_lands_in_user_message_and_system_is_byte_stable(
    db, monkeypatch
):
    """Two analysis turns, different text + different KB hits → identical system
    prompt; each turn's KB evidence appears in that turn's last user message."""
    user, _ = create_authenticated_user(db)
    executor = AgentExecutor(db)
    captured = _install_message_capture(executor, monkeypatch)

    # Per-message KB sentinel — proves placement without seeding the KB corpus.
    # (analysis turns are non-fast, so _build_system_knowledge_prompt_context runs.)
    monkeypatch.setattr(
        executor,
        "_build_system_knowledge_prompt_context",
        lambda user_id, message: f"## 系统知识库依据\n<<KB::{message}>>",
    )

    # Same intent regime (neither triggers the gene nor menu intent-gated block),
    # different user text, different KB. Both are analysis turns (full prompt).
    msg_a = "综合分析我最近的睡眠趋势"
    msg_b = "复盘一下我最近的肝功能变化"

    await _drain(executor, msg_a, user.id)
    await _drain(executor, msg_b, user.id)

    assert len(captured) == 2, "each turn should reach the LLM exactly once"
    sys_a, user_a = _system_and_last_user(captured[0])
    sys_b, user_b = _system_and_last_user(captured[1])

    # (1) SYSTEM prompt is byte-identical across the two turns — user text and KB
    #     hits do NOT leak into the stable prefix.
    assert sys_a == sys_b, (
        "system prompt drifted across turns — turn-scoped content leaked into "
        "the stable prefix (breaks vendor prefix cache)"
    )

    # (2) KB evidence is isolated to each turn's last user message, never in system.
    assert "<<KB::" not in sys_a, "KB evidence must not be in the system prompt"
    assert f"<<KB::{msg_a}>>" in user_a, "turn A's KB evidence must be in its user message"
    assert f"<<KB::{msg_b}>>" in user_b, "turn B's KB evidence must be in its user message"
    # Attributed as system 附注, not user input; original user text preserved after it.
    assert "系统附注" in user_a and msg_a in user_a
    assert "系统附注" in user_b and msg_b in user_b


@pytest.mark.asyncio
async def test_desktop_instruction_and_entry_context_land_in_user_message(
    db, monkeypatch
):
    """Desktop markdown instruction (最高优先级格式要求) + entry deeplink context
    are turn-scoped → last user message, not the system prompt. Two turns whose
    ONLY difference is these client-supplied turn payloads must share a
    byte-identical system prompt."""
    import json

    user, _ = create_authenticated_user(db)
    executor = AgentExecutor(db)
    captured = _install_message_capture(executor, monkeypatch)
    # Isolate desktop/entry placement from KB: no KB block this test.
    monkeypatch.setattr(
        executor, "_build_system_knowledge_prompt_context", lambda user_id, message: ""
    )

    message = "综合分析我最近的睡眠趋势"
    # Desktop instruction extraction requires client=="mac" (see
    # _extract_desktop_response_instruction).
    desktop_ctx = json.dumps(
        {
            "client": "mac",
            "desktop_markdown_response_instruction": "MARK_DESKTOP_INSTRUCTION_XYZ",
        }
    )
    entry_ctx = "ENTRY_CONTEXT_PLAN_ITEM_42"

    await _drain(executor, message, user.id, extra_context=desktop_ctx)
    await _drain(executor, message, user.id, extra_context=entry_ctx)

    sys_desktop, user_desktop = _system_and_last_user(captured[0])
    sys_entry, user_entry = _system_and_last_user(captured[1])

    # System prompt identical despite different per-turn client context.
    assert sys_desktop == sys_entry, "client turn context leaked into system prompt"

    # Desktop instruction → user message, not system.
    assert "MARK_DESKTOP_INSTRUCTION_XYZ" not in sys_desktop
    assert "MARK_DESKTOP_INSTRUCTION_XYZ" in user_desktop
    assert "最高优先级格式要求" in user_desktop

    # Entry deeplink context → user message, not system.
    assert "ENTRY_CONTEXT_PLAN_ITEM_42" not in sys_entry
    assert "ENTRY_CONTEXT_PLAN_ITEM_42" in user_entry
    assert "入口上下文" in user_entry
