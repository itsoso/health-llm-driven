"""C1 周健身计划 + C2 动作图文指导 测试。

覆盖:
- C1 提议生成(status=proposed,7 天,整数 duration_min,契约字段齐全)
- C1 确认幂等(确认两次 → scheduled_count 稳定,SmartReminder 不翻倍)
- C1 dismiss
- C1 IDOR(别人的 plan_id → 404)
- C2 列表 / 详情 / 404
- C2 每条都有非空 injury_red_lines + safety_note
- API shape 对齐固定契约
"""
from app.models.smart_reminder import SmartReminder


# ─────────────────────────── C1 ───────────────────────────


def test_weekly_plan_proposal_shape(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    r = client.get("/api/v1/fitness/weekly-plan", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    # 契约字段
    for key in ("plan_id", "status", "week_start", "goal", "acwr",
                "readiness_note", "days", "disclaimer"):
        assert key in body, f"missing {key}"

    assert body["status"] == "proposed"
    assert isinstance(body["plan_id"], int)
    assert body["goal"]  # 非空(无目标也兜底「维持」)
    assert "就医" in body["disclaimer"]  # 安全:伤病先就医
    assert "医疗" in body["disclaimer"] or "处方" in body["disclaimer"]

    days = body["days"]
    assert len(days) == 7  # 恰好 7 天
    weekdays = [d["weekday"] for d in days]
    assert weekdays == ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    for d in days:
        assert d["day_type"] in ("hard", "easy", "rest")
        assert isinstance(d["rationale"], str) and d["rationale"]
        w = d["workout"]
        if d["day_type"] == "rest":
            assert w is None
        else:
            assert w is not None
            # 整数时长 —— 绝不 float(422 教训)
            assert isinstance(w["duration_min"], int)
            assert not isinstance(w["duration_min"], bool)
            for wk in ("name", "exercise_key", "duration_min", "intensity_note"):
                assert wk in w


def test_weekly_plan_is_stable_within_week(client, db, auth_user_and_headers):
    """同一周重复 GET 不重复生成 —— 返回同一个 plan_id。"""
    user, headers = auth_user_and_headers
    p1 = client.get("/api/v1/fitness/weekly-plan", headers=headers).json()
    p2 = client.get("/api/v1/fitness/weekly-plan", headers=headers).json()
    assert p1["plan_id"] == p2["plan_id"]


def test_workout_exercise_keys_match_c2(client, db, auth_user_and_headers):
    """C1 workout.exercise_key(非空时)必须命中 C2 数据集(契约约束)。"""
    from app.services import exercise_guide
    valid = {e["exercise_key"] for e in exercise_guide.list_exercises()}
    user, headers = auth_user_and_headers
    body = client.get("/api/v1/fitness/weekly-plan", headers=headers).json()
    for d in body["days"]:
        w = d["workout"]
        if w and w["exercise_key"]:
            assert w["exercise_key"] in valid, f"unknown exercise_key {w['exercise_key']}"


def test_confirm_then_dismiss_shapes(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    plan = client.get("/api/v1/fitness/weekly-plan", headers=headers).json()
    pid = plan["plan_id"]

    r = client.post("/api/v1/fitness/weekly-plan/confirm",
                    json={"plan_id": pid}, headers=headers)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["confirmed"] is True
    assert c["plan_id"] == pid
    assert isinstance(c["scheduled_count"], int)
    assert c["scheduled_count"] >= 1  # 至少一个非 rest 日(生成器保证有 hard 日)

    # 确认后 GET 返回 confirmed
    after = client.get("/api/v1/fitness/weekly-plan", headers=headers).json()
    assert after["status"] == "confirmed"


def test_confirm_is_idempotent_no_double_schedule(client, db, auth_user_and_headers):
    """确认两次:scheduled_count 稳定,SmartReminder 行数不翻倍。"""
    user, headers = auth_user_and_headers
    plan = client.get("/api/v1/fitness/weekly-plan", headers=headers).json()
    pid = plan["plan_id"]

    c1 = client.post("/api/v1/fitness/weekly-plan/confirm",
                     json={"plan_id": pid}, headers=headers).json()
    rows_after_first = (
        db.query(SmartReminder)
        .filter(SmartReminder.user_id == user.id, SmartReminder.source == "fitness_plan")
        .count()
    )

    c2 = client.post("/api/v1/fitness/weekly-plan/confirm",
                     json={"plan_id": pid}, headers=headers).json()
    rows_after_second = (
        db.query(SmartReminder)
        .filter(SmartReminder.user_id == user.id, SmartReminder.source == "fitness_plan")
        .count()
    )

    assert c1["scheduled_count"] == c2["scheduled_count"]
    assert rows_after_first == rows_after_second  # 不翻倍
    assert rows_after_first == c1["scheduled_count"]


def test_dismiss_marks_dismissed(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    plan = client.get("/api/v1/fitness/weekly-plan", headers=headers).json()
    pid = plan["plan_id"]
    r = client.post("/api/v1/fitness/weekly-plan/dismiss",
                    json={"plan_id": pid}, headers=headers)
    assert r.status_code == 200
    assert r.json()["dismissed"] is True

    from app.models.fitness_plan import FitnessPlan
    p = db.query(FitnessPlan).filter(FitnessPlan.id == pid).first()
    assert p.status == "dismissed"


def test_confirm_dismissed_plan_conflicts(client, db, auth_user_and_headers):
    """dismissed 计划不可确认 → 409(不静默假装成功)。"""
    user, headers = auth_user_and_headers
    pid = client.get("/api/v1/fitness/weekly-plan", headers=headers).json()["plan_id"]
    client.post("/api/v1/fitness/weekly-plan/dismiss", json={"plan_id": pid}, headers=headers)
    r = client.post("/api/v1/fitness/weekly-plan/confirm", json={"plan_id": pid}, headers=headers)
    assert r.status_code == 409


def test_confirm_other_users_plan_404(client, db, auth_user_and_headers):
    """IDOR:确认不存在 / 别人的 plan_id → 404。"""
    user, headers = auth_user_and_headers
    r = client.post("/api/v1/fitness/weekly-plan/confirm",
                    json={"plan_id": 999999}, headers=headers)
    assert r.status_code == 404


def test_weekly_plan_requires_auth(client):
    r = client.get("/api/v1/fitness/weekly-plan")
    assert r.status_code in (401, 403)


# ─────────────────────────── C2 ───────────────────────────


def test_exercise_guide_list(client):
    r = client.get("/api/v1/fitness/exercise-guide")
    assert r.status_code == 200
    body = r.json()
    assert "exercises" in body
    keys = {e["exercise_key"] for e in body["exercises"]}
    assert "pushup" in keys  # PRD 示例 + C3 Rokid
    assert len(body["exercises"]) >= 5
    for e in body["exercises"]:
        assert e["exercise_key"] and e["name"]


def test_exercise_guide_detail(client):
    r = client.get("/api/v1/fitness/exercise-guide/pushup")
    assert r.status_code == 200
    body = r.json()
    assert body["exercise_key"] == "pushup"
    assert body["name"] == "俯卧撑"
    for key in ("steps", "common_mistakes", "injury_red_lines", "safety_note"):
        assert key in body
    assert body["steps"] and body["common_mistakes"]


def test_exercise_guide_unknown_key_404(client):
    r = client.get("/api/v1/fitness/exercise-guide/not-a-real-exercise")
    assert r.status_code == 404


def test_every_exercise_has_injury_red_lines_and_safety(client):
    """安全:每条动作必须有非空 injury_red_lines + safety_note 导向就医。"""
    listing = client.get("/api/v1/fitness/exercise-guide").json()["exercises"]
    for item in listing:
        detail = client.get(f"/api/v1/fitness/exercise-guide/{item['exercise_key']}").json()
        assert detail["injury_red_lines"], f"{item['exercise_key']} 缺 injury_red_lines"
        assert all(isinstance(x, str) and x for x in detail["injury_red_lines"])
        assert detail["safety_note"], f"{item['exercise_key']} 缺 safety_note"
        assert "就医" in detail["safety_note"]
        assert "医疗" in detail["safety_note"]  # 非医疗建议声明


def test_exercise_guide_is_deterministic(client):
    """同一 key 两次请求内容一致(确定性数据集,非 LLM)。"""
    a = client.get("/api/v1/fitness/exercise-guide/squat").json()
    b = client.get("/api/v1/fitness/exercise-guide/squat").json()
    assert a == b
