"""test_verify_outcomes —— P5-1 N-of-1 自动验证 + metric grading."""

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import uuid
from unittest.mock import patch

import pytest

from app.models.action_card import ActionCard
from app.models.daily_health import GarminData
from app.models.user import User
from app.tasks.metrics import grade_outcome, fetch_metric, FETCHERS
from app.tasks.verify_outcomes import _verify_impl, _verify_one, _score_from_outcome


@pytest.fixture(autouse=True)
def patch_session_local(db):
    @contextmanager
    def _ctx():
        try:
            yield db
        finally:
            pass
    with patch("app.tasks.verify_outcomes.SessionLocal", new=_ctx):
        yield


def _make_user(db, name="verify_user"):
    u = User(
        username=f"{name}_{uuid.uuid4().hex[:8]}",
        email=f"{name}_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name=name,
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_garmin(db, user_id, days_back, **fields):
    db.add(GarminData(
        user_id=user_id,
        record_date=date.today() - timedelta(days=days_back),
        **fields,
    ))
    db.commit()


def _make_card(db, user_id, **kw):
    base = dict(
        user_id=user_id,
        title="t",
        content="c",
        card_type="recommendation",
        source_type="weekly_advisor",
        user_decision="accepted",
        decided_at=datetime.now(timezone.utc) - timedelta(days=10),
        check_back_date=datetime.now(timezone.utc) - timedelta(hours=1),  # 已到期
    )
    base.update(kw)
    c = ActionCard(**base)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# ── grade_outcome ───────────────────────────────────────────────────────


def test_grade_higher_better_improvement():
    # HRV 上升 10% → improved
    out, eff = grade_outcome("hrv", "50", 55.0)
    assert out == "improved"
    assert eff == 0.1


def test_grade_higher_better_worsening():
    out, _ = grade_outcome("hrv", "50", 45.0)
    assert out == "worsened"


def test_grade_higher_better_no_change():
    out, _ = grade_outcome("hrv", "50", 51.0)  # +2% < 5% 阈值
    assert out == "unchanged"


def test_grade_lower_better_improvement():
    # RHR 下降 10% → improved
    out, eff = grade_outcome("rhr", "70", 63.0)
    assert out == "improved"
    assert eff == 0.1


def test_grade_lower_better_worsening():
    out, _ = grade_outcome("weight", "70", 75.0)  # +7% 体重 → worsened
    assert out == "worsened"


def test_grade_invalid_baseline_inconclusive():
    out, eff = grade_outcome("hrv", "abc", 55.0)
    assert out == "inconclusive"
    assert eff is None


def test_grade_zero_baseline_inconclusive():
    out, eff = grade_outcome("hrv", "0", 50.0)
    assert out == "inconclusive"


def test_grade_actual_none_inconclusive():
    out, eff = grade_outcome("hrv", "50", None)
    assert out == "inconclusive"


# ── fetcher: garmin metrics ─────────────────────────────────────────────


def test_fetch_hrv_uses_7day_avg(db):
    user = _make_user(db)
    _make_garmin(db, user.id, days_back=0, hrv=40.0, hrv_7day_avg=55.0)
    val = fetch_metric(db, user.id, "hrv", date.today())
    assert val == 55.0  # 优先 7day_avg


def test_fetch_sleep_score_avg(db):
    user = _make_user(db, "sleep_user")
    _make_garmin(db, user.id, days_back=0, sleep_score=80)
    _make_garmin(db, user.id, days_back=1, sleep_score=70)
    _make_garmin(db, user.id, days_back=2, sleep_score=60)
    val = fetch_metric(db, user.id, "sleep_score", date.today())
    assert val == 70.0


def test_fetch_unknown_metric_returns_none(db):
    user = _make_user(db, "unknown_metric")
    val = fetch_metric(db, user.id, "bogus_metric", date.today())
    assert val is None


def test_fetch_no_data_returns_none(db):
    user = _make_user(db, "no_data")
    val = fetch_metric(db, user.id, "hrv", date.today())
    assert val is None


# ── verify_outcomes: 端到端 ─────────────────────────────────────────────


def test_verify_marks_improved_card(db):
    user = _make_user(db, "improved_card")
    _make_garmin(db, user.id, days_back=0, sleep_score=85)
    _make_garmin(db, user.id, days_back=1, sleep_score=83)
    _make_card(
        db, user.id,
        metric_key="sleep_score",
        baseline_value="70",
        verification_days=7,
    )
    result = _verify_impl()
    assert result["seen"] == 1
    assert result["graded"] == 1
    assert result["improved"] == 1


def test_verify_marks_worsened_card(db):
    user = _make_user(db, "worsened_card")
    _make_garmin(db, user.id, days_back=0, resting_heart_rate=75)
    _make_garmin(db, user.id, days_back=1, resting_heart_rate=78)
    _make_card(
        db, user.id,
        metric_key="rhr",
        baseline_value="60",  # 75 vs 60 = +25% RHR (lower better → worsened)
        verification_days=7,
    )
    result = _verify_impl()
    assert result["worsened"] == 1


def test_verify_marks_inconclusive_when_no_metric_data(db):
    """有 metric_key 有 baseline, 但用户没有 garmin 数据 → inconclusive."""
    user = _make_user(db, "inc_card")
    _make_card(
        db, user.id,
        metric_key="hrv",
        baseline_value="50",
        verification_days=7,
    )
    result = _verify_impl()
    assert result["inconclusive"] == 1


def test_verify_marks_inconclusive_when_no_metric_key(db):
    """没 metric_key 的卡 (兜底建议) → inconclusive, 但 graded_at 写, 不再扫."""
    user = _make_user(db, "no_metric")
    _make_card(
        db, user.id,
        metric_key=None,
        baseline_value=None,
    )
    result = _verify_impl()
    assert result["inconclusive"] == 1
    cards = db.query(ActionCard).filter(ActionCard.user_id == user.id).all()
    assert cards[0].graded_at is not None
    assert cards[0].outcome == "inconclusive"


def test_verify_skips_not_yet_due(db):
    """check_back_date > now 的卡不评."""
    user = _make_user(db, "future_card")
    _make_card(
        db, user.id,
        metric_key="hrv", baseline_value="50",
        check_back_date=datetime.now(timezone.utc) + timedelta(days=1),
    )
    result = _verify_impl()
    assert result["seen"] == 0


def test_verify_skips_already_graded(db):
    """graded_at 已写的卡不重复评."""
    user = _make_user(db, "graded_card")
    _make_card(
        db, user.id,
        metric_key="hrv", baseline_value="50",
        graded_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    result = _verify_impl()
    assert result["seen"] == 0


def test_verify_skips_not_accepted(db):
    """user_decision 不是 accepted (declined / dismissed / NULL) 不评."""
    user = _make_user(db, "rejected_card")
    _make_card(
        db, user.id,
        metric_key="hrv", baseline_value="50",
        user_decision="declined",
    )
    result = _verify_impl()
    assert result["seen"] == 0


def test_score_from_outcome_mapping():
    assert _score_from_outcome("improved") == 80
    assert _score_from_outcome("unchanged") == 50
    assert _score_from_outcome("worsened") == 20
    assert _score_from_outcome("inconclusive") == 0
