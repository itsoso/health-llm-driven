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
