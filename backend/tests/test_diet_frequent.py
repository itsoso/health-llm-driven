"""GET /diet/records/me/frequent —— "常吃"食物聚合的回归测试 (P1-b 一键复用)."""
import uuid
from datetime import date, timedelta

import pytest

from app.models.user import User
from app.models.daily_health import DietRecord


@pytest.fixture
def auth(client, db):
    user = User(
        username=f"freq_{uuid.uuid4().hex[:6]}",
        email=f"freq_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="freq",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(user.id)})
    return user, {"Authorization": f"Bearer {token}"}


def _seed(db, user_id, food, meal, days_ago, *, calories=None, protein=None):
    db.add(DietRecord(
        user_id=user_id,
        record_date=date.today() - timedelta(days=days_ago),
        meal_type=meal,
        food_items=food,
        calories=calories,
        protein=protein,
    ))
    db.commit()


def _get(client, headers, **params):
    resp = client.get("/api/v1/diet/records/me/frequent", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_empty_when_no_records(client, auth, db):
    _user, headers = auth
    assert _get(client, headers) == []


def test_orders_by_frequency_desc(client, auth, db):
    user, headers = auth
    for d in range(3):
        _seed(db, user.id, "鸡胸肉 200g", "lunch", d)        # 3 次
    for d in range(2):
        _seed(db, user.id, "燕麦粥", "breakfast", d)           # 2 次
    _seed(db, user.id, "牛排", "dinner", 0)                    # 1 次

    items = _get(client, headers)
    assert [i["food_items"] for i in items] == ["鸡胸肉 200g", "燕麦粥", "牛排"]
    assert items[0]["count"] == 3
    assert items[0]["meal_type"] == "lunch"


def test_median_nutrition_across_history(client, auth, db):
    user, headers = auth
    # 同一食物三次, 蛋白 [20, 30, 40] → 中位数 30; 卡路里 [100, None, 300] → 中位数 200
    _seed(db, user.id, "蛋白餐", "lunch", 0, calories=100, protein=20)
    _seed(db, user.id, "蛋白餐", "lunch", 1, calories=None, protein=30)
    _seed(db, user.id, "蛋白餐", "lunch", 2, calories=300, protein=40)

    item = _get(client, headers)[0]
    assert item["protein"] == 30
    assert item["calories"] == 200


def test_null_nutrition_not_fabricated(client, auth, db):
    user, headers = auth
    _seed(db, user.id, "无营养记录的食物", "snack", 0)  # 全 None
    item = _get(client, headers)[0]
    assert item["calories"] is None
    assert item["protein"] is None


def test_respects_limit_and_window(client, auth, db):
    user, headers = auth
    for i in range(5):
        _seed(db, user.id, f"食物{i}", "lunch", 0)
    _seed(db, user.id, "太久以前", "lunch", 200)  # 超出 30 天窗口

    items = _get(client, headers, limit=3, days=30)
    assert len(items) == 3
    assert all(i["food_items"] != "太久以前" for i in items)


def test_user_isolation(client, auth, db):
    user, headers = auth
    # 另一个用户的记录不应出现
    other = User(
        username=f"other_{uuid.uuid4().hex[:6]}",
        email=f"other_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x", name="o", is_active=True, is_approved=True,
    )
    db.add(other)
    db.commit()
    db.refresh(other)
    _seed(db, other.id, "别人的菜", "lunch", 0)
    _seed(db, user.id, "我的菜", "lunch", 0)

    items = _get(client, headers)
    assert [i["food_items"] for i in items] == ["我的菜"]


def test_blank_food_items_skipped(client, auth, db):
    user, headers = auth
    _seed(db, user.id, "   ", "lunch", 0)  # 纯空白
    _seed(db, user.id, "正常菜", "lunch", 0)
    items = _get(client, headers)
    assert [i["food_items"] for i in items] == ["正常菜"]


def test_requires_auth(client):
    resp = client.get("/api/v1/diet/records/me/frequent")
    assert resp.status_code in (401, 403)
