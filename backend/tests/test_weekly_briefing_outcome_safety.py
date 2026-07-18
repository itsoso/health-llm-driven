"""Weekly briefing must not expose legacy clinician-confounded efficacy claims."""

from datetime import datetime, timezone

import pytest

from app.api.weekly_briefing import _card_to_dict
from app.models.action_card import ActionCard


@pytest.mark.parametrize(
    ("metric_key", "title"),
    [("ldl", "降低 LDL"), ("blood_glucose", "控制血糖")],
)
def test_weekly_briefing_projects_legacy_clinician_outcome_as_inconclusive(metric_key, title):
    card = ActionCard(
        id=1,
        title=title,
        content="x",
        metric_key=metric_key,
        outcome="improved",
        accuracy_score=95,
        created_at=datetime.now(timezone.utc),
    )

    payload = _card_to_dict(card)

    assert payload["outcome"] == "inconclusive"
    assert payload["score_status"] == "clinician_review"
