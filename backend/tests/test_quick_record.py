"""快捷记录 API 测试"""
import pytest

from app.api.quick_record import _parse_quick_record, _estimate_nutrition


class TestParseQuickRecord:
    """自然语言解析测试"""

    def test_water(self):
        t, d = _parse_quick_record("喝水500")
        assert t == "water"
        assert d["amount"] == 500

    def test_water_with_ml(self):
        t, d = _parse_quick_record("喝水 300ml")
        assert t == "water"
        assert d["amount"] == 300

    def test_weight(self):
        t, d = _parse_quick_record("体重71.5")
        assert t == "weight"
        assert d["weight"] == 71.5

    def test_weight_with_kg(self):
        t, d = _parse_quick_record("体重 72kg")
        assert t == "weight"
        assert d["weight"] == 72.0

    def test_blood_pressure_slash(self):
        t, d = _parse_quick_record("血压120/80")
        assert t == "bp"
        assert d["systolic"] == 120
        assert d["diastolic"] == 80

    def test_blood_pressure_space(self):
        t, d = _parse_quick_record("血压 130 85")
        assert t == "bp"
        assert d["systolic"] == 130
        assert d["diastolic"] == 85

    def test_diet_lunch(self):
        t, d = _parse_quick_record("午餐牛肉面")
        assert t == "diet"
        assert d["meal_type"] == "lunch"
        assert "牛肉面" in d["food"]

    def test_diet_breakfast(self):
        t, d = _parse_quick_record("早餐 鸡蛋牛奶")
        assert t == "diet"
        assert d["meal_type"] == "breakfast"

    def test_diet_ate(self):
        t, d = _parse_quick_record("吃了 鸡胸肉沙拉")
        assert t == "diet"
        assert "鸡胸肉" in d["food"]

    def test_supplement(self):
        t, d = _parse_quick_record("吃了维生素D")
        assert t == "supplement"
        assert "维生素" in d["name"]

    def test_supplement_with_spaced_verb_does_not_become_diet(self):
        t, d = _parse_quick_record("吃了 维生素D")
        assert t == "supplement"
        assert "维生素" in d["name"]

    def test_supplement_fish_oil(self):
        t, d = _parse_quick_record("补剂鱼油")
        assert t == "supplement"
        assert "鱼油" in d["name"]

    def test_medication_intake_does_not_become_diet(self):
        for text in ("吃了 替普瑞酮", "午餐替普瑞酮胶囊（施维舒）"):
            t, d = _parse_quick_record(text)
            assert t is None
            assert d is None

    @pytest.mark.parametrize("text", [
        "没吃维生素D",
        "还没吃维生素D",
        "维生素D还没吃",
        "忘了吃鱼油",
        "今天不吃镁",
        "别忘了吃维生素D",
        "准备吃鱼油",
        "吃了维生素D吗",
        # 分类器判非摄入后, 旧正则兜底(补剂前缀 / 餐次前缀 / 「吃了 X」)不得复活
        "吃了 维生素D吗",
        "午餐没吃",
        "晚饭吃了牛肉面吗",
        "吃了 牛肉面吗",
        # 分类器先判 health_metric 时,旧正则兜底同样不得复活(safety review v1)
        "午餐没吃，血糖5.6",
        "午餐没吃，体重70kg",
        "吃了 维生素D吗，血糖5.6",
        "服用 鱼油没吃 心率60",
    ])
    def test_not_taken_text_is_never_parsed_as_a_record(self, text):
        assert _parse_quick_record(text) == (None, None)

    @pytest.mark.parametrize(("text", "record_type", "field", "value"), [
        ("服用镁", "supplement", "name", "镁"),
        ("晚饭吃了牛肉面, 吃完有点反酸", "diet", "meal_type", "dinner"),
    ])
    def test_affirmative_intake_still_parses(self, text, record_type, field, value):
        t, d = _parse_quick_record(text)
        assert t == record_type
        assert d[field] == value

    def test_unrecognized(self):
        t, d = _parse_quick_record("今天天气不错")
        assert t is None

    def test_empty(self):
        t, d = _parse_quick_record("")
        assert t is None


class TestEstimateNutrition:
    """营养估算测试"""

    def test_known_food(self):
        result = _estimate_nutrition("牛肉面")
        assert result is not None
        assert result[0] == 450  # kcal

    def test_unknown_food(self):
        result = _estimate_nutrition("珍珠翡翠白玉汤")
        assert result is None

    def test_partial_match(self):
        result = _estimate_nutrition("清炒西兰花")
        assert result is not None  # 匹配"西兰花"


class TestQuickRecordAPI:
    """API 端点测试"""

    def test_record_water(self, client, db):
        from tests.conftest import create_authenticated_user
        user, token = create_authenticated_user(db)
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.post("/api/v1/quick-record", json={"text": "喝水250"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "water"
        assert data["success"] is True
        assert "250" in data["message"]
        assert isinstance(data["record_id"], int)
        assert data["undo_path"] == f"water/records/{data['record_id']}"

        undo_resp = client.delete(f"/api/v1/{data['undo_path']}", headers=headers)
        assert undo_resp.status_code == 200

    def test_record_diet(self, client, db):
        from tests.conftest import create_authenticated_user
        user, token = create_authenticated_user(db)
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.post("/api/v1/quick-record", json={"text": "午餐鸡胸肉沙拉"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "diet"
        assert data["success"] is True
        assert isinstance(data["record_id"], int)
        assert data["undo_path"] == f"diet/records/{data['record_id']}"

    def test_record_weight_returns_undo_path(self, client, db):
        from tests.conftest import create_authenticated_user
        user, token = create_authenticated_user(db)
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.post("/api/v1/quick-record", json={"text": "体重70.2"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "weight"
        assert data["success"] is True
        assert isinstance(data["record_id"], int)
        assert data["undo_path"] == f"weight/records/{data['record_id']}"

    def test_record_blood_pressure_returns_undo_path(self, client, db):
        from tests.conftest import create_authenticated_user
        user, token = create_authenticated_user(db)
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.post("/api/v1/quick-record", json={"text": "血压120/80"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "bp"
        assert data["success"] is True
        assert isinstance(data["record_id"], int)
        assert data["undo_path"] == f"blood-pressure/records/{data['record_id']}"

    def test_record_severe_blood_pressure_returns_recheck_and_symptom_triage(self, client, db):
        from tests.conftest import create_authenticated_user
        user, token = create_authenticated_user(db)
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post("/api/v1/quick-record", json={"text": "血压185/85"}, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "bp"
        assert data["category"] == "血压严重升高"
        assert data["category_color"]
        assert data["safety_guidance"]["severity"] == "high"
        assert "复测" in data["safety_guidance"]["recheck_instruction"]
        assert "胸痛" in data["safety_guidance"]["emergency_instruction"]
        assert "高血压急症" not in str(data)

    def test_record_supplement_returns_record_id_without_undo_path(self, client, db):
        from tests.conftest import create_authenticated_user
        user, token = create_authenticated_user(db)
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.post("/api/v1/quick-record", json={"text": "吃了维生素D"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "supplement"
        assert data["success"] is True
        assert isinstance(data["record_id"], int)
        assert data["undo_path"] is None

    def test_record_unrecognized(self, client, db):
        from tests.conftest import create_authenticated_user
        user, token = create_authenticated_user(db)
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.post("/api/v1/quick-record", json={"text": "随便说点什么"}, headers=headers)
        assert resp.status_code == 400

    @pytest.mark.parametrize("text", ["没吃维生素D", "维生素D还没吃", "吃了维生素D吗", "午餐没吃"])
    def test_not_taken_text_writes_nothing(self, client, db, text):
        """漏服/提问不得打卡:既不建补剂定义,也不写 taken=true,也不落饮食记录。"""
        from app.models.daily_health import DietRecord
        from app.models.supplement import SupplementDefinition, SupplementRecord
        from tests.conftest import create_authenticated_user
        user, token = create_authenticated_user(db)
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post("/api/v1/quick-record", json={"text": text}, headers=headers)

        assert resp.status_code == 400
        assert db.query(SupplementDefinition).filter_by(user_id=user.id).count() == 0
        assert db.query(SupplementRecord).filter_by(user_id=user.id).count() == 0
        assert db.query(DietRecord).filter_by(user_id=user.id).count() == 0
