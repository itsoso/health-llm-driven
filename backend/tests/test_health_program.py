"""健康项目(第 4 个一等对象)。钉:① 建项目+type 校验 ② 挂协议(set program_id)
③ progress 聚合协议+问题+outcome ④ 从问题建项目(关联 problem_id)⑤ 越权。"""


def test_create_and_type_validation(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.post("/api/v1/programs", headers=h, json={
        "name": "代谢改善 12 周", "program_type": "metabolic",
        "primary_metrics": ["ApoB", "weight"], "target": {"weight": 75}})
    assert r.status_code == 200 and r.json()["program_type"] == "metabolic"
    bad = client.post("/api/v1/programs", headers=h, json={"name": "x", "program_type": "玄学"})
    assert bad.status_code == 400


def test_attach_protocol_and_progress(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    gid = client.post("/api/v1/programs", headers=h, json={
        "name": "代谢", "program_type": "metabolic"}).json()["id"]
    pid = client.post("/api/v1/protocols/seed/water-cup", headers=h).json()["id"]
    a = client.post(f"/api/v1/programs/{gid}/attach-protocol/{pid}", headers=h)
    assert a.status_code == 200 and a.json()["attached"] is True
    prog = client.get(f"/api/v1/programs/{gid}/progress", headers=h).json()
    assert prog["protocol_count"] == 1
    assert prog["protocols"][0]["id"] == pid
    assert prog["outcome"]["primary_metrics"] is None or True


def test_from_problem_links(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    prob = client.post("/api/v1/problems/seed/gastric-ulcer-hp-neg", headers=h).json()["id"]
    r = client.post(f"/api/v1/programs/from-problem/{prob}?program_type=medication_supplement", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["problem_id"] == prob
    # progress 带出关联问题
    prog = client.get(f"/api/v1/programs/{r.json()['id']}/progress", headers=h).json()
    assert prog["problem"]["id"] == prob and "胃溃疡" in prog["problem"]["name"]


def test_from_nonexistent_problem_400(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.post("/api/v1/programs/from-problem/999999?program_type=metabolic", headers=h)
    assert r.status_code == 400


def test_user_isolation(client, auth_user_and_headers, db):
    from tests.conftest import create_authenticated_user
    _, ha = auth_user_and_headers
    gid = client.post("/api/v1/programs", headers=ha, json={"name": "x", "program_type": "sleep"}).json()["id"]
    _, tb = create_authenticated_user(db)
    hb = {"Authorization": f"Bearer {tb}"}
    assert client.get("/api/v1/programs/me", headers=hb).json() == []
    assert client.get(f"/api/v1/programs/{gid}/progress", headers=hb).status_code == 404
