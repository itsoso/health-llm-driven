"""Reminder landing reads exact owner/date/slot and writes only reviewed contexts."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.models.medication import Medication, MedicationLog


@pytest.fixture
def reminder(client, db, auth_user_and_headers, monkeypatch):
    user, headers = auth_user_and_headers
    monkeypatch.setattr(
        "app.services.medication_reminder_context.get_user_now",
        lambda *_: datetime(2026, 10, 16, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    med = Medication(
        user_id=user.id,
        name="测试药品",
        dosage="1粒",
        frequency="每日一次",
        is_active=True,
        reminder_times=["12:30"],
    )
    db.add(med)
    db.commit()
    return user, headers, med


def context(client, headers, med, **params):
    return client.get(
        f"/api/v1/medication/medications/{med.id}/reminder",
        headers=headers,
        params={"date": "2026-10-16", "time": "12:30", **params},
    )


def post(client, headers, med, snapshot, **overrides):
    return client.post(
        f"/api/v1/medication/medications/{med.id}/reminder/log",
        headers=headers,
        json={
            "date": snapshot["date"],
            "time": snapshot["time"],
            "timezone": snapshot["timezone"],
            "expected_revision": snapshot["revision"],
            "status": "taken",
            **overrides,
        },
    )


def test_exact_historical_slot_and_undated_confirmation(client, db, reminder):
    user, h, med = reminder
    db.add(
        MedicationLog(
            user_id=user.id,
            medication_id=med.id,
            taken_date=date(2026, 10, 15),
            taken_time="12:30",
            status="taken",
        )
    )
    db.commit()
    old = context(client, h, med, date="2026-10-15").json()
    assert old["log"]["taken_date"] == "2026-10-15"
    assert old["log"]["status"] == "taken"
    assert context(client, h, med).json()["log"] is None
    result = client.get(
        f"/api/v1/medication/medications/{med.id}/reminder",
        headers=h,
        params={"time": "12:30"},
    ).json()
    assert result["date"] == "2026-10-16"
    assert result["requires_date_confirmation"] and not result["actionable"]


def test_repeated_writes_exact_receipt_and_skip_conflict(client, db, reminder):
    user, h, med = reminder
    snapshot = context(client, h, med).json()
    first = post(client, h, med, snapshot)
    assert first.status_code == 200
    assert post(client, h, med, snapshot).json() == first.json()
    assert post(client, h, med, snapshot, status="skipped").json()["status"] == "taken"
    assert db.query(MedicationLog).filter_by(medication_id=med.id).count() == 1


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"is_active": False}, "inactive"),
        ({"name": "记录 不要建议我自行停药"}, "invalid_medication_name"),
        ({"dosage": None}, "dose_missing"),
        ({"reminder_times": ["18:00"]}, "schedule_changed"),
    ],
)
def test_changed_medication_blocks_write(client, db, reminder, change, reason):
    _, h, med = reminder
    snapshot = context(client, h, med).json()
    for k, v in change.items():
        setattr(med, k, v)
    db.commit()
    assert context(client, h, med).json()["reason"] == reason
    assert post(client, h, med, snapshot).status_code == 409
    assert db.query(MedicationLog).count() == 0


def test_revision_change_blocks_write(client, db, reminder):
    _, h, med = reminder
    snapshot = context(client, h, med).json()
    med.dosage = "2粒"
    db.commit()
    assert post(client, h, med, snapshot).json()["detail"] == "medication_changed"
    assert db.query(MedicationLog).count() == 0


def test_future_timezone_and_malformed_time(client, db, reminder):
    _, h, med = reminder
    assert (
        context(client, h, med, date="2026-10-17").json()["reason"]
        == "future_occurrence"
    )
    assert (
        context(client, h, med, source_timezone="UTC").json()["reason"]
        == "timezone_mismatch"
    )
    assert context(client, h, med, time="25:00").status_code == 422
    snapshot = context(client, h, med).json()
    assert post(client, h, med, snapshot, timezone="UTC").status_code == 409


def test_wrong_owner_returns_404(client, db, reminder):
    from app.models.user import User

    _, h, med = reminder
    other = User(
        username="reminder_other",
        name="Synthetic other",
        email="other@example.test",
        hashed_password="hash",
        is_active=True,
        is_approved=True,
    )
    db.add(other)
    db.commit()
    med.user_id = other.id
    db.commit()
    assert context(client, h, med).status_code == 404


def test_generic_conflicting_skip_uses_persisted_agenda_status(
    client, db, reminder, monkeypatch
):
    user, h, med = reminder
    from app.utils.timezone import get_user_today

    seen = []
    monkeypatch.setattr(
        "app.api.medication._writeback_agenda_completion",
        lambda _db, _uid, _med, data: seen.append(data.status),
    )
    body = {
        "medication_id": med.id,
        "taken_date": str(get_user_today(db, user.id)),
        "taken_time": "12:30",
        "status": "taken",
    }
    assert (
        client.post("/api/v1/medication/logs", headers=h, json=body).status_code == 200
    )
    response = client.post(
        "/api/v1/medication/logs", headers=h, json={**body, "status": "skipped"}
    )
    assert response.json()["status"] == "taken"
    assert seen == ["taken", "taken"]


def test_effective_timezone_date_and_future_time(client, db, reminder, monkeypatch):
    _, h, med = reminder
    monkeypatch.setattr(
        "app.services.medication_reminder_context.get_user_now",
        lambda *_: datetime(
            2026, 10, 15, 23, 0, tzinfo=ZoneInfo("America/Los_Angeles")
        ),
    )
    snapshot = context(client, h, med, date="2026-10-15").json()
    assert snapshot["timezone"] == "America/Los_Angeles"
    assert snapshot["today_date"] == "2026-10-15"
    assert snapshot["actionable"]
    assert context(client, h, med).json()["reason"] == "future_occurrence"
    assert post(client, h, med, snapshot).status_code == 200


def test_missing_time_and_unknown_status_fail_closed(client, db, reminder):
    _, h, med = reminder
    response = client.get(
        f"/api/v1/medication/medications/{med.id}/reminder",
        headers=h,
        params={"date": "2026-10-16"},
    ).json()
    assert response["time"] is None and response["reason"] == "time_required"
    snapshot = context(client, h, med).json()
    assert post(client, h, med, snapshot, status="delayed").status_code == 422
    assert db.query(MedicationLog).count() == 0


def test_postgres_reminder_lock_blocks_concurrent_medication_edit(
    db, reminder, monkeypatch
):
    """A dose change cannot slip between validation and persisted execution."""
    if db.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock semantics")
    import asyncio
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.exc import OperationalError
    from app.api.medication import ReminderLogCreate, log_medication_reminder
    from app.services.medication_reminder_context import reminder_context
    from app.services.medication_service import medication_service

    user, _, med = reminder
    snapshot = reminder_context(db, user.id, med, date(2026, 10, 16), "12:30")
    user_id, med_id = user.id, med.id
    db.commit()
    entered = threading.Event()
    release = threading.Event()
    original = medication_service.log_medication

    def paused(*args, **kwargs):
        entered.set()
        if not release.wait(10):
            raise AssertionError("test release timed out")
        return original(*args, **kwargs)

    monkeypatch.setattr(medication_service, "log_medication", paused)
    monkeypatch.setattr(
        "app.api.medication._writeback_agenda_completion", lambda *args: None
    )
    monkeypatch.setattr("app.api.medication._invalidate_twin", lambda *args: None)
    Session = sessionmaker(bind=db.bind)

    def write():
        from app.models.user import User

        with Session() as worker:
            owner = worker.get(User, user_id)
            return asyncio.run(
                log_medication_reminder(
                    med_id,
                    ReminderLogCreate(
                        date=date(2026, 10, 16),
                        time="12:30",
                        timezone="Asia/Shanghai",
                        expected_revision=snapshot["revision"],
                        status="taken",
                    ),
                    owner,
                    worker,
                )
            )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(write)
        try:
            assert entered.wait(10)
            with Session() as editor:
                editor.execute(text("SET LOCAL lock_timeout = '200ms'"))
                with pytest.raises(OperationalError):
                    editor.execute(
                        text("UPDATE medications SET dosage=:dose WHERE id=:id"),
                        {"dose": "2粒", "id": med_id},
                    )
                editor.rollback()
        finally:
            release.set()
        assert future.result(timeout=10)["status"] == "taken"
    db.expire_all()
    assert db.get(Medication, med_id).dosage == "1粒"


def test_future_and_course_boundaries_enforced_on_post(client, db, reminder):
    _, h, med = reminder
    snapshot = context(client, h, med).json()
    assert (
        post(client, h, med, snapshot, date="2026-10-17").json()["detail"]
        == "future_occurrence"
    )
    assert (
        post(client, h, med, snapshot, timezone="").json()["detail"]
        == "timezone_mismatch"
    )
    med.start_date = date(2026, 10, 16)
    db.commit()
    old = context(client, h, med, date="2026-10-15").json()
    assert old["reason"] == "outside_course"
    assert post(client, h, med, old).status_code == 409
    assert db.query(MedicationLog).count() == 0
