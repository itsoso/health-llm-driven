"""用药自动驾驶 P0:相对吃饭时点(timing_relation/meal_anchor)。

钉:① 中文时点标签渲染 ② API 写入/读出带时点 ③ today_status 带 timing_label
④ 提醒文案含「饭前/饭后/空腹」(复杂方案如胃溃疡三联无脑化的关键)。
"""
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
