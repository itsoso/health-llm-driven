"""
Digital Health Twin builder 单元测试。

覆盖目标：
1. Schema 默认值不崩
2. 空数据库构建不抛异常，所有字段为空但结构完整
3. 单个子域有数据时能正确填充
4. BMI / AQI 派生分类正确
5. /api/v1/twin/me 端点 200 + JSON shape 正确
"""

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.twin import build_twin
from app.twin.builder import _categorize_bmi, _suitability_from_aqi
from app.twin.formatter import twin_to_prompt_blob
from app.twin.schema import (
    BehavioralState,
    BodyCompositionState,
    EnvironmentalState,
    HealthTwin,
    LabsContext,
    MedicationState,
    PhysiologicalState,
    TwinMeta,
)


# ─────────────────────── 单元：派生函数 ────────────────────────


class TestCategorizations:
    def test_bmi_bucket(self):
        assert _categorize_bmi(17.0) == "体重过低"
        assert _categorize_bmi(18.5) == "正常"
        assert _categorize_bmi(23.9) == "正常"
        assert _categorize_bmi(24.0) == "超重"
        assert _categorize_bmi(27.9) == "超重"
        assert _categorize_bmi(28.0) == "肥胖"
        assert _categorize_bmi(35.0) == "肥胖"

    def test_bmi_none_and_invalid(self):
        assert _categorize_bmi(None) is None
        assert _categorize_bmi("abc") is None

    def test_aqi_suitability(self):
        assert _suitability_from_aqi(0) == "suitable"
        assert _suitability_from_aqi(50) == "suitable"
        assert _suitability_from_aqi(51) == "caution"
        assert _suitability_from_aqi(100) == "caution"
        assert _suitability_from_aqi(101) == "avoid"
        assert _suitability_from_aqi(300) == "avoid"

    def test_aqi_none_and_invalid(self):
        assert _suitability_from_aqi(None) is None
        assert _suitability_from_aqi("bad") is None


# ─────────────────────── 单元：schema 默认值 ───────────────────


class TestSchemaDefaults:
    def test_can_instantiate_empty_twin(self):
        twin = HealthTwin(
            meta=TwinMeta(
                user_id=1,
                generated_at=datetime.utcnow(),
            )
        )
        # 每个子结构都应有默认实例
        assert twin.physiological is not None
        assert twin.body_composition is not None
        assert twin.labs is not None
        assert twin.medication.active_meds == []
        assert twin.medication.has_any is False
        assert twin.supplement.total_active_count == 0
        assert twin.genetic.has_profile is False
        assert twin.behavioral.water_ml_today == 0
        assert twin.behavioral.water_goal_ml == 2000
        assert twin.goals.active_goals_count == 0
        assert twin.freshness.garmin is None

    def test_model_dump_json_serializable(self):
        twin = HealthTwin(
            meta=TwinMeta(
                user_id=1,
                generated_at=datetime.utcnow(),
            )
        )
        payload = twin.model_dump(mode="json")
        assert "meta" in payload
        assert payload["meta"]["user_id"] == 1
        assert "physiological" in payload
        assert "behavioral" in payload


# ─────────────────────── 集成：空库构建 ───────────────────────


class TestBuilderEmptyDB:
    def test_build_on_empty_db_returns_valid_twin(self, db):
        """空数据库 + 不存在的用户 → 不抛异常，返回空 Twin。"""
        twin = build_twin(db, user_id=9999, use_cache=False)
        assert isinstance(twin, HealthTwin)
        assert twin.meta.user_id == 9999
        assert twin.meta.build_ms >= 0
        # 用户相关的字段应全部为空
        assert twin.physiological.hrv_latest is None
        assert twin.medication.active_meds == []
        assert twin.goals.active_goals_count == 0
        assert twin.behavioral.water_ml_today == 0
        assert twin.supplement.total_active_count == 0
        assert twin.genetic.total_variants == 0
        # data_sources 只允许包含外部背景数据（环境）—— 其他都不该出现
        for src in twin.meta.data_sources:
            assert src in ("environment",), f"意外的数据源：{src}"

    def test_build_time_under_2s_empty(self, db):
        """空库构建应该极快，< 2 秒（给 CI 留余量）。"""
        twin = build_twin(db, user_id=1, use_cache=False)
        assert twin.meta.build_ms < 2000


# ─────────────────────── 集成：有部分数据 ─────────────────────


class TestBuilderWithPartialData:
    def test_build_picks_up_water_intake(self, db):
        """插入一条 WaterIntake 后 Twin 应显示。"""
        from app.models.user import User
        from app.models.daily_health import WaterIntake

        # 创建用户
        user = User(
            username=f"tw_{uuid.uuid4().hex[:6]}",
            email=f"tw_{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x",
            name="twin user",
            birth_date=date(1990, 1, 1),
            gender="男",
            is_active=True,
            is_approved=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # 插入饮水
        water = WaterIntake(
            user_id=user.id,
            record_date=date.today(),
            amount_ml=500,
            drink_type="水",
        )
        db.add(water)
        db.commit()

        twin = build_twin(db, user_id=user.id, use_cache=False)
        assert twin.behavioral.water_ml_today == 500
        assert "water" in twin.meta.data_sources

    def test_build_picks_up_rhinitis_checkin(self, db):
        from app.models.user import User
        from app.models.health_checkin import HealthCheckin

        user = User(
            username=f"tw_{uuid.uuid4().hex[:6]}",
            email=f"tw_{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x",
            name="twin user",
            birth_date=date(1990, 1, 1),
            gender="男",
            is_active=True,
            is_approved=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        checkin = HealthCheckin(
            user_id=user.id,
            checkin_date=date.today(),
            sneeze_count=7,
            nasal_wash_count=2,
            daily_score=75,
        )
        db.add(checkin)
        db.commit()

        twin = build_twin(db, user_id=user.id, use_cache=False)
        assert twin.behavioral.sneeze_count_today == 7
        assert twin.behavioral.nasal_wash_count_today == 2
        assert twin.chronic.rhinitis_today.get("daily_score") == 75
        assert "health_checkin" in twin.meta.data_sources


# ─────────────────────── 端到端：API 端点 ─────────────────────


class TestTwinAPI:
    def test_get_my_twin_unauthenticated(self, client):
        resp = client.get("/api/v1/twin/me")
        assert resp.status_code in (401, 403)

    def test_get_my_twin_authenticated_empty(self, client, db):
        from tests.conftest import create_authenticated_user

        _, token = create_authenticated_user(db)
        resp = client.get(
            "/api/v1/twin/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Shape 校验
        assert "meta" in body
        assert "physiological" in body
        assert "body_composition" in body
        assert "labs" in body
        assert "medication" in body
        assert "supplement" in body
        assert "genetic" in body
        assert "environment" in body
        assert "behavioral" in body
        assert "mental" in body
        assert "chronic" in body
        assert "goals" in body
        assert "freshness" in body
        assert body["meta"]["cache_status"] in ("hit", "miss")
        assert body["meta"]["build_ms"] >= 0

    def test_fresh_param_bypasses_cache(self, client, db):
        from tests.conftest import create_authenticated_user

        _, token = create_authenticated_user(db)
        headers = {"Authorization": f"Bearer {token}"}

        # 先构建一次（写入缓存）
        resp1 = client.get("/api/v1/twin/me", headers=headers)
        assert resp1.status_code == 200

        # fresh=true 应忽略缓存
        resp2 = client.get("/api/v1/twin/me?fresh=true", headers=headers)
        assert resp2.status_code == 200
        assert resp2.json()["meta"]["cache_status"] == "miss"

    def test_invalidate_endpoint(self, client, db):
        from tests.conftest import create_authenticated_user

        _, token = create_authenticated_user(db)
        resp = client.post(
            "/api/v1/twin/me/invalidate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "invalidated" in resp.json().get("message", "")


# ─────────────────────── 单元：formatter ──────────────────────


class TestTwinFormatter:
    def _fresh_twin(self) -> HealthTwin:
        return HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))

    def test_empty_twin_returns_empty_string(self):
        twin = self._fresh_twin()
        assert twin_to_prompt_blob(twin) == ""

    def test_formats_physiological(self):
        twin = self._fresh_twin()
        twin.physiological = PhysiologicalState(
            hrv_latest=42.0,
            hrv_7d_avg=58.0,
            resting_hr=55,
            sleep_score_latest=78,
            sleep_duration_h_latest=7.2,
            body_battery_current=42,
            stress_level_current=33,
            steps_today=8421,
        )
        text = twin_to_prompt_blob(twin)
        assert "HRV 42ms" in text
        assert "7日均 58" in text
        assert "静息心率 55" in text
        assert "睡眠分 78" in text
        assert "7.2h" in text
        assert "电量 42" in text
        assert "压力 33" in text
        assert "步数 8421" in text
        assert text.startswith("生理:")

    def test_formats_body_and_labs(self):
        twin = self._fresh_twin()
        twin.body_composition = BodyCompositionState(
            weight_kg=70.5,
            bmi=22.1,
            bmi_category="正常",
            body_fat_pct=18.5,
            tdee_kcal=2400,
        )
        twin.labs = LabsContext(
            blood_pressure_systolic=118,
            blood_pressure_diastolic=76,
            total_cholesterol=4.8,
            flagged_abnormal=[
                {"item_name": "ALT", "value": 55},
                {"item_name": "LDL", "value": 3.9},
            ],
        )
        text = twin_to_prompt_blob(twin)
        assert "体重 70.5kg" in text
        assert "BMI 22.1(正常)" in text
        assert "体脂 18.5%" in text
        assert "TDEE 2400" in text
        assert "118/76" in text
        assert "总胆固醇 4.8" in text
        assert "异常项: ALT, LDL" in text

    def test_formats_medication_and_behavioral(self):
        twin = self._fresh_twin()
        twin.medication = MedicationState(
            active_meds=[
                {"name": "糠酸莫米松鼻喷雾剂"},
                {"name": "盐酸西替利嗪片"},
                {"name": "替尔泊肽"},
            ],
            adherence_7d_pct=85.0,
            has_any=True,
        )
        twin.behavioral = BehavioralState(
            diet_calories_today=1840,
            diet_protein_g_today=112,
            meals_logged_today=3,
            water_ml_today=1500,
            water_goal_ml=2000,
            workouts_this_week=4,
            acute_chronic_ratio=1.25,
            acwr_zone="optimal",
            sneeze_count_today=5,
            nasal_wash_count_today=2,
        )
        text = twin_to_prompt_blob(twin)
        assert "在服药物 (3种)" in text
        assert "糠酸莫米松鼻喷雾剂" in text
        assert "7日依从率 85%" in text
        assert "饮食 1840kcal" in text
        assert "蛋白112g" in text
        assert "水 1500/2000ml" in text
        assert "本周 4 次运动" in text
        assert "ACWR 1.25(optimal)" in text
        assert "喷嚏 5次" in text
        assert "洗鼻 2次" in text

    def test_formats_environment(self):
        twin = self._fresh_twin()
        twin.environment = EnvironmentalState(
            city="北京",
            temperature_c=22.0,
            humidity_pct=45,
            aqi=78,
            aqi_level="良",
            outdoor_exercise_suitability="caution",
        )
        text = twin_to_prompt_blob(twin)
        assert "北京" in text
        assert "22°C" in text
        assert "湿度 45%" in text
        assert "AQI 78(良)" in text
        assert "户外运动: caution" in text

    def test_skips_missing_fields(self):
        """缺数据的行应完全跳过，不是显示 None。"""
        twin = self._fresh_twin()
        twin.physiological.hrv_latest = 50.0
        # 只设了一个字段，其他都是默认
        text = twin_to_prompt_blob(twin)
        assert "HRV 50ms" in text
        assert "None" not in text
        assert "压力" not in text  # 没设值就不该出现
