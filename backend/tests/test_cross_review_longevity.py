# -*- coding: utf-8 -*-
"""跨垂直语义冲突:抗衰 N-of-1 加量 × 低 readiness(Next Horizon Tier 5,扩 cross_review)。"""
from datetime import datetime, timezone

from app.orchestrator.cross_review import detect_conflicts
from app.orchestrator.schema import ProposedCard, SpecialistFinding
from app.twin.schema import HealthTwin, TwinMeta


def _twin():
    return HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(timezone.utc)))


def _longevity(with_card: bool):
    cards = []
    if with_card:
        cards = [ProposedCard(
            title="12 周抗衰 N-of-1", content="...", metric_key="phenotypic_age",
            baseline_value="47", target_value="<45", verification_days=84,
        )]
    return SpecialistFinding(specialist_name="longevity", category="longevity",
                             summary="", proposed_cards=cards)


def _recovery(zone):
    return SpecialistFinding(specialist_name="recovery_coach", category="recovery",
                             summary="", raw={"zone": zone})


def test_conflict_when_intensify_and_rest():
    conflicts = detect_conflicts([_longevity(True), _recovery("rest")], _twin())
    pair = {(c.specialist_a, c.specialist_b) for c in conflicts}
    assert ("longevity", "recovery_coach") in pair
    c = next(c for c in conflicts if c.specialist_a == "longevity")
    assert "缓启" in c.resolution_hint or "主动恢复" in c.resolution_hint


def test_no_conflict_when_readiness_ok():
    assert not any(c.specialist_a == "longevity"
                   for c in detect_conflicts([_longevity(True), _recovery("moderate")], _twin()))


def test_no_conflict_when_no_card():
    """没提 N-of-1 卡(没启动强周期)→ 不冲突。"""
    assert not any(c.specialist_a == "longevity"
                   for c in detect_conflicts([_longevity(False), _recovery("rest")], _twin()))
