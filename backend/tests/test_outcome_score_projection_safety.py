"""All user-facing ActionCard projections share the clinician-review boundary."""

from app.models.action_card import ActionCard
from app.services.diet_plan import _card_to_dict as diet_card_to_dict
from app.services.genetic_report import _card_to_dict as genetic_card_to_dict
from app.services.movement_plan import _card_to_dict as movement_card_to_dict


def test_user_facing_plan_projections_hide_clinician_gated_legacy_outcomes():
    card = ActionCard(
        id=1,
        title="降低 LDL",
        content="临床复盘",
        metric_key="ldl",
        accuracy_score=95,
        outcome="improved",
        effect_size=0.8,
    )

    for serializer in (diet_card_to_dict, movement_card_to_dict, genetic_card_to_dict):
        payload = serializer(card)
        assert payload["accuracy_score"] is None
        assert payload["score_status"] == "clinician_review"
        assert payload["outcome"] == "inconclusive"
        assert payload["effect_size"] is None


def test_user_facing_plan_projections_keep_eligible_outcomes():
    card = ActionCard(
        id=2,
        title="改善睡眠",
        content="恢复复盘",
        metric_key="sleep_score",
        accuracy_score=80,
        outcome="improved",
        effect_size=0.4,
    )

    for serializer in (diet_card_to_dict, movement_card_to_dict, genetic_card_to_dict):
        payload = serializer(card)
        assert payload["accuracy_score"] == 80
        assert payload["score_status"] == "eligible"
        assert payload["outcome"] == "improved"
        assert payload["effect_size"] == 0.4
