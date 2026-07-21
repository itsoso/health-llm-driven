"""用药自动驾驶 P0:相对吃饭时点(timing_relation/meal_anchor)。

钉:① 中文时点标签渲染 ② API 写入/读出带时点 ③ today_status 带 timing_label
④ 提醒文案含「饭前/饭后/空腹」(复杂方案如胃溃疡三联无脑化的关键)。
"""
import app.services.medication_safety as medication_safety
from app.agents.safety_guardian.schema import Alert, Severity
from app.models.medication import medication_timing_label


# ── 纯函数:时点 → 中文执行指令 ──────────────────────────────
def test_label_empty_stomach_no_meal():
    assert medication_timing_label("empty_stomach") == "空腹"
    # 空腹不挂餐次
    assert medication_timing_label("empty_stomach", "breakfast") == "空腹"


def test_label_before_meal_with_anchor():
    assert medication_timing_label("before_meal_30", "breakfast") == "早餐前30分钟"
    assert medication_timing_label("before_meal", "dinner") == "晚餐前"
    assert medication_timing_label("after_meal", "lunch") == "午餐后"


def test_label_before_meal_without_anchor():
    assert medication_timing_label("before_meal_30") == "饭前30分钟"
    assert medication_timing_label("after_meal") == "饭后"


def test_label_bedtime_and_anytime_and_empty():
    assert medication_timing_label("bedtime", "dinner") == "睡前"  # 睡前不挂餐次
    assert medication_timing_label("anytime") == ""
    assert medication_timing_label(None) == ""
    assert medication_timing_label("不认识的值") == ""


# ── API:写入带时点 → 读出带 timing_label ──────────────────
def test_create_medication_with_timing_roundtrips(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.post("/api/v1/medication/medications", headers=h, json={
        "name": "雷贝拉唑", "dosage": "10mg", "times_per_day": 2,
        "reminder_times": ["07:00", "19:00"],
        "timing_relation": "before_meal_30", "meal_anchor": "breakfast",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["timing_relation"] == "before_meal_30"
    assert body["meal_anchor"] == "breakfast"
    assert body["timing_label"] == "早餐前30分钟"


def test_today_status_carries_timing_label(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    client.post("/api/v1/medication/medications", headers=h, json={
        "name": "阿莫西林", "dosage": "1000mg", "times_per_day": 2,
        "timing_relation": "after_meal",
    })
    r = client.get("/api/v1/medication/today/me", headers=h)
    assert r.status_code == 200, r.text
    items = r.json()
    amox = next(i for i in items if i["name"] == "阿莫西林")
    assert amox["timing_relation"] == "after_meal"
    assert amox["timing_label"] == "饭后"


def test_medication_without_timing_is_backward_compatible(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.post("/api/v1/medication/medications", headers=h, json={
        "name": "维生素C", "dosage": "1片",
    })
    assert r.status_code == 200, r.text
    # 无时点 → label 空串,不报错
    assert r.json()["timing_label"] == ""


def test_create_medication_returns_medication_safety_alerts(client, auth_user_and_headers, monkeypatch):
    """录入药物后立刻返回 PGx/DDI/DSI 提醒,但不混入非用药类安全提醒。

    A3 迁移后:预检不再走 build_twin,改用 evaluate_rules_with_status(传入 db 填好的
    极简 twin)。这里 patch 规则引擎 seam,验证 category 过滤(pgx 保留 / vitals 滤掉)+
    failed_count=0 时不注入 fail-safe advisory。
    """
    _, h = auth_user_and_headers

    def fake_evaluate_rules_with_status(twin):
        return ([
            Alert(
                rule_id="pgx.cpic.tpmt_硫唑嘌呤",
                category="pgx",
                severity=Severity.CRITICAL,
                title="TPMT × 硫唑嘌呤 —— CPIC 药物基因组提示",
                message="TPMT 低活性携带者使用硫唑嘌呤风险升高。",
                action="请与医生确认基因检测结果和剂量方案。",
                requires_medical_attention=True,
            ),
            Alert(
                rule_id="vitals.bp_crisis",
                category="vitals",
                severity=Severity.CRITICAL,
                title="血压危象",
                message="这不是用药录入响应应该混入的提醒。",
            ),
        ], 0)

    monkeypatch.setattr(
        medication_safety,
        "evaluate_rules_with_status",
        fake_evaluate_rules_with_status,
        raising=True,
    )

    r = client.post("/api/v1/medication/medications", headers=h, json={
        "name": "硫唑嘌呤", "dosage": "50mg",
    })
    assert r.status_code == 200, r.text

    body = r.json()
    assert [a["rule_id"] for a in body["safety_alerts"]] == ["pgx.cpic.tpmt_硫唑嘌呤"]
    assert body["safety_alerts"][0]["severity"]["label"] == "critical"


def test_list_and_get_medications_include_safety_alerts(client, auth_user_and_headers, monkeypatch):
    """客户端重进页面/打开详情时也必须能拿到用药安全提醒,不能只在新增/更新响应里出现。"""
    _, h = auth_user_and_headers

    def fake_evaluate_rules_with_status(twin):
        return ([
            Alert(
                rule_id="ddi.warfarin_bleeding",
                category="ddi",
                severity=Severity.CRITICAL,
                title="华法林相互作用",
                message="出血风险升高。",
            ),
        ], 0)

    monkeypatch.setattr(
        medication_safety,
        "evaluate_rules_with_status",
        fake_evaluate_rules_with_status,
        raising=True,
    )

    created = client.post("/api/v1/medication/medications", headers=h, json={"name": "华法林"})
    assert created.status_code == 200, created.text
    med_id = created.json()["id"]

    list_body = client.get("/api/v1/medication/medications/me", headers=h).json()
    detail_body = client.get(f"/api/v1/medication/medications/{med_id}", headers=h).json()

    assert [a["rule_id"] for a in list_body[0]["safety_alerts"]] == ["ddi.warfarin_bleeding"]
    assert [a["rule_id"] for a in detail_body["safety_alerts"]] == ["ddi.warfarin_bleeding"]
