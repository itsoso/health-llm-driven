"""Weekly briefing must not expose legacy clinician-confounded efficacy claims."""

from datetime import datetime, timezone

from app.api.weekly_briefing import _card_to_dict
from app.models.action_card import ActionCard


def test_weekly_briefing_projects_legacy_clinician_outcome_as_inconclusive():
    card = ActionCard(
        id=1,
        title="降低 LDL",
        content="x",
        metric_key="ldl",
        outcome="improved",
        accuracy_score=95,
        created_at=datetime.now(timezone.utc),
    )

    payload = _card_to_dict(card)

    assert payload["outcome"] == "inconclusive"
    assert payload["score_status"] == "clinician_review"
