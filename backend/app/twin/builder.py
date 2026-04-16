"""
Digital Health Twin 组装器。

调用策略（Phase 3 并行优化）：
  Phase A: _fill_integrated_profile               → 先执行（下游依赖 BP）
  Phase B: _fill_physiological_derived ~ _fill_cgm → 8 个并行（各自独立 DB 会话）
  Phase C: _fill_collectors                        → 最后执行（读取 Phase A 写入的 BP）

约束：
  - Phase B 每个线程创建独立 DB 会话（SQLAlchemy Session 不线程安全）
  - 每步都是可选的，异常不能让整个 build_twin 崩
  - twin 对象的并发写入安全：各 _fill_* 写入不同字段，无竞争
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from typing import Any, Callable, Dict, List, Set, Tuple

from sqlalchemy.orm import Session

from app.twin import _collectors
from app.twin.schema import (
    BodyCompositionState,
    CgmContext,
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


def build_twin(db: Session, user_id: int, use_cache: bool = True) -> HealthTwin:
    """
    构建用户的 Digital Health Twin。

    use_cache=True 时先尝试 Redis 缓存（5 min TTL），命中则直接返回
    反序列化的 HealthTwin 对象，避免重复 DB 查询。
    所有内部调用方（safety/orchestrator）默认走缓存。
    """
    if use_cache:
        from app.twin.cache import get_cached_twin, set_cached_twin

        cached = get_cached_twin(user_id)
        if cached is not None:
            try:
                twin = HealthTwin.model_validate(cached)
                twin.meta.cache_status = "hit"
                return twin
            except Exception:
                pass  # 缓存反序列化失败，重新构建

    t0 = time.monotonic()
    sources: Set[str] = set()

    twin = HealthTwin(
        meta=TwinMeta(
            user_id=user_id,
            generated_at=datetime.now(UTC),
        )
    )

    # ── Phase A: integrated_profile 先行（下游 _fill_collectors 依赖 BP 字段）──
    _fill_integrated_profile(db, user_id, twin, sources)

    # ── Phase B: 8 个独立步骤并行执行 ──
    # 每个线程使用独立 DB 会话（SQLAlchemy Session 不线程安全）
    from app.database import SessionLocal

    parallel_fillers: List[Tuple[str, Callable]] = [
        ("physiological_derived", lambda s: _fill_physiological_derived(s, user_id, twin)),
        ("sleep_deep",            lambda s: _fill_sleep_deep(s, user_id, twin, sources)),
        ("medication",            lambda s: _fill_medication(s, user_id, twin, sources)),
        ("mood",                  lambda s: _fill_mood(s, user_id, twin, sources)),
        ("training_load",         lambda s: _fill_training_load(s, user_id, twin, sources)),
        ("diet_today",            lambda s: _fill_diet_today(s, user_id, twin, sources)),
        ("environment",           lambda s: _fill_environment(s, user_id, twin, sources)),
        ("goals",                 lambda s: _fill_goals(s, user_id, twin, sources)),
        ("cgm",                   lambda s: _fill_cgm(s, user_id, twin, sources)),
    ]

    def _run_filler(name: str, fn: Callable) -> None:
        thread_db = SessionLocal()
        try:
            fn(thread_db)
        except Exception as e:
            logger.warning(f"[twin] {name} 并行执行失败: {e}")
        finally:
            thread_db.close()

    max_workers = min(len(parallel_fillers), 4)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_filler, name, fn): name
            for name, fn in parallel_fillers
        }
        for future in as_completed(futures):
            exc = future.exception()
            if exc:
                logger.warning(f"[twin] {futures[future]} 线程异常: {exc}")

    # ── Phase C: collectors 最后执行（依赖 Phase A 的 BP 数据）──
    _fill_collectors(db, user_id, twin, sources)

    twin.meta.data_sources = sorted(sources)
    twin.meta.build_ms = int((time.monotonic() - t0) * 1000)
    twin.meta.cache_status = "miss"

    # 写入缓存供后续调用复用（safety/orchestrator 共享同一个 Twin）
    if use_cache:
        try:
            from app.twin.cache import set_cached_twin

            set_cached_twin(user_id, twin.model_dump(mode="json"))
        except Exception:
            pass

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
        from app.utils.redis_cache import RedisCache

        ENV_CACHE_KEY = f"twin_env:{user_id}"
        ENV_CACHE_TTL = 3600  # 环境数据 1 小时缓存（天气/AQI 变化缓慢）

        # 先查缓存
        env = RedisCache.get(ENV_CACHE_KEY)
        if not env:
            from app.services.daily_recommendation import DailyRecommendationService
            env = DailyRecommendationService().get_environment_data_sync(db, user_id)
            if env:
                RedisCache.set(ENV_CACHE_KEY, env, ttl=ENV_CACHE_TTL)

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


# ─────────────────────────── 9.5 CGM 连续血糖 ───────────────────────


def _fill_cgm(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    """调用 CgmService 填充 CgmContext。失败静默降级。"""
    try:
        from app.services.cgm import CgmService

        svc = CgmService()
        summary = svc.get_24h_summary(db, user_id)
        if summary.count == 0 and summary.latest_mg_dl is None:
            return  # 没 CGM 数据就跳过

        twin.cgm = CgmContext(
            has_cgm=True,
            latest_mg_dl=summary.latest_mg_dl,
            latest_trend_arrow=summary.latest_trend_arrow,
            mean_24h_mg_dl=summary.mean_mg_dl,
            std_24h_mg_dl=summary.std_mg_dl,
            cv_24h_pct=summary.cv_pct,
            tir_24h_pct=summary.tir_pct,
            time_below_24h_pct=summary.time_below_pct,
            time_above_24h_pct=summary.time_above_pct,
            gmi_estimated_a1c=summary.gmi,
            severe_low_count_24h=summary.severe_low_count,
            severe_high_count_24h=summary.severe_high_count,
            readings_count_24h=summary.count,
        )

        # 同时把最新读数同步到 labs.blood_glucose（如果最近 1 小时内）
        if summary.latest_mg_dl is not None:
            sources.add("cgm")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[twin] cgm 失败: {e}")


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

    # — Medical exam abnormal + latest meta (单次 joinedload 查询)
    abnormal, latest_exam = _collectors.fetch_medical_exam_abnormal(db, user_id)
    if abnormal:
        twin.labs.flagged_abnormal = abnormal
        sources.add("medical_exam")

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
