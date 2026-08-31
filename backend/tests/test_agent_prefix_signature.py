# -*- coding: utf-8 -*-
"""前缀指纹可观测性 (Phase-2 rank3 第0步)。

_prompt_prefix_signature 是纯函数, 给每次 LLM 调用取 system 块 + 最后一条 user 之前
序列的 sha12 + token-ish 长度, 只出 hash 不出内容 —— 用来从 journalctl 量测跨轮/跨
回合前缀分歧, 为显式缓存 (rank3) 定 marker 布局。

锁死:
  1. system 相同 → system_hash 相同; 不同 → 不同 (12 hex);
  2. prefix_hash 只看最后一条 user 之前 (turn 尾部变化不影响前缀 = 前缀缓存前提);
  3. 历史 (前缀内) 变化 → prefix_hash 变;
  4. 多模态 (list content) 不炸且稳定;
  5. _log_prompt_prefix_signature 每调用记 1 行, 且**不泄漏**任何 prompt 内容。
"""
import logging

from app.services.agent_executor import (
    AgentExecutor,
    _prompt_payload_budget,
    _prompt_prefix_signature,
)


def test_identical_system_same_hash():
    a = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]
    b = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "另一个尾巴"}]
    sa, sb = _prompt_prefix_signature(a), _prompt_prefix_signature(b)
    assert sa["system_hash"] == sb["system_hash"]
    assert len(sa["system_hash"]) == 12


def test_different_system_different_hash():
    a = [{"role": "system", "content": "SYS-A"}, {"role": "user", "content": "hi"}]
    b = [{"role": "system", "content": "SYS-B"}, {"role": "user", "content": "hi"}]
    assert (
        _prompt_prefix_signature(a)["system_hash"]
        != _prompt_prefix_signature(b)["system_hash"]
    )


def test_prefix_hash_ignores_last_user_tail():
    base = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]
    a = base + [{"role": "user", "content": "今天喝了多少水"}]
    b = base + [{"role": "user", "content": "帮我记录喝了500ml水"}]
    assert (
        _prompt_prefix_signature(a)["prefix_hash"]
        == _prompt_prefix_signature(b)["prefix_hash"]
    )


def test_prefix_hash_changes_when_history_changes():
    tail = {"role": "user", "content": "tail"}
    a = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        tail,
    ]
    b = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1-CHANGED"},
        tail,
    ]
    assert (
        _prompt_prefix_signature(a)["prefix_hash"]
        != _prompt_prefix_signature(b)["prefix_hash"]
    )


def test_lengths_and_tokenish():
    msgs = [{"role": "system", "content": "x" * 40}, {"role": "user", "content": "y" * 8}]
    sig = _prompt_prefix_signature(msgs)
    assert sig["total_chars"] == 48
    assert sig["approx_tokens"] == 12  # 48 // 4
    assert sig["prefix_chars"] > 0


def test_handles_non_string_content_stably():
    msgs = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": [
            {"type": "text", "text": "hi"},
            {"type": "image_url", "image_url": {"url": "x"}},
        ]},
    ]
    sig = _prompt_prefix_signature(msgs)
    assert len(sig["system_hash"]) == 12
    assert _prompt_prefix_signature(msgs)["prefix_hash"] == sig["prefix_hash"]


def test_prompt_payload_budget_accounts_for_blocks_without_content():
    messages = [
        {"role": "system", "content": "SECRET_SYSTEM"},
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "SECRET_CURRENT_TURN"},
    ]
    tools = [{
        "type": "function",
        "function": {
            "name": "health_query",
            "description": "SECRET_TOOL_DESCRIPTION",
            "parameters": {"type": "object", "properties": {}},
        },
    }]

    budget = _prompt_payload_budget(messages, tools)

    assert budget["system_chars"] == len("SECRET_SYSTEM")
    assert budget["turn_chars"] == len("SECRET_CURRENT_TURN")
    assert budget["history_chars"] == len("old question") + len("old answer")
    assert budget["tool_count"] == 1
    assert budget["tool_schema_chars"] > 0
    assert budget["total_approx_tokens"] >= budget["message_approx_tokens"]
    rendered = repr(budget)
    assert "SECRET_SYSTEM" not in rendered
    assert "SECRET_CURRENT_TURN" not in rendered
    assert "SECRET_TOOL_DESCRIPTION" not in rendered


def test_log_emits_one_line_without_content_leak(db, caplog):
    executor = AgentExecutor(db)
    provider = type("P", (), {"model": "qwen3.6-flash"})()
    msgs = [
        {"role": "system", "content": "TOPSECRET_SYSTEM_PROMPT"},
        {"role": "user", "content": "TOPSECRET_USER_MESSAGE"},
    ]
    tools = [{
        "type": "function",
        "function": {
            "name": "health_query",
            "description": "TOPSECRET_TOOL_DESCRIPTION",
        },
    }]
    with caplog.at_level(logging.INFO, logger="app.services.agent_executor"):
        executor._log_prompt_prefix_signature(msgs, provider, tools)
    lines = [r.getMessage() for r in caplog.records if "llm_prefix" in r.getMessage()]
    assert len(lines) == 1
    msg = lines[0]
    assert "sys_hash=" in msg and "prefix_hash=" in msg and "model=qwen3.6-flash" in msg
    assert "system_tokens=" in msg and "tool_count=1" in msg and "payload_tokens=" in msg
    # 绝不泄漏 prompt 内容 (只出 hash)。
    assert "TOPSECRET_SYSTEM_PROMPT" not in msg
    assert "TOPSECRET_USER_MESSAGE" not in msg
    assert "TOPSECRET_TOOL_DESCRIPTION" not in msg
