"""健康协议层 P1:HealthProtocol + 双轨完成/跳过 + 今日投影。

钉:① 创建+domain 校验 ② 饮水模板 can_default_complete ③ today 待办→完成态
④ 协议轨/手工轨都写同一事件、每天一条(幂等)⑤ skip 带失败原因(R14)+ 非法原因 400
⑥ skip↔complete 翻转 ⑦ 越权 404 ⑧ 手工轨可带量。
"""
import pytest


def _h(auth):
    return auth[1]


def test_create_and_domain_validation(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.post("/api/v1/protocols", headers=h, json={
        "domain": "diet", "name": "Wagas 标准餐", "mechanism": "pre_commit",
        "implied_quantity": {"kcal": 530, "protein_g": 40},
    })
    assert r.status_code == 200, r.text
    assert r.json()["domain"] == "diet" and r.json()["mechanism"] == "pre_commit"
    # 未知 domain → 400
    bad = client.post("/api/v1/protocols", headers=h, json={"domain": "玄学", "name": "x"})
    assert bad.status_code == 400


def test_seed_water_cup_default_complete(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.post("/api/v1/protocols/seed/water-cup", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["domain"] == "hydration"
    assert body["implied_quantity"]["water_ml"] == 2000
    assert body["can_default_complete"] is True   # 饮水可默认完成(R12 边界)


def test_today_pending_then_complete_protocol_track(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    pid = client.post("/api/v1/protocols/seed/water-cup", headers=h).json()["id"]
    # today 初始 pending
    t0 = client.get("/api/v1/protocols/today", headers=h).json()
    row = next(x for x in t0 if x["protocol_id"] == pid)
    assert row["today_status"] == "pending" and row["is_due_today"] is True
    # 协议轨一键完成
    c = client.post(f"/api/v1/protocols/{pid}/complete", headers=h, json={"track": "protocol"})
    assert c.status_code == 200 and c.json()["status"] == "completed" and c.json()["track"] == "protocol"
    # today 变 completed
    t1 = client.get("/api/v1/protocols/today", headers=h).json()
    row = next(x for x in t1 if x["protocol_id"] == pid)
    assert row["today_status"] == "completed" and row["today_track"] == "protocol"


def test_manual_track_with_value(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    pid = client.post("/api/v1/protocols/seed/water-cup", headers=h).json()["id"]
    c = client.post(f"/api/v1/protocols/{pid}/complete", headers=h,
                    json={"track": "manual", "value": {"water_ml": 1500}})
    assert c.status_code == 200 and c.json()["track"] == "manual"


def test_water_completion_writes_real_water_intake(client, auth_user_and_headers, db):
    """双轨写同一份记录:饮水协议完成 → 真实 WaterIntake(手工轨用 value 的量)。"""
    from app.models.daily_health import WaterIntake
    user, h = auth_user_and_headers
    pid = client.post("/api/v1/protocols/seed/water-cup", headers=h).json()["id"]
    client.post(f"/api/v1/protocols/{pid}/complete", headers=h,
                json={"track": "manual", "value": {"volume_ml": 500}})
    rows = db.query(WaterIntake).filter(WaterIntake.user_id == user.id).all()
    assert len(rows) == 1 and rows[0].amount_ml == 500


def test_complete_is_idempotent_per_day(client, auth_user_and_headers, db):
    from app.models.health_protocol import HealthProtocolEvent
    user, h = auth_user_and_headers
    pid = client.post("/api/v1/protocols/seed/water-cup", headers=h).json()["id"]
    client.post(f"/api/v1/protocols/{pid}/complete", headers=h, json={"track": "protocol"})
    client.post(f"/api/v1/protocols/{pid}/complete", headers=h, json={"track": "manual", "value": {"water_ml": 2000}})
    # 每协议每天只一条事件(更新而非新增)
    n = db.query(HealthProtocolEvent).filter(HealthProtocolEvent.protocol_id == pid).count()
    assert n == 1


def test_skip_with_reason_and_flip(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    pid = client.post("/api/v1/protocols/seed/water-cup", headers=h).json()["id"]
    s = client.post(f"/api/v1/protocols/{pid}/skip", headers=h, json={"reason": "too_tired"})
    assert s.status_code == 200 and s.json()["status"] == "skipped" and s.json()["skip_reason"] == "too_tired"
    # 非法原因 → 400
    bad = client.post(f"/api/v1/protocols/{pid}/skip", headers=h, json={"reason": "懒"})
    assert bad.status_code == 400
    # skip 后又完成 → 翻成 completed,仍一条
    c = client.post(f"/api/v1/protocols/{pid}/complete", headers=h, json={"track": "protocol"})
    assert c.json()["status"] == "completed"
    t = client.get("/api/v1/protocols/today", headers=h).json()
    row = next(x for x in t if x["protocol_id"] == pid)
    assert row["today_status"] == "completed"


def test_user_isolation(client, auth_user_and_headers, db):
    from tests.conftest import create_authenticated_user
    user_a, ha = auth_user_and_headers
    pid = client.post("/api/v1/protocols/seed/water-cup", headers=ha).json()["id"]
    _, token_b = create_authenticated_user(db)
    hb = {"Authorization": f"Bearer {token_b}"}
    # B 不能完成 A 的协议
    r = client.post(f"/api/v1/protocols/{pid}/complete", headers=hb, json={"track": "protocol"})
    assert r.status_code == 404
    assert client.get("/api/v1/protocols/me", headers=hb).json() == []
