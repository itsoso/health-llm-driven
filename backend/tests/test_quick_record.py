"""快捷记录 API 测试"""
import logging

import pytest

from app.api.quick_record import _parse_quick_record, _estimate_nutrition
from app.models.blood_pressure import BloodPressureRecord
from app.models.daily_health import DietRecord, WaterIntake
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.weight import WeightRecord
from app.twin import _collectors
from tests.conftest import create_authenticated_user

QUICK_RECORD = "/api/v1/quick-record"


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


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _definition(db, user_id, name, is_active=True):
    supp = SupplementDefinition(user_id=user_id, name=name, is_active=is_active)
    db.add(supp)
    db.commit()
    db.refresh(supp)
    return supp


def _records_of(db, supp):
    return db.query(SupplementRecord).filter(SupplementRecord.supplement_id == supp.id).all()


class TestOtherDayText:
    """快速记录只记今天:文本点名别的日子时整句拒绝,绝不把它按今天写库。"""

    @pytest.mark.parametrize("text", [
        "昨天午餐牛肉面", "上周三晚饭吃了牛肉面", "9月28日午餐牛肉面", "28号午餐牛肉面", "午餐牛肉面 3天前",
        "明天早餐牛奶", "体重71.5 昨天", "喝水500 前天", "血压130/85 昨天", "补剂鱼油 1粒 昨天",
        "前晚吃了鱼油", "三日前午餐牛肉面", "补剂鱼油 上次",
    ])
    def test_other_day_text_is_rejected_for_every_record_type(self, client, db, text):
        user, token = create_authenticated_user(db)

        resp = client.post(QUICK_RECORD, json={"text": text}, headers=_headers(token))

        assert resp.status_code == 400
        assert "今天" in resp.json()["detail"]
        for model in (DietRecord, WaterIntake, WeightRecord, BloodPressureRecord,
                      SupplementRecord, SupplementDefinition):
            assert db.query(model).filter(model.user_id == user.id).count() == 0

    @pytest.mark.parametrize("text", [
        "今天午餐牛肉面", "喝水500", "血压95/60", "体重71.5", "早上月饼", "晚上周黑鸭",
        "补剂鱼油 每周一次", "补剂鱼油 饭后", "吃了维生素K2（别名MK-7）",
        "早餐吃了3号套餐", "午餐 麦当劳1号餐", "喝水2000/3000", "吃了鱼油，以后天天吃", "补剂鱼油 目前天天吃",
    ])
    def test_same_day_text_is_not_mistaken_for_another_day(self, text):
        from app.api.quick_record import _OTHER_DAY_RE

        assert _OTHER_DAY_RE.search(text) is None


class TestSupplementDefinitionResolution:
    """打卡落在哪个补剂定义上必须确定且可见:精确同名优先,多个候选 409 不猜,回复点名定义。"""

    def test_ambiguous_name_returns_409_listing_candidates_and_writes_nothing(self, client, db):
        user, token = create_authenticated_user(db)
        vitamin_c = _definition(db, user.id, "维生素C")
        vitamin_d3 = _definition(db, user.id, "维生素D3")

        resp = client.post(QUICK_RECORD, json={"text": "吃了维生素"}, headers=_headers(token))

        assert resp.status_code == 409
        assert "维生素C" in resp.json()["detail"] and "维生素D3" in resp.json()["detail"]
        assert _records_of(db, vitamin_c) == [] and _records_of(db, vitamin_d3) == []
        assert db.query(SupplementDefinition).filter(SupplementDefinition.user_id == user.id).count() == 2

    def test_exact_normalized_name_wins_over_longer_names(self, client, db):
        user, token = create_authenticated_user(db)
        vitamin_d3 = _definition(db, user.id, "维生素D3")
        vitamin_d = _definition(db, user.id, "维生素D")

        resp = client.post(QUICK_RECORD, json={"text": "吃了维生素d"}, headers=_headers(token))

        assert resp.status_code == 200, resp.text
        assert len(_records_of(db, vitamin_d)) == 1
        assert _records_of(db, vitamin_d3) == []

    def test_single_partial_match_is_not_guessed(self, client, db):
        """与 intake-batch 一致:非精确的相似定义(可能是复方)不猜,409 点名让用户写全称。"""
        user, token = create_authenticated_user(db)
        combo = _definition(db, user.id, "鱼油+维生素D3")

        resp = client.post(QUICK_RECORD, json={"text": "吃了鱼油 2粒"}, headers=_headers(token))

        assert resp.status_code == 409
        assert "鱼油+维生素D3" in resp.json()["detail"]
        assert _records_of(db, combo) == []

    def test_reply_names_the_stored_definition(self, client, db):
        user, token = create_authenticated_user(db)
        vitamin_d3 = _definition(db, user.id, "Vitamin D3")

        resp = client.post(QUICK_RECORD, json={"text": "补剂vitamin d3 2粒"}, headers=_headers(token))

        assert resp.status_code == 200, resp.text
        assert resp.json()["message"] == "已打卡补剂：Vitamin D3"
        assert len(_records_of(db, vitamin_d3)) == 1

    def test_duplicate_exact_definitions_return_409_instead_of_picking_one(self, client, db):
        user, token = create_authenticated_user(db)
        first = _definition(db, user.id, "鱼油")
        second = _definition(db, user.id, "鱼 油")

        resp = client.post(QUICK_RECORD, json={"text": "吃了鱼油"}, headers=_headers(token))

        assert resp.status_code == 409
        assert _records_of(db, first) == [] and _records_of(db, second) == []

    def test_like_wildcards_in_text_do_not_match_other_definitions(self, client, db):
        user, token = create_authenticated_user(db)
        vitamin_d3 = _definition(db, user.id, "维生素D3")

        resp = client.post(QUICK_RECORD, json={"text": "吃了维生素%3"}, headers=_headers(token))

        assert resp.status_code == 200, resp.text
        assert _records_of(db, vitamin_d3) == []

    def test_inactive_definition_is_skipped_and_new_definition_is_announced(self, client, db):
        """Twin 只统计 active 定义的打卡:落在停用定义上等于写丢,还会回「已打卡」。"""
        user, token = create_authenticated_user(db)
        stopped = _definition(db, user.id, "鱼油", is_active=False)

        resp = client.post(QUICK_RECORD, json={"text": "吃了鱼油"}, headers=_headers(token))

        assert resp.status_code == 200, resp.text
        assert "新建" in resp.json()["message"] and "鱼油" in resp.json()["message"]
        assert _records_of(db, stopped) == []
        [active] = db.query(SupplementDefinition).filter(
            SupplementDefinition.user_id == user.id, SupplementDefinition.is_active.is_(True),
        ).all()
        assert len(_records_of(db, active)) == 1
        assert "鱼油" in _collectors.fetch_supplement_today(db, user.id)["taking_recent_names"]

    def test_name_without_identity_characters_is_rejected(self, db):
        """归一化后为空的名字若放行,会「包含」于每个定义 —— 必须 400,不能挑一个打卡。"""
        from fastapi import HTTPException
        from app.api.quick_record import _resolve_supplement_definition

        user, _token = create_authenticated_user(db)
        _definition(db, user.id, "鱼油")

        with pytest.raises(HTTPException) as exc:
            _resolve_supplement_definition(db, user.id, "%%")

        assert exc.value.status_code == 400


class TestMacSupplementForm:
    """Mac 结构化表单发「补剂<名称> <剂量与时间>」:名称必须干净,才能对上已有定义。"""

    @pytest.mark.parametrize("text, name", [
        ("补剂鱼油", "鱼油"),
        ("补剂鱼油 1粒", "鱼油"),
        ("补剂鱼油 早餐后", "鱼油"),
        ("补剂镁 2粒 睡前", "镁"),
        ("补剂鱼油 每周一次", "鱼油"),
        ("补剂维生素D3 2粒", "维生素D3"),
        ("补剂Vitamin D3 1 softgel", "Vitamin D3"),
        ("补剂：鱼油 1粒", "鱼油"),
        ("补剂维生素Ｄ３　２粒", "维生素D3"),
        ("补剂钙片 1片", "钙片"),
        ("补剂Omega 3", "Omega 3"),
        ("吃了鱼油2粒", "鱼油"),
        ("吃了2粒鱼油", "鱼油"),
    ])
    def test_form_text_parses_to_the_bare_supplement_name(self, text, name):
        assert _parse_quick_record(text) == ("supplement", {"name": name})

    def test_chinese_numeral_inside_name_is_not_a_dose(self):
        from app.api.quick_record import _supplement_name

        assert _supplement_name("补剂三七片 2片") == "三七片"

    @pytest.mark.parametrize("text", [
        "补剂二甲双胍 500mg", "补剂鱼油 1粒 没吃",
        # 剂量后面还有别的内容(药名/未知词)时不截断丢弃:整句拒绝,不能只记补剂而静默吞掉药。
        "补剂维生素D3 1粒 布洛芬", "补剂鱼油 1粒 华法林", "补剂鱼油 早餐后 阿托伐他汀",
        "补剂维生素D 1粒 骨化三醇",
        # 分类仍看完整原文:mg/μg/IU 剂量照旧走用药守卫(与改动前一致,放宽归共享分类器 follow-up)。
        "补剂维生素D 骨化三醇 0.25μg", "补剂维生素D3 1000IU",
    ])
    def test_form_text_never_writes_more_than_before(self, text):
        assert _parse_quick_record(text) == (None, None)

    @pytest.mark.parametrize("text", [
        "补剂鱼油 1粒 华法林", "补剂维生素D3 1000IU 布洛芬", "补剂维生素D 骨化三醇 0.25μg",
        # 自由文本同理:剂量后跟未收录的药名不能被截掉后假报「已打卡」。
        "吃了维生素D 1粒 骨化三醇", "服用维生素D 1粒 骨化三醇", "吃了叶酸 1片 MTX",
        "吃了鱼油 早上 阿法骨化醇", "吃了钙片 1片 骨化三醇",
    ])
    def test_text_with_drug_after_dose_writes_nothing(self, client, db, text):
        user, token = create_authenticated_user(db)
        for name in ("维生素D", "叶酸", "鱼油", "钙片"):
            _definition(db, user.id, name)

        resp = client.post(QUICK_RECORD, json={"text": text}, headers=_headers(token))

        assert resp.status_code == 400
        assert db.query(SupplementRecord).filter(SupplementRecord.user_id == user.id).count() == 0
        assert db.query(SupplementDefinition).filter(SupplementDefinition.user_id == user.id).count() == 4

    def test_form_checkin_lands_on_existing_definition_without_duplicate(self, client, db):
        user, token = create_authenticated_user(db)
        fish_oil = _definition(db, user.id, "鱼油")

        resp = client.post(QUICK_RECORD, json={"text": "补剂鱼油 1粒"}, headers=_headers(token))

        assert resp.status_code == 200, resp.text
        assert resp.json()["message"] == "已打卡补剂：鱼油"
        assert len(_records_of(db, fish_oil)) == 1
        assert db.query(SupplementDefinition).filter(SupplementDefinition.user_id == user.id).count() == 1


class TestVitalsInputIsNotRewritten:
    @pytest.mark.parametrize("text, expected", [
        ("体重70²", ("weight", {"weight": 70.0})),
        ("血压120/80²", ("bp", {"systolic": 120, "diastolic": 80})),
        ("喝水500³", ("water", {"amount": 500})),
    ])
    def test_superscript_digits_are_not_folded_into_vitals(self, text, expected):
        """NFKC 只用于补剂/日期判断;不能把「80²」折成 802 写进血压(假 CRITICAL)。"""
        assert _parse_quick_record(text) == expected

    @pytest.mark.parametrize("text", ["吃鱼油\ufe56", "吃鱼油\ufe16", "我\uf967吃了鱼油"])
    def test_compatibility_characters_do_not_bypass_not_taken_filter(self, text):
        assert _parse_quick_record(text) == (None, None)


class TestUnexpectedFailure:
    def test_unexpected_error_returns_generic_detail_and_logs_type_only(self, client, db, monkeypatch, caplog):
        """异常原文可能带 SQL/参数/健康值:不回显给客户端;ERROR 只记类型,堆栈只进 DEBUG。"""
        user, token = create_authenticated_user(db)
        leaked = "SELECT weight FROM weight_records WHERE user_id=3 -- 血压185/85"

        def boom(_food):
            raise RuntimeError(leaked)

        monkeypatch.setattr("app.api.quick_record._estimate_nutrition", boom)
        with caplog.at_level(logging.DEBUG, logger="app.api.quick_record"):
            resp = client.post(QUICK_RECORD, json={"text": "午餐牛肉面"}, headers=_headers(token))

        assert resp.status_code == 500
        assert leaked not in resp.text and "RuntimeError" not in resp.text
        own = [r for r in caplog.records if r.name == "app.api.quick_record"]
        errors = [r for r in own if r.levelno >= logging.ERROR]
        assert len(errors) == 1
        assert "RuntimeError" in errors[0].getMessage()
        assert leaked not in errors[0].getMessage() and errors[0].exc_info is None
        assert any(r.levelno == logging.DEBUG and r.exc_info for r in own)
        assert db.query(DietRecord).filter(DietRecord.user_id == user.id).count() == 0
