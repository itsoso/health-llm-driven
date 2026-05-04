"""
Tests for backend/app/services/action_card_extractor.py.

抽取器是 best-effort: 失败必须不抛, 任何非法输出必须被过滤. 这些测试守护这两条不变量.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from app.services.action_card_extractor import (
    ExtractedFields,
    extract_from_content,
    _validate_and_clean,
    _strip_codeblock,
    _ALLOWED_METRIC_KEYS,
)


# ─────────────────────── _validate_and_clean ────────────────────────


def test_validate_clean_full_valid():
    out = _validate_and_clean({
        "metric_key": "weight",
        "baseline_value": "82kg",
        "target_value": "80kg",
        "verification_days": 14,
    })
    assert out.metric_key == "weight"
    assert out.baseline_value == "82kg"
    assert out.target_value == "80kg"
    assert out.verification_days == 14


def test_validate_clean_unknown_metric_dropped():
    """白名单外的 metric_key 必须丢弃, 防 LLM 编造."""
    out = _validate_and_clean({"metric_key": "happiness_score"})
    assert out.metric_key is None


def test_validate_clean_metric_whitespace_handled():
    out = _validate_and_clean({"metric_key": "  hrv  "})
    assert out.metric_key == "hrv"


def test_validate_clean_verification_days_out_of_range():
    """LLM 给 365 这种离谱值必须丢弃 (允许 1-30)."""
    out = _validate_and_clean({"verification_days": 365})
    assert out.verification_days is None

    out = _validate_and_clean({"verification_days": 0})
    assert out.verification_days is None

    out = _validate_and_clean({"verification_days": -3})
    assert out.verification_days is None


def test_validate_clean_verification_days_string_coerced():
    """LLM 偶尔返回字符串数字, 应能转换."""
    out = _validate_and_clean({"verification_days": "7"})
    assert out.verification_days == 7


def test_validate_clean_verification_days_bad_string():
    out = _validate_and_clean({"verification_days": "一周"})
    assert out.verification_days is None


def test_validate_clean_verification_days_boundary():
    """边界值 1 和 30 都接受."""
    assert _validate_and_clean({"verification_days": 1}).verification_days == 1
    assert _validate_and_clean({"verification_days": 30}).verification_days == 30
    assert _validate_and_clean({"verification_days": 31}).verification_days is None


def test_validate_clean_value_too_long_dropped():
    """超过 100 字符的 baseline/target 必须丢弃 (DB column 限制)."""
    long_str = "x" * 200
    out = _validate_and_clean({
        "baseline_value": long_str,
        "target_value": long_str,
    })
    assert out.baseline_value is None
    assert out.target_value is None


def test_validate_clean_numeric_value_coerced():
    """LLM 偶尔返回数字而非字符串, 应能转字符串."""
    out = _validate_and_clean({"baseline_value": 82, "target_value": 80.5})
    assert out.baseline_value == "82"
    assert out.target_value == "80.5"


def test_validate_clean_empty_strings_filtered():
    out = _validate_and_clean({
        "baseline_value": "",
        "target_value": "   ",
    })
    assert out.baseline_value is None
    assert out.target_value is None


def test_validate_clean_all_null():
    out = _validate_and_clean({})
    assert out.metric_key is None
    assert out.baseline_value is None
    assert out.target_value is None
    assert out.verification_days is None


def test_validate_clean_explicit_null_values():
    """LLM 显式返回 null 必须当不存在处理."""
    out = _validate_and_clean({
        "metric_key": None,
        "baseline_value": None,
        "target_value": None,
        "verification_days": None,
    })
    assert out.metric_key is None
    assert out.verification_days is None


# ─────────────────────── _strip_codeblock ────────────────────────


def test_strip_codeblock_with_lang():
    raw = '```json\n{"a": 1}\n```'
    assert _strip_codeblock(raw) == '{"a": 1}'


def test_strip_codeblock_no_lang():
    raw = '```\n{"a": 1}\n```'
    assert _strip_codeblock(raw) == '{"a": 1}'


def test_strip_codeblock_no_block():
    raw = '{"a": 1}'
    assert _strip_codeblock(raw) == '{"a": 1}'


def test_strip_codeblock_with_surrounding_whitespace():
    raw = '\n\n```json\n{"a": 1}\n```\n\n'
    assert _strip_codeblock(raw) == '{"a": 1}'


# ─────────────────────── extract_from_content ────────────────────────


def _mock_llm_returning(text: str):
    """生成一个能让 extract_from_content 内部 LLM 路径返回 text 的 patch context."""
    async def fake_chat(messages, temperature=0.0, max_tokens=200):
        return text

    mock_provider = MagicMock()
    mock_provider.chat = fake_chat
    return mock_provider


def test_extract_empty_content_short_circuits():
    """空 content 不调 LLM, 直接返回空."""
    out = extract_from_content("", title="x")
    assert out == ExtractedFields()


def test_extract_whitespace_content_short_circuits():
    out = extract_from_content("   \n\n  ")
    assert out == ExtractedFields()


def test_extract_happy_path():
    """LLM 返回合规 JSON → 字段全部抽到."""
    fake_json = '{"metric_key": "weight", "baseline_value": "82kg", "target_value": "80kg", "verification_days": 14}'
    with patch("app.services.llm.factory.get_llm_provider",
               return_value=_mock_llm_returning(fake_json)), \
         patch("app.services.llm.usage_tracker.set_caller"):
        out = extract_from_content("减重计划: 7天减2斤", title="减重", user_id=1)
    assert out.metric_key == "weight"
    assert out.target_value == "80kg"
    assert out.verification_days == 14


def test_extract_with_codeblock_wrapping():
    """LLM 习惯用 markdown 代码块包 JSON, 必须能解开."""
    fake = '```json\n{"metric_key": "hrv", "verification_days": 7}\n```'
    with patch("app.services.llm.factory.get_llm_provider",
               return_value=_mock_llm_returning(fake)), \
         patch("app.services.llm.usage_tracker.set_caller"):
        out = extract_from_content("观察 HRV 一周", "HRV 实验")
    assert out.metric_key == "hrv"
    assert out.verification_days == 7


def test_extract_invalid_json_returns_empty():
    """LLM 返回非 JSON 不抛异常, 返回空."""
    with patch("app.services.llm.factory.get_llm_provider",
               return_value=_mock_llm_returning("这不是 JSON, 是闲聊")), \
         patch("app.services.llm.usage_tracker.set_caller"):
        out = extract_from_content("内容", "标题")
    assert out == ExtractedFields()


def test_extract_non_dict_json_returns_empty():
    """LLM 返回 list/str/数字 也不能崩."""
    with patch("app.services.llm.factory.get_llm_provider",
               return_value=_mock_llm_returning("[1, 2, 3]")), \
         patch("app.services.llm.usage_tracker.set_caller"):
        out = extract_from_content("内容")
    assert out == ExtractedFields()


def test_extract_llm_exception_returns_empty():
    """LLM 调用本身抛异常 (网络等) → 静默吞, 返回空."""
    bad_provider = MagicMock()
    async def boom(**kw):
        raise RuntimeError("network down")
    bad_provider.chat = boom
    with patch("app.services.llm.factory.get_llm_provider",
               return_value=bad_provider), \
         patch("app.services.llm.usage_tracker.set_caller"):
        out = extract_from_content("内容")
    assert out == ExtractedFields()


def test_extract_llm_returns_invalid_metric_key_filtered():
    """LLM 编造白名单外的 metric (如 mood / happiness) 必须被过滤."""
    fake = '{"metric_key": "mood", "verification_days": 7}'
    with patch("app.services.llm.factory.get_llm_provider",
               return_value=_mock_llm_returning(fake)), \
         patch("app.services.llm.usage_tracker.set_caller"):
        out = extract_from_content("情绪追踪")
    # mood 不在白名单 → metric_key 为 None, verification_days 仍保留
    assert out.metric_key is None
    assert out.verification_days == 7


def test_extract_truncates_long_content_does_not_crash():
    """长文不应崩 (内部限制 2000)."""
    fake = '{}'
    with patch("app.services.llm.factory.get_llm_provider",
               return_value=_mock_llm_returning(fake)), \
         patch("app.services.llm.usage_tracker.set_caller"):
        out = extract_from_content("a" * 100000)
    assert out == ExtractedFields()


# ─────────────────────── 白名单覆盖 sanity ────────────────────────


@pytest.mark.parametrize("key", [
    "weight", "hrv", "sleep_score", "rhr", "spo2_odi",
    "ldl", "hdl", "hba1c", "fasting_glucose",
    "systolic_bp", "diastolic_bp", "bmi", "body_fat",
    "alt", "ast", "creatinine", "uric_acid",
])
def test_metric_key_whitelist_covers_common(key):
    """常见 metric 都应在白名单里, 防回归."""
    assert key in _ALLOWED_METRIC_KEYS
