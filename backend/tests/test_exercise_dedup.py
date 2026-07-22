"""test_exercise_dedup —— 1 秒窗口幂等保护 (2026-05-11 双击 race fix)."""

from datetime import datetime, timedelta, timezone
import uuid

from app.models.daily_health import ExerciseRecord
from app.models.user import User
from app.services.auth import auth_service


def _user_headers(db, name="ex_user"):
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
    token = auth_service.create_access_token({"sub": str(u.id)})
    return u, {"Authorization": f"Bearer {token}"}


def _payload(reps=20, exercise_type="俯卧撑", sets=1):
    return {
        "record_date": "2026-05-11",
        "exercise_type": exercise_type,
        "sets": sets,
        "reps": reps,
        "intensity": "high",
    }


def test_double_click_same_payload_returns_existing(client, db):
    """同 user/type/reps/sets, 1 秒内连续两次 POST → 只写一条."""
    user, headers = _user_headers(db)

    r1 = client.post("/api/v1/daily-health/exercise", headers=headers, json=_payload())
    assert r1.status_code == 200
    id1 = r1.json()["id"]

    # Pin the stored timestamp inside the one-second window. Using two full HTTP
    # round trips made this test depend on runner speed and intermittently cross
    # the production window before the second request began.
    rec = db.query(ExerciseRecord).filter(ExerciseRecord.id == id1).one()
    rec.created_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    db.commit()

    r2 = client.post("/api/v1/daily-health/exercise", headers=headers, json=_payload())
    assert r2.status_code == 200
    assert r2.json()["id"] == id1, "1 秒窗口内应返回 existing record"

    rows = db.query(ExerciseRecord).filter(
        ExerciseRecord.user_id == user.id,
        ExerciseRecord.exercise_type == "俯卧撑",
    ).count()
    assert rows == 1


def test_different_reps_writes_two_rows(client, db):
    """同 type 但不同 reps 不算重复 — 用户做了第二组."""
    user, headers = _user_headers(db, "diff_reps")

    r1 = client.post("/api/v1/daily-health/exercise", headers=headers, json=_payload(reps=20))
    r2 = client.post("/api/v1/daily-health/exercise", headers=headers, json=_payload(reps=30))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] != r2.json()["id"]

    rows = db.query(ExerciseRecord).filter(
        ExerciseRecord.user_id == user.id,
        ExerciseRecord.exercise_type == "俯卧撑",
    ).count()
    assert rows == 2


def test_different_users_not_deduped(client, db):
    """不同用户即使同 payload 也不去重."""
    user_a, headers_a = _user_headers(db, "alice")
    user_b, headers_b = _user_headers(db, "bob")

    client.post("/api/v1/daily-health/exercise", headers=headers_a, json=_payload())
    client.post("/api/v1/daily-health/exercise", headers=headers_b, json=_payload())

    assert db.query(ExerciseRecord).count() == 2


def test_outside_1s_window_writes_again(client, db):
    """1 秒外的同 payload 视为新记录 (用户真的连做两次)."""
    user, headers = _user_headers(db, "outside_window")

    r1 = client.post("/api/v1/daily-health/exercise", headers=headers, json=_payload())
    id1 = r1.json()["id"]

    # 手动把 created_at 改到窗口外，避免依赖测试机实际执行速度。
    rec = db.query(ExerciseRecord).filter(ExerciseRecord.id == id1).first()
    rec.created_at = datetime.now(timezone.utc) - timedelta(seconds=2)
    db.commit()

    r2 = client.post("/api/v1/daily-health/exercise", headers=headers, json=_payload())
    assert r2.json()["id"] != id1
    assert db.query(ExerciseRecord).filter(ExerciseRecord.user_id == user.id).count() == 2


def test_duration_exercise_dedup(client, db):
    """duration_seconds 模式 (如 plank) 同样去重."""
    user, headers = _user_headers(db, "plank")

    payload = {
        "record_date": "2026-05-11",
        "exercise_type": "平板支撑",
        "sets": 1,
        "duration_seconds": 60,
        "intensity": "high",
    }
    r1 = client.post("/api/v1/daily-health/exercise", headers=headers, json=payload)
    id1 = r1.json()["id"]

    # Keep the second request deterministically inside the production window.
    # A full CI HTTP round trip may otherwise exceed one second and turn this
    # idempotency test into a runner-speed test.
    rec = db.query(ExerciseRecord).filter(ExerciseRecord.id == id1).one()
    rec.created_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    db.commit()

    r2 = client.post("/api/v1/daily-health/exercise", headers=headers, json=payload)
    assert id1 == r2.json()["id"]
