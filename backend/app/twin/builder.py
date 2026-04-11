"""
Digital Health Twin 组装器。

调用顺序（每步独立 try/except，任一失败不影响其他）：
  1. MultiSourceIntegrationService.get_integrated_profile  → wearable/body/labs/diet/genetic highlights
  2. DigitalTwinService.calculate_bmr/tdee                  → 派生生理指标
  3. SleepAnalysisService.get_deep_analysis                 → 睡眠深度分析
  4. MedicationService.get_today_status/get_adherence_stats → 药物 on-board
  5. MoodService.get_stats                                  → 情绪 7d
  6. ExerciseRecoveryService.get_training_load              → 训练负荷 ACWR
  7. DietRecommendationService.get_today_intake             → 饮食今日
  8. DailyRecommendationService.get_environment_data_sync   → 环境
  9. GoalManagementService.get_user_goals                   → 当前目标
 10. _collectors.*                                          → water/checkin/supplement/bp/exam/genetic

约束：
  - 禁止直接 import SQLAlchemy model（model 访问集中在 _collectors.py）
  - 每步都是可选的，二次异常也不能让整个 build_twin 崩
"""

import logging
import time
from datetime import date, datetime
from typing import Any, Dict, Set

from sqlalchemy.orm import Session

from app.twin import _collectors
from app.twin.schema import (
    BodyCompositionState,
    DataFreshness,
    EnvironmentalState,
    GeneticContext,
    GoalsContext,
    HealthTwin,
    LabsContext,
    MedicationState,
    MentalState,
    PhysiologicalState,
    SupplementState,
    TwinMeta,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────── 入口 ─────────────────────────────────


def build_twin(db: Session, user_id: int) -> HealthTwin:
    """构建用户的 Digital Health Twin。"""
    t0 = time.monotonic()
    sources: Set[str] = set()

    twin = HealthTwin(
        meta=TwinMeta(
            user_id=user_id,
            generated_at=datetime.utcnow(),
        )
    )

    _fill_integrated_profile(db, user_id, twin, sources)
    _fill_physiological_derived(db, user_id, twin)
    _fill_sleep_deep(db, user_id, twin, sources)
    _fill_medication(db, user_id, twin, sources)
    _fill_mood(db, user_id, twin, sources)
    _fill_training_load(db, user_id, twin, sources)
    _fill_diet_today(db, user_id, twin, sources)
    _fill_environment(db, user_id, twin, sources)
    _fill_goals(db, user_id, twin, sources)
    _fill_collectors(db, user_id, twin, sources)

    twin.meta.data_sources = sorted(sources)
    twin.meta.build_ms = int((time.monotonic() - t0) * 1000)
    return twin


# ─────────────────────── 1. multi-source 集成视图 ─────────────────────


def _fill_integrated_profile(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    try:
        from app.services.multi_source_integration_service import MultiSourceIntegrationService

        profile = MultiSourceIntegrationService().get_integrated_profile(db, user_id)
        if not profile or "error" in profile:
            return

        latest = profile.get("latest_metrics") or {}
        freshness = profile.get("data_freshness") or {}

        # — Garmin
        garmin = latest.get("garmin") or {}
        if garmin:
            p = twin.physiological
            p.hrv_latest = _as_float(garmin.get("hrv"))
            p.resting_hr = _as_int(garmin.get("resting_hr"))
            p.sleep_score_latest = _as_int(garmin.get("sleep_score"))
            p.steps_today = _as_int(garmin.get("steps"))
            p.stress_level_current = _as_int(garmin.get("stress_level"))
            p.body_battery_current = _as_int(garmin.get("body_battery_current"))
            p.last_updated = _as_date(garmin.get("date"))
            sources.add("garmin")

        # — Body composition
        bc = latest.get("body_composition") or {}
        if bc:
            body = twin.body_composition
            body.weight_kg = _as_float(bc.get("weight"))
            body.bmi = _as_float(bc.get("bmi"))
            body.body_fat_pct = _as_float(bc.get("body_fat_pct"))
            body.last_weighed = _as_date(bc.get("date"))
            body.bmi_category = _categorize_bmi(body.bmi)
            sources.add("weight")

        # — Labs
        labs = latest.get("labs") or {}
        if labs:
            L = twin.labs
            L.total_cholesterol = _as_float(labs.get("total_cholesterol"))
            L.blood_glucose = _as_float(labs.get("blood_glucose"))
            bp = labs.get("blood_pressure")
            if bp and isinstance(bp, str) and "/" in bp:
                try:
                    s, d = bp.split("/", 1)
                    L.blood_pressure_systolic = int(s.strip())
                    L.blood_pressure_diastolic = int(d.strip())
                except (ValueError, TypeError):
                    pass
            sources.add("labs")

        # — Genetic highlights（简单字符串列表，详细分类在 _fill_collectors 里覆盖）
        gen = latest.get("genetic_highlights") or []
        if gen:
            twin.genetic.has_profile = True
            twin.genetic.total_variants = len(gen)
            sources.add("genetic")

        # — Freshness
        f = twin.freshness
        f.garmin = freshness.get("garmin")
        f.weight = freshness.get("weight")
        f.labs = freshness.get("labs")
        f.diet = freshness.get("diet")
        f.genetic = freshness.get("genetic")
    except Exception as e:
        logger.warning(f"[twin] integrated_profile 失败: {e}")


# ───────────────────── 2. 生理派生量 BMR / TDEE ───────────────────────


def _fill_physiological_derived(db: Session, user_id: int, twin: HealthTwin) -> None:
    try:
        from app.services.digital_twin import DigitalTwinService

        dts = DigitalTwinService(db, user_id)
        bmr = dts.calculate_bmr()
        tdee = dts.calculate_tdee()
        if bmr:
            twin.body_composition.bmr_kcal = float(bmr)
        if tdee:
            twin.body_composition.tdee_kcal = float(tdee)
    except Exception as e:
        logger.warning(f"[twin] physiological_derived 失败: {e}")


# ─────────────────────────── 3. 睡眠深度 ───────────────────────────


def _fill_sleep_deep(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    try:
        from app.services.sleep_analysis_service import SleepAnalysisService

        analysis = SleepAnalysisService().get_deep_analysis(db, user_id, days=14)
        if not analysis or not isinstance(analysis, dict):
            return

        arch = analysis.get("architecture") or {}
        consistency = analysis.get("consistency") or {}
        hrv_recovery = analysis.get("hrv_recovery") or {}

        if isinstance(arch, dict):
            twin.physiological.sleep_deep_h_avg_14d = _as_float(
                arch.get("deep_hours") or arch.get("deep_sleep_hours")
            )

        if isinstance(consistency, dict):
            twin.physiological.sleep_consistency_score = _as_float(
                consistency.get("score") or consistency.get("consistency_score")
            )

        if isinstance(hrv_recovery, dict):
            hrv_avg = _as_float(hrv_recovery.get("avg_hrv"))
            if hrv_avg and not twin.physiological.hrv_7d_avg:
                twin.physiological.hrv_7d_avg = hrv_avg

        twin.physiological.sleep_duration_h_latest = _as_float(
            analysis.get("duration_avg_hours")
        )

        if arch or consistency or hrv_recovery:
            sources.add("sleep")
    except Exception as e:
        logger.warning(f"[twin] sleep_deep 失败: {e}")


# ─────────────────────────── 4. 药物 on-board ─────────────────────────


def _fill_medication(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    try:
        from app.services.medication_service import MedicationService

        svc = MedicationService()
        active = svc.get_today_status(db, user_id) or []
        twin.medication.active_meds = active
        twin.medication.has_any = len(active) > 0

        try:
            stats = svc.get_adherence_stats(db, user_id, days=7) or {}
            twin.medication.adherence_7d_pct = _as_float(stats.get("adherence_rate"))
        except Exception as e:
            logger.debug(f"[twin] adherence_stats 失败: {e}")

        if active:
            sources.add("medication")
            twin.freshness.medication = "今日"
    except Exception as e:
        logger.warning(f"[twin] medication 失败: {e}")


# ─────────────────────────── 5. 情绪 7d ──────────────────────────────


def _fill_mood(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    try:
        from app.services.mood_service import MoodService

        svc = MoodService()
        stats = svc.get_stats(db, user_id, days=7)
        if not stats:
            return

        def _g(key: str):
            if hasattr(stats, key):
                return getattr(stats, key)
            if isinstance(stats, dict):
                return stats.get(key)
            return None

        twin.mental.mood_7d_avg = _as_float(_g("avg_mood") or _g("mood_avg"))
        twin.mental.energy_7d_avg = _as_float(_g("avg_energy") or _g("energy_avg"))
        twin.mental.stress_7d_avg = _as_float(_g("avg_stress") or _g("stress_avg"))
        twin.mental.sleep_quality_7d_avg = _as_float(_g("avg_sleep_quality"))

        if twin.mental.mood_7d_avg is not None or twin.mental.energy_7d_avg is not None:
            sources.add("mood")
    except Exception as e:
        logger.warning(f"[twin] mood 失败: {e}")


# ─────────────────────────── 6. 训练负荷 ──────────────────────────────


def _fill_training_load(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    try:
        from app.services.exercise_recovery_service import ExerciseRecoveryService

        load = ExerciseRecoveryService().get_training_load(db, user_id) or {}
        if not load:
            return

        twin.behavioral.acute_chronic_ratio = _as_float(load.get("acwr"))
        twin.behavioral.acwr_zone = load.get("acwr_zone")
        twin.behavioral.training_load_7d = _as_float(load.get("acute_load_7d"))

        daily = load.get("daily_loads") or []
        if daily:
            from datetime import timedelta

            cutoff = date.today() - timedelta(days=7)
            count = 0
            for d in daily:
                try:
                    dt = d.get("date") if isinstance(d, dict) else None
                    if isinstance(dt, str):
                        dt = date.fromisoformat(dt)
                    if dt and dt >= cutoff and (d.get("trimp") or 0) > 0:
                        count += 1
                except Exception:
                    continue
            twin.behavioral.workouts_this_week = count

        if twin.behavioral.acute_chronic_ratio or twin.behavioral.training_load_7d:
            sources.add("exercise")
    except Exception as e:
        logger.warning(f"[twin] training_load 失败: {e}")


# ─────────────────────────── 7. 饮食今日 ──────────────────────────────


def _fill_diet_today(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    try:
        from app.services.diet_recommendation import DietRecommendationService

        intake = DietRecommendationService().get_today_intake(db, user_id) or {}
        if not intake:
            return

        b = twin.behavioral
        b.diet_calories_today = _as_float(intake.get("calories")) or b.diet_calories_today
        b.diet_protein_g_today = _as_float(intake.get("protein_g"))
        b.diet_carbs_g_today = _as_float(intake.get("carbs_g"))
        b.diet_fat_g_today = _as_float(intake.get("fat_g"))
        if intake.get("meals_count") is not None:
            b.meals_logged_today = int(intake["meals_count"])

        if b.diet_calories_today or b.meals_logged_today:
            sources.add("diet")
    except Exception as e:
        logger.warning(f"[twin] diet_today 失败: {e}")


# ─────────────────────────── 8. 环境 ─────────────────────────────────


def _fill_environment(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    try:
        from app.services.daily_recommendation import DailyRecommendationService

        env = DailyRecommendationService().get_environment_data_sync(db, user_id)
        if not env:
            return

        # env 的结构可能是 {weather, aqi, recommendations, city} 或更深的嵌套 —— 做防御性解析
        weather = env.get("weather") or {}
        if isinstance(weather, dict) and "current" in weather:
            weather = weather["current"] or {}

        aqi_data = env.get("aqi") or env.get("air_quality") or {}
        if isinstance(aqi_data, dict) and "current" in aqi_data:
            aqi_data = aqi_data["current"] or {}

        e = twin.environment
        e.city = env.get("city") or weather.get("city")
        e.temperature_c = _as_float(weather.get("temperature") or weather.get("temp_c") or weather.get("temp"))
        e.humidity_pct = _as_float(weather.get("humidity"))
        e.weather_description = weather.get("description") or weather.get("weather") or weather.get("condition")
        e.aqi = _as_int(aqi_data.get("aqi") or aqi_data.get("value"))
        e.aqi_level = aqi_data.get("level") or aqi_data.get("category") or aqi_data.get("health_level")
        e.pm25 = _as_float(aqi_data.get("pm25") or aqi_data.get("pm2_5"))
        e.uv_index = _as_float(weather.get("uv") or weather.get("uv_index"))
        e.outdoor_exercise_suitability = _suitability_from_aqi(e.aqi)

        if e.city or e.aqi or e.temperature_c is not None:
            sources.add("environment")
    except Exception as e:
        logger.warning(f"[twin] environment 失败: {e}")


# ─────────────────────────── 9. 当前目标 ──────────────────────────────


def _fill_goals(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    try:
        from app.models.goal import GoalStatus
        from app.services.goal_management import GoalManagementService

        goals = GoalManagementService().get_user_goals(db, user_id, status=GoalStatus.ACTIVE) or []
        twin.goals.active_goals = [_goal_to_dict(g) for g in goals]
        twin.goals.active_goals_count = len(twin.goals.active_goals)
        if goals:
            sources.add("goals")
    except Exception as e:
        logger.warning(f"[twin] goals 失败: {e}")


# ─────────────────────────── 10. 直接收集器 ───────────────────────────


def _fill_collectors(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    # — Water
    water = _collectors.fetch_water_today(db, user_id)
    twin.behavioral.water_ml_today = water["total_ml"]
    twin.behavioral.water_goal_ml = water["goal_ml"]
    twin.behavioral.water_progress_pct = water["progress_pct"]
    if water["total_ml"] > 0:
        sources.add("water")

    # — Health checkin (rhinitis)
    checkin = _collectors.fetch_health_checkin_today(db, user_id)
    if checkin:
        twin.behavioral.nasal_wash_count_today = checkin.get("nasal_wash_count", 0)
        twin.behavioral.sneeze_count_today = checkin.get("sneeze_count", 0)
        twin.chronic.rhinitis_today = checkin
        sources.add("health_checkin")

    # — Supplement
    supp = _collectors.fetch_supplement_today(db, user_id)
    twin.supplement = SupplementState(**supp)
    if supp["total_active_count"] > 0:
        sources.add("supplement")

    # — Blood pressure (若 integrated_profile 没填则用此覆盖)
    if twin.labs.blood_pressure_systolic is None:
        bp = _collectors.fetch_blood_pressure_latest(db, user_id)
        if bp:
            twin.labs.blood_pressure_systolic = bp.get("systolic")
            twin.labs.blood_pressure_diastolic = bp.get("diastolic")
            twin.labs.blood_pressure_date = bp.get("record_date")
            sources.add("blood_pressure")

    # — Medical exam abnormal
    abnormal = _collectors.fetch_medical_exam_abnormal(db, user_id)
    if abnormal:
        twin.labs.flagged_abnormal = abnormal
        sources.add("medical_exam")

    latest_exam = _collectors.fetch_latest_exam_meta(db, user_id)
    if latest_exam:
        twin.labs.last_exam_date = latest_exam.get("exam_date")
        twin.labs.last_exam_type = latest_exam.get("exam_type")

    # — Genetic (细分类别覆盖 integrated_profile 的字符串列表)
    gen = _collectors.fetch_genetic_variants_categorized(db, user_id)
    if gen and gen.get("total", 0) > 0:
        twin.genetic.has_profile = True
        twin.genetic.total_variants = gen["total"]
        twin.genetic.drug_sensitivity = gen.get("drug_sensitivity", [])
        twin.genetic.risk_variants = gen.get("risk", [])
        twin.genetic.protective_variants = gen.get("protective", [])
        sources.add("genetic")


# ─────────────────────────── 工具 ─────────────────────────────────────


def _as_float(v: Any) -> Any:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _as_int(v: Any) -> Any:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _as_date(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v)
        except ValueError:
            return None
    return None


def _categorize_bmi(bmi: Any) -> Any:
    if bmi is None:
        return None
    try:
        b = float(bmi)
    except (ValueError, TypeError):
        return None
    if b < 18.5:
        return "体重过低"
    if b < 24:
        return "正常"
    if b < 28:
        return "超重"
    return "肥胖"


def _suitability_from_aqi(aqi: Any) -> Any:
    if aqi is None:
        return None
    try:
        v = int(aqi)
    except (ValueError, TypeError):
        return None
    if v <= 50:
        return "suitable"
    if v <= 100:
        return "caution"
    return "avoid"


def _goal_to_dict(goal: Any) -> Dict[str, Any]:
    if isinstance(goal, dict):
        return goal
    return {
        "id": getattr(goal, "id", None),
        "title": getattr(goal, "title", None),
        "goal_type": str(getattr(goal, "goal_type", "")) or None,
        "goal_period": str(getattr(goal, "goal_period", "")) or None,
        "target_value": getattr(goal, "target_value", None),
        "current_value": getattr(goal, "current_value", None),
        "progress_pct": (
            getattr(goal, "progress_percent", None)
            or getattr(goal, "progress", None)
        ),
    }
