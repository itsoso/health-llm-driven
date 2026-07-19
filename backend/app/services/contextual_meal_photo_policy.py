"""Typed policy for chat meal-photo capture.

This module deliberately has no access to raw chat text.  The caller supplies a
semantic intent frame and structured vision evidence, so presentation words such
as "记录" cannot by themselves turn a read request into a health-data write.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.utils.timezone import DEFAULT_TIMEZONE_NAME


AUTO_RECORD_CONFIDENCE = 0.85


class MealPhotoSemanticIntent(StrEnum):
    """Semantic intent emitted by the Agent intent boundary, not text parsing."""

    IMPLICIT_CAPTURE = "implicit_capture"
    EXPLICIT_CAPTURE = "explicit_capture"
    ANALYZE_ONLY = "analyze_only"


MealPhotoDecisionKind = Literal["auto_record", "confirm", "analyze_only"]
MealType = Literal["breakfast", "lunch", "dinner", "snack"]


@dataclass(frozen=True)
class MealPhotoCandidate:
    origin: str
    semantic_intent: MealPhotoSemanticIntent
    classification: str
    recognition_confidence: float | None
    reference_now: datetime
    timezone_name: str
    idempotency_clear: bool


@dataclass(frozen=True)
class MealPhotoDecision:
    decision: MealPhotoDecisionKind
    meal_type: MealType
    local_time: datetime
    timezone_name: str
    reason_codes: tuple[str, ...]


def decide_contextual_meal_photo(candidate: MealPhotoCandidate) -> MealPhotoDecision:
    """Decide whether a recognized meal photo is auto-recorded or confirmed.

    Persistence, authorization and idempotent receipt lookup intentionally live
    outside this function.  It is therefore safe to use before any write path.
    """
    local_time, timezone_name = _resolve_local_time(
        candidate.reference_now,
        candidate.timezone_name,
    )
    meal_type, in_auto_window = _meal_context(local_time)

    if candidate.semantic_intent == MealPhotoSemanticIntent.ANALYZE_ONLY:
        return _decision("analyze_only", meal_type, local_time, timezone_name, "semantic_analyze_only")
    if candidate.classification != "food":
        return _decision("analyze_only", meal_type, local_time, timezone_name, "not_food")
    if candidate.origin != "chat":
        return _decision("confirm", meal_type, local_time, timezone_name, "non_chat_origin")
    if not candidate.idempotency_clear:
        return _decision("confirm", meal_type, local_time, timezone_name, "idempotency_not_clear")
    if (candidate.recognition_confidence or 0.0) < AUTO_RECORD_CONFIDENCE:
        return _decision("confirm", meal_type, local_time, timezone_name, "low_confidence")
    if not in_auto_window:
        return _decision("confirm", meal_type, local_time, timezone_name, "outside_auto_meal_window")

    return MealPhotoDecision(
        decision="auto_record",
        meal_type=meal_type,
        local_time=local_time,
        timezone_name=timezone_name,
        reason_codes=("chat_food", "high_confidence", f"meal_window:{meal_type}"),
    )


def _resolve_local_time(reference_now: datetime, requested_timezone: str) -> tuple[datetime, str]:
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=timezone.utc)
    try:
        timezone_name = requested_timezone or DEFAULT_TIMEZONE_NAME
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        timezone_name = DEFAULT_TIMEZONE_NAME
        zone = ZoneInfo(timezone_name)
    return reference_now.astimezone(zone), timezone_name


def _meal_context(local_time: datetime) -> tuple[MealType, bool]:
    hour = local_time.hour
    if 5 <= hour < 11:
        return "breakfast", True
    if 11 <= hour < 15:
        return "lunch", True
    if 17 <= hour < 22:
        return "dinner", True
    return "snack", False


def _decision(
    decision: MealPhotoDecisionKind,
    meal_type: MealType,
    local_time: datetime,
    timezone_name: str,
    reason_code: str,
) -> MealPhotoDecision:
    return MealPhotoDecision(
        decision=decision,
        meal_type=meal_type,
        local_time=local_time,
        timezone_name=timezone_name,
        reason_codes=(reason_code,),
    )
