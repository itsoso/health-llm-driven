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


def test_cadence_weekly_due_until_completed_this_week(client, auth_user_and_headers):
    """周协议:本周未完成→到期;完成后→不到期(掉出议程,下周再现)。"""
    _, h = auth_user_and_headers
    pid = client.post("/api/v1/protocols", headers=h, json={
        "domain": "training", "name": "周一次长跑", "cadence": "weekly",
    }).json()["id"]
    row = next(x for x in client.get("/api/v1/protocols/today", headers=h).json()
               if x["protocol_id"] == pid)
    assert row["is_due_today"] is True
    client.post(f"/api/v1/protocols/{pid}/complete", headers=h, json={"track": "protocol"})
    row = next(x for x in client.get("/api/v1/protocols/today", headers=h).json()
               if x["protocol_id"] == pid)
    assert row["is_due_today"] is False  # 本周已完成


def test_cadence_event_triggered_not_on_daily_calendar(client, auth_user_and_headers):
    """event_triggered 不上每日日历(由事件触发)→ is_due_today=False。"""
    _, h = auth_user_and_headers
    pid = client.post("/api/v1/protocols", headers=h, json={
        "domain": "diet", "name": "饭后散步", "cadence": "event_triggered",
    }).json()["id"]
    row = next(x for x in client.get("/api/v1/protocols/today", headers=h).json()
               if x["protocol_id"] == pid)
    assert row["is_due_today"] is False


def test_self_correction_triggers_on_repeated_skips(client, auth_user_and_headers, db):
    """近 7 天跳过 ≥2 次 → /corrections 出非羞辱式建议(R14)。"""
    user, h = auth_user_and_headers
    pid = client.post("/api/v1/protocols/seed/water-cup", headers=h).json()["id"]
    from datetime import date, timedelta
    from app.services import health_protocol_service as svc

    # 还没跳过 → 无建议
    assert client.get("/api/v1/protocols/corrections", headers=h).json()["skip_based"] == []

    # 跳过昨天 + 今天(同因 no_supply)。skip_protocol 支持 day 参数,直接落两天事件。
    svc.skip_protocol(db, pid, user.id, reason="no_supply", day=date.today() - timedelta(days=1))
    svc.skip_protocol(db, pid, user.id, reason="no_supply", day=date.today())
    db.commit()

    corr = client.get("/api/v1/protocols/corrections", headers=h).json()["skip_based"]
    assert len(corr) == 1
    assert corr[0]["skip_count"] == 2
    assert corr[0]["dominant_reason"] == "no_supply"
    assert "不是你的错" in corr[0]["message"]          # 非羞辱式措辞
    assert "耗材" in corr[0]["suggestion"]             # no_supply → 查耗材

    # 也进今日议程(advisory correction 项)
    items = client.get("/api/v1/agenda/today", headers=h).json()["items"]
    assert any(i["type"] == "correction" for i in items)


def _add_weights(db, user_id, weights, *, height=None, base_days=12):
    from datetime import date, timedelta
    from app.models.basic_health import BasicHealthData
    n = len(weights)
    for i, w in enumerate(weights):
        # 均匀铺在 base_days 天窗口内
        day = date.today() - timedelta(days=int(base_days * (n - 1 - i) / (n - 1)))
        db.add(BasicHealthData(user_id=user_id, weight=w, height=height, record_date=day))
    db.commit()


def test_outcome_correction_weight_uptrend(client, auth_user_and_headers, db):
    """体重均线上升(首/尾 3 日均值差 ≥1kg)→ outcome 纠偏,措辞不开方(defer 专业)。"""
    user, h = auth_user_and_headers
    # 6 点,首3均值≈70.2 → 尾3均值≈71.7,change≈1.5kg,跨 12 天;height 170→BMI~24(正常)
    _add_weights(db, user.id, [70.0, 70.2, 70.4, 71.5, 71.7, 72.0], height=170.0)
    out = client.get("/api/v1/protocols/corrections", headers=h).json()["outcome_based"]
    weight = next(c for c in out if c["kind"] == "weight_uptrend")
    assert weight["abs_change"] >= 1.0
    # 不主动给「降热量」方向,只 defer 专业
    assert "热量" not in weight["message"]
    assert "医生" in weight["suggestion"] or "营养" in weight["suggestion"]


def test_outcome_correction_weight_noise_no_trigger(client, auth_user_and_headers, db):
    """带噪声的平坦体重序列(首尾均值近似)→ 不触发(防假阳性)。"""
    user, h = auth_user_and_headers
    # height 170(BMI 正常,排除门控干扰)→ 纯验噪声过滤:首3≈70.0 尾3≈70.07
    _add_weights(db, user.id, [70.0, 71.0, 69.0, 70.5, 69.5, 70.2], height=170.0)
    out = client.get("/api/v1/protocols/corrections", headers=h).json()["outcome_based"]
    assert not any(c["kind"] == "weight_uptrend" for c in out)


def test_outcome_correction_degrades_on_query_error(client, auth_user_and_headers, monkeypatch):
    """体重查询抛错 → outcome 降级(不 500),且 except 处理器自身不再 NameError。"""
    _, h = auth_user_and_headers
    import app.services.protocol_self_correction as psc

    def _boom(*a, **k):
        raise RuntimeError("db blip")
    # 让体重分支炸,验证整条 /corrections 仍 200(降级)
    monkeypatch.setattr(psc, "_has_ed_or_lowweight_problem", _boom)
    r = client.get("/api/v1/protocols/corrections", headers=h)
    assert r.status_code == 200
    assert "outcome_based" in r.json()


def test_outcome_correction_weight_gated_for_low_bmi(client, auth_user_and_headers, db):
    """低 BMI 用户即使体重上升也不给减重相关建议(安全门控)。"""
    user, h = auth_user_and_headers
    # height 180cm, 体重 ~58→60kg → BMI ~18,上升但应被门控
    _add_weights(db, user.id, [58.0, 58.3, 58.6, 59.4, 59.7, 60.0], height=180.0)
    out = client.get("/api/v1/protocols/corrections", headers=h).json()["outcome_based"]
    assert not any(c["kind"] == "weight_uptrend" for c in out)


def test_period_start_boundaries():
    """_period_start:周/月/季/年 边界。"""
    from datetime import date
    from app.services.health_protocol_service import _period_start
    d = date(2026, 6, 15)  # 周一? 2026-06-15 是周一
    assert _period_start("weekly", d) == date(2026, 6, 15)
    assert _period_start("monthly", d) == date(2026, 6, 1)
    assert _period_start("quarterly", d) == date(2026, 4, 1)   # Q2 首月
    assert _period_start("annual", d) == date(2026, 1, 1)
    assert _period_start("daily", d) is None


def test_medical_source_model_must_match_domain(client, auth_user_and_headers):
    """防御纵深:医疗级 source_model 不得借非医疗 domain 绕过语音/R4 白名单。

    错配协议 {domain:"hydration", source_model:"medication_logs"} 会以 type:"hydration"
    过 Rokid 语音「确认」门,完成时却落真实 MedicationLog → 创建处必须 400 拒绝。
    """
    _, h = auth_user_and_headers
    # hydration + medication_logs → 拒绝
    bad = client.post("/api/v1/protocols", headers=h, json={
        "domain": "hydration", "name": "伪装成饮水的服药",
        "source_model": "medication_logs", "source_id": 1,
    })
    assert bad.status_code == 400, bad.text
    assert "medication_logs" in bad.json()["detail"]

    # 同样钉补剂 / 饮食错配
    bad2 = client.post("/api/v1/protocols", headers=h, json={
        "domain": "sleep", "name": "伪装成睡眠的补剂",
        "source_model": "supplement_records", "source_id": 1,
    })
    assert bad2.status_code == 400, bad2.text
    bad3 = client.post("/api/v1/protocols", headers=h, json={
        "domain": "mood", "name": "伪装成心情的饮食", "source_model": "diet_records",
    })
    assert bad3.status_code == 400, bad3.text

    # 正确配对仍放行(medication+medication_logs)
    ok = client.post("/api/v1/protocols", headers=h, json={
        "domain": "medication", "name": "正常服药协议",
        "source_model": "medication_logs", "source_id": 1,
    })
    assert ok.status_code == 200, ok.text
    assert ok.json()["domain"] == "medication"

    # 非医疗 source_model(water_records)不受此门约束,任意域放行
    ok2 = client.post("/api/v1/protocols", headers=h, json={
        "domain": "hydration", "name": "正常饮水协议", "source_model": "water_records",
    })
    assert ok2.status_code == 200, ok2.text


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
