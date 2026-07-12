# -*- coding: utf-8 -*-
"""prompt_cache.apply_cache_markers 纯函数单测 (Phase-2 rank3, DashScope 显式上下文缓存)。

锁死:
  1. 默认布局 = system + history_prefix 两个 append-only 断点, 形状 = Anthropic 式
     content 数组 + cache_control ephemeral;
  2. **绝不原地改**传入的 message dict (调用方还要拿 messages 存库);
  3. 非字符串 / 空串 content 保守跳过 (数组形 vision、assistant tool_calls 无正文);
  4. 断点数硬顶 MAX_CACHE_BREAKPOINTS;单条 system-only 不重复标;
  5. 所有 knob 关 → 原样返回 (byte-identical 语义)。
"""
import copy

from app.services.llm.prompt_cache import (
    CACHE_CONTROL_EPHEMERAL,
    MAX_CACHE_BREAKPOINTS,
    apply_cache_markers,
)


def _is_marked(msg):
    """content 是带 ephemeral cache_control 的单 text block 数组。"""
    c = msg.get("content")
    return (
        isinstance(c, list)
        and len(c) == 1
        and c[0].get("type") == "text"
        and c[0].get("cache_control") == {"type": "ephemeral"}
    )


def _marked_count(messages):
    return sum(1 for m in messages if _is_marked(m))


# ──── 1. 默认布局: system + history_prefix ────

def test_default_marks_system_and_history_prefix():
    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "turn1 q"},
        {"role": "assistant", "content": "turn1 a"},
        {"role": "user", "content": "turn2 q (current)"},
    ]
    out = apply_cache_markers(messages)
    # system (idx0) + history_prefix = 最后一条 user 之前的最后一条 = assistant turn1 a (idx2)
    assert _is_marked(out[0])  # system
    assert _is_marked(out[2])  # history prefix (assistant turn1)
    assert not _is_marked(out[1])
    assert not _is_marked(out[3])  # 当前 user 不标
    assert _marked_count(out) == 2


def test_marked_content_preserves_original_text():
    messages = [{"role": "system", "content": "SYS-TEXT"}, {"role": "user", "content": "hi"}]
    out = apply_cache_markers(messages)
    assert out[0]["content"][0]["text"] == "SYS-TEXT"
    assert out[0]["role"] == "system"


# ──── 2. 不原地改传入的 dict ────

def test_does_not_mutate_input_messages():
    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "assistant", "content": "prev"},
        {"role": "user", "content": "now"},
    ]
    snapshot = copy.deepcopy(messages)
    out = apply_cache_markers(messages)
    assert messages == snapshot  # 原 list 里的 dict content 仍是字符串
    assert out is not messages
    # 被标的 message 是新 dict (不是原引用)
    assert out[0] is not messages[0]


# ──── 3. 非字符串 / 空串 content 保守跳过 ────

def test_skips_non_string_and_empty_content():
    messages = [
        {"role": "system", "content": "SYS"},
        # history_prefix 落点 = assistant, 但 content=None (带 tool_calls 无正文) → 跳过
        {"role": "assistant", "content": None, "tool_calls": [{"id": "t1"}]},
        {"role": "user", "content": "now"},
    ]
    out = apply_cache_markers(messages)
    assert _is_marked(out[0])          # system 仍标
    assert not _is_marked(out[1])      # None content 不标 (保持原样)
    assert out[1]["content"] is None
    assert _marked_count(out) == 1


def test_skips_array_content_history_prefix():
    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": [{"type": "text", "text": "vision turn"}]},  # 多模态
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "now"},
    ]
    out = apply_cache_markers(messages)
    # history_prefix = idx2 assistant (字符串) → 标; 多模态 user 不受影响
    assert _is_marked(out[0])
    assert _is_marked(out[2])
    assert out[1]["content"] == [{"type": "text", "text": "vision turn"}]


# ──── 4. system-only / 单轮不重复标 ────

def test_single_system_only_marks_once():
    messages = [{"role": "system", "content": "SYS"}]
    out = apply_cache_markers(messages)
    assert _marked_count(out) == 1  # history_prefix 落点 = last_user-1 = -2 越界 → 跳过


def test_system_plus_single_user_no_history_prefix():
    # [system, user]: last_user=1, history_prefix idx=0 == system 断点 → 去重, 只 system 一个断点
    messages = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "q"}]
    out = apply_cache_markers(messages)
    assert _is_marked(out[0])
    assert not _is_marked(out[1])
    assert _marked_count(out) == 1


# ──── 5. knob 关 → 原样返回 ────

def test_all_knobs_off_returns_input_unchanged():
    messages = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "q"}]
    out = apply_cache_markers(messages, mark_system=False, mark_history_prefix=False)
    assert out is messages  # 无落点 → 原对象返回, byte-identical


def test_empty_messages_returns_input():
    assert apply_cache_markers([]) == []


# ──── 6. tail knob (可选, 默认关) ────

def test_tail_knob_marks_last_message():
    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "t1"}]},
        {"role": "tool", "content": "tool result json"},
    ]
    out = apply_cache_markers(messages, mark_history_prefix=False, mark_tail=True)
    assert _is_marked(out[0])   # system
    assert _is_marked(out[3])   # tail = tool result
    assert _marked_count(out) == 2


# ──── 7. 断点数硬顶 ────

def test_never_exceeds_max_breakpoints():
    # 构造 system + history_prefix + tail 都可标 → 仍 ≤ MAX
    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},   # history_prefix 落点
        {"role": "user", "content": "q2"},
        {"role": "tool", "content": "trailing"},   # tail 落点
    ]
    out = apply_cache_markers(messages, mark_system=True, mark_history_prefix=True, mark_tail=True)
    assert _marked_count(out) <= MAX_CACHE_BREAKPOINTS


def test_cache_control_constant_shape():
    assert CACHE_CONTROL_EPHEMERAL == {"type": "ephemeral"}
