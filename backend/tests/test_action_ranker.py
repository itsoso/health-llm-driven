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


def test_trajectory_context_boosts_and_explains_top_action():
    base = _item("累计 35-45 分钟中等强度活动", "movement", priority=65)
    with_trajectory = dict(base)
    with_trajectory["trajectory_context"] = {
        "domain": "metabolic_health",
        "level": "attention",
        "state_variable": "waist_cm",
        "horizon": "upstream_90d",
        "why": "腰围和血压提示代谢轨迹需要关注。",
        "confidence": "high",
        "verification_window_days": 7,
        "verification_signal": "waist_cm",
    }

    ranked_plain = rank_agenda_action(base)
    ranked_context = rank_agenda_action(with_trajectory)

    assert ranked_context["leverage_score"] > ranked_plain["leverage_score"]
    assert ranked_context["trajectory_context"]["state_variable"] == "waist_cm"
    assert ranked_context["verification_window_days"] == 7
    assert "轨迹" in ranked_context["rationale_short"]


def test_personal_prediction_context_boosts_matching_verifiable_action():
    base = _item("记录晚餐后 10 分钟步行", "movement", priority=55)
    with_prediction = dict(base)
    with_prediction["verification"] = {"metrics": ["weight"], "window_days": 7}
    with_prediction["personal_prediction_context"] = {
        "id": "personal_prediction:cycle:1:weight",
        "prediction_type": "intervention_cycle_projection",
        "metric": "weight",
        "domain": "metabolic_health",
        "horizon_days": 28,
        "expected_signal": {"direction": "down", "expected_delta": -1.2},
        "confidence": "medium",
        "uncertainty": {"level": "medium", "drivers": ["short_cycle_observation"]},
        "claim_boundary": "这是个人统计预测, 不替代医生诊断、处方或治疗。",
    }

    ranked_plain = rank_agenda_action(base)
    ranked_prediction = rank_agenda_action(with_prediction)

    assert ranked_prediction["leverage_score"] > ranked_plain["leverage_score"]
    assert ranked_prediction["personal_prediction_context"]["metric"] == "weight"
    assert ranked_prediction["verification_window_days"] == 7
    assert "预测" in ranked_prediction["rationale_short"]
