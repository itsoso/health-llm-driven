"""#4b: shared salience engine consumed by both chips and proactive push.

`compute_salient_signals` is the single "what matters now" source; the open-loop
push path adds `_detect_salient_state` that surfaces ONLY the critical recovery
signals no existing push covers (readiness crash, acute illness), avoiding
double-push with SafetyGuardian (which owns ACWR/BP/etc.).
"""
from datetime import datetime, timezone
from unittest.mock import patch


def test_detect_salient_state_pushes_only_uncovered_criticals(db, monkeypatch):
    from app.services.conversation_starters import SuggestionCandidate
    import app.services.conversation_starters as cs
    from app.tasks import open_loop_manager as olm

    fake = [
        SuggestionCandidate(100, "今天恢复评分 32，帮我安排轻负荷或休息日方案", "readiness"),
        SuggestionCandidate(100, "我有发热症状，今天该怎么休息和恢复？", "acute_illness"),
        # acwr danger is critical but SafetyGuardian.training_load already pushes it → must be EXCLUDED
        SuggestionCandidate(100, "训练负荷进入风险区，帮我减量并安排恢复", "acwr"),
        # non-critical → never pushed
        SuggestionCandidate(80, "身体电量只剩 25，怎么快速恢复精力？", "body_battery_stress"),
    ]
    monkeypatch.setattr(cs, "compute_salient_signals", lambda _db, _uid, **_k: fake)

    loops = olm._detect_salient_state(db, 1)

    assert {loop.signal_key for loop in loops} == {"readiness", "acute_illness"}
    assert all(loop.kind == "salient_state" for loop in loops)
    assert all(loop.score == 100 for loop in loops)
    assert any("恢复评分 32" in loop.body for loop in loops)


def test_detect_salient_state_empty_when_no_critical(db, monkeypatch):
    from app.services.conversation_starters import SuggestionCandidate
    import app.services.conversation_starters as cs
    from app.tasks import open_loop_manager as olm

    # only non-critical signals → nothing to proactively push
    monkeypatch.setattr(
        cs, "compute_salient_signals",
        lambda _db, _uid, **_k: [SuggestionCandidate(60, "复盘最近一次跑步", "workout")],
    )
    assert olm._detect_salient_state(db, 1) == []


def test_compute_salient_signals_ranks_critical_first(db, auth_user_and_headers):
    """The shared engine surfaces readiness crash as a critical (priority>=100) — the
    same signal chips show — proving push and chips draw from one engine."""
    from app.services.conversation_starters import compute_salient_signals
    from app.twin.schema import HealthTwin, TwinMeta, PhysiologicalState

    user, _ = auth_user_and_headers
    fake_twin = HealthTwin(
        meta=TwinMeta(user_id=user.id, generated_at=datetime.now(timezone.utc)),
        physiological=PhysiologicalState(
            training_readiness_score=32, training_readiness_level="poor"
        ),
    )
    with patch("app.twin.builder.build_twin", return_value=fake_twin):
        signals = compute_salient_signals(db, user.id, limit=8)

    assert signals, "should produce ranked candidates"
    assert signals[0].priority >= 100  # critical sorts first
    assert any(s.key == "readiness" and s.priority >= 100 for s in signals)
