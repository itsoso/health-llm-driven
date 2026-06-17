"""Apple Watch 腕上摘要(W1)。

钉:状态灯/headline 来自训练项、top_action 取最高优先级 pending 协议、push 分级(逾期复查 P0、
其余 P1)+ 限 3 条、quick_actions 目录齐、API 走通 + 鉴权。
用 monkeypatch 注入 agenda.today,纯映射逻辑确定性可测。
"""
import uuid
from datetime import date, timedelta

import pytest

import app.services.watch_summary as ws
from app.models.daily_health import GarminData
from app.models.user import User


@pytest.fixture
def auth(client, db):
    user = User(username=f"w_{uuid.uuid4().hex[:6]}", email=f"w_{uuid.uuid4().hex[:6]}@x.com",
                hashed_password="x", name="w", is_active=True, is_approved=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    from app.services.auth import auth_service
    return user, {"Authorization": f"Bearer {auth_service.create_access_token({'sub': str(user.id)})}"}


def _agenda(items):
    return {"agenda_date": "2026-06-16", "count": len(items), "items": items}


def _protocol(title, status="pending", priority=50, domain="hydration"):
    return {"type": domain, "title": title, "status": status, "priority": priority,
            "time_window": "anytime", "source": {"object_type": "health_protocol", "object_id": 1}}


def test_status_light_and_headline_from_training(db, auth, monkeypatch):
    user, _ = auth
    items = [{"type": "training", "title": "今日训练", "status": "info", "light": "red",
              "readiness_score": 40, "source": {"object_type": "training_decision", "object_id": user.id}}]
    monkeypatch.setattr(ws.agenda_service, "today", lambda d, u, **k: _agenda(items))
    s = ws.build_watch_summary(db, user.id)
    assert s["status"]["light"] == "red"
    assert s["status"]["readiness_score"] == 40
    assert "休息" in s["status"]["headline"]


def test_status_freshness_marks_old_wearable_data_stale(db, auth, monkeypatch):
    user, _ = auth
    old_date = date.today() - timedelta(days=2)
    db.add(GarminData(
        user_id=user.id,
        record_date=old_date,
        data_source="apple-watch",
        training_readiness_score=68,
    ))
    db.commit()
    items = [{"type": "training", "title": "今日训练", "status": "info", "light": "green",
              "readiness_score": 68, "source": {"object_type": "training_decision", "object_id": user.id}}]
    monkeypatch.setattr(ws.agenda_service, "today", lambda d, u, **k: _agenda(items))

    s = ws.build_watch_summary(db, user.id)

    freshness = s["status"]["freshness"]
    assert freshness["state"] == "stale"
    assert freshness["latest_date"] == old_date.isoformat()
    assert freshness["age_days"] >= 2
    assert "偏旧" in freshness["label"]


def test_status_freshness_missing_without_wearable_data(db, auth, monkeypatch):
    user, _ = auth
    monkeypatch.setattr(ws.agenda_service, "today", lambda d, u, **k: _agenda([]))

    s = ws.build_watch_summary(db, user.id)

    freshness = s["status"]["freshness"]
    assert freshness["state"] == "missing"
    assert freshness["latest_date"] is None
    assert freshness["age_days"] is None
    assert "待同步" in freshness["label"]


def test_top_action_is_highest_priority_pending(db, auth, monkeypatch):
    user, _ = auth
    items = [_protocol("喝水", priority=50), _protocol("吃药", priority=80, domain="medication")]
    monkeypatch.setattr(ws.agenda_service, "today", lambda d, u, **k: _agenda(items))
    s = ws.build_watch_summary(db, user.id)
    assert s["top_action"]["title"] == "吃药"          # 80 > 50
    assert s["top_action"]["priority_tier"] == "P1"
    assert s["top_action"]["verification_window_days"] == 28
    assert s["top_action"]["leverage_score"] > 0
    assert "依从" in s["top_action"]["rationale_short"]
    assert s["agenda"]["pending"] == 2


def test_training_protocol_can_be_top_action_for_watch_micro_movement(db, auth, monkeypatch):
    """训练类 health_protocol 是 Watch-first 工作日微运动的执行对象。"""
    user, _ = auth
    item = _protocol("到公司后俯卧撑 12 个", priority=80, domain="training")
    item["source"]["object_id"] = 7
    monkeypatch.setattr(ws.agenda_service, "today", lambda d, u, **k: _agenda([item]))

    s = ws.build_watch_summary(db, user.id)

    assert s["top_action"]["title"] == "到公司后俯卧撑 12 个"
    assert s["top_action"]["kind"] == "training"
    assert s["top_action"]["action_id"] == "agenda-health_protocol-7"
    assert s["top_action"]["source"]["object_type"] == "health_protocol"
    assert s["top_action"]["priority_tier"] == "P2"
    assert s["top_action"]["leverage_score"] > 0
    assert s["agenda"]["pending"] == 1


def test_due_items_preserve_source_for_watch_completion(db, auth, monkeypatch):
    """Watch due item 需要 source 才能判定 health_protocol 可一键完成。"""
    user, _ = auth
    items = [
        _protocol("吃药", priority=80, domain="medication"),
        _protocol("到公司后俯卧撑 12 个", priority=70, domain="training"),
    ]
    items[0]["source"]["object_id"] = 7
    items[1]["source"]["object_id"] = 8
    monkeypatch.setattr(ws.agenda_service, "today", lambda d, u, **k: _agenda(items))

    s = ws.build_watch_summary(db, user.id)

    by_title = {i["title"]: i for i in s["due_items"]}
    assert by_title["吃药"]["action_id"] == "agenda-health_protocol-7"
    assert by_title["吃药"]["source"] == {"object_type": "health_protocol", "object_id": 7}
    assert by_title["到公司后俯卧撑 12 个"]["source"] == {
        "object_type": "health_protocol",
        "object_id": 8,
    }


def test_push_tiering_and_cap(db, auth, monkeypatch):
    user, _ = auth
    items = [
        {"type": "checkup", "title": "复查:胃溃疡", "status": "overdue", "priority": 95,
         "source": {"object_type": "health_problem", "object_id": 1}},
        {"type": "training", "title": "今日训练", "status": "info", "light": "red",
         "source": {"object_type": "training_decision", "object_id": user.id}},
        {"type": "correction", "title": "协议待调整", "status": "info",
         "source": {"object_type": "health_protocol", "object_id": 2}},
        _protocol("吃药", domain="medication"),
    ]
    monkeypatch.setattr(ws.agenda_service, "today", lambda d, u, **k: _agenda(items))
    s = ws.build_watch_summary(db, user.id)
    assert len(s["push_items"]) <= 3
    assert s["push_items"][0]["tier"] == "P0"          # 逾期复查排首
    assert s["push_items"][0]["kind"] == "checkup"
    assert all(p["tier"] in ("P0", "P1") for p in s["push_items"])


def test_no_training_defaults_gray(db, auth, monkeypatch):
    user, _ = auth
    monkeypatch.setattr(ws.agenda_service, "today", lambda d, u, **k: _agenda([]))
    s = ws.build_watch_summary(db, user.id)
    assert s["status"]["light"] == "gray"
    assert s["top_action"] is None
    assert s["push_items"] == []


def test_quick_actions_catalog_present(db, auth, monkeypatch):
    user, _ = auth
    monkeypatch.setattr(ws.agenda_service, "today", lambda d, u, **k: _agenda([]))
    kinds = {a["kind"] for a in ws.build_watch_summary(db, user.id)["quick_actions"]}
    assert {"water", "supplement", "exercise", "diet_voice"} <= kinds


def test_api_watch_summary(client, auth):
    _, headers = auth
    r = client.get("/api/v1/watch/summary", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "status" in body and "quick_actions" in body and "push_items" in body


def test_api_watch_summary_requires_auth(client):
    assert client.get("/api/v1/watch/summary").status_code == 401
