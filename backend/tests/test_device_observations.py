"""P2 设备观察 API(折叠进 HealthEvent 流,无新表)。

钉死:
1. SIGNAL(posture_bad)→ 200,落一条 HealthEvent(event_type/provider/confidence),不翻议程。
2. COMPLETION(nasal_wash_completed)带可解析协议 → 议程项经 complete_by_ref 翻 done,
   恰一条领域写(HealthProtocolEvent),重复 POST 幂等(仍恰一条)。
3. 原始媒体拒绝:payload 含 image/frame/base64 → 422,什么都不写。
4. 跨用户隔离:GET 只回本人观察;completion 引用他人协议 → 不闭环、不跨用户写。
5. 无 token → 401。
"""
from app.models.health_event import HealthEvent
from app.models.health_protocol import HealthProtocol, HealthProtocolEvent


def _create_passive_respiratory_protocol(db, user_id: int) -> HealthProtocol:
    """一个可被设备观察自动闭环的洗鼻协议(respiratory 域 + passive_device)。"""
    p = HealthProtocol(
        user_id=user_id,
        domain="respiratory",
        name="每日洗鼻",
        mechanism="passive_device",
        completion_mode="auto_observed",
        cadence="daily",
        status="active",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# ───────────────────────── 1. SIGNAL ─────────────────────────

def test_signal_observation_records_no_agenda_flip(client, db, auth_user_and_headers):
    """SIGNAL posture_bad:200 + 落 HealthEvent,不翻任何议程项(无 agenda_action 行)。"""
    user, h = auth_user_and_headers

    r = client.post(
        "/api/v1/device-observations/",
        headers=h,
        json={
            "provider": "rokid",
            "device_type": "glasses",
            "event_type": "posture_bad",
            "confidence": 0.92,
            "payload": {"angle_deg": 35, "duration_s": 12},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["event_type"] == "posture_bad"
    assert body["provider"] == "rokid"
    assert body["confidence"] == 0.92

    # HealthEvent 落库,字段正确
    ev = db.query(HealthEvent).filter(
        HealthEvent.user_id == user.id,
        HealthEvent.event_type == "posture_bad",
    ).first()
    assert ev is not None
    assert ev.source == "rokid"
    assert ev.confidence == 0.92
    assert ev.association_only is False
    assert ev.raw_data == {"angle_deg": 35, "duration_s": 12}

    # SIGNAL 绝不物化议程行(agenda_action),也无协议事件
    agenda_rows = db.query(HealthEvent).filter(
        HealthEvent.user_id == user.id,
        HealthEvent.event_type == "agenda_action",
    ).count()
    assert agenda_rows == 0
    assert db.query(HealthProtocolEvent).filter(
        HealthProtocolEvent.user_id == user.id,
    ).count() == 0


# ───────────────────── 2. COMPLETION 闭环 ─────────────────────

def test_completion_flips_agenda_via_complete_by_ref(client, db, auth_user_and_headers):
    """COMPLETION nasal_wash_completed 带可解析协议 → 议程项翻 done,恰一条领域写,幂等。"""
    user, h = auth_user_and_headers
    protocol = _create_passive_respiratory_protocol(db, user.id)

    payload = {
        "provider": "rokid",
        "event_type": "nasal_wash_completed",
        "confidence": 0.9,
        "payload": {"health_protocol_id": protocol.id},
    }
    r = client.post("/api/v1/device-observations/", headers=h, json=payload)
    assert r.status_code == 200, r.text

    # 议程 HealthEvent(agenda_action)被 complete_by_ref 懒物化并翻 done
    agenda = db.query(HealthEvent).filter(
        HealthEvent.user_id == user.id,
        HealthEvent.event_type == "agenda_action",
    ).all()
    assert len(agenda) == 1
    assert agenda[0].agenda_status == "done"
    assert agenda[0].complete_ref == {"object_type": "health_protocol", "object_id": protocol.id}

    # 恰一条领域写:同一 (protocol_id, event_date) 的 HealthProtocolEvent
    proto_events = db.query(HealthProtocolEvent).filter(
        HealthProtocolEvent.protocol_id == protocol.id,
    ).all()
    assert len(proto_events) == 1
    assert proto_events[0].status in ("completed", "auto_observed")

    # 幂等:重复 POST 不二次领域写、议程仍 done
    r2 = client.post("/api/v1/device-observations/", headers=h, json=payload)
    assert r2.status_code == 200, r2.text
    assert db.query(HealthProtocolEvent).filter(
        HealthProtocolEvent.protocol_id == protocol.id,
    ).count() == 1
    agenda2 = db.query(HealthEvent).filter(
        HealthEvent.user_id == user.id,
        HealthEvent.event_type == "agenda_action",
    ).all()
    assert len(agenda2) == 1
    assert agenda2[0].agenda_status == "done"


def test_completion_ambiguous_match_records_fact_only(client, db, auth_user_and_headers):
    """同域多个待办被动协议(无显式 id)→ 不臆断闭环哪一个,仅记录事实(under-close 安全)。"""
    user, h = auth_user_and_headers
    _create_passive_respiratory_protocol(db, user.id)
    _create_passive_respiratory_protocol(db, user.id)  # 第二个 → 匹配不唯一

    r = client.post(
        "/api/v1/device-observations/",
        headers=h,
        json={"provider": "rokid", "event_type": "nasal_wash_completed", "confidence": 0.9},
    )
    assert r.status_code == 200, r.text
    # 事实记录,但两个协议都不闭环、不物化议程行
    assert db.query(HealthEvent).filter(
        HealthEvent.user_id == user.id,
        HealthEvent.event_type == "nasal_wash_completed",
    ).count() == 1
    assert db.query(HealthEvent).filter(
        HealthEvent.user_id == user.id,
        HealthEvent.event_type == "agenda_action",
    ).count() == 0
    assert db.query(HealthProtocolEvent).filter(
        HealthProtocolEvent.user_id == user.id,
    ).count() == 0


def test_completion_without_resolvable_protocol_records_fact_only(client, db, auth_user_and_headers):
    """无可解析协议(无显式 id、无唯一匹配)→ 仅记录观察事实,不假装完成。"""
    user, h = auth_user_and_headers

    r = client.post(
        "/api/v1/device-observations/",
        headers=h,
        json={"provider": "mac_screen", "event_type": "eye_break_completed", "confidence": 0.9},
    )
    assert r.status_code == 200, r.text
    # 观察事实在,但无议程物化、无协议事件
    assert db.query(HealthEvent).filter(
        HealthEvent.user_id == user.id,
        HealthEvent.event_type == "eye_break_completed",
    ).count() == 1
    assert db.query(HealthEvent).filter(
        HealthEvent.user_id == user.id,
        HealthEvent.event_type == "agenda_action",
    ).count() == 0
    assert db.query(HealthProtocolEvent).filter(
        HealthProtocolEvent.user_id == user.id,
    ).count() == 0


# ─────────────────── 3. 原始媒体拒绝 ───────────────────

def test_raw_media_payload_rejected(client, db, auth_user_and_headers):
    """payload 含原始媒体键 → 422,什么都不写。"""
    user, h = auth_user_and_headers
    for bad_key in ("image", "frame", "base64"):
        r = client.post(
            "/api/v1/device-observations/",
            headers=h,
            json={
                "provider": "rokid",
                "event_type": "posture_bad",
                "confidence": 0.9,
                "payload": {bad_key: "AAAA", "angle_deg": 30},
            },
        )
        assert r.status_code == 422, f"{bad_key}: {r.text}"
    # 一条都没写
    assert db.query(HealthEvent).filter(HealthEvent.user_id == user.id).count() == 0


# ─────────────────── 4. 跨用户隔离 ───────────────────

def test_user_isolation_list_and_cross_user_completion(client, db, auth_user_and_headers):
    """GET 只回本人观察;completion 引用他人协议 → 不闭环、不跨用户写。"""
    from tests.conftest import create_authenticated_user

    user_a, h_a = auth_user_and_headers
    user_b, token_b = create_authenticated_user(db)
    h_b = {"Authorization": f"Bearer {token_b}"}

    # B 建一个 passive 协议;A 用观察引用 B 的协议 id 想闭环
    protocol_b = _create_passive_respiratory_protocol(db, user_b.id)

    # A 记一条自己的 SIGNAL
    client.post(
        "/api/v1/device-observations/",
        headers=h_a,
        json={"provider": "rokid", "event_type": "posture_ok", "confidence": 0.9},
    )
    # A 的 completion 引用 B 的协议 → 记录事实但绝不闭环 B 的协议
    r = client.post(
        "/api/v1/device-observations/",
        headers=h_a,
        json={
            "provider": "rokid",
            "event_type": "nasal_wash_completed",
            "confidence": 0.9,
            "payload": {"health_protocol_id": protocol_b.id},
        },
    )
    assert r.status_code == 200, r.text

    # B 的协议没有任何完成/观测事件(无跨用户写)
    assert db.query(HealthProtocolEvent).filter(
        HealthProtocolEvent.protocol_id == protocol_b.id,
    ).count() == 0
    # 没有给 A 或 B 物化任何议程行
    assert db.query(HealthEvent).filter(
        HealthEvent.event_type == "agenda_action",
    ).count() == 0

    # GET 只回 A 的观察(不含 B 的任何东西;B 列表为空)
    list_a = client.get("/api/v1/device-observations/", headers=h_a)
    assert list_a.status_code == 200, list_a.text
    types_a = {o["event_type"] for o in list_a.json()}
    assert "posture_ok" in types_a
    assert "nasal_wash_completed" in types_a

    list_b = client.get("/api/v1/device-observations/", headers=h_b)
    assert list_b.status_code == 200, list_b.text
    assert list_b.json() == []


# ─────────────────── 5. 认证必需 ───────────────────

def test_auth_required(client, db):
    """无 token → 401(摄入与查询都要认证)。"""
    r = client.post(
        "/api/v1/device-observations/",
        json={"provider": "rokid", "event_type": "posture_bad", "confidence": 0.9},
    )
    assert r.status_code == 401, r.text

    r2 = client.get("/api/v1/device-observations/")
    assert r2.status_code == 401, r2.text
