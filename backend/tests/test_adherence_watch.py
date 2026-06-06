# -*- coding: utf-8 -*-
"""依从性智能(Next Horizon Tier 2)回归。

钉:已接受+未评分+过半窗口→midway_risk;逾期→overdue;已评分/未接受/已归档跳过;
nudge 文案温和;db-backed evaluate_user_adherence。
"""
from datetime import datetime, timedelta


class _Card:
    def __init__(self, **kw):
        self.id = kw.get("id", 1)
        self.title = kw.get("title", "计划")
        self.metric_key = kw.get("metric_key", "weight")
        self.outcome = kw.get("outcome")
        self.status = kw.get("status", "active")
        self.user_decision = kw.get("user_decision", "accepted")
        self.verification_days = kw.get("verification_days", 84)
        self.created_at = kw.get("created_at")


_NOW = datetime(2026, 6, 6)


def test_midway_risk(_now=_NOW):
    from app.services.adherence_watch import at_risk_cards
    # 84 天窗口,已过 60 天(71%)→ midway_risk
    c = _Card(created_at=_NOW - timedelta(days=60))
    out = at_risk_cards([c], _NOW)
    assert len(out) == 1 and out[0].kind == "midway_risk"
    assert out[0].days_left == 24 and out[0].progress_pct == 71


def test_overdue():
    from app.services.adherence_watch import at_risk_cards
    c = _Card(created_at=_NOW - timedelta(days=90))  # 超过 84
    out = at_risk_cards([c], _NOW)
    assert len(out) == 1 and out[0].kind == "overdue" and out[0].days_left == 6


def test_early_window_not_at_risk():
    from app.services.adherence_watch import at_risk_cards
    c = _Card(created_at=_NOW - timedelta(days=10))  # 12% < 60%
    assert at_risk_cards([c], _NOW) == []


def test_skips_graded_unaccepted_archived():
    from app.services.adherence_watch import at_risk_cards
    base = dict(created_at=_NOW - timedelta(days=70))
    cards = [
        _Card(outcome="improved", **base),          # 已评分
        _Card(user_decision="declined", **base),     # 未接受
        _Card(status="archived", **base),            # 已归档
        _Card(verification_days=None, **base),       # 无窗口
    ]
    assert at_risk_cards(cards, _NOW) == []


def test_nudge_text_gentle():
    from app.services.adherence_watch import AtRiskCard, nudge_text
    t1, m1 = nudge_text(AtRiskCard(1, "减重计划", "weight", "overdue", 5, 110))
    assert "复检" in m1 or "记一次" in m1
    t2, m2 = nudge_text(AtRiskCard(1, "减重计划", "weight", "midway_risk", 20, 70))
    assert "坚持" in t2 or "保持" in m2  # 鼓励不报警


def test_evaluate_user_adherence_db(db):
    from app.models.action_card import ActionCard
    from app.tasks.adherence_watch import evaluate_user_adherence
    db.add(ActionCard(user_id=1, title="t", content="x", metric_key="weight",
                      user_decision="accepted", outcome=None, verification_days=84,
                      status="active", created_at=_NOW - timedelta(days=70)))
    db.commit()
    risks = evaluate_user_adherence(db, 1, _NOW)
    assert len(risks) == 1 and risks[0].kind == "midway_risk"
