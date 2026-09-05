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
from datetime import date, datetime, timedelta, timezone

import pytest

from app.twin import build_twin
from app.twin.builder import _categorize_bmi, _suitability_from_aqi
from app.twin.formatter import twin_to_prompt_blob
from app.twin.schema import (
    AcuteHealthState,
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
        assert twin.acute.has_active_illness is False
        assert twin.acute.should_rest_from_training is False
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
    def test_build_picks_up_active_cold_and_recent_respiratory_symptoms(self, db):
        """活跃感冒或近期呼吸道症状应进入 Twin acute 分区, 用于压制运动建议。"""
        from app.models.user import User
        from app.models.illness import IllnessEpisode
        from app.models.symptom_entry import SymptomEntry

        user = User(
            username=f"tw_{uuid.uuid4().hex[:6]}",
            email=f"tw_{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x",
            name="Twin Test User",
            is_active=True,
            is_approved=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        db.add(IllnessEpisode(
            user_id=user.id,
            name="感冒",
            start_date=date.today() - timedelta(days=1),
            status="active",
            severity=5,
        ))
        db.add(SymptomEntry(
            user_id=user.id,
            occurred_at=datetime.now(timezone.utc),
            body_part="respiratory",
            description="咳嗽，嗓子疼，鼻塞",
            severity=4,
            source="voice",
        ))
        db.commit()

        twin = build_twin(db, user_id=user.id, use_cache=False)

        assert twin.acute.has_active_illness is True
        assert twin.acute.suspected_cold is True
        assert twin.acute.should_rest_from_training is True
        assert "感冒" in twin.acute.illness_names
        assert any("咳嗽" in s for s in twin.acute.recent_symptoms)
        assert "acute" in twin.meta.data_sources

    def test_build_projects_monitoring_problem_red_lines(self, db):
        """未 resolved 的 HealthProblem 红线应投影到 Twin。

        覆盖安全评审建议①:愈合转 monitoring 的问题红线不能丢(黑便复发场景)。
        """
        from app.models.user import User
        from app.services import health_problem_service as prob_svc

        user = User(
            username=f"rl_{uuid.uuid4().hex[:6]}",
            email=f"rl_{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x", name="RedLine User", is_active=True, is_approved=True,
        )
        db.add(user); db.commit(); db.refresh(user)

        p = prob_svc.create_problem(db, user.id, {
            "name": "胃溃疡(随访中)", "risk_level": "P1", "status": "active",
            "red_lines": [{"condition": "黑便/呕血", "action": "立即就医/急诊"}],
        })
        prob_svc.set_status(db, p.id, user.id, "monitoring")

        twin = build_twin(db, user_id=user.id, use_cache=False)

        conds = [rl.condition for rl in twin.acute.problem_red_lines]
        assert "黑便/呕血" in conds
        assert twin.acute.problem_red_lines[0].action == "立即就医/急诊"

    def test_fill_red_lines_default_swallows_keeps_build_resilient(self, db, monkeypatch):
        """默认 raise_on_error=False:填充崩 → 只 log warning、正常返回,不阻塞 Twin 构建。

        这是 build_twin 主流程的契约(通用报告要韧性)。改 helper 加参数后,默认行为
        必须零变化 —— 红线填充失败不该让整个 Twin 构建炸。
        """
        from app.twin.builder import _fill_problem_red_lines
        from app.twin.schema import HealthTwin, TwinMeta
        from app.services import health_problem_service

        monkeypatch.setattr(
            health_problem_service, "list_problems",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(timezone.utc)))
        sources: set = set()
        # 默认不抛:正常返回
        _fill_problem_red_lines(db, 1, twin, sources)
        assert twin.acute.problem_red_lines == []  # 留空(降级)
        assert "problem_red_lines" not in sources

    def test_fill_red_lines_raise_on_error_propagates(self, db, monkeypatch):
        """raise_on_error=True:填充崩 → 不吞、向上抛(安全关键路径用,调用方感知不完整)。"""
        import pytest as _pytest
        from app.twin.builder import _fill_problem_red_lines
        from app.twin.schema import HealthTwin, TwinMeta
        from app.services import health_problem_service

        monkeypatch.setattr(
            health_problem_service, "list_problems",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(timezone.utc)))
        with _pytest.raises(RuntimeError):
            _fill_problem_red_lines(db, 1, twin, set(), raise_on_error=True)

    def test_cross_source_confidence_back_filled(self, monkeypatch):
        """R3 回灌:多源用户 → device_agreement_index + divergent_metrics 写进 physiological。"""
        from app.twin.builder import _fill_cross_source
        from app.twin.schema import HealthTwin, TwinMeta
        import app.services.recovery_decision as rd
        import app.services.cross_source_validator as csv

        monkeypatch.setattr(rd, "device_agreement_index",
                            lambda db, uid, days=7: (0.72, {"sources": ["garmin", "ringconn"]}))
        monkeypatch.setattr(csv, "detect_cross_source_anomalies", lambda db, uid, days=7: [
            {"metric": "resting_heart_rate", "label": "静息心率", "trusted_source": "garmin",
             "outlier_source": "ringconn", "deviation_pct": 22.0, "hint": "戒指偏高"},
        ])
        twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
        srcs: set = set()
        _fill_cross_source(None, 1, twin, srcs)

        assert twin.physiological.device_agreement_index == 0.72
        assert twin.physiological.device_sources == ["garmin", "ringconn"]
        assert len(twin.physiological.divergent_metrics) == 1
        assert twin.physiological.divergent_metrics[0].trusted_source == "garmin"
        assert "cross_source" in srcs

    def test_cross_source_single_source_skipped(self, monkeypatch):
        """单源用户(<2 设备)→ 不写,保持默认 None(无跨源置信可言)。"""
        from app.twin.builder import _fill_cross_source
        from app.twin.schema import HealthTwin, TwinMeta
        import app.services.recovery_decision as rd

        monkeypatch.setattr(rd, "device_agreement_index",
                            lambda db, uid, days=7: (None, {"sources": ["garmin"]}))
        twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
        _fill_cross_source(None, 1, twin, set())
        assert twin.physiological.device_agreement_index is None
        assert twin.physiological.divergent_metrics == []

    def test_garmin_only_spo2_excluded_in_overnight_fill(self, db):
        """血氧整源剔除 garmin:garmin-only → spo2_avg/spo2_min_overnight 均 None。

        覆盖安全评审阻断:_fill_spo2_overnight 直查 SQL 兜底曾绕过 EXCLUDED_SOURCES,
        把 garmin 假性低值漏进夜间低氧 CRITICAL 规则。直接调该 filler(它是 Phase B,
        build_twin 里走 SessionLocal 看不到测试 db)。
        """
        from app.models.user import User
        from app.models.daily_health import GarminData
        from app.twin.builder import _fill_spo2_overnight
        from app.twin.schema import HealthTwin, TwinMeta

        user = User(
            username=f"sp_{uuid.uuid4().hex[:6]}", email=f"sp_{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x", name="SpO2 User", is_active=True, is_approved=True,
        )
        db.add(user); db.commit(); db.refresh(user)
        db.add(GarminData(user_id=user.id, record_date=date.today(),
                          data_source="garmin", spo2_avg=85.0, spo2_min=80.0))
        db.commit()

        twin = HealthTwin(meta=TwinMeta(user_id=user.id, generated_at=datetime.utcnow()))
        _fill_spo2_overnight(db, user.id, twin, set())
        assert twin.physiological.spo2_avg is None            # garmin 血氧不采纳
        assert twin.physiological.spo2_min_overnight is None   # 不漏进夜间低氧 CRITICAL

    def test_ringconn_spo2_kept_in_overnight_fill(self, db):
        """RingConn spo2 正常采纳(只排 garmin,不误伤可信源)。"""
        from app.models.user import User
        from app.models.daily_health import GarminData
        from app.twin.builder import _fill_spo2_overnight
        from app.twin.schema import HealthTwin, TwinMeta

        user = User(
            username=f"rc_{uuid.uuid4().hex[:6]}", email=f"rc_{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x", name="Ring User", is_active=True, is_approved=True,
        )
        db.add(user); db.commit(); db.refresh(user)
        db.add(GarminData(user_id=user.id, record_date=date.today(),
                          data_source="ringconn", spo2_avg=96.0, spo2_min=93.0))
        db.commit()

        twin = HealthTwin(meta=TwinMeta(user_id=user.id, generated_at=datetime.utcnow()))
        _fill_spo2_overnight(db, user.id, twin, set())
        assert twin.physiological.spo2_min_overnight == 93.0

    def test_mixed_source_spo2_garmin_low_excluded_in_overnight_fill(self, db):
        """混源夜:garmin 假性低值(78)被剔除,取 ringconn 的 93(不误触夜间低氧)。"""
        from app.models.user import User
        from app.models.daily_health import GarminData
        from app.twin.builder import _fill_spo2_overnight
        from app.twin.schema import HealthTwin, TwinMeta

        user = User(
            username=f"mx_{uuid.uuid4().hex[:6]}", email=f"mx_{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x", name="Mixed User", is_active=True, is_approved=True,
        )
        db.add(user); db.commit(); db.refresh(user)
        db.add(GarminData(user_id=user.id, record_date=date.today(),
                          data_source="ringconn", spo2_avg=96.0, spo2_min=93.0))
        db.add(GarminData(user_id=user.id, record_date=date.today(),
                          data_source="garmin", spo2_avg=82.0, spo2_min=78.0))
        db.commit()

        twin = HealthTwin(meta=TwinMeta(user_id=user.id, generated_at=datetime.utcnow()))
        _fill_spo2_overnight(db, user.id, twin, set())
        assert twin.physiological.spo2_min_overnight == 93.0   # garmin 78 被剔除

    def test_spo2sample_garmin_excluded_main_branch(self, db):
        """主分支(有 SpO2Sample):garmin 逐分钟样本被剔除 → spo2_min_overnight None。

        SpO2Sample 只由 garmin 写(source 硬编码 garmin),是戴 Garmin 用户真实命中的路径。
        覆盖第二轮安全评审阻断:此前主分支无 source 过滤,garmin 假性低值直灌夜间低氧 CRITICAL。
        """
        from app.models.user import User
        from app.models.daily_health import SpO2Sample
        from app.twin.builder import _fill_spo2_overnight
        from app.twin.schema import HealthTwin, TwinMeta

        user = User(
            username=f"ss_{uuid.uuid4().hex[:6]}", email=f"ss_{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x", name="Sample User", is_active=True, is_approved=True,
        )
        db.add(user); db.commit(); db.refresh(user)
        for i, v in enumerate([95, 78, 80, 90]):  # garmin 含假性低值 78
            db.add(SpO2Sample(user_id=user.id, record_date=date.today(),
                              sample_time=datetime(2026, 6, 15, 0, i).time(),
                              epoch_ms=i * 60000, spo2_value=v, source="garmin"))
        db.commit()

        twin = HealthTwin(meta=TwinMeta(user_id=user.id, generated_at=datetime.utcnow()))
        _fill_spo2_overnight(db, user.id, twin, set())
        assert twin.physiological.spo2_min_overnight is None   # garmin 样本全剔除
        assert twin.physiological.spo2_avg is None

    def test_spo2sample_ringconn_kept_main_branch(self, db):
        """若 SpO2Sample 来自可信源(ringconn)→ 主分支正常采纳低点。"""
        from app.models.user import User
        from app.models.daily_health import SpO2Sample
        from app.twin.builder import _fill_spo2_overnight
        from app.twin.schema import HealthTwin, TwinMeta

        user = User(
            username=f"sr_{uuid.uuid4().hex[:6]}", email=f"sr_{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x", name="Sample Ring", is_active=True, is_approved=True,
        )
        db.add(user); db.commit(); db.refresh(user)
        for i, v in enumerate([96, 92, 94]):
            db.add(SpO2Sample(user_id=user.id, record_date=date.today(),
                              sample_time=datetime(2026, 6, 15, 0, i).time(),
                              epoch_ms=i * 60000, spo2_value=v, source="ringconn"))
        db.commit()

        twin = HealthTwin(meta=TwinMeta(user_id=user.id, generated_at=datetime.utcnow()))
        _fill_spo2_overnight(db, user.id, twin, set())
        assert twin.physiological.spo2_min_overnight == 92

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

    def test_metabolic_freshness_waist_bp_sleep(self, db):
        """代谢健康 freshness 3 项 (waist / blood_pressure / sleep) 应填入 ISO 日期串.

        Sleep 优先 Garmin, 缺则 SleepRecord, 取较新者.
        """
        from app.models.user import User
        from app.models.waist import WaistRecord
        from app.models.blood_pressure import BloodPressureRecord
        from app.models.sleep_record import SleepRecord
        from app.models.daily_health import GarminData

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

        today = date.today()
        yesterday = today - timedelta(days=1)
        three_days_ago = today - timedelta(days=3)

        db.add(WaistRecord(user_id=user.id, record_date=yesterday, waist_cm=85.0))
        db.add(BloodPressureRecord(
            user_id=user.id, record_date=today, systolic=120, diastolic=80,
        ))
        # Garmin 3 天前; SleepRecord 昨天 → sleep 应取较新的昨天
        db.add(GarminData(user_id=user.id, record_date=three_days_ago, sleep_score=82))
        db.add(SleepRecord(
            user_id=user.id, record_date=yesterday,
            bedtime=datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.utc),
            wake_time=datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
            sleep_quality=4,
        ))
        db.commit()

        twin = build_twin(db, user_id=user.id, use_cache=False)
        assert twin.freshness.waist == yesterday.isoformat()
        assert twin.freshness.blood_pressure == today.isoformat()
        assert twin.freshness.sleep == yesterday.isoformat()  # SleepRecord 更新

    def test_nocturnal_spo2_fallback_from_non_garmin_source(self, db):
        """戒指/手表用户(无逐秒 SpO2Sample)的夜间低血氧应进 spo2_min_overnight,
        否则夜间严重低氧规则永不触发。取跨源最小(worst-value)。
        直接测 _fill_spo2_overnight(避开 build_twin 并行 phase 的独立会话)。"""
        from app.models.user import User
        from app.models.daily_health import GarminData
        from app.twin.builder import _fill_spo2_overnight
        from app.twin.schema import HealthTwin

        user = User(
            username=f"sp_{uuid.uuid4().hex[:6]}",
            email=f"sp_{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x", name="ring user",
            birth_date=date(1990, 1, 1), gender="男",
            is_active=True, is_approved=True,
        )
        db.add(user); db.commit(); db.refresh(user)

        today = date.today()
        # 同一天:戒指夜间低点 82,手表 85 → 取最差 82。无 SpO2Sample。
        db.add(GarminData(user_id=user.id, record_date=today,
                          data_source="ringconn", spo2_min=82.0, spo2_avg=90.0))
        db.add(GarminData(user_id=user.id, record_date=today,
                          data_source="apple-watch", spo2_min=85.0, spo2_avg=93.0))
        db.commit()

        twin = HealthTwin(meta=TwinMeta(user_id=user.id, generated_at=datetime.utcnow()))
        _fill_spo2_overnight(db, user.id, twin, set())
        assert twin.physiological.spo2_min_overnight == 82.0
        assert twin.physiological.spo2_avg == 90.0  # 跨源最差日均

    def test_nocturnal_spo2_fallback_skipped_for_garmin_only(self, db):
        """纯 garmin 用户(无 SpO2Sample)行为不变:不从日 spo2_min 兜底夜间值。"""
        from app.models.user import User
        from app.models.daily_health import GarminData
        from app.twin.builder import _fill_spo2_overnight
        from app.twin.schema import HealthTwin

        user = User(
            username=f"gm_{uuid.uuid4().hex[:6]}",
            email=f"gm_{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x", name="garmin user",
            birth_date=date(1990, 1, 1), gender="男",
            is_active=True, is_approved=True,
        )
        db.add(user); db.commit(); db.refresh(user)
        db.add(GarminData(user_id=user.id, record_date=date.today(),
                          data_source="garmin", spo2_min=82.0, spo2_avg=90.0))
        db.commit()

        twin = HealthTwin(meta=TwinMeta(user_id=user.id, generated_at=datetime.utcnow()))
        _fill_spo2_overnight(db, user.id, twin, set())
        assert twin.physiological.spo2_min_overnight is None  # 纯 garmin 不兜底夜间值

    def test_build_computes_phenoage_when_all_9_inputs_present(self, db):
        """抗衰 MVP Step 2: 9 项血检 + 实足年龄齐 → twin.labs.phenotypic_age 被填."""
        from app.models.family_health import MedicalIndicator
        from app.models.user import User

        user = User(
            username=f"pa_{uuid.uuid4().hex[:6]}",
            email=f"pa_{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x",
            name="phenoage user",
            birth_date=date(1980, 1, 1),  # 实足约 46 岁
            gender="男",
            is_active=True,
            is_approved=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        today = date.today()
        # 9 项血检 (单位对齐 phenoage.py docstring)
        indicators = [
            ("白蛋白", 45.0),
            ("肌酐", 80.0),
            ("空腹血糖", 5.2),
            ("CRP", 0.08),
            ("淋巴细胞百分比", 32.0),
            ("MCV", 89.0),
            ("RDW", 13.0),
            ("ALP", 70.0),
            ("WBC", 6.0),
        ]
        for name, value in indicators:
            db.add(MedicalIndicator(
                user_id=user.id,
                name=name,
                value=value,
                record_date=today,
                source="manual",
            ))
        db.commit()

        twin = build_twin(db, user_id=user.id, use_cache=False)

        assert twin.labs.phenotypic_age is not None, (
            "9 项血检 + age 齐应触发 compute_phenoage"
        )
        assert twin.labs.phenotypic_age_delta_years is not None
        assert twin.labs.phenotypic_age_inputs_complete is True
        assert twin.labs.phenoage_evidence_tier == "validated"
        assert twin.labs.phenoage_claim_boundary  # 非空

    def test_build_no_phenoage_when_inputs_missing(self, db):
        """缺任一血检 → phenotypic_age 留 None,不猜算。"""
        from app.models.family_health import MedicalIndicator
        from app.models.user import User

        user = User(
            username=f"pa_{uuid.uuid4().hex[:6]}",
            email=f"pa_{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x",
            name="phenoage missing",
            birth_date=date(1980, 1, 1),
            gender="男",
            is_active=True,
            is_approved=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # 只录入 3 项(<9), phenoage 不应触发
        for name, value in [("白蛋白", 45.0), ("CRP", 0.08), ("WBC", 6.0)]:
            db.add(MedicalIndicator(
                user_id=user.id,
                name=name,
                value=value,
                record_date=date.today(),
                source="manual",
            ))
        db.commit()

        twin = build_twin(db, user_id=user.id, use_cache=False)
        assert twin.labs.phenotypic_age is None
        assert twin.labs.phenotypic_age_delta_years is None

    def test_metabolic_freshness_missing_returns_none(self, db):
        """3 项无任何记录 → freshness 字段保持 None, 不抛."""
        from app.models.user import User

        user = User(
            username=f"tw_{uuid.uuid4().hex[:6]}",
            email=f"tw_{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x",
            name="empty twin user",
            birth_date=date(1990, 1, 1),
            gender="男",
            is_active=True,
            is_approved=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        twin = build_twin(db, user_id=user.id, use_cache=False)
        assert twin.freshness.waist is None
        assert twin.freshness.blood_pressure is None
        assert twin.freshness.sleep is None

    def test_physiological_merges_latest_date_multi_source(self, db):
        """同一最新日期下,Apple Watch + RingConn + Garmin 三行 → twin.physiological
        按 per-metric 优先级合并 (hrv→ring, resting_hr→apple-watch, steps→watch)。
        """
        from app.models.user import User
        from app.models.daily_health import GarminData

        user = User(
            username=f"tw_{uuid.uuid4().hex[:6]}",
            email=f"tw_{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x",
            name="multi source user",
            birth_date=date(1990, 1, 1),
            gender="男",
            is_active=True,
            is_approved=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        today = date.today()
        db.add(GarminData(
            user_id=user.id, record_date=today, data_source="garmin",
            hrv=45.0, resting_heart_rate=52, steps=9200, sleep_score=70,
        ))
        db.add(GarminData(
            user_id=user.id, record_date=today, data_source="apple-watch",
            hrv=48.0, resting_heart_rate=54, steps=8500, sleep_score=78,
        ))
        db.add(GarminData(
            user_id=user.id, record_date=today, data_source="ringconn",
            hrv=52.0, resting_heart_rate=55, sleep_score=85,
        ))
        db.commit()

        twin = build_twin(db, user_id=user.id, use_cache=False)
        p = twin.physiological
        assert p.hrv_latest == 52.0          # ringconn 优先
        assert p.resting_hr == 54            # apple-watch 优先(用户指定 RHR 源)
        assert p.steps_today == 8500         # apple-watch 优先
        assert p.sleep_score_latest == 85    # ringconn 优先
        # field_sources 暴露每指标中标源,便于 LLM source-aware
        assert p.field_sources.get("hrv") == "ringconn"
        assert p.field_sources.get("resting_heart_rate") == "apple-watch"

    def test_physiological_single_garmin_row_back_compat(self, db):
        """旧 garmin-only 单行用户 → 合并结果 == 该行 (additive 不破坏)."""
        from app.models.user import User
        from app.models.daily_health import GarminData

        user = User(
            username=f"tw_{uuid.uuid4().hex[:6]}",
            email=f"tw_{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x",
            name="legacy garmin user",
            birth_date=date(1990, 1, 1),
            gender="男",
            is_active=True,
            is_approved=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        today = date.today()
        db.add(GarminData(
            user_id=user.id, record_date=today, data_source="garmin",
            hrv=48.0, resting_heart_rate=58, steps=8000, sleep_score=75,
        ))
        db.commit()

        twin = build_twin(db, user_id=user.id, use_cache=False)
        p = twin.physiological
        assert p.hrv_latest == 48.0
        assert p.resting_hr == 58
        assert p.steps_today == 8000
        assert p.sleep_score_latest == 75


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


# ─────────── 单元：基因证据分级 (Phase 1) ──────────


class TestGeneticVariantClassification:
    """builder 给每条 variant dict 注入 (actionability, evidence_grade)。"""

    def _fresh_twin(self) -> HealthTwin:
        return HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))

    def _classified_twin(self) -> HealthTwin:
        from app.twin.builder import _classify_genetic_variants

        twin = self._fresh_twin()
        twin.genetic.has_profile = True
        twin.genetic.total_variants = 4
        twin.genetic.drug_sensitivity = [
            {"gene_name": "CYP2C19", "genotype": "*2/*2", "rsid": "rs4244285"},
        ]
        twin.genetic.risk_variants = [
            {"gene_name": "APOE", "result_label": "e3/e4", "rsid": "rs429358"},
            {"gene_name": "FTO", "result_label": "AA risk", "rsid": "rs9939609"},
        ]
        twin.genetic.nutrition_variants = [
            {"gene_name": "ALDH2", "genotype": "GA", "rsid": "rs671"},
        ]
        _classify_genetic_variants(twin.genetic)
        return twin

    def test_builder_injects_two_dim_fields_on_each_variant(self):
        twin = self._classified_twin()
        drug = twin.genetic.drug_sensitivity[0]
        assert drug["actionability"] == "act"
        assert drug["evidence_grade"] == "cpic_a"

        apoe = twin.genetic.risk_variants[0]
        assert apoe["actionability"] == "risk_stratify"
        assert apoe["evidence_grade"] == "clinvar_likely"

        fto = twin.genetic.risk_variants[1]
        assert fto["actionability"] == "de_emphasize"
        assert fto["evidence_grade"] == "gwas_association"

    def test_partition_still_has_genetic_keys(self):
        # 加字段不改分区结构: genetic 分区仍存在且字段类型不变。
        twin = self._classified_twin()
        assert isinstance(twin.genetic.drug_sensitivity, list)
        assert isinstance(twin.genetic.drug_sensitivity[0], dict)

    def test_formatter_de_emphasize_forces_disclaimer_prefix(self):
        from app.services.genetic_registry import DE_EMPHASIZE_PREFIX

        twin = self._classified_twin()
        text = twin_to_prompt_blob(twin)
        # de_emphasize variant (FTO) 必须带强制前缀
        assert DE_EMPHASIZE_PREFIX in text
        assert "群体弱关联,个体无预测力,非诊断" in text

    def test_formatter_act_variant_is_highlighted(self):
        twin = self._classified_twin()
        text = twin_to_prompt_blob(twin)
        # act 级前置/突出: ▲ 标记 + 行动级 header
        assert "行动级 ACT" in text
        assert "▲ CYP2C19" in text
        assert "CPIC-A" in text

    def test_formatter_risk_stratify_variant_is_centered(self):
        twin = self._classified_twin()
        text = twin_to_prompt_blob(twin)
        assert "背景调阈值 RISK-STRATIFY" in text
        assert "APOE" in text

    def test_formatter_falls_back_to_classify_when_keys_absent(self):
        # 未经 builder 分类 (e.g. 部分 twin) 时, formatter 仍按 rsid/gene 现算分级。
        twin = self._fresh_twin()
        twin.genetic.has_profile = True
        twin.genetic.total_variants = 1
        twin.genetic.risk_variants = [{"gene_name": "FTO", "result_label": "AA"}]
        text = twin_to_prompt_blob(twin)
        assert "群体弱关联" in text  # FTO → de_emphasize 仍出前缀

    def test_formatter_proxy_locus_shows_guardrail(self):
        from app.twin.builder import _classify_genetic_variants

        twin = self._fresh_twin()
        twin.genetic.has_profile = True
        twin.genetic.total_variants = 1
        # rs5030655 = CYP2D6 indel proxy → act actionability, proxy_uncertain grade
        twin.genetic.drug_sensitivity = [
            {"gene_name": "CYP2D6", "genotype": "del", "rsid": "rs5030655"},
        ]
        _classify_genetic_variants(twin.genetic)
        assert twin.genetic.drug_sensitivity[0]["evidence_grade"] == "proxy_uncertain"
        text = twin_to_prompt_blob(twin)
        assert "阴性不代表无风险" in text

    def test_formatter_hla_proxy_promoted_still_shows_guardrail(self):
        # 安全回归: rs1265181 (HLA-B*58:01, 别嘌醇 SJS/TEN) 提级到 act+pharmgkb_1a
        # 后, formatter 仍须保留 "阴性不代表无风险" proxy 护栏 (走 is_proxy_variant)。
        from app.twin.builder import _classify_genetic_variants

        twin = self._fresh_twin()
        twin.genetic.has_profile = True
        twin.genetic.total_variants = 1
        twin.genetic.drug_sensitivity = [
            {"gene_name": "HLA-B*5801", "genotype": "+", "rsid": "rs1265181"},
        ]
        _classify_genetic_variants(twin.genetic)
        v = twin.genetic.drug_sensitivity[0]
        assert v["actionability"] == "act"
        assert v["evidence_grade"] == "pharmgkb_1a"
        text = twin_to_prompt_blob(twin)
        assert "行动级 ACT" in text
        assert "阴性不代表无风险" in text  # proxy 护栏未丢

    def test_formatter_carbamazepine_hla_tag_shows_guardrail(self):
        # 安全回归: rs1061235 (HLA-A*31:01, 卡马西平 SCAR) 与 rs1265181 同为 tier0
        # 致死 HLA tag SNP, 提级到 act+pharmgkb_1a 后 formatter 同样须保留 proxy 护栏。
        # 修复前只有别嘌醇等位基因带护栏, 卡马西平等位基因裸奔。
        from app.twin.builder import _classify_genetic_variants

        twin = self._fresh_twin()
        twin.genetic.has_profile = True
        twin.genetic.total_variants = 1
        twin.genetic.drug_sensitivity = [
            {"gene_name": "HLA-A*31:01", "genotype": "+", "rsid": "rs1061235"},
        ]
        _classify_genetic_variants(twin.genetic)
        v = twin.genetic.drug_sensitivity[0]
        assert v["actionability"] == "act"
        assert v["evidence_grade"] == "pharmgkb_1a"
        text = twin_to_prompt_blob(twin)
        assert "行动级 ACT" in text
        assert "阴性不代表无风险" in text  # proxy 护栏未丢

    def test_formatter_brca_act_gets_founder_variant_footnote(self):
        # 建议 1: BRCA (act + clinvar_path_confirm) 即使非 proxy rsid, 也强制追加
        # "消费级芯片仅覆盖部分创始变异, 阴性不代表无风险" 语义 (doc §3)。
        from app.twin.builder import _classify_genetic_variants

        twin = self._fresh_twin()
        twin.genetic.has_profile = True
        twin.genetic.total_variants = 1
        twin.genetic.risk_variants = [
            {"gene_name": "BRCA1", "result_label": "致病变异", "rsid": "rs80357906"},
        ]
        _classify_genetic_variants(twin.genetic)
        v = twin.genetic.risk_variants[0]
        assert v["actionability"] == "act"
        assert v["evidence_grade"] == "clinvar_path_confirm"
        text = twin_to_prompt_blob(twin)
        assert "仅覆盖部分创始变异" in text
        assert "阴性不代表无风险" in text

    def test_formatter_hfe_risk_stratify_gets_referral(self):
        # 建议 2: HFE 留 risk_stratify (tier 不动), 但 formatter 追加专科转诊 +
        # 临床级测序确认 (补回 doc §3 的转诊框架)。
        from app.twin.builder import _classify_genetic_variants

        twin = self._fresh_twin()
        twin.genetic.has_profile = True
        twin.genetic.total_variants = 1
        twin.genetic.risk_variants = [
            {"gene_name": "HFE", "result_label": "C282Y 纯合", "rsid": "rs1800562"},
        ]
        _classify_genetic_variants(twin.genetic)
        v = twin.genetic.risk_variants[0]
        assert v["actionability"] == "risk_stratify"
        text = twin_to_prompt_blob(twin)
        assert "RISK-STRATIFY" in text
        assert "建议专科就诊" in text
        assert "临床级测序确认" in text


class TestAgeLabel:
    def test_none_returns_empty(self):
        from app.twin.formatter import _age_label
        assert _age_label(None) == ""
        assert _age_label("") == ""

    def test_today(self):
        from app.twin.formatter import _age_label
        ts = datetime.now(timezone.utc).isoformat()
        assert _age_label(ts) == "(今日)"

    def test_yesterday(self):
        from app.twin.formatter import _age_label
        ts = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        assert _age_label(ts) == "(昨日)"

    def test_stale_warns_one(self):
        from app.twin.formatter import _age_label
        ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        assert _age_label(ts) == "(10 天前) ⚠"

    def test_dead_warns_two(self):
        from app.twin.formatter import _age_label
        ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        assert _age_label(ts) == "(2 月前) ⚠⚠"

    def test_years(self):
        from app.twin.formatter import _age_label
        ts = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        assert _age_label(ts) == "(1 年前) ⚠⚠"

    def test_labs_use_longer_window(self):
        """化验默认 stale_days=90, 7 天不报 ⚠."""
        from app.twin.formatter import _age_label
        ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        assert _age_label(ts, stale_days=90, dead_days=365) == "(30 天前)"

    def test_invalid_iso_returns_empty(self):
        from app.twin.formatter import _age_label
        assert _age_label("not-a-date") == ""

    def test_physiological_header_with_stale_garmin(self):
        """Garmin 7 天前 → Twin 生理分区应出现 "⚠" 提示 LLM."""
        from app.twin.formatter import twin_to_prompt_blob
        twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
        twin.physiological = PhysiologicalState(hrv_latest=38.0)
        twin.freshness.garmin = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        text = twin_to_prompt_blob(twin)
        assert "⚠" in text
        assert "生理(" in text

    def test_labs_header_with_stale_6_months(self):
        """化验 6 月前 → 应出现 ⚠ (stale 但还没 dead)."""
        from app.twin.formatter import twin_to_prompt_blob
        from app.twin.schema import LabsContext
        twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
        twin.labs = LabsContext(total_cholesterol=5.5)
        twin.freshness.labs = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
        text = twin_to_prompt_blob(twin)
        assert "⚠" in text
        assert "化验(" in text

    def test_labs_header_with_dead_2_years(self):
        """化验 2 年前 → 应出现 ⚠⚠ (dead)."""
        from app.twin.formatter import twin_to_prompt_blob
        from app.twin.schema import LabsContext
        twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
        twin.labs = LabsContext(total_cholesterol=5.5)
        twin.freshness.labs = (datetime.now(timezone.utc) - timedelta(days=730)).isoformat()
        text = twin_to_prompt_blob(twin)
        assert "⚠⚠" in text


# ─────────────────────── ECG / AFib (Apple Watch) ────────────────────────


def _make_user(db):
    from app.models.user import User
    user = User(
        username=f"ecg_{uuid.uuid4().hex[:6]}",
        email=f"ecg_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="ecg user",
        birth_date=date(1990, 1, 1),
        gender="男",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestEcgTwin:
    """ECG 观测落库 + Twin physiological 暴露 + 用户隔离。"""

    def test_build_picks_up_afib_ecg(self, db):
        from app.models.ecg_observation import EcgObservation
        user = _make_user(db)
        db.add(EcgObservation(
            user_id=user.id,
            classification="AtrialFibrillation",
            recorded_at=datetime(2026, 6, 14, 9, 30),
            afib_event_count=2,
            data_source="apple-watch",
        ))
        db.commit()

        twin = build_twin(db, user_id=user.id, use_cache=False)
        assert twin.physiological.ecg_classification == "AtrialFibrillation"
        assert twin.physiological.afib_recent is True
        assert twin.physiological.afib_event_count == 2
        assert "ecg" in twin.meta.data_sources

    def test_sinus_rhythm_not_flagged_afib(self, db):
        from app.models.ecg_observation import EcgObservation
        user = _make_user(db)
        db.add(EcgObservation(
            user_id=user.id,
            classification="SinusRhythm",
            recorded_at=datetime(2026, 6, 14, 9, 30),
            afib_event_count=0,
        ))
        db.commit()

        twin = build_twin(db, user_id=user.id, use_cache=False)
        assert twin.physiological.ecg_classification == "SinusRhythm"
        assert twin.physiological.afib_recent is False

    def test_latest_ecg_wins(self, db):
        from app.models.ecg_observation import EcgObservation
        user = _make_user(db)
        db.add(EcgObservation(
            user_id=user.id, classification="AtrialFibrillation",
            recorded_at=datetime(2026, 6, 10, 8, 0), afib_event_count=1,
        ))
        db.add(EcgObservation(
            user_id=user.id, classification="SinusRhythm",
            recorded_at=datetime(2026, 6, 14, 8, 0), afib_event_count=0,
        ))
        db.commit()

        twin = build_twin(db, user_id=user.id, use_cache=False)
        # 最近一次是 SinusRhythm → 不标房颤
        assert twin.physiological.ecg_classification == "SinusRhythm"
        assert twin.physiological.afib_recent is False

    def test_user_isolation(self, db):
        from app.models.ecg_observation import EcgObservation
        u1 = _make_user(db)
        u2 = _make_user(db)
        db.add(EcgObservation(
            user_id=u1.id, classification="AtrialFibrillation",
            recorded_at=datetime(2026, 6, 14, 9, 0), afib_event_count=1,
        ))
        db.commit()

        twin2 = build_twin(db, user_id=u2.id, use_cache=False)
        assert twin2.physiological.ecg_classification is None
        assert twin2.physiological.afib_recent is False

    def test_no_ecg_no_exposure(self, db):
        user = _make_user(db)
        twin = build_twin(db, user_id=user.id, use_cache=False)
        assert twin.physiological.ecg_classification is None
        assert twin.physiological.afib_recent is False
        assert twin.physiological.afib_event_count == 0


class TestHealthKitEcgImport:
    """HealthKit import payload 的 ECG 字段 → 落库 ecg_observations。"""

    def test_import_persists_ecg(self, db):
        from app.services.device_adapters.healthkit import HealthKitAdapter
        from app.models.ecg_observation import EcgObservation
        user = _make_user(db)

        records = [{
            "record_date": "2026-06-14",
            "data_source": "apple-watch",
            "ecg_classification": "AtrialFibrillation",
            "ecg_recorded_at": "2026-06-14T09:30:00",
            "afib_event_count": 1,
            "resting_heart_rate": 60,
        }]
        result = HealthKitAdapter.batch_save(db, user.id, records)
        assert result["imported_count"] == 1

        rows = db.query(EcgObservation).filter(EcgObservation.user_id == user.id).all()
        assert len(rows) == 1
        assert rows[0].classification == "AtrialFibrillation"
        assert rows[0].afib_event_count == 1

    def test_import_without_ecg_no_row(self, db):
        from app.services.device_adapters.healthkit import HealthKitAdapter
        from app.models.ecg_observation import EcgObservation
        user = _make_user(db)
        records = [{
            "record_date": "2026-06-14",
            "data_source": "apple-watch",
            "resting_heart_rate": 60,
        }]
        HealthKitAdapter.batch_save(db, user.id, records)
        rows = db.query(EcgObservation).filter(EcgObservation.user_id == user.id).all()
        assert len(rows) == 0

    def test_ecg_persists_even_when_daily_aggregation_fails(self, db):
        """ECG 是点事件, 不依赖日聚合成功。record_date 缺失 → 日聚合解析抛错,
        但带 ecg_classification 的 ECG 仍须独立落库; 日聚合失败不静默,
        以可区分的 kind='daily' 错误项反映在 import 返回里 (不假装成功)。"""
        from app.services.device_adapters.healthkit import HealthKitAdapter
        from app.models.ecg_observation import EcgObservation
        user = _make_user(db)

        records = [{
            # record_date 缺失 → _record_to_normalized 抛 ValueError (日聚合失败)
            "data_source": "apple-watch",
            "ecg_classification": "AtrialFibrillation",
            "ecg_recorded_at": "2026-06-14T09:30:00",
            "afib_event_count": 2,
        }]
        result = HealthKitAdapter.batch_save(db, user.id, records)

        # 日聚合: 0 导入, 但失败必须被反映 (不静默)
        assert result["imported_count"] == 0
        daily_errors = [e for e in result["errors"] if e["kind"] == "daily"]
        assert len(daily_errors) == 1
        assert daily_errors[0]["index"] == 0
        assert "record_date" in daily_errors[0]["error"]

        # ECG: 仍然落库成功 (与日聚合并行, 不被其失败拖垮)
        assert result["ecg_imported_count"] == 1
        assert not [e for e in result["errors"] if e["kind"] == "ecg"]
        rows = db.query(EcgObservation).filter(EcgObservation.user_id == user.id).all()
        assert len(rows) == 1
        assert rows[0].classification == "AtrialFibrillation"
        assert rows[0].afib_event_count == 2
        assert rows[0].data_source == "apple-watch"

    def test_import_ecg_idempotent_on_same_recorded_at(self, db):
        from app.services.device_adapters.healthkit import HealthKitAdapter
        from app.models.ecg_observation import EcgObservation
        user = _make_user(db)
        rec = {
            "record_date": "2026-06-14",
            "data_source": "apple-watch",
            "ecg_classification": "AtrialFibrillation",
            "ecg_recorded_at": "2026-06-14T09:30:00",
            "afib_event_count": 1,
        }
        HealthKitAdapter.batch_save(db, user.id, [dict(rec)])
        # 同一 recorded_at 再上送 (计数更新) → 应 upsert 不重复
        rec["afib_event_count"] = 3
        HealthKitAdapter.batch_save(db, user.id, [dict(rec)])
        rows = db.query(EcgObservation).filter(EcgObservation.user_id == user.id).all()
        assert len(rows) == 1
        assert rows[0].afib_event_count == 3
