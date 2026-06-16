"""Apple Watch 腕上摘要(W1)。

钉:状态灯/headline 来自训练项、top_action 取最高优先级 pending 协议、push 分级(逾期复查 P0、
其余 P1)+ 限 3 条、quick_actions 目录齐、API 走通 + 鉴权。
用 monkeypatch 注入 agenda.today,纯映射逻辑确定性可测。
"""
import uuid

import pytest

import app.services.watch_summary as ws
from app.models.user import User


@pytest.fixture
def auth(client, db):
    user = User(username=f"w_{uuid.uuid4().hex[:6]}", email=f"w_{uuid.uuid4().hex[:6]}@x.com",
                hashed_password="x", name="w", is_active=True, is_approved=True)
    db.add(user); db.commit(); db.refresh(user)
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


def test_top_action_is_highest_priority_pending(db, auth, monkeypatch):
    user, _ = auth
    items = [_protocol("喝水", priority=50), _protocol("吃药", priority=80, domain="medication")]
    monkeypatch.setattr(ws.agenda_service, "today", lambda d, u, **k: _agenda(items))
    s = ws.build_watch_summary(db, user.id)
    assert s["top_action"]["title"] == "吃药"          # 80 > 50
    assert s["agenda"]["pending"] == 2


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
