"""Contract tests for contextual meal-photo decisions.

The policy intentionally consumes typed intent and structured vision evidence.
It must never infer a write intent from raw user text.
"""
from datetime import datetime, timezone

from app.services.contextual_meal_photo_policy import (
    MealPhotoCandidate,
    MealPhotoSemanticIntent,
    decide_contextual_meal_photo,
)


def _candidate(**overrides) -> MealPhotoCandidate:
    defaults = {
        "origin": "chat",
        "semantic_intent": MealPhotoSemanticIntent.IMPLICIT_CAPTURE,
        "classification": "food",
        "recognition_confidence": 0.93,
        "reference_now": datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc),
        "timezone_name": "America/New_York",
        "idempotency_clear": True,
    }
    defaults.update(overrides)
    return MealPhotoCandidate(**defaults)


def test_empty_chat_food_photo_at_user_local_lunch_auto_records():
    decision = decide_contextual_meal_photo(_candidate())

    assert decision.decision == "auto_record"
    assert decision.meal_type == "lunch"
    assert decision.local_time.isoformat() == "2026-07-19T12:30:00-04:00"
    assert decision.reason_codes == ("chat_food", "high_confidence", "meal_window:lunch")


def test_food_photo_outside_normal_meal_window_requires_current_page_confirmation():
    decision = decide_contextual_meal_photo(
        _candidate(reference_now=datetime(2026, 7, 20, 3, 30, tzinfo=timezone.utc))
    )

    assert decision.decision == "confirm"
    assert decision.meal_type == "snack"
    assert "outside_auto_meal_window" in decision.reason_codes


def test_explicit_food_photo_write_outside_meal_window_still_records():
    decision = decide_contextual_meal_photo(
        _candidate(
            semantic_intent=MealPhotoSemanticIntent.EXPLICIT_CAPTURE,
            reference_now=datetime(2026, 7, 20, 3, 30, tzinfo=timezone.utc),
        )
    )

    assert decision.decision == "auto_record"
    assert decision.meal_type == "snack"
    assert "explicit_capture" in decision.reason_codes


def test_semantic_analysis_request_never_creates_a_diet_draft_or_record():
    decision = decide_contextual_meal_photo(
        _candidate(semantic_intent=MealPhotoSemanticIntent.ANALYZE_ONLY)
    )

    assert decision.decision == "analyze_only"
    assert decision.reason_codes == ("semantic_analyze_only",)


def test_non_food_image_never_creates_a_diet_draft_or_record():
    decision = decide_contextual_meal_photo(_candidate(classification="non_food"))

    assert decision.decision == "analyze_only"
    assert decision.reason_codes == ("not_food",)


def test_low_confidence_or_non_chat_food_photo_requires_confirmation():
    low_confidence = decide_contextual_meal_photo(
        _candidate(recognition_confidence=0.61)
    )
    camera_origin = decide_contextual_meal_photo(_candidate(origin="camera"))

    assert low_confidence.decision == "confirm"
    assert "low_confidence" in low_confidence.reason_codes
    assert camera_origin.decision == "confirm"
    assert "non_chat_origin" in camera_origin.reason_codes


def test_duplicate_candidate_is_never_auto_written_again():
    decision = decide_contextual_meal_photo(_candidate(idempotency_clear=False))

    assert decision.decision == "confirm"
    assert decision.reason_codes == ("idempotency_not_clear",)
