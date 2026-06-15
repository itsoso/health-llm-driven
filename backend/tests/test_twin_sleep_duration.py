"""Twin physiological sleep_duration_h_latest + resting_hr/body_battery come from
the merged garmin latest metrics (not the flaky sleep-deep analysis).

Regression for the home-dashboard "睡眠时长/心率/电量 = --" bug: the data was synced
and the Twin had it, but sleep_duration_h_latest wasn't populated and mobile read
the wrong keys. Here we lock that the Twin surfaces all three.
"""
from datetime import date


def test_twin_surfaces_sleep_duration_rhr_battery_from_garmin(db):
    from app.models.user import User
    from app.models.daily_health import GarminData
    from app.twin import build_twin

    user = User(username="slp", email="slp@test.com", hashed_password="x", name="s")
    db.add(user)
    db.commit()
    db.refresh(user)

    db.add(GarminData(
        user_id=user.id,
        record_date=date.today(),
        total_sleep_duration=420,  # 分钟 → 7.0h
        resting_heart_rate=53,
        body_battery_current=42,
        hrv=48.0,
        sleep_score=80,
        data_source="garmin",
    ))
    db.commit()

    p = build_twin(db, user_id=user.id, use_cache=False).physiological
    assert p.sleep_duration_h_latest == 7.0
    assert p.resting_hr == 53
    assert p.body_battery_current == 42
    assert p.sleep_score_latest == 80
