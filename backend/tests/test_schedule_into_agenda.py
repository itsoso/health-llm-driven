"""cut 6:timing-solver 当日锻炼块接进 agenda → 手表 due_items/top_action 可见。"""
import uuid

import pytest

import app.services.watch_summary as ws
from app.models.user import User
from app.models.user_profile import UserProfile
from app.services import agenda_service


@pytest.fixture
def user(db):
    u = User(username=f"a_{uuid.uuid4().hex[:6]}", email=f"a_{uuid.uuid4().hex[:6]}@x.com",
             hashed_password="x", name="a", is_active=True, is_approved=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _profile(db, user_id, **kw):
    base = dict(user_id=user_id, usual_wake_time="07:00", usual_sleep_time="22:30",
                work_start_time="09:00", work_end_time="18:00",
                workout_pref_window="evening", workout_target_minutes=45)
    base.update(kw)
    p = UserProfile(**base)
    db.add(p)
    db.commit()
    return p


# ── agenda 集成 ───────────────────────────────────────────────────────
def test_agenda_includes_workout_when_pref_set(db, user):
    _profile(db, user.id)
    agenda = agenda_service.today(db, user.id)
    wk = [i for i in agenda["items"]
          if (i.get("source") or {}).get("object_type") == "day_schedule_workout"]
    assert len(wk) == 1
    assert wk[0]["type"] == "movement"
    assert wk[0]["status"] == "pending"
    assert wk[0].get("time")  # solver 求解的精确时点


def test_agenda_no_workout_without_pref(db, user):
    _profile(db, user.id, workout_pref_window=None)
    agenda = agenda_service.today(db, user.id)
    assert not any((i.get("source") or {}).get("object_type") == "day_schedule_workout"
                   for i in agenda["items"])


def test_agenda_survives_when_no_profile(db, user):
    # 无 profile → 不求解、不炸,agenda 正常返回(无锻炼项)。
    agenda = agenda_service.today(db, user.id)
    assert "items" in agenda
    assert not any((i.get("source") or {}).get("object_type") == "day_schedule_workout"
                   for i in agenda["items"])


# ── watch_summary 映射(monkeypatch 注入 agenda)────────────────────────
def _agenda(items):
    return {"agenda_date": "2026-06-17", "count": len(items), "items": items}


def _workout_item(status="pending", **kw):
    base = dict(type="movement", title="锻炼 45 分钟", status=status, time="19:30",
                time_window="evening", priority=55,
                source={"object_type": "day_schedule_workout", "object_id": 1})
    base.update(kw)
    return base


def _runtime(items):
    """build_watch_summary 现读 runtime_range_view(rolling runtime),不再读 today;
    它从 days[].time_windows[].items[] 取项。模拟该投影 shape(boundary mock,同 test_watch_actions/test_inline_cards)。"""
    first = items[0] if items else None
    return {
        "mode": "runtime",
        "next_action": first,
        "days": [
            {"date": "2026-06-17", "next_action": first,
             "time_windows": [{"label": "evening", "items": items}]},
        ],
    }


def test_watch_due_items_include_workout(db, user, monkeypatch):
    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", lambda d, u, **k: _runtime([_workout_item()]))
    s = ws.build_watch_summary(db, user.id)
    kinds = [d["kind"] for d in s["due_items"]]
    assert "movement" in kinds
    assert s["top_action"] is not None
    assert s["top_action"]["kind"] == "movement"


def test_watch_workout_push_tier_is_p1():
    # 锻炼块够格推到手腕(P1);实际是否推还受 proactive_coordinator 预算门控(R15)。
    assert ws._push_tier(_workout_item()) == "P1"
    assert ws._push_tier(_workout_item(status="info")) is None  # 休息项不推


def test_watch_rest_day_workout_not_actionable(db, user, monkeypatch):
    # Red 休息项 status=info → 不进 due_items(非待打点)。
    rest = _workout_item(status="info", title="锻炼", time=None)
    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", lambda d, u, **k: _runtime([rest]))
    s = ws.build_watch_summary(db, user.id)
    assert not any(d["kind"] == "movement" for d in s["due_items"])


def test_workout_is_exercise_nudge_for_critical_suppression():
    # 锻炼块算运动行为 nudge → critical 安全信号活跃时被 _can_include_push 压制。
    assert ws._is_exercise_behavior_nudge(_workout_item()) is True


def test_workout_push_suppressed_when_critical_active(db, user, monkeypatch):
    monkeypatch.setattr(ws.agenda_service, "runtime_range_view", lambda d, u, **k: _runtime([_workout_item()]))
    monkeypatch.setattr(ws, "_has_active_critical_safety", lambda d, u: True)
    monkeypatch.setattr(ws.proactive_coordinator, "can_notify_proactively", lambda *a, **k: True)
    s = ws.build_watch_summary(db, user.id)
    assert not any("锻炼" in (p.get("title") or "") for p in s["push_items"])
