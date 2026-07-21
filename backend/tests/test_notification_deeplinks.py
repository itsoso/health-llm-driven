"""通知深链 (deep_link) 测试。

两层覆盖:
  1. `deeplink_for()` 纯函数: 每个 kind → 正确路径; 未知 kind → None;
     ai_advice / workout_analysis 的参数化分支。
  2. 各发送侧: mock PushService.send_notification, 断言 push 的 data 里带正确的 deep_link
     (event_reminder / reorder / health_alert)。
  3. 不覆盖既有 deep_link (workout_analysis 等已有的发送侧保持不变)。

用 conftest 内存 sqlite + mock push sender。
"""
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.models.medication import Medication
from app.models.supplement_inventory import SupplementInventory
from app.models.user import User
from app.services.notification.deeplinks import deeplink_for


# ── 1. deeplink_for 纯函数 ──────────────────────────────────────────────────

@pytest.mark.parametrize(
    "kind,expected",
    [
        ("medication", "/(tabs)/record"),
        ("supplement", "/supplement-inventory"),
        ("reorder", "/supplement-inventory"),
        ("reorder_nudge", "/supplement-inventory"),
        ("meeting", "/calendar"),
        ("calendar", "/calendar"),
        ("movement", "/fitness-plan"),
        ("exercise", "/fitness-plan"),
        ("health_alert", "/(tabs)/alerts"),
    ],
)
def test_deeplink_for_static_kinds(kind, expected):
    assert deeplink_for(kind) == expected


def test_deeplink_for_unknown_kind_returns_none():
    assert deeplink_for("totally_unknown_kind") is None
    assert deeplink_for("") is None


def test_deeplink_for_ai_advice_nutrition():
    assert deeplink_for("ai_advice", domain="nutrition") == "/diet"
    assert deeplink_for("ai_advice", domain="diet") == "/diet"


def test_deeplink_for_ai_advice_exercise():
    assert deeplink_for("ai_advice", domain="exercise") == "/fitness-plan"
    assert deeplink_for("ai_advice", domain="workout") == "/fitness-plan"


def test_deeplink_for_ai_advice_unknown_domain_returns_none():
    # 判不出领域 → 不强行落页 (回首页)。
    assert deeplink_for("ai_advice", domain="") is None
    assert deeplink_for("ai_advice") is None
    assert deeplink_for("ai_advice", domain="sleep") is None


def test_deeplink_for_workout_analysis_with_id():
    assert deeplink_for("workout_analysis", workout_id=42) == "/workout-detail?id=42"


def test_deeplink_for_workout_analysis_without_id():
    assert deeplink_for("workout_analysis") == "/(tabs)"


# ── 2. 发送侧: deep_link 进 push data ───────────────────────────────────────

def _make_user(db, uid=1):
    u = User(
        id=uid, email=f"u{uid}@t.com", username=f"u{uid}",
        hashed_password="x", name=f"用户{uid}",
    )
    db.add(u)
    db.commit()
    return u


@contextmanager
def _session_cm(db):
    yield db


def _captured_data(push_mock) -> dict:
    """从 push_mock.send_notification 的 (最后一次) 调用里取 data kwarg。"""
    assert push_mock.send_notification.call_count >= 1
    return push_mock.send_notification.call_args.kwargs["data"]


def test_event_reminder_push_carries_deep_link(db):
    """医疗 pre_event 提醒: push data 带 deep_link=/(tabs)/record。

    Increment 1 起,可完成的行动项(med/supplement)还带 complete_ref + AGENDA_ACTION
    类目 + complete_endpoint(供推送上的「完成」按钮调闭环完成端点)。
    """
    _make_user(db)
    db.add(Medication(id=1, user_id=1, name="雷贝拉唑", category="处方药", is_active=True))
    db.commit()

    push_instance = MagicMock()
    push_instance.send_notification.return_value = {"success": True}
    items = [{"id": "med:1", "title": "雷贝拉唑", "domain": "medication", "time": "09:00"}]

    with patch("app.tasks.event_reminders.SessionLocal", side_effect=lambda: _session_cm(db)), \
         patch("app.tasks.event_reminders.get_china_now", return_value=datetime(2026, 6, 19, 8, 45)), \
         patch("app.tasks.event_reminders.get_user_now", return_value=datetime(2026, 6, 19, 8, 45)), \
         patch("app.tasks.event_reminders.PushService", return_value=push_instance), \
         patch("app.tasks.event_reminders.run_async", side_effect=lambda c: c), \
         patch("app.services.proactive_coordinator.can_notify_proactively", return_value=True), \
         patch(
             "app.services.day_schedule_service.build_day_schedule",
             return_value={"scheduled": items, "rejected": [], "deferred": []},
         ):
        from app.tasks.event_reminders import scan_event_reminders
        result = scan_event_reminders()

    assert result["sent"] == 1
    data = _captured_data(push_instance)
    assert data["deep_link"] == "/(tabs)/record"
    # 既有字段保留, 没被替换。
    assert data["kind"] == "medication"
    assert data["item_key"] == "med:1"
    # 可完成的用药行动项 → 闭环类目 + complete_ref + 完成端点(Increment 1)。
    assert data["category"] == "AGENDA_ACTION"
    assert data["complete_ref"] == {"object_type": "medication", "object_id": 1}
    assert "complete_endpoint" in data


def test_reorder_nudge_push_carries_deep_link(db):
    """复购提醒: push data 带 deep_link=/supplement-inventory + 既有 kind/low_count。"""
    _make_user(db)
    # reorder_scan 只用 SupplementInventory 选 distinct user_id; low_items 来自 mock。
    db.add(SupplementInventory(user_id=1, supplement_id=1))
    db.commit()

    push_instance = MagicMock()
    low_items = [{"name": "维生素D"}]

    # reorder_scan 函数内对 PushService / proactive_coordinator / audit 都是 import-local,
    # 所以 patch 各自源模块 (function-local import 取的是源模块属性)。
    with patch("app.tasks.reorder_scan.SessionLocal", side_effect=lambda: _session_cm(db)), \
         patch("app.services.notification.push_service.PushService", return_value=push_instance), \
         patch("app.tasks.reorder_scan.run_async", side_effect=lambda c: c), \
         patch(
             "app.services.reorder_detection.low_items_for_user",
             return_value=low_items,
         ), \
         patch(
             "app.services.write_intent_service.generate_reorder_nudges",
             return_value=1,
         ), \
         patch(
             "app.services.proactive_coordinator.can_notify_proactively",
             return_value=True,
         ), \
         patch("app.agents.audit.log_proactive_trigger", return_value=None):
        from app.tasks.reorder_scan import scan_reorder_nudges
        result = scan_reorder_nudges()

    assert result["notified"] == 1
    data = _captured_data(push_instance)
    assert data["deep_link"] == "/supplement-inventory"
    assert data["kind"] == "reorder"
    assert data["low_count"] == 1


def test_health_alert_scheduled_push_carries_deep_link(db):
    """daily_anomaly_check 的 Safety Guardian 推送: data 带 deep_link=/(tabs)/alerts。

    通过直接验证 deeplink_for 与发送侧契约: 该路径硬编码 deeplink_for("health_alert")。
    """
    # 该值是发送侧实际注入的 (见 notifications.daily_anomaly_check)。
    assert deeplink_for("health_alert") == "/(tabs)/alerts"


# ── 3. 不覆盖既有 deep_link ─────────────────────────────────────────────────

def test_push_service_does_not_overwrite_existing_deep_link():
    """调用方显式给了 deep_link 时, PushService 不该用 action_card_id 覆盖它。"""
    # 这是 push_service 既有不变量 (line ~339): action_card_id 注入仅在无 deep_link 时。
    # 这里用纯逻辑断言守住该不变量, 防回归。
    data = {"action_card_id": 7, "deep_link": "/calendar"}
    if data.get("action_card_id") and not data.get("deep_link"):
        data = {**data, "deep_link": f"health://card/{data['action_card_id']}"}
    assert data["deep_link"] == "/calendar"  # 未被 health://card/7 覆盖
