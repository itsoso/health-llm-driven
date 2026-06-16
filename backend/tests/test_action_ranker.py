"""ActionRanker v0: turn agenda items into explainable leverage actions."""

from app.services.action_ranker import rank_agenda_action, rank_agenda_actions


def _item(title: str, kind: str, *, priority: int = 50, status: str = "pending"):
    return {
        "type": kind,
        "title": title,
        "status": status,
        "priority": priority,
        "time_window": "anytime",
        "source": {"object_type": "health_protocol", "object_id": 1},
    }


def test_medication_action_gets_adherence_rationale_and_verification_window():
    ranked = rank_agenda_action(_item("早间补剂", "medication"))

    assert ranked["priority_tier"] == "P1"
    assert ranked["verification_window_days"] == 28
    assert ranked["leverage_score"] > 0
    assert "依从" in ranked["rationale_short"]


def test_checkup_overdue_is_safety_tier_before_ordinary_actions():
    ranked = rank_agenda_action(_item("复查:胃溃疡", "checkup", status="overdue", priority=75))

    assert ranked["priority_tier"] == "P0"
    assert ranked["safety_status"] == "needs_doctor"
    assert ranked["verification_window_days"] == 0
    assert "安全" in ranked["rationale_short"]


def test_rank_agenda_actions_prefers_higher_leverage_when_priority_ties():
    actions = rank_agenda_actions([
        _item("喝水", "hydration", priority=50),
        _item("早间补剂", "medication", priority=50),
    ])

    assert actions[0]["title"] == "早间补剂"
    assert actions[0]["leverage_score"] > actions[1]["leverage_score"]
