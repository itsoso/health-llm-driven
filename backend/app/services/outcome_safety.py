"""Safety boundary for ActionCard outcome scores.

Some metrics are materially confounded by medication or clinician-managed care.
Their measurements remain useful records, but a card score must never become a
claim that the agent's recommendation worked or failed.
"""
from __future__ import annotations

from typing import Any

from app.services.personal_models.intervention_priors import is_clinician_gated_metric


def is_efficacy_score_eligible(metric_key: Any) -> bool:
    """Whether a metric may contribute to automated recommendation hit rates."""
    return not is_clinician_gated_metric(str(metric_key or ""))


def is_efficacy_score_eligible_card(card: Any) -> bool:
    """Card-shaped convenience wrapper shared by readers and graders."""
    return is_efficacy_score_eligible(getattr(card, "metric_key", None))


def user_facing_efficacy_fields(card: Any) -> dict[str, Any]:
    """Project a card's outcome without exposing a confounded efficacy claim."""
    if is_efficacy_score_eligible_card(card):
        return {
            "accuracy_score": getattr(card, "accuracy_score", None),
            "score_status": "eligible",
            "outcome": getattr(card, "outcome", None),
            "effect_size": getattr(card, "effect_size", None),
        }
    return {
        "accuracy_score": None,
        "score_status": "clinician_review",
        "outcome": "inconclusive",
        "effect_size": None,
    }


def clinician_review_grading_note(metric_key: Any) -> str:
    return (
        f"{metric_key or '该指标'} 受用药或临床管理混杂影响；系统仅保留测量记录，"
        "不将其计入建议命中率或有效性结论，需由临床专业人员综合解读。"
    )


def clinician_review_display_note(metric_key: Any) -> str:
    """Neutral copy for any user-facing legacy card detail."""
    return (
        f"{metric_key or '该指标'} 受用药或临床管理等因素影响；"
        "本次仅保留测量记录，不将其解读为建议有效或无效。"
    )
