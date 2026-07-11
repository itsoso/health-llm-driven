# -*- coding: utf-8 -*-
"""情境心跳(Slice 2, v1 零 LLM)回归。

钉:
- 4 条确定性规则各有正反例;
- `evaluate_heartbeat` 逐规则 fail-loud —— 一条抛错计入 failed_rules 且其余照跑;
- 白天窗 [08,22),夜间 tick 不干活(不建 Twin);
- **对抗**:打扰预算耗尽时 tick 产出 0 push(硬闸,不绕);
- 预算可用时真推,并写 notified=True 埋点;
- 久坐参照步数从上一 tick 的 heartbeat_tick 快照取(无新表)。
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

import app.services.contextual_heartbeat as chb
import app.services.proactive_coordinator as pc
import app.tasks.contextual_heartbeat as task
from app.models.agent_audit_log import AgentAuditLog
from app.models.medication import Medication
from app.models.user import User
from app.twin.schema import HealthTwin, TwinMeta
from app.utils.timezone import CHINA_TIMEZONE


# ─────────────────────────── 纯规则:饮水缺口 ────────────────────────────


def test_hydration_gap_fires_afternoon_behind():
    c = chb.rule_hydration_gap(hour=16, water_ml_today=500, water_goal_ml=2000, water_progress_pct=25.0)
    assert c is not None and c.rule_id == "hydration_gap" and c.tier == "P1"


def test_hydration_gap_silent_before_15():
    assert chb.rule_hydration_gap(hour=13, water_ml_today=500, water_goal_ml=2000, water_progress_pct=25.0) is None


def test_hydration_gap_silent_when_on_track():
    assert chb.rule_hydration_gap(hour=16, water_ml_today=1200, water_goal_ml=2000, water_progress_pct=60.0) is None


def test_hydration_gap_silent_when_zero_logged():
    # 0 无法区分「没喝」与「没记录」→ 不骚扰不记饮水的用户
    assert chb.rule_hydration_gap(hour=16, water_ml_today=0, water_goal_ml=2000, water_progress_pct=0.0) is None


# ─────────────────────────── 纯规则:用药窗错过 ──────────────────────────


def test_medication_missed_fires_past_grace_uncovered():
    meds = [{"name": "二甲双胍", "reminder_times": ["08:00"], "taken_count": 0}]
    c = chb.rule_medication_missed(now_minutes=9 * 60, active_meds=meds)  # 09:00,过 30min
    assert c is not None and c.rule_id == "medication_missed" and "二甲双胍" in c.reason


def test_medication_missed_silent_within_grace():
    meds = [{"name": "药", "reminder_times": ["08:00"], "taken_count": 0}]
    # 08:15 < 08:00+30 → 宽限期内不报
    assert chb.rule_medication_missed(now_minutes=8 * 60 + 15, active_meds=meds) is None


def test_medication_missed_silent_when_covered():
    meds = [{"name": "药", "reminder_times": ["08:00"], "taken_count": 1}]
    assert chb.rule_medication_missed(now_minutes=9 * 60, active_meds=meds) is None


# ─────────────────────────── 纯规则:复查到期 ────────────────────────────


def test_recheck_due_fires_when_end_reached():
    today = date(2026, 7, 11)
    cycles = [{"id": 1, "cycle_type": "metabolic_90d", "planned_end_date": date(2026, 7, 10)}]
    c = chb.rule_recheck_due(today=today, active_cycles=cycles)
    assert c is not None and c.rule_id == "recheck_due"


def test_recheck_due_silent_when_future():
    today = date(2026, 7, 11)
    cycles = [{"id": 1, "cycle_type": "metabolic_90d", "planned_end_date": date(2026, 8, 1)}]
    assert chb.rule_recheck_due(today=today, active_cycles=cycles) is None


# ─────────────────────────── 纯规则:久坐 ────────────────────────────────


def test_sedentary_fires_no_step_delta_work_hours():
    c = chb.rule_sedentary(hour=14, steps_now=5030, steps_prior=5000, prior_age_hours=2.0)
    assert c is not None and c.rule_id == "sedentary"


def test_sedentary_silent_when_active():
    assert chb.rule_sedentary(hour=14, steps_now=5400, steps_prior=5000, prior_age_hours=2.0) is None


def test_sedentary_silent_outside_work_hours():
    assert chb.rule_sedentary(hour=19, steps_now=5030, steps_prior=5000, prior_age_hours=2.0) is None


def test_sedentary_silent_without_prior_sample():
    assert chb.rule_sedentary(hour=14, steps_now=5030, steps_prior=None, prior_age_hours=None) is None


def test_sedentary_silent_when_prior_too_recent():
    # 参照才 0.5h 前 → 还没到 ~2h,不判久坐
    assert chb.rule_sedentary(hour=14, steps_now=5030, steps_prior=5000, prior_age_hours=0.5) is None


# ─────────────────────────── 白天窗 + fail-loud ─────────────────────────


def test_is_daytime_window():
    assert chb.is_daytime(8) is True
    assert chb.is_daytime(21) is True
    assert chb.is_daytime(22) is False
    assert chb.is_daytime(7) is False
    assert chb.is_daytime(0) is False


def _full_inputs(**over):
    base = dict(
        hour=16, today=date(2026, 7, 11), now_minutes=16 * 60,
        water_ml_today=500, water_goal_ml=2000, water_progress_pct=25.0,
        active_meds=[{"name": "药", "reminder_times": ["08:00"], "taken_count": 0}],
        active_cycles=[], steps_now=None, steps_prior=None, prior_age_hours=None,
    )
    base.update(over)
    return chb.HeartbeatInputs(**base)


def test_evaluate_fail_loud_one_rule_raises_others_run(monkeypatch):
    """一条规则抛错 → failed_rules 计数 + 其余规则照跑(不挂整 tick)。"""
    def _boom(**_kw):
        raise RuntimeError("simulated rule crash")

    monkeypatch.setattr(chb, "rule_hydration_gap", _boom)
    res = chb.evaluate_heartbeat(_full_inputs())
    assert res.failed_rules == 1
    assert "hydration_gap" in res.failed_rule_ids
    # medication_missed 仍产出候选(其余规则未受影响)
    assert any(c.rule_id == "medication_missed" for c in res.candidates)


def test_evaluate_all_clean_collects_candidates():
    res = chb.evaluate_heartbeat(_full_inputs())
    assert res.failed_rules == 0
    ids = {c.rule_id for c in res.candidates}
    assert "hydration_gap" in ids and "medication_missed" in ids


# ─────────────────────────── task 层:db-backed ─────────────────────────


def _mk_user(db) -> User:
    u = User(
        username=f"hb_{uuid.uuid4().hex[:6]}",
        email=f"hb_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x", name="hb", is_active=True, is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _seed_active_med(db, user_id: int):
    # 只为把用户纳入候选人群;实际规则输入走 crafted twin(active_meds=[])。
    db.add(Medication(user_id=user_id, name="占位药", is_active=True))
    db.commit()


def _fill_budget(db, user_id: int, n: int):
    for _ in range(n):
        db.add(AgentAuditLog(
            user_id=user_id, agent_type="trajectory_watch", action="proactive_trigger",
            result_detail={"notified": True},
        ))
    db.commit()


def _craft_twin(*, water_ml=500, water_goal=2000, water_pct=25.0, steps=None, meds=None) -> HealthTwin:
    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(timezone.utc)))
    t.behavioral.water_ml_today = water_ml
    t.behavioral.water_goal_ml = water_goal
    t.behavioral.water_progress_pct = water_pct
    t.physiological.steps_today = steps
    t.medication.active_meds = meds if meds is not None else []
    return t


@pytest.fixture
def _awake(monkeypatch):
    """隔离挂钟:非静默、非忙碌窗 —— 让预算成为唯一变量。"""
    monkeypatch.setattr(pc, "_in_quiet_hours", lambda db, uid: False)
    monkeypatch.setattr(pc, "_in_busy_window", lambda db, uid: False)


@pytest.fixture
def _push_recorder(monkeypatch):
    """记录 run_async 调用次数,关闭 coroutine 不实际推送。"""
    calls = []

    def fake_run_async(coro):
        calls.append(coro)
        try:
            coro.close()
        except Exception:  # noqa: BLE001
            pass
        # 模拟真实 push_service.send_notification 成功返回;
        # notified 回写以此为准(安全评审 #3)。失败路径见 test_push_failure_*。
        return {"success": True}

    monkeypatch.setattr(task, "run_async", fake_run_async)
    return calls


def test_night_tick_does_no_work(db, monkeypatch):
    """夜间(23:00 用户时区)→ 不 tick:不建 Twin、users_scanned=0、0 push。"""
    u = _mk_user(db)
    _seed_active_med(db, u.id)  # 进候选人群

    built = []
    monkeypatch.setattr(task, "build_twin", lambda *a, **k: built.append(1) or _craft_twin())
    monkeypatch.setattr(task, "get_user_now",
                        lambda d, uid: datetime(2026, 7, 11, 23, 0, tzinfo=CHINA_TIMEZONE))

    res = task.run_contextual_heartbeat(db)
    assert res["users_scanned"] == 0
    assert res["emitted"] == 0
    assert built == []  # 夜间门在 _assemble_inputs 之前拦住,绝不重建 Twin


def test_budget_exhausted_zero_push(db, monkeypatch, _awake, _push_recorder):
    """对抗:全局周预算已满(15)→ 命中候选也 0 push,记 suppressed_by_budget。"""
    u = _mk_user(db)
    _seed_active_med(db, u.id)
    _fill_budget(db, u.id, 15)  # 顶满默认 proactive_global_weekly_budget

    twin = _craft_twin(water_ml=500, water_pct=25.0)  # 触发 hydration_gap
    monkeypatch.setattr(task, "build_twin", lambda *a, **k: twin)
    monkeypatch.setattr(task, "get_user_now",
                        lambda d, uid: datetime(2026, 7, 11, 16, 0, tzinfo=CHINA_TIMEZONE))

    res = task.run_contextual_heartbeat(db)
    assert res["users_scanned"] == 1
    assert res["considered"] >= 1
    assert res["emitted"] == 0                    # 预算耗尽 = 0 push
    assert res["suppressed_by_budget"] >= 1
    assert _push_recorder == []                    # 真没调推送


def test_push_failure_not_counted_as_notified(db, monkeypatch, _awake):
    """安全评审 #3:APNs 发送失败 → notified=False(不消耗打扰预算)+ push_failed 计数。"""
    u = _mk_user(db)
    _seed_active_med(db, u.id)

    twin = _craft_twin(water_ml=500, water_pct=25.0)
    monkeypatch.setattr(task, "build_twin", lambda *a, **k: twin)
    monkeypatch.setattr(task, "get_user_now",
                        lambda d, uid: datetime(2026, 7, 11, 16, 0, tzinfo=CHINA_TIMEZONE))

    def failing_run_async(coro):
        try:
            coro.close()
        except Exception:  # noqa: BLE001
            pass
        return {"success": False, "reason": "no_token"}

    monkeypatch.setattr(task, "run_async", failing_run_async)

    res = task.run_contextual_heartbeat(db)
    assert res["emitted"] == 0
    assert res["push_failed"] >= 1
    # 失败不得写 notified=True(否则虚耗全局预算)
    notified = db.query(AgentAuditLog).filter(
        AgentAuditLog.user_id == u.id,
        AgentAuditLog.action == "proactive_trigger",
        AgentAuditLog.agent_type == task._AGENT_TYPE,
    ).all()
    assert all(not (r.result_detail or {}).get("notified") for r in notified)


def test_emit_when_budget_available(db, monkeypatch, _awake, _push_recorder):
    """预算可用 → 真推,并写 notified=True 埋点(计入下 tick 预算)。"""
    u = _mk_user(db)
    _seed_active_med(db, u.id)

    twin = _craft_twin(water_ml=500, water_pct=25.0)
    monkeypatch.setattr(task, "build_twin", lambda *a, **k: twin)
    monkeypatch.setattr(task, "get_user_now",
                        lambda d, uid: datetime(2026, 7, 11, 16, 0, tzinfo=CHINA_TIMEZONE))

    res = task.run_contextual_heartbeat(db)
    assert res["emitted"] == 1
    assert res["suppressed_by_budget"] == 0
    assert len(_push_recorder) == 1
    # 埋点:一条 notified=True 的 proactive_trigger(计入全局预算)
    notified = db.query(AgentAuditLog).filter(
        AgentAuditLog.user_id == u.id,
        AgentAuditLog.action == "proactive_trigger",
        AgentAuditLog.agent_type == task._AGENT_TYPE,
    ).all()
    assert any((r.result_detail or {}).get("notified") for r in notified)


def test_tick_snapshot_persisted_for_sedentary_history(db, monkeypatch, _awake, _push_recorder):
    """每 tick 写 heartbeat_tick 快照(steps_today + snapshot_at + 遥测),供久坐下 tick 参照。"""
    u = _mk_user(db)
    _seed_active_med(db, u.id)

    twin = _craft_twin(water_ml=0, steps=5000)  # 只留 steps;无候选
    monkeypatch.setattr(task, "build_twin", lambda *a, **k: twin)
    monkeypatch.setattr(task, "get_user_now",
                        lambda d, uid: datetime(2026, 7, 11, 16, 0, tzinfo=CHINA_TIMEZONE))

    task.run_contextual_heartbeat(db)
    snap = db.query(AgentAuditLog).filter(
        AgentAuditLog.user_id == u.id, AgentAuditLog.action == task._TICK_ACTION,
    ).one()
    assert snap.result_detail["steps_today"] == 5000
    assert "snapshot_at" in snap.result_detail


def test_sedentary_uses_prior_tick_snapshot(db, monkeypatch, _awake, _push_recorder):
    """久坐 e2e:上一 tick 快照(2h 前 steps)→ 本 tick 步数几乎没动 → 起身提示推送。"""
    u = _mk_user(db)
    _seed_active_med(db, u.id)

    local_now = datetime(2026, 7, 11, 14, 0, tzinfo=CHINA_TIMEZONE)  # 工作时段
    now_utc = local_now.astimezone(timezone.utc)
    # 2h 前快照,steps=5000
    db.add(AgentAuditLog(
        user_id=u.id, agent_type=task._AGENT_TYPE, action=task._TICK_ACTION,
        result_detail={"steps_today": 5000,
                       "snapshot_at": (now_utc - timedelta(hours=2)).isoformat()},
    ))
    db.commit()

    twin = _craft_twin(water_ml=0, steps=5030)  # +30 步 < 100 → 久坐;water 0 不触发补水
    monkeypatch.setattr(task, "build_twin", lambda *a, **k: twin)
    monkeypatch.setattr(task, "get_user_now", lambda d, uid: local_now)

    res = task.run_contextual_heartbeat(db)
    assert res["emitted"] == 1
    assert len(_push_recorder) == 1
