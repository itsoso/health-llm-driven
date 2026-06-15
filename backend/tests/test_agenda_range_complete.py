"""议程区间视图 + 统一完成路由(R1 补全)。

钉:① /range 列常驻每日协议 + 窗口内复查 ② 窗口外复查不进 ③ /complete 经议程路由完成协议
(写真实记录,today 反映)④ 不支持的来源 400。"""


def test_range_recurring_and_scheduled(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    client.post("/api/v1/protocols/seed/water-cup", headers=h)  # 每日协议
    client.post("/api/v1/problems", headers=h, json={
        "name": "近期复查", "follow_up": {"next_due": "2020-02-02", "what_to_check": "x"}})  # 已逾期(窗口内)
    r = client.get("/api/v1/agenda/range?days=7", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert any(rp["domain"] == "hydration" for rp in body["recurring_protocols"])
    assert any("近期复查" in s["title"] for s in body["scheduled"])


def test_range_excludes_far_checkup(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    client.post("/api/v1/problems", headers=h, json={
        "name": "远期复查", "follow_up": {"next_due": "2027-12-31", "what_to_check": "x"}})
    body = client.get("/api/v1/agenda/range?days=7", headers=h).json()
    assert all("远期复查" not in s["title"] for s in body["scheduled"])


def test_complete_via_agenda_routes_to_protocol(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    pid = client.post("/api/v1/protocols/seed/water-cup", headers=h).json()["id"]
    r = client.post("/api/v1/agenda/complete", headers=h,
                    json={"object_type": "health_protocol", "object_id": pid, "track": "protocol"})
    assert r.status_code == 200 and r.json()["status"] == "completed"
    # today 反映完成
    items = client.get("/api/v1/agenda/today", headers=h).json()["items"]
    assert next(i for i in items if i["type"] == "hydration")["status"] == "completed"


def test_complete_unsupported_source_400(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.post("/api/v1/agenda/complete", headers=h,
                    json={"object_type": "health_problem", "object_id": 1})
    assert r.status_code == 400


def test_complete_nonexistent_protocol_400(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.post("/api/v1/agenda/complete", headers=h,
                    json={"object_type": "health_protocol", "object_id": 999999})
    assert r.status_code == 400
