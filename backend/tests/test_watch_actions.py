"""Watch 到点项一键完成 + 服药/补剂依从回写(安全敏感)。

覆盖 docs/design-watch-action-complete.md §测试计划 1-9:
- 正常完成落 1 条领域记录(用药)
- 幂等:双 POST → 恰好 1 条 MedicationLog
- IDOR:A token 完成 B 协议 → 404 且 B 未变
- 非协议源 400 / 畸形 action_id 400 / 不存在 protocol 404
- 补剂分支落 SupplementRecord(taken=True) + 写失败向上抛
- watch_summary 各项带正确 action_id 格式
- 无 token → 401

钉「不假装完成」(Rule #1)+ 幂等(防依从灌水)+ 防 IDOR 三条不变量。
"""
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

import app.services.watch_summary as ws
from app.models.medication import Medication, MedicationLog
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.user import User
from app.services import health_protocol_service as proto_svc


# ── fixtures ──────────────────────────────────────────────────────────
def _mk_user(db):
    u = User(username=f"wa_{uuid.uuid4().hex[:6]}", email=f"wa_{uuid.uuid4().hex[:6]}@x.com",
             hashed_password="x", name="wa", is_active=True, is_approved=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _headers(user):
    from app.services.auth import auth_service
    return {"Authorization": f"Bearer {auth_service.create_access_token({'sub': str(user.id)})}"}


def _med_protocol(db, user_id):
    """一味药 + 其用药域协议(source_model=medication_logs)。"""
    med = Medication(user_id=user_id, name="瑞舒伐他汀", dosage="10mg")
    db.add(med)
    db.commit()
    db.refresh(med)
    return proto_svc.create_protocol_for_medication(db, user_id, med.id)


def _supp_protocol(db, user_id):
    """一味补剂定义 + 其补剂域协议(source_model=supplement_records)。"""
    sd = SupplementDefinition(user_id=user_id, name="维生素D3", dosage="5000IU", timing="morning",
                              is_active=True)
    db.add(sd)
    db.commit()
    db.refresh(sd)
    p = proto_svc.create_protocol(db, user_id, {
        "domain": "supplement",
        "name": "维生素D3 补剂",
        "mechanism": "fixed_container",
        "cadence": "daily",
        "can_default_complete": False,       # 补剂需显式确认(非饮水)
        "source_model": "supplement_records",
        "source_id": sd.id,
    })
    return sd, p


# ── 1) 正常完成落 1 条 MedicationLog ───────────────────────────────────
def test_complete_medication_writes_one_log(client, db):
    user = _mk_user(db)
    p = _med_protocol(db, user.id)
    r = client.post(f"/api/v1/watch/actions/agenda-health_protocol-{p.id}/complete",
                    headers=_headers(user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object_type"] == "health_protocol"
    assert body["object_id"] == p.id
    assert body["status"] == "completed"
    assert body["written"] == "medication_log"
    assert body["action_id"] == f"agenda-health_protocol-{p.id}"
    logs = db.query(MedicationLog).filter(MedicationLog.user_id == user.id).all()
    assert len(logs) == 1
    assert logs[0].status == "taken"


# ── 2) 幂等:双 POST → 恰好 1 条 MedicationLog ─────────────────────────
def test_idempotent_double_post_one_log(client, db):
    user = _mk_user(db)
    p = _med_protocol(db, user.id)
    url = f"/api/v1/watch/actions/agenda-health_protocol-{p.id}/complete"
    r1 = client.post(url, headers=_headers(user))
    r2 = client.post(url, headers=_headers(user))
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text          # 第二次幂等成功,不报错
    assert r2.json()["status"] == "completed"
    logs = db.query(MedicationLog).filter(MedicationLog.user_id == user.id).all()
    assert len(logs) == 1, f"幂等被破坏:写了 {len(logs)} 条,依从被灌水"


def test_skip_protocol_action_marks_today_skipped(client, db):
    """Watch 跳过按钮 → 只写协议事件,不落用药/补剂等领域完成记录。"""
    user = _mk_user(db)
    p = _med_protocol(db, user.id)

    r = client.post(
        f"/api/v1/watch/actions/agenda-health_protocol-{p.id}/skip",
        headers=_headers(user),
        json={"reason": "too_tired"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action_id"] == f"agenda-health_protocol-{p.id}"
    assert body["status"] == "skipped"
    assert body["skip_reason"] == "too_tired"
    logs = db.query(MedicationLog).filter(MedicationLog.user_id == user.id).all()
    assert logs == [], "跳过不是完成,不能落 MedicationLog"


def test_skip_non_protocol_source_400(client, db):
    user = _mk_user(db)
    r = client.post(
        "/api/v1/watch/actions/agenda-training_decision-5/skip",
        headers=_headers(user),
        json={"reason": "no_time"},
    )
    assert r.status_code == 400, r.text


def test_snooze_protocol_action_marks_today_snoozed(client, db):
    """Watch 稍后按钮 → 后端持久化 snooze,不落领域完成记录。"""
    user = _mk_user(db)
    p = _med_protocol(db, user.id)

    r = client.post(
        f"/api/v1/watch/actions/agenda-health_protocol-{p.id}/snooze",
        headers=_headers(user),
        json={"minutes": 45},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action_id"] == f"agenda-health_protocol-{p.id}"
    assert body["status"] == "snoozed"
    assert body["minutes"] == 45
    assert body["snoozed_until"]
    logs = db.query(MedicationLog).filter(MedicationLog.user_id == user.id).all()
    assert logs == [], "稍后不是完成,不能落 MedicationLog"
    today = proto_svc.today_status(db, user.id)
    assert today[0]["today_status"] == "snoozed"


def test_expired_snooze_returns_to_pending(db):
    """snooze 过期后协议重新进入 pending,让 agenda/top_action 可再次投影。"""
    user = _mk_user(db)
    p = _med_protocol(db, user.id)
    ev = proto_svc.snooze_protocol(db, p.id, user.id, minutes=30)
    ev.value = {
        "minutes": 30,
        "snoozed_until": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    }
    db.commit()

    today = proto_svc.today_status(db, user.id)

    assert today[0]["today_status"] == "pending"


def test_snooze_non_protocol_source_400(client, db):
    user = _mk_user(db)
    r = client.post(
        "/api/v1/watch/actions/agenda-training_decision-5/snooze",
        headers=_headers(user),
        json={"minutes": 30},
    )
    assert r.status_code == 400, r.text


# ── 3) IDOR:A token 完成 B 协议 → 404 且 B 未变 ───────────────────────
def test_idor_a_cannot_complete_b_protocol(client, db):
    user_a = _mk_user(db)
    user_b = _mk_user(db)
    p_b = _med_protocol(db, user_b.id)          # 协议属于 B
    r = client.post(f"/api/v1/watch/actions/agenda-health_protocol-{p_b.id}/complete",
                    headers=_headers(user_a))    # A 的 token 猜中 B 的 id
    assert r.status_code == 404, r.text
    # B 的协议未被完成,无任何领域记录落库
    logs = db.query(MedicationLog).filter(MedicationLog.user_id == user_b.id).all()
    assert len(logs) == 0, "IDOR:他人协议被完成,落了不该有的记录"
    from app.models.health_protocol import HealthProtocolEvent
    evs = db.query(HealthProtocolEvent).filter(
        HealthProtocolEvent.protocol_id == p_b.id).all()
    assert len(evs) == 0, "IDOR:他人协议产生了完成事件"


# ── 4) 非协议源 → 400 ─────────────────────────────────────────────────
def test_non_protocol_source_400(client, db):
    user = _mk_user(db)
    r = client.post("/api/v1/watch/actions/agenda-training_decision-5/complete",
                    headers=_headers(user))
    assert r.status_code == 400, r.text
    assert "不支持" in r.json()["detail"]


def test_health_problem_source_400(client, db):
    user = _mk_user(db)
    r = client.post("/api/v1/watch/actions/agenda-health_problem-5/complete",
                    headers=_headers(user))
    assert r.status_code == 400, r.text


# ── 5) 畸形 action_id → 400 ───────────────────────────────────────────
@pytest.mark.parametrize("bad", [
    "foo",
    "agenda-x",
    "agenda-health_protocol-abc",   # oid 非数字
    "agenda-health_protocol-",      # 缺 oid
    "agenda--5",                    # 缺 ot
    "health_protocol-5",            # 缺前缀
])
def test_malformed_action_id_400(client, db, bad):
    user = _mk_user(db)
    r = client.post(f"/api/v1/watch/actions/{bad}/complete", headers=_headers(user))
    assert r.status_code == 400, f"{bad} 应 400, got {r.status_code}: {r.text}"


# ── 6) 不存在的 protocol_id → 404 ─────────────────────────────────────
def test_nonexistent_protocol_404(client, db):
    user = _mk_user(db)
    r = client.post("/api/v1/watch/actions/agenda-health_protocol-999999/complete",
                    headers=_headers(user))
    assert r.status_code == 404, r.text


# ── 7) 补剂分支:落 1 条 SupplementRecord(taken=True, taken_time≈now) ──
def test_supplement_branch_writes_record(client, db):
    user = _mk_user(db)
    sd, p = _supp_protocol(db, user.id)
    r = client.post(f"/api/v1/watch/actions/agenda-health_protocol-{p.id}/complete",
                    headers=_headers(user))
    assert r.status_code == 200, r.text
    assert r.json()["written"] == "supplement_record"
    recs = db.query(SupplementRecord).filter(SupplementRecord.user_id == user.id).all()
    assert len(recs) == 1
    rec = recs[0]
    assert rec.supplement_id == sd.id
    assert rec.taken is True
    assert rec.record_date == date.today()
    assert rec.taken_time is not None        # taken_time≈now


def test_supplement_branch_idempotent(client, db):
    user = _mk_user(db)
    sd, p = _supp_protocol(db, user.id)
    url = f"/api/v1/watch/actions/agenda-health_protocol-{p.id}/complete"
    client.post(url, headers=_headers(user))
    client.post(url, headers=_headers(user))
    recs = db.query(SupplementRecord).filter(SupplementRecord.user_id == user.id).all()
    assert len(recs) == 1, "补剂幂等被破坏"


def test_supplement_write_failure_propagates(client, db, monkeypatch):
    """写补剂记录失败 → 向上抛(不静默报完成,守 Rule #1)。"""
    user = _mk_user(db)
    sd, p = _supp_protocol(db, user.id)

    def _boom(*a, **k):
        raise RuntimeError("db write boom")

    # 让补剂分支的 flush 炸:patch Session.flush 在补剂写入路径上
    import app.services.health_protocol_service as svc
    orig_write = svc._write_domain_record

    def _wrapped(db_, user_id, proto, track, value, day):
        if proto.source_model == "supplement_records":
            raise RuntimeError("db write boom")
        return orig_write(db_, user_id, proto, track, value, day)

    monkeypatch.setattr(svc, "_write_domain_record", _wrapped)
    r = client.post(f"/api/v1/watch/actions/agenda-health_protocol-{p.id}/complete",
                    headers=_headers(user))
    assert r.status_code >= 500, f"写失败必须冒泡成错误, got {r.status_code}"
    # 没有静默落的半成品记录
    recs = db.query(SupplementRecord).filter(SupplementRecord.user_id == user.id).all()
    assert len(recs) == 0


# ── 8) watch_summary action_id 注入 ───────────────────────────────────
def _agenda(items):
    return {"agenda_date": "2026-06-16", "count": len(items), "items": items}


def _proto_item(title, priority=50, domain="medication", oid=7):
    return {"type": domain, "title": title, "status": "pending", "priority": priority,
            "time_window": "anytime",
            "source": {"object_type": "health_protocol", "object_id": oid}}


def test_watch_summary_top_action_has_action_id(db, monkeypatch):
    user = _mk_user(db)
    items = [_proto_item("吃药", priority=80, oid=42)]
    monkeypatch.setattr(ws.agenda_service, "today", lambda d, u, **k: _agenda(items))
    s = ws.build_watch_summary(db, user.id)
    assert s["top_action"]["action_id"] == "agenda-health_protocol-42"


def test_watch_summary_due_items_have_action_id(db, monkeypatch):
    user = _mk_user(db)
    items = [_proto_item("吃药", oid=1), _proto_item("补剂", oid=2)]
    monkeypatch.setattr(ws.agenda_service, "today", lambda d, u, **k: _agenda(items))
    s = ws.build_watch_summary(db, user.id)
    assert "due_items" in s
    ids = {d["action_id"] for d in s["due_items"]}
    assert ids == {"agenda-health_protocol-1", "agenda-health_protocol-2"}


def test_watch_summary_quick_actions_have_action_id_key(db, monkeypatch):
    user = _mk_user(db)
    monkeypatch.setattr(ws.agenda_service, "today", lambda d, u, **k: _agenda([]))
    s = ws.build_watch_summary(db, user.id)
    # quick_actions 是无 source 的目录入口 → action_id 必须为 null(不可一键完成具体项)
    for qa in s["quick_actions"]:
        assert qa["action_id"] is None


def test_watch_summary_item_without_source_action_id_null(db, monkeypatch):
    user = _mk_user(db)
    # 无 source 的项(如训练灯)action_id=null
    items = [{"type": "training", "title": "今日训练", "status": "info", "light": "green",
              "readiness_score": 70}]
    monkeypatch.setattr(ws.agenda_service, "today", lambda d, u, **k: _agenda(items))
    s = ws.build_watch_summary(db, user.id)
    # training 不是 pending health_protocol,不进 due_items;top_action 为 None
    assert s["top_action"] is None
    assert s["due_items"] == []


# ── 9) 鉴权:无 token → 401 ───────────────────────────────────────────
def test_complete_requires_auth(client):
    r = client.post("/api/v1/watch/actions/agenda-health_protocol-1/complete")
    assert r.status_code == 401
