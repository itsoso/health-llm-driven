"""WorkdayHealthScheduler v0.

目标:把工作日微运动生成为 HealthProtocol,让 agenda/watch_summary 直接消费。
"""
import uuid
from datetime import date

from app.models.daily_health import GarminData
from app.models.health_protocol import HealthProtocol
from app.models.user import User
from app.services import agenda_service
from app.services import workday_health_scheduler as scheduler


def _user(db):
    user = User(
        username=f"workday_{uuid.uuid4().hex[:8]}",
        email=f"workday_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="workday",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _readiness(db, user_id: int, score: int):
    db.add(GarminData(
        user_id=user_id,
        record_date=date.today(),
        data_source="apple-watch",
        training_readiness_score=score,
    ))
    db.commit()


def _workday_protocols(db, user_id: int):
    return db.query(HealthProtocol).filter(
        HealthProtocol.user_id == user_id,
        HealthProtocol.status == "active",
        HealthProtocol.notes.like("workday_scheduler:v0:%"),
    ).order_by(HealthProtocol.time_window, HealthProtocol.id).all()


def test_green_readiness_generates_three_micro_movement_protocols_and_agenda_items(db):
    user = _user(db)
    _readiness(db, user.id, 82)

    result = scheduler.generate_today(db, user.id)

    assert result["readiness_tone"] == "green"
    assert result["created"] == 3
    protocols = _workday_protocols(db, user.id)
    assert len(protocols) == 3
    assert any(p.name == "到公司后俯卧撑 12 个" for p in protocols)
    assert any(p.implied_quantity.get("slot") == "post_lunch" for p in protocols)

    agenda = agenda_service.today(db, user.id)
    titles = {item["title"] for item in agenda["items"]}
    assert "到公司后俯卧撑 12 个" in titles
    assert "午餐后轻松步行 10 分钟" in titles


def test_red_readiness_downgrades_strength_to_light_movement(db):
    user = _user(db)
    _readiness(db, user.id, 35)

    result = scheduler.generate_today(db, user.id)

    assert result["readiness_tone"] == "red"
    protocols = _workday_protocols(db, user.id)
    assert len(protocols) == 3
    assert all("俯卧撑" not in p.name for p in protocols)
    arrival = next(p for p in protocols if p.implied_quantity.get("slot") == "arrival")
    assert arrival.domain == "activity"
    assert arrival.implied_quantity["downgraded_from"] == "pushups"
    assert arrival.implied_quantity["readiness_tone"] == "red"


def test_training_decision_red_overrides_green_garmin_readiness(db, monkeypatch):
    user = _user(db)
    _readiness(db, user.id, 85)
    monkeypatch.setattr(
        scheduler.recovery_decision,
        "training_decision",
        lambda _db, _user_id: {
            "light": "red",
            "readiness_score": 85,
            "source": "training_decision",
            "next_action": "今天恢复/休息,暂停高强度",
            "reasons": ["急性训练负荷偏高", "多设备一致性 62%"],
        },
    )

    result = scheduler.generate_today(db, user.id)

    assert result["readiness_tone"] == "red"
    protocols = _workday_protocols(db, user.id)
    assert all("俯卧撑" not in p.name for p in protocols)
    assert all(p.implied_quantity["readiness_source"] == "training_decision" for p in protocols)


def test_generate_today_is_idempotent_for_same_workday_slots(db):
    user = _user(db)
    _readiness(db, user.id, 78)

    first = scheduler.generate_today(db, user.id)
    second = scheduler.generate_today(db, user.id)

    assert first["created"] == 3
    assert second["created"] == 0
    assert second["updated"] == 3
    protocols = _workday_protocols(db, user.id)
    assert len(protocols) == 3


def test_watch_workday_generate_api_requires_auth(client):
    assert client.post("/api/v1/watch/workday/generate").status_code == 401


def test_watch_workday_generate_api_creates_protocols(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    _readiness(db, user.id, 82)

    resp = client.post("/api/v1/watch/workday/generate", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["readiness_tone"] == "green"
    assert body["created"] == 3
    assert len(_workday_protocols(db, user.id)) == 3
