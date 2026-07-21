"""P1-B 事件前提醒 (scan_event_reminders) 测试。

覆盖:
  - 提前量窗口在 T−lead 命中一次并推送(med/supplement/movement)
  - 去重: 同项次扫描已推 → 不二次推
  - 稀缺门: can_notify_proactively=False → 不推
  - 会议标题进本人推送(隐私: 给本人设备可带标题)
  - fail-soft: 单用户失败不中断整批

用 conftest 内存 sqlite; mock push sender + proactive_coordinator + 时钟。
"""
from contextlib import contextmanager
from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

from app.models.calendar_sync import CalendarEvent, CalendarSource
from app.models.medication import Medication
from app.models.sent_event_reminder import SentEventReminder
from app.models.user import User

CHINA_DATE = datetime(2026, 6, 19)


def _make_user(db, uid=1):
    u = User(id=uid, email=f"u{uid}@t.com", username=f"u{uid}", hashed_password="x", name=f"用户{uid}")
    db.add(u)
    db.commit()
    return u


def _patched_now(hour, minute):
    """返回一个 get_china_now 替身,固定到 2026-06-19 hour:minute。"""
    return datetime(2026, 6, 19, hour, minute)


@contextmanager
def _session_cm(db):
    """模拟 SessionLocal() 上下文管理器,产出测试 db(不真正关闭)。"""
    yield db


def _run(db, *, now, schedule_items=None, can_notify=True, push_result=None):
    """跑 scan_event_reminders,统一注入 mock。返回 (result, push_mock)。"""
    push_instance = MagicMock()
    push_instance.send_notification.return_value = push_result or {"success": True}

    def fake_session():
        return _session_cm(db)

    with patch("app.tasks.event_reminders.SessionLocal", side_effect=fake_session), \
         patch("app.tasks.event_reminders.get_china_now", return_value=now), \
         patch("app.tasks.event_reminders.get_user_now", return_value=now), \
         patch("app.tasks.event_reminders.PushService", return_value=push_instance), \
         patch("app.tasks.event_reminders.run_async", side_effect=lambda c: c), \
         patch(
             "app.services.proactive_coordinator.can_notify_proactively",
             return_value=can_notify,
         ), \
         patch(
             "app.services.day_schedule_service.build_day_schedule",
             return_value={"scheduled": schedule_items or [], "rejected": [], "deferred": []},
         ):
        from app.tasks.event_reminders import scan_event_reminders
        result = scan_event_reminders()
    return result, push_instance


# ── 提前量窗口 ─────────────────────────────────────────────────────────────
def test_medication_fires_at_lead_window(db):
    """服药 lead=15: 项 09:00 → 08:45 推一次。"""
    _make_user(db)
    db.add(Medication(id=1, user_id=1, name="雷贝拉唑", category="处方药", is_active=True))
    db.commit()

    items = [{"id": "med:1", "title": "雷贝拉唑", "domain": "medication", "time": "09:00"}]
    result, push = _run(db, now=_patched_now(8, 45), schedule_items=items)

    assert result["sent"] == 1
    assert push.send_notification.call_count == 1
    # 占坑记账写了一行
    assert db.query(SentEventReminder).filter_by(user_id=1, item_key="med:1").count() == 1


def test_no_fire_outside_window(db):
    """不到 T−lead(08:44)不推。"""
    _make_user(db)
    db.add(Medication(id=1, user_id=1, name="药", category="处方药", is_active=True))
    db.commit()

    items = [{"id": "med:1", "title": "药", "domain": "medication", "time": "09:00"}]
    result, push = _run(db, now=_patched_now(8, 44), schedule_items=items)

    assert result["sent"] == 0
    assert push.send_notification.call_count == 0


def test_workout_lead_is_20min(db):
    """锻炼 lead=20: 18:00 → 17:40 推。"""
    _make_user(db)
    db.add(Medication(id=1, user_id=1, name="药", category="处方药", is_active=True))
    db.commit()

    items = [{"id": "workout:today", "title": "Z2 有氧 40 分钟", "domain": "movement", "time": "18:00"}]
    result, push = _run(db, now=_patched_now(17, 40), schedule_items=items)
    assert result["sent"] == 1


def test_diet_lead_zero_never_fires(db):
    """餐 lead=0: 不做事件前提醒(任何时刻都不推)。"""
    _make_user(db)
    db.add(Medication(id=1, user_id=1, name="药", category="处方药", is_active=True))
    db.commit()

    items = [{"id": "meal:lunch", "title": "午餐", "domain": "diet", "time": "12:00"}]
    # 即使 now 正好等于项时刻,也不推(lead=0)
    result, push = _run(db, now=_patched_now(12, 0), schedule_items=items)
    assert result["sent"] == 0


# ── 去重 ───────────────────────────────────────────────────────────────────
def test_dedup_no_second_push_same_day(db):
    """同 (user,item,date) 第二次扫描不再推。"""
    _make_user(db)
    db.add(Medication(id=1, user_id=1, name="药", category="处方药", is_active=True))
    db.commit()
    items = [{"id": "med:1", "title": "药", "domain": "medication", "time": "09:00"}]

    r1, p1 = _run(db, now=_patched_now(8, 45), schedule_items=items)
    assert r1["sent"] == 1

    # 模拟下一扫描(同窗口边界,beat 抖动)再跑一次 — 已占坑 → 不推
    r2, p2 = _run(db, now=_patched_now(8, 45), schedule_items=items)
    assert r2["sent"] == 0
    assert p2.send_notification.call_count == 0
    # 仍只有一行记账
    assert db.query(SentEventReminder).filter_by(user_id=1, item_key="med:1").count() == 1


def test_failed_push_releases_claim_and_can_retry_in_same_minute(db):
    _make_user(db)
    db.add(Medication(id=1, user_id=1, name="药", category="处方药", is_active=True))
    db.commit()
    items = [{"id": "med:1", "title": "药", "domain": "medication", "time": "09:00"}]

    failed, _ = _run(
        db,
        now=_patched_now(8, 45),
        schedule_items=items,
        push_result={"success": False, "reason": "没有可用的推送渠道"},
    )
    assert failed["sent"] == 0
    assert db.query(SentEventReminder).filter_by(user_id=1, item_key="med:1").count() == 0

    retried, push = _run(db, now=_patched_now(8, 45), schedule_items=items)
    assert retried["sent"] == 1
    assert push.send_notification.call_count == 1


# ── 稀缺门 ─────────────────────────────────────────────────────────────────
def test_scarcity_gate_blocks_push(db):
    """can_notify_proactively=False → 不推,也不占坑。"""
    _make_user(db)
    db.add(Medication(id=1, user_id=1, name="药", category="处方药", is_active=True))
    db.commit()
    items = [{"id": "med:1", "title": "药", "domain": "medication", "time": "09:00"}]

    result, push = _run(db, now=_patched_now(8, 45), schedule_items=items, can_notify=False)
    assert result["sent"] == 0
    assert push.send_notification.call_count == 0
    assert db.query(SentEventReminder).filter_by(user_id=1).count() == 0


# ── 会议标题进本人推送 ──────────────────────────────────────────────────────
def test_meeting_title_in_user_push(db):
    """会议 lead=10: 项 14:00 → 13:50 推,正文含标题(本人设备,非 LLM 路径)。"""
    _make_user(db)
    src = CalendarSource(id=1, user_id=1, name="我的日历", encrypted_credentials="x")
    db.add(src)
    db.commit()
    ev = CalendarEvent(
        id=1, user_id=1, source_id=1, uid="evt-1",
        start_time=datetime(2026, 6, 19, 14, 0),
        end_time=datetime(2026, 6, 19, 15, 0),
        all_day=False,
    )
    ev.set_title("产品评审会")
    db.add(ev)
    db.commit()

    # 无排程项,只有会议
    result, push = _run(db, now=_patched_now(13, 50), schedule_items=[])
    assert result["sent"] == 1
    args, kwargs = push.send_notification.call_args
    assert "产品评审会" in kwargs["content"]
    assert kwargs["data"]["kind"] == "meeting"


def test_meeting_uses_users_local_clock_for_aware_timestamp(db):
    from zoneinfo import ZoneInfo

    from app.tasks.event_reminders import _calendar_start_in_user_timezone

    local = _calendar_start_in_user_timezone(
        datetime(2026, 7, 20, 13, 0, tzinfo=UTC),
        ZoneInfo("America/New_York"),
    )
    assert local.date() == date(2026, 7, 20)
    assert (local.hour, local.minute) == (9, 0)


# ── fail-soft ──────────────────────────────────────────────────────────────
def test_fail_soft_one_user_failure_does_not_abort(db):
    """user 1 的排程构建抛错,user 2 仍能推。"""
    _make_user(db, uid=1)
    _make_user(db, uid=2)
    db.add(Medication(id=1, user_id=1, name="药1", category="处方药", is_active=True))
    db.add(Medication(id=2, user_id=2, name="药2", category="处方药", is_active=True))
    db.commit()

    items_for = {
        1: RuntimeError("boom"),
        2: [{"id": "med:2", "title": "药2", "domain": "medication", "time": "09:00"}],
    }

    def fake_build(_db, user_id, **kw):
        v = items_for[user_id]
        if isinstance(v, Exception):
            raise v
        return {"scheduled": v, "rejected": [], "deferred": []}

    push_instance = MagicMock()
    push_instance.send_notification.return_value = {"success": True}
    with patch("app.tasks.event_reminders.SessionLocal", side_effect=lambda: _session_cm(db)), \
         patch("app.tasks.event_reminders.get_china_now", return_value=_patched_now(8, 45)), \
         patch("app.tasks.event_reminders.get_user_now", return_value=_patched_now(8, 45)), \
         patch("app.tasks.event_reminders.PushService", return_value=push_instance), \
         patch("app.tasks.event_reminders.run_async", side_effect=lambda c: c), \
         patch("app.services.proactive_coordinator.can_notify_proactively", return_value=True), \
         patch("app.services.day_schedule_service.build_day_schedule", side_effect=fake_build):
        from app.tasks.event_reminders import scan_event_reminders
        result = scan_event_reminders()

    # user 1 炸了被吞,user 2 正常推
    assert result["sent"] == 1
    assert push_instance.send_notification.call_count == 1


# ── 常量回归(守 PRD 提前量) ───────────────────────────────────────────────
def test_lead_minutes_constants():
    from app.tasks.event_reminders import LEAD_MINUTES
    assert LEAD_MINUTES["meeting"] == 10
    assert LEAD_MINUTES["medication"] == 15
    assert LEAD_MINUTES["supplement"] == 15
    assert LEAD_MINUTES["movement"] == 20
    assert LEAD_MINUTES["diet"] == 0
    assert LEAD_MINUTES["sleep"] == 0


def test_protocol_collection_uses_the_users_local_day(db):
    from app.services import health_protocol_service as proto_svc
    from app.tasks.event_reminders import _collect_timed_items

    user = _make_user(db)
    protocol = proto_svc.create_water_cup_protocol(db, user.id)
    protocol.time_window = "morning"
    db.commit()
    local_day = date(2026, 7, 20)
    proto_svc.snooze_protocol(db, protocol.id, user.id, minutes=30, day=local_day)

    items = _collect_timed_items(db, user.id, local_day)

    assert all(item["item_key"] != f"protocol:{protocol.id}" for item in items)


def test_scanner_matches_each_users_local_clock(db):
    from app.tasks import event_reminders as er

    user = _make_user(db)
    push_instance = MagicMock()
    push_instance.send_notification.return_value = {"success": True}
    local_now = datetime(2026, 7, 20, 8, 0)
    item = {
        "item_key": "protocol:1",
        "kind": "protocol",
        "title": "晨间行动",
        "start_min": 8 * 60,
        "lead": 0,
        "complete_ref": {"object_type": "health_protocol", "object_id": 1},
    }

    with patch("app.tasks.event_reminders.SessionLocal", side_effect=lambda: _session_cm(db)), \
         patch("app.tasks.event_reminders.get_china_now", return_value=datetime(2026, 7, 20, 20, 0)), \
         patch("app.tasks.event_reminders.get_user_now", return_value=local_now), \
         patch("app.tasks.event_reminders._candidate_user_ids", return_value=[user.id]), \
         patch("app.tasks.event_reminders._collect_timed_items", return_value=[item]), \
         patch("app.tasks.event_reminders._protocol_throttled", return_value=False), \
         patch("app.tasks.event_reminders.PushService", return_value=push_instance), \
         patch("app.tasks.event_reminders.run_async", side_effect=lambda c: c), \
         patch("app.services.proactive_coordinator.can_notify_proactively", return_value=True), \
         patch("app.agents.audit.log_proactive_trigger"):
        result = er.scan_event_reminders()

    assert result["sent"] == 1
    assert db.query(SentEventReminder).one().remind_date == local_now.date()
