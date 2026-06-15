"""统一健康议程投影(R1)。钉:① 协议待办进议程 ② 到期复查进议程
③ 完成的协议状态正确 ④ 高优先级(复查/P1)排在前 ⑤ 空态。"""


def test_empty_agenda(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.get("/api/v1/agenda/today", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 0 and r.json()["items"] == []


def test_protocol_appears_in_agenda(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    client.post("/api/v1/protocols/seed/water-cup", headers=h)
    items = client.get("/api/v1/agenda/today", headers=h).json()["items"]
    water = next(i for i in items if i["type"] == "hydration")
    assert water["status"] == "pending"
    assert water["source"]["object_type"] == "health_protocol"


def test_completed_protocol_status_reflected(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    pid = client.post("/api/v1/protocols/seed/water-cup", headers=h).json()["id"]
    client.post(f"/api/v1/protocols/{pid}/complete", headers=h, json={"track": "protocol"})
    items = client.get("/api/v1/agenda/today", headers=h).json()["items"]
    assert next(i for i in items if i["type"] == "hydration")["status"] == "completed"


def test_due_checkup_in_agenda_and_priority(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    # 过期复查(过去日期)
    client.post("/api/v1/problems", headers=h, json={
        "name": "血脂复查", "risk_level": "P1",
        "follow_up": {"next_due": "2020-01-01", "what_to_check": "ApoB"}})
    # 一个普通协议
    client.post("/api/v1/protocols/seed/water-cup", headers=h)
    items = client.get("/api/v1/agenda/today", headers=h).json()["items"]
    checkup = next(i for i in items if i["type"] == "checkup")
    assert checkup["status"] == "overdue"
    assert checkup["source"]["object_type"] == "health_problem"
    # 复查(P1,priority 95)排在饮水协议(50)前面
    assert items[0]["type"] == "checkup"


def test_training_light_skipped_when_no_signal(monkeypatch):
    """无任何恢复/负荷信号(zone=unknown 且无 acwr)→ 不投训练灯(不假装黄灯)。"""
    from app.services import agenda_service
    monkeypatch.setattr(agenda_service, "training_decision",
                        lambda db, uid: {"zone": "unknown", "light": "yellow"},
                        raising=False)
    # training_decision 在函数内部 import,需 patch 源模块
    import app.services.recovery_decision as rd
    monkeypatch.setattr(rd, "training_decision",
                        lambda db, uid: {"zone": "unknown", "light": "yellow"})
    assert agenda_service._training_item(None, 1) is None


def test_training_light_projected_when_signal_present(monkeypatch):
    """有恢复信号 → 投只读训练灯项(status=info,带灯色/分数,不可完成)。"""
    from app.services import agenda_service
    import app.services.recovery_decision as rd
    monkeypatch.setattr(rd, "training_decision", lambda db, uid: {
        "zone": "rest", "light": "red", "readiness_score": 38,
        "next_action": "今天以休息为主", "reasons": ["恢复就绪度 38/100"],
        "confidence": 0.7,
    })
    item = agenda_service._training_item(None, 7)
    assert item is not None
    assert item["type"] == "training" and item["status"] == "info"
    assert item["light"] == "red" and item["readiness_score"] == 38
    assert item["priority"] == 90  # red 抬到复查档
    assert item["source"]["object_type"] == "training_decision"


def _twin_with_divergence(*divs):
    from app.twin.schema import HealthTwin, TwinMeta, CrossSourceDivergence
    from datetime import datetime
    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    twin.physiological.device_agreement_index = 0.6
    twin.physiological.device_sources = ["garmin", "ringconn"]
    twin.physiological.divergent_metrics = [
        CrossSourceDivergence(metric=m, label=lbl, trusted_source="garmin",
                              outlier_source="ringconn", deviation_pct=18.0,
                              hint=f"{lbl} 差异较大")
        for m, lbl in divs
    ]
    return twin


def test_data_quality_item_when_divergence(monkeypatch):
    """跨源偏离 → 议程出 data_quality 提示项(只读,不可完成)。"""
    from app.services import agenda_service
    import app.twin.builder as builder
    monkeypatch.setattr(builder, "build_twin",
                        lambda db, uid, use_cache=True: _twin_with_divergence(
                            ("resting_heart_rate", "静息心率"), ("hrv", "HRV")))
    item = agenda_service._data_quality_item(None, 1)
    assert item is not None
    assert item["type"] == "data_quality" and item["status"] == "info"
    assert "静息心率" in item["title"] and "等 2 项" in item["title"]
    assert len(item["divergent_metrics"]) == 2
    assert item["source"]["object_type"] == "data_quality"


def test_data_quality_item_none_when_no_divergence(monkeypatch):
    from app.services import agenda_service
    import app.twin.builder as builder
    monkeypatch.setattr(builder, "build_twin",
                        lambda db, uid, use_cache=True: _twin_with_divergence())
    assert agenda_service._data_quality_item(None, 1) is None
