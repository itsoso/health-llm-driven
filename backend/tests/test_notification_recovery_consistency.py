"""Push copy consistency with recovery/Agent guidance."""

from datetime import date, timedelta

from app.models.daily_health import GarminData
from app.models.health_trend import HealthTrendReport
from app.models.user import User


def _make_user(db, username="recovery_consistency"):
    user = User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="x",
        name=username,
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_exercise_undertraining_push_reframes_when_recovery_is_low(db):
    """readiness/HRV 低时, 趋势 push 不应催用户增加跑步强度。"""
    from app.tasks.notifications import _trend_push_body_for_user

    user = _make_user(db, "recovery_low_push")
    today = date.today()
    db.add(GarminData(
        user_id=user.id,
        record_date=today,
        training_readiness_score=38,
        hrv_status="low",
        sleep_score=82,
        body_battery_most_charged=55,
    ))
    report = HealthTrendReport(
        user_id=user.id,
        report_date=today - timedelta(days=1),
        dimension="exercise",
        period="7d",
        trend_direction="declining",
        risk_alerts=["长期运动不足可能导致体能下降，建议关注并及时干预"],
    )
    db.add(report)
    db.commit()

    body = _trend_push_body_for_user(db, user.id, [report], today=today)

    assert "恢复优先" in body
    assert "长期运动不足" not in body
    assert "体能下降" not in body


def test_exercise_undertraining_push_stays_when_recovery_is_good(db):
    """恢复状态正常时, 原 exercise trend 风险仍可推送。"""
    from app.tasks.notifications import _trend_push_body_for_user

    user = _make_user(db, "recovery_ok_push")
    today = date.today()
    db.add(GarminData(
        user_id=user.id,
        record_date=today,
        training_readiness_score=82,
        hrv_status="balanced",
        sleep_score=86,
        body_battery_most_charged=88,
    ))
    report = HealthTrendReport(
        user_id=user.id,
        report_date=today - timedelta(days=1),
        dimension="exercise",
        period="7d",
        trend_direction="declining",
        risk_alerts=["长期运动不足可能导致体能下降，建议关注并及时干预"],
    )
    db.add(report)
    db.commit()

    body = _trend_push_body_for_user(db, user.id, [report], today=today)

    assert body == "⚠️ 长期运动不足可能导致体能下降，建议关注并及时干预"
