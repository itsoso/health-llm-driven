"""Apple Watch 腕上摘要(W1)。

钉:状态灯/headline 来自训练项、top_action 取最高优先级 pending 协议、push 分级(逾期复查 P0、
其余 P1)+ 限 3 条、quick_actions 目录齐、API 走通 + 鉴权。
用 monkeypatch 注入 agenda.runtime_range_view,纯映射逻辑确定性可测。
"""
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

import app.services.watch_summary as ws
from app.models.agent_audit_log import AgentAuditLog
from app.models.daily_health import GarminData
from app.models.health_protocol import HealthProtocol, HealthProtocolEvent
from app.models.smart_reminder import SmartReminder
from app.models.user import User
from app.utils.timezone import get_user_now


@pytest.fixture
def auth(client, db):
    user = User(username=f"w_{uuid.uuid4().hex[:6]}", email=f"w_{uuid.uuid4().hex[:6]}@x.com",
                hashed_password="x", name="w", is_active=True, is_approved=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    from app.services.auth import auth_service
    return user, {"Authorization": f"Bearer {auth_service.create_access_token({'sub': str(user.id)})}"}


def _runtime_projection(items):
    return {
        "start": "2026-06-16",
        "end": "2026-06-16",
        "mode": "runtime",
        "generated_by": "rolling_health_runtime_v1",
        "horizon_days": 1,
        "next_action": items[0] if items else None,
        "runtime_context": {"safety_boundary": "这是健康管理行动建议, 不替代医生诊断。"},
        "days": [
            {
                "date": "2026-06-16",
                "next_action": items[0] if items else None,
                "time_windows": [{"label": "anytime", "items": items}],
            }
        ],
    }


def _protocol(title, status="pending", priority=50, domain="hydration"):
    return {"type": domain, "title": title, "status": status, "priority": priority,
            "time_window": "anytime", "source": {"object_type": "health_protocol", "object_id": 1}}


def test_status_light_and_headline_from_training(db, auth, monkeypatch):
    user, _ = auth
    items = [{"type": "training", "title": "今日训练", "status": "info", "light": "red",
              "readiness_score": 40, "source": {"object_type": "training_decision", "object_id": user.id}}]
    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", lambda d, u, days=1, max_items_per_day=3: _runtime_projection(items))
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
    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", lambda d, u, days=1, max_items_per_day=3: _runtime_projection(items))

    s = ws.build_watch_summary(db, user.id)

    freshness = s["status"]["freshness"]
    assert freshness["state"] == "stale"
    assert freshness["latest_date"] == old_date.isoformat()
    assert freshness["age_days"] >= 2
    assert "偏旧" in freshness["label"]


def test_status_freshness_missing_without_wearable_data(db, auth, monkeypatch):
    user, _ = auth
    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", lambda d, u, days=1, max_items_per_day=3: _runtime_projection([]))

    s = ws.build_watch_summary(db, user.id)

    freshness = s["status"]["freshness"]
    assert freshness["state"] == "missing"
    assert freshness["latest_date"] is None
    assert freshness["age_days"] is None
    assert "待同步" in freshness["label"]


def test_top_action_is_highest_priority_pending(db, auth, monkeypatch):
    user, _ = auth
    items = [_protocol("喝水", priority=50), _protocol("吃药", priority=80, domain="medication")]
    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", lambda d, u, days=1, max_items_per_day=3: _runtime_projection(items))
    s = ws.build_watch_summary(db, user.id)
    assert s["top_action"]["title"] == "吃药"          # 80 > 50
    assert s["top_action"]["priority_tier"] == "P1"
    assert s["top_action"]["verification_window_days"] == 28
    assert s["top_action"]["leverage_score"] > 0
    assert "依从" in s["top_action"]["rationale_short"]
    assert s["agenda"]["pending"] == 2


def test_top_action_preserves_trajectory_context_for_watch(db, auth, monkeypatch):
    user, _ = auth
    item = _protocol("累计 35-45 分钟中等强度活动", priority=65, domain="movement")
    item["trajectory_context"] = {
        "domain": "metabolic_health",
        "level": "attention",
        "state_variable": "waist_cm",
        "horizon": "upstream_90d",
        "why": "腰围和血压提示代谢轨迹需要关注。",
        "confidence": "high",
        "verification_window_days": 7,
        "verification_signal": "waist_cm",
    }
    item["target_state_variable"] = "waist_cm"
    item["verification_signal"] = "waist_cm"
    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", lambda d, u, days=1, max_items_per_day=3: _runtime_projection([item]))

    s = ws.build_watch_summary(db, user.id)

    assert s["top_action"]["trajectory_context"]["state_variable"] == "waist_cm"
    assert s["top_action"]["target_state_variable"] == "waist_cm"
    assert s["top_action"]["verification_signal"] == "waist_cm"


def test_watch_summary_uses_runtime_projection_contract(db, auth, monkeypatch):
    user, _ = auth
    item = _protocol("晚餐后步行 15 分钟", priority=80, domain="movement")
    item["runtime_context"] = {
        "current_state_summary": "晚餐后是今天最短的代谢干预窗口。",
        "replan_reason": "today_smart_rank",
        "safety_boundary": "这是健康管理行动建议, 不替代医生诊断。",
        "verification_window": {
            "metrics": ["post_meal_walk_completed", "waist_cm"],
            "window_days": 7,
        },
    }
    calls = {}

    def fake_runtime_range_view(db_arg, user_id, days=1, max_items_per_day=3):
        calls["user_id"] = user_id
        calls["days"] = days
        calls["max_items_per_day"] = max_items_per_day
        return _runtime_projection([item])

    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", fake_runtime_range_view)

    s = ws.build_watch_summary(db, user.id)

    assert calls == {"user_id": user.id, "days": 1, "max_items_per_day": 3}
    assert s["runtime"]["generated_by"] == "rolling_health_runtime_v1"
    assert s["runtime"]["horizon_days"] == 1
    assert s["top_action"]["runtime_context"]["replan_reason"] == "today_smart_rank"
    assert s["top_action"]["runtime_context"]["verification_window"]["metrics"] == [
        "post_meal_walk_completed",
        "waist_cm",
    ]


def test_training_protocol_can_be_top_action_for_watch_micro_movement(db, auth, monkeypatch):
    """训练类 health_protocol 是 Watch-first 工作日微运动的执行对象。"""
    user, _ = auth
    item = _protocol("到公司后俯卧撑 12 个", priority=80, domain="training")
    item["source"]["object_id"] = 7
    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", lambda d, u, days=1, max_items_per_day=3: _runtime_projection([item]))

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
    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", lambda d, u, days=1, max_items_per_day=3: _runtime_projection(items))

    s = ws.build_watch_summary(db, user.id)

    by_title = {i["title"]: i for i in s["due_items"]}
    assert by_title["吃药"]["action_id"] == "agenda-health_protocol-7"
    assert by_title["吃药"]["source"] == {"object_type": "health_protocol", "object_id": 7}
    assert by_title["到公司后俯卧撑 12 个"]["source"] == {
        "object_type": "health_protocol",
        "object_id": 8,
    }


def test_agent_water_reminder_enters_watch_due_items(db, auth, monkeypatch):
    """Agent 创建的饮水提醒应进入 Watch 动态任务流,而不是只停在手机推送文案。"""
    user, _ = auth
    now = get_user_now(db, user.id)
    reminder = SmartReminder(
        user_id=user.id,
        title="定时饮水提醒",
        message="喝 200ml 水",
        remind_at=now + timedelta(minutes=10),
        recurrence="daily",
        priority="normal",
        status="pending",
        source="agent_skill",
        extra_data={"watch_kind": "hydration"},
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    monkeypatch.setattr(
        ws.agenda_service,
        "runtime_range_view",
        lambda d, u, days=1, max_items_per_day=3: _runtime_projection([]),
    )

    s = ws.build_watch_summary(db, user.id)

    by_title = {i["title"]: i for i in s["due_items"]}
    item = by_title["定时饮水提醒"]
    assert item["kind"] == "hydration"
    assert item["action_id"] == f"agenda-smart_reminder-{reminder.id}"
    assert item["source"] == {"object_type": "smart_reminder", "object_id": reminder.id}
    assert item["delivery_status"]["watch"]["route"] == "watch_summary_due_item"
    assert item["delivery_status"]["watch"]["delivery_confirmed"] is False
    assert any(p["source"]["object_type"] == "smart_reminder" for p in s["push_items"])


def test_smart_reminder_delivery_confirmed_after_watch_visible_event(db, auth, monkeypatch):
    """Watch 摘要刷新到具体提醒后,下一次摘要应带已看见 receipt."""
    from app.models.client_event import ClientEvent

    user, _ = auth
    now = get_user_now(db, user.id)
    reminder = SmartReminder(
        user_id=user.id,
        title="定时饮水提醒",
        message="喝 200ml 水",
        remind_at=now + timedelta(minutes=10),
        recurrence="daily",
        priority="normal",
        status="pending",
        source="agent_skill",
        extra_data={"watch_kind": "hydration"},
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    db.add(ClientEvent(
        user_id=user.id,
        event_name="watch_smart_reminder_visible",
        meta={
            "action_id": f"agenda-smart_reminder-{reminder.id}",
            "reminder_id": str(reminder.id),
            "kind": "hydration",
            "surface": "watch_summary",
        },
        created_at=now,
    ))
    db.commit()
    monkeypatch.setattr(
        ws.agenda_service,
        "runtime_range_view",
        lambda d, u, days=1, max_items_per_day=3: _runtime_projection([]),
    )

    summary = ws.build_watch_summary(db, user.id)

    item = next(i for i in summary["due_items"] if i["source"]["object_id"] == reminder.id)
    watch_status = item["delivery_status"]["watch"]
    assert watch_status["delivery_confirmed"] is True
    assert watch_status["status"] == "visible_on_watch_summary"
    assert watch_status["receipt_event_id"]
    assert watch_status["confirmed_at"]


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
    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", lambda d, u, days=1, max_items_per_day=3: _runtime_projection(items))
    s = ws.build_watch_summary(db, user.id)
    assert len(s["push_items"]) <= 3
    assert s["push_items"][0]["tier"] == "P0"          # 逾期复查排首
    assert s["push_items"][0]["kind"] == "checkup"
    assert all(p["tier"] in ("P0", "P1") for p in s["push_items"])


def test_medication_watch_nudge_survives_quiet_budget_gate(db, auth, monkeypatch):
    """用药执行提醒不是普通行为 nudge,不能被静默时段/预算 gate 吞掉。"""
    user, _ = auth
    item = _protocol("二甲双胍 0.5g", priority=90, domain="medication")
    item["source"]["object_id"] = 11
    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", lambda d, u, days=1, max_items_per_day=3: _runtime_projection([item]))
    monkeypatch.setattr(ws.proactive_coordinator, "can_notify_proactively", lambda *a, **k: False)

    s = ws.build_watch_summary(db, user.id)

    assert [p["title"] for p in s["push_items"]] == ["二甲双胍 0.5g"]


def test_recent_too_tired_skip_suppresses_exercise_watch_nudge(db, auth, monkeypatch):
    """连续失败是系统信号:近期 too_tired/unwell/too_hard 跳过后,运动 nudge 先降噪。"""
    user, _ = auth
    protocol = HealthProtocol(
        user_id=user.id,
        domain="exercise",
        name="餐后轻松步行 20 分钟",
        status="active",
    )
    db.add(protocol)
    db.flush()
    db.add(HealthProtocolEvent(
        user_id=user.id,
        protocol_id=protocol.id,
        event_date=date.today() - timedelta(days=1),
        status="skipped",
        track="protocol",
        skip_reason="too_tired",
    ))
    db.commit()

    item = _protocol("餐后轻松步行 20 分钟", priority=70, domain="exercise")
    item["source"]["object_id"] = protocol.id
    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", lambda d, u, days=1, max_items_per_day=3: _runtime_projection([item]))
    monkeypatch.setattr(ws.proactive_coordinator, "can_notify_proactively", lambda *a, **k: True)

    s = ws.build_watch_summary(db, user.id)

    assert s["push_items"] == []


def test_exercise_watch_nudge_daily_cap_suppresses_extra_push(db, auth, monkeypatch):
    user, _ = auth
    for idx in range(3):
        db.add(AgentAuditLog(
            user_id=user.id,
            agent_type="watch_nudge",
            action="proactive_trigger",
            result_summary=f"exercise nudge {idx}",
            result_detail={"notified": True, "tier": "P1", "kind": "exercise"},
            created_at=datetime.now(UTC),
        ))
    db.commit()

    item = _protocol("下午站立拉伸", priority=60, domain="exercise")
    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", lambda d, u, days=1, max_items_per_day=3: _runtime_projection([item]))
    monkeypatch.setattr(ws.proactive_coordinator, "can_notify_proactively", lambda *a, **k: True)

    s = ws.build_watch_summary(db, user.id)

    assert s["push_items"] == []


def test_no_training_defaults_gray(db, auth, monkeypatch):
    user, _ = auth
    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", lambda d, u, days=1, max_items_per_day=3: _runtime_projection([]))
    s = ws.build_watch_summary(db, user.id)
    assert s["status"]["light"] == "gray"
    assert s["top_action"] is None
    assert s["push_items"] == []


def test_quick_actions_catalog_present(db, auth, monkeypatch):
    user, _ = auth
    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", lambda d, u, days=1, max_items_per_day=3: _runtime_projection([]))
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
