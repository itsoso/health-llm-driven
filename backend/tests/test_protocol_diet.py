"""协议层 × 饮食打通:完成餐模板协议 → 写真实 DietRecord(双轨同源)。

钉:① 建餐模板协议(pre_commit,不可默认完成)② 协议轨完成 → 建 DietRecord(用模板先验热量蛋白)
③ 重复完成不重复写 ④ 手工轨 value 覆盖份量 → DietRecord 用覆盖值。
"""


def _tpl(client, h, **over):
    body = {"name": "Wagas 标准餐", "meal_type": "午餐", "food_items": "鸡胸+蔬菜+糙米",
            "calories": 530, "protein": 40, "carbs": 45, "fat": 14}
    body.update(over)
    return client.post("/api/v1/protocols/meal-template", headers=h, json=body)


def test_create_meal_template_protocol(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = _tpl(client, h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["domain"] == "diet" and body["mechanism"] == "pre_commit"
    assert body["source_model"] == "diet_records"
    assert body["can_default_complete"] is False
    assert body["implied_quantity"]["calories"] == 530


def test_complete_writes_diet_record_once(client, auth_user_and_headers, db):
    from app.models.daily_health import DietRecord
    user, h = auth_user_and_headers
    pid = _tpl(client, h).json()["id"]
    c = client.post(f"/api/v1/protocols/{pid}/complete", headers=h, json={"track": "protocol"})
    assert c.status_code == 200
    recs = db.query(DietRecord).filter(DietRecord.user_id == user.id).all()
    assert len(recs) == 1
    assert recs[0].meal_type == "午餐" and recs[0].calories == 530 and recs[0].protein == 40
    # 重复完成不重复写
    client.post(f"/api/v1/protocols/{pid}/complete", headers=h, json={"track": "manual"})
    assert db.query(DietRecord).filter(DietRecord.user_id == user.id).count() == 1


def test_manual_track_overrides_quantity(client, auth_user_and_headers, db):
    from app.models.daily_health import DietRecord
    user, h = auth_user_and_headers
    pid = _tpl(client, h).json()["id"]
    # 手工轨改份量:只吃半份 → calories 覆盖
    c = client.post(f"/api/v1/protocols/{pid}/complete", headers=h,
                    json={"track": "manual", "value": {"calories": 265, "protein": 20}})
    assert c.status_code == 200
    rec = db.query(DietRecord).filter(DietRecord.user_id == user.id).first()
    assert rec.calories == 265 and rec.protein == 20  # value 覆盖 implied_quantity
    assert rec.meal_type == "午餐"                     # 未覆盖项仍用模板先验
