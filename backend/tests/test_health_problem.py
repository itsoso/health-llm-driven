"""医学问题登记(R13)。钉:① 登记+risk 校验 ② 胃溃疡 seed(Hp-/红线/随访)
③ P0 排序 ④ 到期随访(within_days + overdue)⑤ 状态 resolve ⑥ 越权。"""


def test_create_and_risk_validation(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.post("/api/v1/problems", headers=h, json={
        "name": "脂肪肝", "risk_level": "P1",
        "diagnosis": {"分型": "MASLD", "evidence_grade": "B"},
        "follow_up": {"next_due": "2026-09-01", "what_to_check": "FibroScan"},
    })
    assert r.status_code == 200 and r.json()["name"] == "脂肪肝"
    bad = client.post("/api/v1/problems", headers=h, json={"name": "x", "risk_level": "P9"})
    assert bad.status_code == 400


def test_seed_gastric_ulcer_hp_negative(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.post("/api/v1/problems/seed/gastric-ulcer-hp-neg", headers=h)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["diagnosis"]["hp_status"] == "negative"        # ← 决定不走根除模板
    assert p["risk_level"] == "P1"
    assert p["follow_up"]["next_due"] == "2026-08-11"
    assert any("黑便" in rl["condition"] or "呕血" in rl["condition"] for rl in p["red_lines"])


def test_list_sorted_p0_first(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    client.post("/api/v1/problems", headers=h, json={"name": "B-P2", "risk_level": "P2"})
    client.post("/api/v1/problems", headers=h, json={"name": "A-P0", "risk_level": "P0"})
    lst = client.get("/api/v1/problems/me", headers=h).json()
    assert lst[0]["risk_level"] == "P0"   # P0 压在前


def test_due_followups_window_and_overdue(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    # 过期项
    client.post("/api/v1/problems", headers=h, json={
        "name": "血脂复查", "follow_up": {"next_due": "2020-01-01", "what_to_check": "ApoB"}})
    # 远期项(胃溃疡 seed next_due 2026-08-11)
    client.post("/api/v1/problems/seed/gastric-ulcer-hp-neg", headers=h)
    # 默认 45 天窗:只命中过期项(远期 ~57 天外)
    due = client.get("/api/v1/problems/due", headers=h).json()
    names = {d["name"] for d in due}
    assert "血脂复查" in names
    overdue = next(d for d in due if d["name"] == "血脂复查")
    assert overdue["overdue"] is True
    # 放宽到 90 天 → 远期胃溃疡也进
    due90 = client.get("/api/v1/problems/due?within_days=90", headers=h).json()
    assert any("胃溃疡" in d["name"] for d in due90)


def test_resolve_removes_from_active(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    pid = client.post("/api/v1/problems", headers=h, json={"name": "临时问题"}).json()["id"]
    client.post(f"/api/v1/problems/{pid}/status?status=resolved", headers=h)
    active = client.get("/api/v1/problems/me", headers=h).json()
    assert all(p["id"] != pid for p in active)


def test_user_isolation(client, auth_user_and_headers, db):
    from tests.conftest import create_authenticated_user
    _, ha = auth_user_and_headers
    pid = client.post("/api/v1/problems/seed/gastric-ulcer-hp-neg", headers=ha).json()["id"]
    _, tb = create_authenticated_user(db)
    hb = {"Authorization": f"Bearer {tb}"}
    assert client.get("/api/v1/problems/me", headers=hb).json() == []
    assert client.post(f"/api/v1/problems/{pid}/status?status=resolved", headers=hb).status_code == 404
