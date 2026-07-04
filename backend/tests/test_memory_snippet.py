"""test_memory_snippet — serving-side sanitizer for memory opener text.

修 2026-07-04 founder 截图: chat opener 直接把 JSON blob 塞给 UI。
sanitize_memory_snippet 在 serving 边界整形, 坏数据不再泄漏。
纯函数, 无 DB。
"""
from __future__ import annotations

from app.services.memory_snippet import (
    looks_like_json_blob,
    sanitize_memory_snippet,
)


# ── blob 检测 ──


def test_detects_wellformed_json_object_as_blob():
    assert looks_like_json_blob('{"建议":"多喝水", "注意":"少熬夜"}') is True


def test_detects_key_value_fragment_as_blob():
    # founder 截图那种被截断的碎片 (没有外层花括号)
    frag = '短期按说明书需要时服用。", "注意事项": "有肝病时慎用对乙酰氨…'
    assert looks_like_json_blob(frag) is True


def test_clean_chinese_sentence_not_blob():
    assert looks_like_json_blob("你对花粉和尘螨过敏，春季需注意。") is False


# ── blob → cleaned ──


def test_wellformed_json_extracts_first_value():
    out = sanitize_memory_snippet(
        '{"建议":"鼻炎发作时优先生理盐水冲洗。", "注意事项": "不要连续使用含麻黄碱喷剂。"}',
        max_len=60,
    )
    assert out == "鼻炎发作时优先生理盐水冲洗。"


def test_truncated_json_fragment_stripped_of_artifacts():
    frag = '短期按说明书需要时服用。", "注意事项": "有肝病时慎用对乙酰氨基酚，出现不适及时就医。'
    out = sanitize_memory_snippet(frag, max_len=80)
    assert out is not None
    # JSON key/引号碎片被剥掉
    assert '"' not in out
    assert "注意事项" not in out or "：" not in out  # 至少不再是 key: 形态
    assert "按说明书需要时服用" in out


# ── skip when nothing sensible remains ──


def test_blob_stripping_to_tiny_value_returns_none():
    # 良构 JSON 但唯一值太短 (<6 实义字符) → None, 调用方 SKIP
    assert sanitize_memory_snippet('{"x":"短"}', max_len=60) is None


def test_pure_braces_returns_none():
    assert sanitize_memory_snippet('{ }', max_len=60) is None
    assert sanitize_memory_snippet('{"":""}', max_len=60) is None


def test_empty_and_none_return_none():
    assert sanitize_memory_snippet("", max_len=60) is None
    assert sanitize_memory_snippet(None, max_len=60) is None
    assert sanitize_memory_snippet("   ", max_len=60) is None


# ── clean short memory must survive (no over-kill) ──


def test_clean_short_memory_survives():
    # "对花粉过敏" 5 字, 干净, 不该被 <6 规则误杀 (现有 opener 测试依赖它)
    assert sanitize_memory_snippet("对花粉过敏", max_len=60) == "对花粉过敏"


def test_clean_three_char_memory_survives():
    assert sanitize_memory_snippet("新医嘱", max_len=60) == "新医嘱"


def test_clean_sentence_noop():
    txt = "你对花粉和尘螨过敏，春季外出建议戴口罩。"
    assert sanitize_memory_snippet(txt, max_len=60) == txt


# ── sentence-boundary truncation ──


def test_truncates_at_sentence_boundary_within_maxlen():
    txt = "第一句在这里结束了。第二句太长应该被整段截掉继续继续继续继续继续"
    out = sanitize_memory_snippet(txt, max_len=20)
    assert out == "第一句在这里结束了。"


def test_midclause_cut_adds_ellipsis():
    txt = "这是一段没有任何句末标点的很长很长很长很长很长很长的记忆文本内容"
    out = sanitize_memory_snippet(txt, max_len=15)
    assert out.endswith("…")
    assert len(out) <= 16  # 15 + 省略号


def test_whitespace_collapsed():
    out = sanitize_memory_snippet("你   最近   经常   头痛   需要   休息", max_len=60)
    assert "   " not in out
    assert out == "你 最近 经常 头痛 需要 休息"
