"""Deterministic safety boundary for Xiaoba's external Wan media work.

This is deliberately not the conversational intent classifier.  The LLM may
help propose a draft, but provider dispatch is rejected unless it is assigned
to a bounded wellness-communication purpose and it does not ask the generated
asset to diagnose, prescribe, dose, or promise treatment.  The small, explicit
red-line vocabulary is a fail-closed safety control, not a keyword shortcut for
deciding what a user meant in general conversation.
"""
from __future__ import annotations

import unicodedata


ALLOWED_PURPOSES = frozenset(
    {
        "meal_visual",
        "movement_routine",
        "hydration_reminder",
        "sleep_routine",
        "wellness_story",
    }
)

_MEDICAL_RED_LINES = (
    "诊断", "确诊", "处方", "开药", "药方", "药量", "剂量", "用药方案", "治疗方案",
    "治愈", "疗效保证", "替代医生", "停药", "加药", "减药", "化验单解读", "检验报告解读",
    "diagnose", "diagnosis", "prescribe", "prescription", "dosage", "medication plan",
    "treatment plan", "cure", "replace a doctor",
)


class AIGCMediaPolicyError(ValueError):
    """A draft falls outside the permitted external-media product boundary."""


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def validate_aigc_media_policy(*, purpose: str, prompt: str) -> str:
    """Return a normalized purpose or fail before any provider interaction."""
    normalized_purpose = _normalize(purpose)
    if normalized_purpose not in ALLOWED_PURPOSES:
        raise AIGCMediaPolicyError("AIGC 仅支持健康行动沟通类视觉内容")
    normalized_prompt = _normalize(prompt)
    if any(term in normalized_prompt for term in _MEDICAL_RED_LINES):
        raise AIGCMediaPolicyError("AIGC 不能生成诊断、处方、用药或治疗决策内容")
    return normalized_purpose
