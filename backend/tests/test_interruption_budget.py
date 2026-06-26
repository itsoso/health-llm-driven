"""Interruption budget contract for proactive health nudges."""


def test_p2_is_log_only_even_with_complete_contract():
    from app.services.interruption_budget import evaluate_interruption

    decision = evaluate_interruption(
        tier="P2",
        sent_global=0,
        global_budget=15,
        reason="步数同步完成",
        action="写入周复盘",
        fallback_surface="mac",
    )

    assert decision["allowed"] is False
    assert decision["blocked_reason"] == "log_only"
    assert decision["delivery_policy"] == "log_only"
    assert decision["contract_complete"] is True


def test_p1_is_blocked_during_quiet_hours_with_delay_policy():
    from app.services.interruption_budget import evaluate_interruption

    decision = evaluate_interruption(
        tier="P1",
        sent_global=0,
        global_budget=15,
        in_quiet_hours=True,
        reason="睡前流程已到点",
        action="延后到静默结束后提醒",
        fallback_surface="mobile",
    )

    assert decision["allowed"] is False
    assert decision["blocked_reason"] == "quiet_hours"
    assert decision["quiet_hours_respected"] is True
    assert decision["delivery_policy"] == "delay_or_fallback"


def test_p0_can_bypass_quiet_hours_but_contract_is_explicit():
    from app.services.interruption_budget import evaluate_interruption

    decision = evaluate_interruption(
        tier="P0",
        sent_global=0,
        global_budget=15,
        sent_tier=0,
        tier_budget=3,
        in_quiet_hours=True,
        reason="严重低氧阈值触发",
        action="立即查看安全提醒",
        fallback_surface="mobile",
    )

    assert decision["allowed"] is True
    assert decision["blocked_reason"] is None
    assert decision["quiet_hours_respected"] is False
    assert decision["delivery_policy"] == "immediate"
    assert decision["contract_complete"] is True
    assert decision["missing_contract_fields"] == []


def test_p0_p1_missing_contract_fields_are_reported_not_hidden():
    from app.services.interruption_budget import evaluate_interruption

    decision = evaluate_interruption(
        tier="P1",
        sent_global=0,
        global_budget=15,
        in_quiet_hours=False,
    )

    assert decision["allowed"] is True
    assert decision["contract_complete"] is False
    assert decision["missing_contract_fields"] == [
        "reason",
        "action",
        "fallback_surface",
    ]


def test_global_and_tier_caps_are_reported_with_block_reason():
    from app.services.interruption_budget import evaluate_interruption

    global_block = evaluate_interruption(
        tier="P1",
        sent_global=15,
        global_budget=15,
        reason="训练提醒",
        action="打开 Watch 确认",
        fallback_surface="watch",
    )
    assert global_block["allowed"] is False
    assert global_block["blocked_reason"] == "global_budget"

    p0_block = evaluate_interruption(
        tier="P0",
        sent_global=2,
        global_budget=15,
        sent_tier=3,
        tier_budget=3,
        reason="安全提醒",
        action="立即查看",
        fallback_surface="mobile",
    )
    assert p0_block["allowed"] is False
    assert p0_block["blocked_reason"] == "tier_budget"
