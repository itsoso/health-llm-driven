"""首页脊柱 Increment 1:first-class HealthEvent 议程生命周期 + 闭环完成 + past 投影。

钉死闭环修复点 —— point-in-time 提醒 → 点完成 → 首页脊柱项熄灭 + 计入 past.completed:
① 物化:可完成的脊柱行动项带 first-class HealthEvent event_id(供客户端调完成端点)
② 完成 done:翻 HealthEvent done + 双轨回写真实 source(WaterIntake 真落库)+ 脊柱项熄灭
③ 完成 skipped:翻 skipped + 带 skip_reason,不回写
④ 幂等:双击只一次效果(idempotent=True,不二次回写)
⑤ 跨用户隔离:完成别人的 event → 404
⑥ past 投影:含晨间简报 + 异常,且 critical/medical-grade 异常被排除,洞察标 association_only
⑦ 提醒发 complete_ref + category=AGENDA_ACTION
"""
from datetime import date, datetime, timezone

import pytest

from app.services import today_timeline_service as tts
from app.services import timeline_agenda_service as tas


# ─────────────────────────── 物化 + 完成端点 ───────────────────────────

def _seed_water_protocol(client, headers):
    r = client.post("/api/v1/protocols/seed/water-cup", headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_completable_item_carries_event_id(client, db, auth_user_and_headers):
    """可完成的脊柱行动项必须带物化后的 first-class HealthEvent id。"""
    user, h = auth_user_and_headers
    _seed_water_protocol(client, h)

    spine = build = tts.build_today_spine(db, user.id)
    water = next(
        it for it in spine["items"]
        if it.get("complete_ref") and it["complete_ref"]["object_type"] == "health_protocol"
    )
    assert water["can_complete"] is True
    assert isinstance(water["event_id"], int), "可完成项必须物化出 event_id"
    assert water["action_kind"]  # hydration


def test_complete_done_dual_track_writes_and_turns_off(client, db, auth_user_and_headers):
    """完成 done:翻 HealthEvent done + 双轨真落 WaterIntake + 下次脊柱该项熄灭 + 计入 past.completed。"""
    from app.models.daily_health import WaterIntake

    user, h = auth_user_and_headers
    _seed_water_protocol(client, h)
    spine = tts.build_today_spine(db, user.id)
    water = next(it for it in spine["items"] if it.get("event_id"))
    event_id = water["event_id"]

    before = db.query(WaterIntake).filter(WaterIntake.user_id == user.id).count()
    r = client.post(f"/api/v1/timeline/events/{event_id}/complete", headers=h,
                    json={"status": "done"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["agenda_status"] == "done"
    assert body["idempotent"] is False
    # 双轨回写发生:source_write 指向 health_protocol
    assert body["source_write"] is not None
    assert body["source_write"]["object_type"] == "health_protocol"

    # 真实 source 落库(WaterIntake 多了一条 —— 不是假完成)
    after = db.query(WaterIntake).filter(WaterIntake.user_id == user.id).count()
    assert after == before + 1, "完成必须真写 WaterIntake(双轨),不能假成功"

    # 脊柱项熄灭:下次 build 该行 can_complete=False、status=completed,计入 past.completed
    spine2 = tts.build_today_spine(db, user.id)
    row = next((it for it in spine2["items"] if it.get("event_id") == event_id), None)
    if row is not None:  # 仍在 items 里(协议每天到期),但应已熄灭
        assert row["can_complete"] is False
        assert row["status"] in ("completed", "auto_observed")
    assert spine2["past"]["completed_count"] >= 1


def test_complete_skipped_with_reason_no_writeback(client, db, auth_user_and_headers):
    """完成 skipped:翻 skipped + 带 skip_reason,不回写真实 source。"""
    from app.models.daily_health import WaterIntake

    user, h = auth_user_and_headers
    _seed_water_protocol(client, h)
    spine = tts.build_today_spine(db, user.id)
    event_id = next(it["event_id"] for it in spine["items"] if it.get("event_id"))

    before = db.query(WaterIntake).filter(WaterIntake.user_id == user.id).count()
    r = client.post(f"/api/v1/timeline/events/{event_id}/complete", headers=h,
                    json={"status": "skipped", "skip_reason": "forgot"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["agenda_status"] == "skipped"
    assert body["skip_reason"] == "forgot"
    assert body["source_write"] is None
    after = db.query(WaterIntake).filter(WaterIntake.user_id == user.id).count()
    assert after == before, "skip 不应回写真实 source"


def test_complete_is_idempotent(client, db, auth_user_and_headers):
    """双击完成:第一次回写,第二次幂等(idempotent=True,不二次写)。"""
    from app.models.daily_health import WaterIntake

    user, h = auth_user_and_headers
    _seed_water_protocol(client, h)
    spine = tts.build_today_spine(db, user.id)
    event_id = next(it["event_id"] for it in spine["items"] if it.get("event_id"))

    r1 = client.post(f"/api/v1/timeline/events/{event_id}/complete", headers=h,
                     json={"status": "done"})
    assert r1.status_code == 200
    assert r1.json()["idempotent"] is False
    after1 = db.query(WaterIntake).filter(WaterIntake.user_id == user.id).count()

    r2 = client.post(f"/api/v1/timeline/events/{event_id}/complete", headers=h,
                     json={"status": "done"})
    assert r2.status_code == 200
    assert r2.json()["idempotent"] is True, "二次完成应幂等"
    after2 = db.query(WaterIntake).filter(WaterIntake.user_id == user.id).count()
    assert after2 == after1, "双击只能落一条 WaterIntake(一次效果)"


def test_complete_cross_user_404(client, db, auth_user_and_headers):
    """跨用户完成别人的议程事件 → 404(用户隔离不变量)。"""
    from app.services.auth import auth_service
    from tests.conftest import create_authenticated_user  # type: ignore

    owner, h_owner = auth_user_and_headers
    _seed_water_protocol(client, h_owner)
    spine = tts.build_today_spine(db, owner.id)
    event_id = next(it["event_id"] for it in spine["items"] if it.get("event_id"))

    # 第二个用户
    other, token2 = create_authenticated_user(db)
    h_other = {"Authorization": f"Bearer {token2}"}
    r = client.post(f"/api/v1/timeline/events/{event_id}/complete", headers=h_other,
                    json={"status": "done"})
    assert r.status_code == 404, "跨用户完成必须 404"


def test_complete_nonexistent_404(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.post("/api/v1/timeline/events/999999/complete", headers=h,
                    json={"status": "done"})
    assert r.status_code == 404


def test_complete_bad_status_400(client, db, auth_user_and_headers):
    user, h = auth_user_and_headers
    _seed_water_protocol(client, h)
    spine = tts.build_today_spine(db, user.id)
    event_id = next(it["event_id"] for it in spine["items"] if it.get("event_id"))
    r = client.post(f"/api/v1/timeline/events/{event_id}/complete", headers=h,
                    json={"status": "bogus"})
    assert r.status_code == 400


# ─────────────────────────── past 投影 ───────────────────────────

def _write_briefing(db, user_id, content="今日 HRV 偏低,注意恢复。"):
    from app.models.openclaw import OpenClawConversation, OpenClawMessage
    from app.tasks.notifications import _briefing_title_for

    conv = OpenClawConversation(user_id=user_id, title=_briefing_title_for(date.today()))
    db.add(conv)
    db.commit()
    db.refresh(conv)
    msg = OpenClawMessage(conversation_id=conv.id, role="assistant", content=content,
                          created_at=datetime.now(timezone.utc))
    db.add(msg)
    db.commit()
    return conv, msg


def _write_anomaly(db, user_id, severity="warning", metric="resting_heart_rate", value=68.0):
    from app.models.anomaly_alert import AnomalyAlert

    a = AnomalyAlert(
        user_id=user_id,
        alert_type="rhr_spike",
        severity=severity,
        metric_name=metric,
        current_value=value,
        detection_date=date.today(),
        message=f"{metric} 偏离基线",
    )
    db.add(a)
    db.commit()
    return a


def test_past_projection_includes_briefing_and_anomaly(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    _write_briefing(db, user.id)
    _write_anomaly(db, user.id, severity="warning")

    spine = tts.build_today_spine(db, user.id)
    past_ids = [e["id"] for e in spine["past"]["events"]]
    assert any(i.startswith("briefing_") for i in past_ids), "past 应含晨间简报"
    assert any(i.startswith("anomaly_") for i in past_ids), "past 应含异常检测"

    # 洞察项必须标 association_only(相关非因果,R4/R9)
    insights = [e for e in spine["past"]["events"] if e["kind"] == "insight"]
    assert insights
    for e in insights:
        assert e["proof"] and e["proof"]["association_only"] is True


def test_past_projection_excludes_critical_anomaly(db, auth_user_and_headers):
    """critical/medical-grade 异常绝不进首页脊柱(走专门安全通道)。"""
    user, _ = auth_user_and_headers
    _write_anomaly(db, user.id, severity="critical", metric="spo2_avg", value=82.0)

    spine = tts.build_today_spine(db, user.id)
    past_ids = [e["id"] for e in spine["past"]["events"]]
    assert not any(i.startswith("anomaly_") for i in past_ids), \
        "critical 异常不得渲染成首页脊柱项"


def test_past_projection_warning_anomaly_kept(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    _write_anomaly(db, user.id, severity="warning")
    spine = tts.build_today_spine(db, user.id)
    assert any(e["id"].startswith("anomaly_") for e in spine["past"]["events"])


# ─────────────────────────── 提醒 emit complete_ref ───────────────────────────

def test_reminder_collect_attaches_complete_ref():
    """day-schedule 的 med:{id} 项 → complete_ref 自描述(供 push 完成按钮)。"""
    from app.tasks.event_reminders import _complete_ref_for

    assert _complete_ref_for("med:42", "medication") == {
        "object_type": "medication", "object_id": 42}
    assert _complete_ref_for("med:7", "supplement") == {
        "object_type": "supplement", "object_id": 7}
    # 认不出格式 → None(不假装能完成)
    assert _complete_ref_for("cal:9", "meeting") is None
    assert _complete_ref_for("workout:today", "movement") is None
    assert _complete_ref_for(None, "medication") is None


def test_reminder_emits_agenda_action_category(db, auth_user_and_headers, monkeypatch):
    """带 complete_ref 的提醒项 → push data category=AGENDA_ACTION + complete_endpoint。

    直接验证 scan 在命中窗口时构造的 data;用 monkeypatch 把 push 截下来断言 data。
    """
    import app.tasks.event_reminders as er
    from app.utils.timezone import get_china_now

    user, _ = auth_user_and_headers

    now = get_china_now()
    fire_item = {
        "item_key": "med:5",
        "kind": "medication",
        "title": "二甲双胍",
        "start_min": now.hour * 60 + now.minute + 15,  # T = now + lead(15) → 命中
        "lead": 15,
        "complete_ref": {"object_type": "medication", "object_id": 5},
    }

    monkeypatch.setattr(er, "_candidate_user_ids", lambda db_, today_: [user.id])
    monkeypatch.setattr(er, "_collect_timed_items", lambda db_, uid, today_: [fire_item])
    monkeypatch.setattr(er, "_try_mark_sent", lambda *a, **k: True)
    monkeypatch.setattr("app.services.proactive_coordinator.can_notify_proactively",
                        lambda *a, **k: True)

    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(er.PushService, "send_notification",
                        lambda self, **kwargs: fake_send(**kwargs))

    er.scan_event_reminders()

    assert captured, "应已触发一条推送"
    data = captured["data"]
    assert data["category"] == "AGENDA_ACTION"
    assert data["complete_ref"] == {"object_type": "medication", "object_id": 5}
    assert "complete_endpoint" in data
