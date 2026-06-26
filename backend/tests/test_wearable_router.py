"""Wearable Router v1: metric source arbitration, freshness, conflict, Agenda projection."""

from datetime import timedelta


def _user(db):
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    return user


def _wearable_row(db, user_id, record_date, source, **metrics):
    from app.models.daily_health import GarminData

    row = GarminData(
        user_id=user_id,
        record_date=record_date,
        data_source=source,
        **metrics,
    )
    db.add(row)
    return row


def test_router_selects_winning_source_and_explains_metric(db):
    from app.services import wearable_router
    from app.utils.timezone import get_china_today

    user = _user(db)
    today = get_china_today()
    _wearable_row(db, user.id, today, "garmin", hrv=48.0, resting_heart_rate=54)
    _wearable_row(db, user.id, today, "ringconn", hrv=52.0, resting_heart_rate=53)
    db.commit()

    snapshot = wearable_router.build_snapshot(db, user.id, metrics=["hrv", "resting_heart_rate"])

    hrv = snapshot["metrics"]["hrv"]
    assert hrv["value"] == 52.0
    assert hrv["winning_source"] == "ringconn"
    assert hrv["freshness_hours"] == 0
    assert hrv["reliability"] == "high"
    assert hrv["agreement_score"] is not None
    assert hrv["confidence"] in {"high", "medium"}
    assert "RingConn" in hrv["source_reason"]

    rhr = snapshot["metrics"]["resting_heart_rate"]
    assert rhr["winning_source"] == "ringconn"
    assert rhr["source_values"] == {"garmin": 54, "ringconn": 53}


def test_router_emits_stale_issue_for_old_key_metric(db):
    from app.services import wearable_router
    from app.utils.timezone import get_china_today

    user = _user(db)
    _wearable_row(
        db,
        user.id,
        get_china_today() - timedelta(days=3),
        "ringconn",
        hrv=50.0,
    )
    db.commit()

    snapshot = wearable_router.build_snapshot(db, user.id, metrics=["hrv"])

    assert snapshot["metrics"]["hrv"]["freshness_hours"] >= 72
    issue = snapshot["data_quality_issues"][0]
    assert issue["kind"] == "stale"
    assert issue["metric"] == "hrv"
    assert "HRV" in issue["title"]
    assert issue["stale_hours"] >= 72


def test_router_emits_conflict_issue_without_averaging_sources(db):
    from app.services import wearable_router
    from app.utils.timezone import get_china_today

    user = _user(db)
    today = get_china_today()
    _wearable_row(db, user.id, today, "garmin", hrv=30.0)
    _wearable_row(db, user.id, today, "ringconn", hrv=90.0)
    db.commit()

    snapshot = wearable_router.build_snapshot(db, user.id, metrics=["hrv"])

    hrv = snapshot["metrics"]["hrv"]
    assert hrv["value"] == 90.0
    assert hrv["winning_source"] == "ringconn"
    assert hrv["value"] not in {60.0, "60.0"}
    issue = next(i for i in snapshot["data_quality_issues"] if i["kind"] == "conflict")
    assert issue["metric"] == "hrv"
    assert issue["agreement_score"] < 0.75


def test_agenda_projects_wearable_router_stale_quality_item(client, db, auth_user_and_headers):
    from app.models.daily_health import GarminData
    from app.utils.timezone import get_china_today

    user, headers = auth_user_and_headers
    db.add(GarminData(
        user_id=user.id,
        record_date=get_china_today() - timedelta(days=3),
        data_source="ringconn",
        hrv=50.0,
    ))
    db.commit()

    body = client.get("/api/v1/agenda/today", headers=headers).json()
    issue = next(
        item for item in body["items"]
        if item["type"] == "data_quality"
        and item["source"]["object_type"] == "wearable_router"
    )

    assert issue["status"] == "info"
    assert issue["metric"] == "hrv"
    assert issue["issue_kind"] == "stale"
    assert issue["contract"]["source_known"] is True
