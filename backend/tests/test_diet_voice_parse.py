"""语音食物解析(Apple Watch Companion / R5)。

钉:规则层(餐次/风险标签)、记忆层(常吃营养补全)、LLM 层(可注入)、
降级(LLM 空→单食物低置信)、缺量→needs_confirmation+澄清问题、API 走通(降级)。
"""
import asyncio
import uuid
from datetime import date, timedelta

import pytest

from app.models.daily_health import DietRecord
from app.models.food_nutrition import FoodItem as FoodCatalogItem, FoodNutrient
from app.models.user import User
from app.services import diet_voice_parser as dvp


@pytest.fixture
def auth(client, db):
    user = User(username=f"vp_{uuid.uuid4().hex[:6]}", email=f"vp_{uuid.uuid4().hex[:6]}@x.com",
                hashed_password="x", name="vp", is_active=True, is_approved=True)
    db.add(user); db.commit(); db.refresh(user)
    from app.services.auth import auth_service
    return user, {"Authorization": f"Bearer {auth_service.create_access_token({'sub': str(user.id)})}"}


# ── 规则层 ──
def test_infer_meal_type_keyword_beats_hour():
    assert dvp.infer_meal_type("早上吃了两个包子", hour=20) == "breakfast"


def test_infer_meal_type_by_hour():
    assert dvp.infer_meal_type("两个包子", hour=8) == "breakfast"
    assert dvp.infer_meal_type("一碗面", hour=12) == "lunch"
    assert dvp.infer_meal_type("烧烤", hour=23) == "snack"


def test_detect_risk_tags():
    assert "alcohol" in dvp.detect_risk_tags("喝了两瓶啤酒")
    assert "sweet_drink" in dvp.detect_risk_tags("一杯奶茶")
    assert dvp.detect_risk_tags("白米饭") == []


# ── 服务层(LLM 注入)──
def _run(coro):
    return asyncio.run(coro)


def _stub(foods, conf):
    async def fn(db, uid, raw):
        return foods, conf
    return fn


def test_parse_high_conf_no_confirmation(db, auth):
    user, _ = auth
    foods = [{"name": "鸡胸肉沙拉", "quantity": 1, "unit": "份", "calories": 300, "protein": 30}]
    draft = _run(dvp.parse_voice_food(db, user.id, "午餐吃了鸡胸肉沙拉", llm_parse=_stub(foods, 0.9)))
    assert draft["meal_type"] == "lunch"
    assert draft["meal_type_label"] == "午餐"
    assert draft["confidence"] == 0.9
    assert draft["needs_confirmation"] is False
    assert draft["clarifying_question"] is None
    assert draft["parser_version"] == dvp.PARSER_VERSION


def test_parse_missing_quantity_asks(db, auth):
    user, _ = auth
    async def stub(db, uid, raw):
        return [{"name": "红烧肉", "quantity": None, "unit": None, "calories": None}], 0.8
    draft = _run(dvp.parse_voice_food(db, user.id, "吃了红烧肉", llm_parse=stub))
    assert draft["needs_confirmation"] is True
    assert "红烧肉" in draft["clarifying_question"]


def test_memory_enriches_missing_nutrition(db, auth):
    user, _ = auth
    # 常吃:鸡胸肉 出现 2 次,中位 calories=200
    for d in (3, 6):
        db.add(DietRecord(user_id=user.id, record_date=date.today() - timedelta(days=d),
                          meal_type="午餐", food_name="鸡胸肉", calories=200.0, protein=25.0))
    db.commit()
    foods = [{"name": "鸡胸肉", "quantity": 1, "unit": "份", "calories": None, "protein": None}]
    draft = _run(dvp.parse_voice_food(db, user.id, "吃了鸡胸肉", llm_parse=_stub(foods, 0.9)))
    f = draft["foods"][0]
    assert f["calories"] == 200.0 and f["protein"] == 25.0   # 记忆层补全


def test_food_table_enriches_missing_nutrition_before_memory(db, auth):
    user, _ = auth
    db.add(FoodCatalogItem(
        food_id="cfc:chicken_breast",
        canonical_name="鸡胸肉",
        aliases=["鸡胸肉", "鸡肉"],
        calibration_names=["鸡胸肉"],
        locale="zh-CN",
        source="china_food_composition",
        source_ref="test-fixture",
    ))
    db.add(FoodNutrient(
        food_id="cfc:chicken_breast",
        kcal_per_100g=165.0,
        protein_g_per_100g=31.0,
        carbs_g_per_100g=0.0,
        fat_g_per_100g=3.6,
        fiber_g_per_100g=0.0,
        source="china_food_composition",
        source_ref="test-fixture",
    ))
    for d in (3, 6):
        db.add(DietRecord(user_id=user.id, record_date=date.today() - timedelta(days=d),
                          meal_type="lunch", food_name="鸡胸肉", calories=999.0, protein=1.0))
    db.commit()

    foods = [{"name": "鸡胸肉", "quantity": 150, "unit": "g", "calories": None, "protein": None}]
    draft = _run(dvp.parse_voice_food(db, user.id, "午餐吃了鸡胸肉 150g", llm_parse=_stub(foods, 0.9)))

    f = draft["foods"][0]
    assert f["food_id"] == "cfc:chicken_breast"
    assert f["source"] == "china_food_composition"
    assert f["calories"] == 247.5
    assert f["protein"] == 46.5
    assert f["fat"] == 5.4


def test_degrade_when_llm_empty(db, auth):
    user, _ = auth
    draft = _run(dvp.parse_voice_food(db, user.id, "随便吃了点东西", llm_parse=_stub([], None)))
    assert len(draft["foods"]) == 1                    # 整段当单食物
    assert draft["confidence"] == 0.2
    assert draft["needs_confirmation"] is True


# ── fast-tier provider 选择(腕上简单记录走最快可靠工具模型)──
def test_fast_provider_uses_fast_tier_model(db, auth, monkeypatch):
    """快路径:拿到 fast-tier model id → 走 create_provider_for_model_id,不碰激活模型工厂。"""
    from app.services.llm import factory as llm_factory
    from app.services.llm import model_registry as reg

    picked = {}
    monkeypatch.setattr(reg, "pick_fast_tool_model_id", lambda **_k: "deepseek-v4-flash")

    def fake_for_model_id(model_id):
        picked["model_id"] = model_id
        return object()

    def boom_for_user(*a, **k):  # 若误走激活模型工厂即失败
        raise AssertionError("fast 路径不应调用 create_provider_for_user")

    monkeypatch.setattr(llm_factory, "create_provider_for_model_id", fake_for_model_id)
    monkeypatch.setattr(llm_factory, "create_provider_for_user", boom_for_user)

    provider = dvp._fast_provider(auth[0].id, db)
    assert picked["model_id"] == "deepseek-v4-flash"
    assert provider is not None


def test_fast_provider_failsoft_falls_back_to_active(db, auth, monkeypatch):
    """fail-soft:快模型创建失败 → 回退 create_provider_for_user,记餐链路不断。"""
    from app.services.llm import factory as llm_factory
    from app.services.llm import model_registry as reg

    monkeypatch.setattr(reg, "pick_fast_tool_model_id", lambda **_k: "deepseek-v4-flash")

    def boom_for_model_id(model_id):
        raise ValueError("fast env 缺")

    sentinel = object()
    monkeypatch.setattr(llm_factory, "create_provider_for_model_id", boom_for_model_id)
    monkeypatch.setattr(llm_factory, "create_provider_for_user", lambda uid, database: sentinel)

    provider = dvp._fast_provider(auth[0].id, db)
    assert provider is sentinel   # 回退到激活模型 provider


# ── API(显式 mock LLM 空结果 → 降级路径,仍 200)──
def test_api_voice_parse_degraded_path(client, auth, monkeypatch):
    _, headers = auth

    async def empty_llm_parse(db, user_id, raw_text):
        return [], None

    monkeypatch.setattr(dvp, "_llm_parse_foods", empty_llm_parse)
    r = client.post("/api/v1/diet/voice/parse", headers=headers,
                    json={"raw_text": "晚饭喝了一瓶啤酒"})   # 关键词「晚饭」→确定性,不看挂钟
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meal_type"] == "dinner"
    assert body["meal_type_label"] == "晚餐"
    assert "alcohol" in body["risk_tags"]
    assert body["parser_version"] == dvp.PARSER_VERSION
    assert body["needs_confirmation"] is True          # 降级必确认


def test_api_voice_parse_requires_auth(client):
    assert client.post("/api/v1/diet/voice/parse", json={"raw_text": "x"}).status_code == 401


def test_api_voice_parse_rejects_invalid_meal_type(client, auth):
    _, headers = auth
    r = client.post(
        "/api/v1/diet/voice/parse",
        headers=headers,
        json={"raw_text": "吃了鸡胸肉", "meal_type": "午餐"},
    )
    assert r.status_code == 422


def test_watch_voice_confirm_preserves_ai_audit_fields(client, db, auth):
    user, headers = auth

    r = client.post(
        "/api/v1/diet/records",
        headers=headers,
        json={
            "record_date": date.today().isoformat(),
            "meal_type": "lunch",
            "food_items": "鸡胸肉 150g, 米饭 1碗",
            "calories": 480,
            "protein": 50.7,
            "carbs": 51.8,
            "fat": 5.9,
            "food_id": "cfc:chicken_breast",
            "source": "china_food_composition",
            "ai_recognized": 1,
            "ai_confidence": 0.82,
            "notes": "Watch 语音草稿: 午餐吃了鸡胸肉 150g 和米饭一碗 | parser: rules-v1 | confidence: 0.82",
        },
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ai_recognized"] == 1
    assert body["ai_confidence"] == 0.82
    assert body["food_id"] == "cfc:chicken_breast"
    assert body["source"] == "china_food_composition"

    record = db.query(DietRecord).filter(DietRecord.user_id == user.id).one()
    assert record.ai_recognized is True
    assert record.ai_confidence == 0.82
    assert record.food_id == "cfc:chicken_breast"
    assert record.source == "china_food_composition"
    assert "parser: rules-v1" in record.notes
