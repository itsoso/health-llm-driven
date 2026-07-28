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
from datetime import UTC, date, datetime, timedelta
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
    # 急性病/感冒症状是安全约束，必须在主流程同步填充，避免并行 session
    # 在测试或事务边界内看不到刚写入的症状/病症记录。
    _fill_acute_health(db, user_id, twin, sources)
    # 个性化红线也是安全约束,同步填充(同 acute,避免并行 session 看不到刚写入的 problem)
    _fill_problem_red_lines(db, user_id, twin, sources)
    _fill_epigenetic(db, user_id, twin, sources)

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
        ("spo2_overnight",        lambda s: _fill_spo2_overnight(s, user_id, twin, sources)),
        ("hrv_nightly",           lambda s: _fill_hrv_nightly(s, user_id, twin, sources)),
        ("respiration_nightly",   lambda s: _fill_respiration_nightly(s, user_id, twin, sources)),
        ("garmin_official",       lambda s: _fill_garmin_official(s, user_id, twin, sources)),
        ("vo2max",                lambda s: _fill_vo2max(s, user_id, twin, sources)),
        ("personal_baseline",     lambda s: _fill_personal_baseline(s, user_id, twin, sources)),
        ("cross_source",          lambda s: _fill_cross_source(s, user_id, twin, sources)),
    ]

    def _run_filler(name: str, fn: Callable) -> None:
        thread_db = SessionLocal()
        try:
            fn(thread_db)
        except Exception as e:
            # 通用兜底(各 _fill_* 自己的 try/except 先接;这里只捕漏网的)。
            # 同样记进 failed_partitions —— 否则「分区评估失败」与「无数据」不可分辨。
            logger.error(f"[twin] {name} 并行执行失败: {e}", exc_info=True)
            twin.meta.failed_partitions.append(name)
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

    # 构建基因配置文件
    try:
        from app.twin.gene_config import build_gene_config
        twin.gene_config = build_gene_config(twin)
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
            p.spo2_avg = _as_float(garmin.get("spo2_avg"))
            # 最近一晚睡眠时长(分钟→小时)。total_sleep_duration 后端单位是分钟。
            _sleep_min = _as_int(garmin.get("total_sleep_duration"))
            if _sleep_min:
                p.sleep_duration_h_latest = round(_sleep_min / 60, 1)
            p.last_updated = _as_date(garmin.get("date"))
            # P4: 多源合并产生的字段→source 字典 (LLM 可知道每个数值由哪个设备提供)
            srcs = garmin.get("sources") or {}
            if isinstance(srcs, dict) and srcs:
                p.field_sources = {k: str(v) for k, v in srcs.items() if v}
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
        # 代谢健康第一阶段补 3 项: waist / blood_pressure / sleep.
        # 不进 MultiSourceIntegrationService 避免给那层加耦合, 直接 SQL latest record_date 即可.
        _fill_metabolic_freshness(db, user_id, twin)
    except Exception as e:
        logger.warning(f"[twin] integrated_profile 失败: {e}")


def _fill_metabolic_freshness(db: Session, user_id: int, twin: HealthTwin) -> None:
    """补 waist / blood_pressure / sleep 三项 freshness (代谢健康核心 7 项的剩余 3 项).

    Sleep 优先用 Garmin 自动采集 (覆盖率高), 缺失再 fallback SleepRecord 手动记录.
    """
    from sqlalchemy import func as _func
    from app.models.waist import WaistRecord
    from app.models.blood_pressure import BloodPressureRecord
    from app.models.sleep_record import SleepRecord
    from app.models.daily_health import GarminData

    def _latest_date(model, date_col):
        try:
            d = (
                db.query(_func.max(date_col))
                .filter(model.user_id == user_id)
                .scalar()
            )
            return d.isoformat() if d else None
        except Exception as _e:  # noqa: BLE001
            logger.debug(f"[twin] freshness {model.__tablename__} 失败: {_e}")
            return None

    twin.freshness.waist = _latest_date(WaistRecord, WaistRecord.record_date)
    twin.freshness.blood_pressure = _latest_date(
        BloodPressureRecord, BloodPressureRecord.record_date,
    )
    # Sleep: Garmin 先, SleepRecord 后, 取较新
    g = _latest_date(GarminData, GarminData.record_date)
    s = _latest_date(SleepRecord, SleepRecord.record_date)
    twin.freshness.sleep = max(filter(None, [g, s]), default=None)


def _fill_epigenetic(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    try:
        from app.services.epigenetic_report_service import latest_epigenetic_state

        twin.epigenetic = latest_epigenetic_state(db, user_id)
        if twin.epigenetic.has_methylation_report:
            sources.add("epigenetic_report")
            twin.freshness.epigenetic = "long_term"
    except Exception as e:
        logger.warning(f"[twin] epigenetic 失败: {e}")


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


def _fill_vo2max(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    """填充 VO2max / 体能年龄(抗衰第二信号)。

    Twin 已有 vo2max_running/cycling 字段但此前无人填充(死字段);这里补齐。
    VO2max 是全因死亡率最强单一预测因子;vo2max_fitness_age 是 Garmin 直接算的
    "体能年龄",可与实足年龄对比,做 PhenoAge 之外的第二个生物年龄信号。
    取最近 90 天里有 vo2max 的最新一天(VO2max 变化慢,窗口放宽)。
    """
    try:
        from datetime import timedelta

        from app.models.daily_health import GarminData

        cutoff = (twin.meta.generated_at.date() if twin.meta.generated_at else date.today()) - timedelta(days=90)
        row = (
            db.query(GarminData)
            .filter(GarminData.user_id == user_id)
            .filter(GarminData.vo2max_running.isnot(None))
            .filter(GarminData.record_date >= cutoff)
            .order_by(GarminData.record_date.desc())
            .limit(1)
            .first()
        )
        if not row:
            return
        p = twin.physiological
        if row.vo2max_running is not None:
            p.vo2max_running = float(row.vo2max_running)
        if row.vo2max_cycling is not None:
            p.vo2max_cycling = float(row.vo2max_cycling)
        if getattr(row, "vo2max_fitness_age", None) is not None:
            p.vo2max_fitness_age = int(row.vo2max_fitness_age)
        sources.add("garmin")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[twin] vo2max 填充失败: {e}")


def _fill_personal_baseline(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    """Phase 0: 个人滚动基线 + 当前值偏离 (z-score) 写入 physiological.personal_baselines.

    "你现在 vs 你自己的 90 天历史" —— 纯统计, 喂 agent 解读 (≠ #149 跨源差异)。
    冷启动不足的指标 personal_baseline service 自动跳过, 这里只搬运。
    """
    try:
        from app.services.personal_baseline import compute_personal_baselines
        from app.twin.schema import PersonalBaselineMetric

        ref_date = twin.meta.generated_at.date() if twin.meta.generated_at else date.today()
        baselines = compute_personal_baselines(db, user_id, today=ref_date)
        if not baselines:
            return
        twin.physiological.personal_baselines = [
            PersonalBaselineMetric(**mb.to_dict()) for mb in baselines
        ]
        sources.add("garmin")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[twin] personal_baseline 填充失败: {e}")


def _fill_garmin_official(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    """
    接入 Garmin 官方 Training Readiness / Training Status 到 Twin.

    这些字段已经由 garmin_connect.py 写入 daily_health_data 表 (P1a),
    但之前 Twin 不 load, 导致 recovery_coach 自己用 HRV+sleep 重造轮子,
    movement_coach 只认我们自算的 ACWR. 这里补齐.
    """
    try:
        from app.models.daily_health import GarminData

        # 取最近 7 天里有 training_readiness_score 的最新一天 (不一定是今天,
        # Garmin watch 同步延迟 + readiness 可能当天没算完)
        row = (
            db.query(GarminData)
            .filter(GarminData.user_id == user_id)
            .filter(GarminData.training_readiness_score.isnot(None))
            .order_by(GarminData.record_date.desc())
            .limit(1)
            .first()
        )
        if not row:
            return

        p = twin.physiological
        b = twin.behavioral

        if row.training_readiness_score is not None:
            p.training_readiness_score = int(row.training_readiness_score)
            p.training_readiness_date = row.record_date  # 哪天的 readiness(前端判新鲜度,旧分不当今日)
        if row.training_readiness_level:
            p.training_readiness_level = str(row.training_readiness_level)
        if row.training_readiness_factors:
            p.training_readiness_factors = row.training_readiness_factors

        if row.training_status:
            b.training_status = str(row.training_status)
        if row.training_status_feedback:
            b.training_status_feedback = str(row.training_status_feedback)
        if row.acute_load is not None:
            b.acute_load = float(row.acute_load)
        if row.load_ratio is not None:
            b.load_ratio = float(row.load_ratio)

        sources.add("garmin_official")
    except Exception as e:
        logger.warning(f"[twin] garmin_official 失败: {e}")


_COLD_KEYWORDS = (
    "感冒", "发烧", "发热", "低烧", "高烧", "咳嗽", "咽痛", "嗓子疼", "喉咙痛",
    "鼻塞", "流鼻涕", "流涕", "打喷嚏", "头痛", "头疼", "畏寒", "寒战",
    "乏力", "肌肉酸痛", "全身酸痛", "新冠", "流感", "上呼吸道",
)
_FEVER_KEYWORDS = ("发烧", "发热", "低烧", "高烧", "体温", "38", "39", "40")
_RESPIRATORY_BODY_PARTS = {"respiratory", "head", "general"}


def _looks_like_cold(text: str) -> bool:
    lowered = (text or "").lower()
    return any(k.lower() in lowered for k in _COLD_KEYWORDS)


def _fill_acute_health(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    """填充近期急性病/感冒症状状态。

    规则偏保守：只要有未痊愈 illness episode，或 72 小时内出现呼吸道/全身
    感冒关键词，就把训练建议降到 rest。用户恢复后删除/标记 resolved 即解除。
    """
    try:
        from app.models.illness import IllnessEpisode
        from app.models.symptom_entry import SymptomEntry

        active_illnesses = (
            db.query(IllnessEpisode)
            .filter(
                IllnessEpisode.user_id == user_id,
                IllnessEpisode.status.in_(["active", "improving"]),
            )
            .order_by(IllnessEpisode.start_date.desc())
            .limit(5)
            .all()
        )

        cutoff = datetime.now(UTC) - timedelta(hours=72)
        recent_symptoms = (
            db.query(SymptomEntry)
            .filter(
                SymptomEntry.user_id == user_id,
                SymptomEntry.occurred_at >= cutoff,
            )
            .order_by(SymptomEntry.occurred_at.desc())
            .limit(10)
            .all()
        )

        illness_names = [i.name for i in active_illnesses if i.name]
        # 全部症状描述(未过滤)—— 供症状级急症红线匹配胸痛/卒中/腹痛等
        symptom_texts_all = [s.description for s in recent_symptoms if s.description]
        symptom_texts = [
            s.description for s in recent_symptoms
            if s.description and (
                s.body_part in _RESPIRATORY_BODY_PARTS or _looks_like_cold(s.description)
            )
        ]
        combined = " ".join(illness_names + symptom_texts)
        suspected_cold = bool(combined and _looks_like_cold(combined))
        fever_reported = any(k in combined for k in _FEVER_KEYWORDS)
        has_active = bool(active_illnesses)

        # 注意:含 symptom_texts_all —— 即使只有非呼吸道症状(胸痛/腹痛等),
        # 也要继续填充,否则症状级急症红线拿不到数据。
        if not (has_active or symptom_texts or symptom_texts_all):
            return

        severities = [
            int(v) for v in (
                [getattr(i, "severity", None) for i in active_illnesses]
                + [getattr(s, "severity", None) for s in recent_symptoms]
            )
            if isinstance(v, int)
        ]

        twin.acute.has_active_illness = has_active
        twin.acute.illness_names = illness_names[:5]
        twin.acute.illness_severity_max = max(severities) if severities else None
        twin.acute.recent_symptoms = symptom_texts[:8]
        twin.acute.symptom_texts_all = symptom_texts_all[:12]
        twin.acute.suspected_cold = suspected_cold
        twin.acute.fever_reported = fever_reported
        twin.acute.should_rest_from_training = bool(has_active or suspected_cold or fever_reported)
        if twin.acute.should_rest_from_training:
            if fever_reported:
                twin.acute.training_guardrail = "发热/疑似感染期暂停训练；退热且症状明显缓解后再从低强度恢复。"
            elif suspected_cold:
                twin.acute.training_guardrail = "感冒/上呼吸道症状期不要求完成运动目标；优先休息、补水和睡眠。"
            else:
                twin.acute.training_guardrail = "急性不适期暂停训练目标；症状缓解后再恢复低强度活动。"
        sources.add("acute")
    except Exception as e:
        logger.warning(f"[twin] acute_health 失败: {e}")


def _fill_problem_red_lines(
    db: Session,
    user_id: int,
    twin: HealthTwin,
    sources: Set[str],
    raise_on_error: bool = False,
) -> None:
    """把 active HealthProblem 的个性化红线投影到 acute 分区,供 safety 规则消费。

    独立于 _fill_acute_health(它无症状即早返回);红线即使当下无症状也要在 Twin 里,
    安全规则才能在症状出现时拿来匹配。

    失败语义二选一:
    - `raise_on_error=False`(默认)—— 失败降级,只 log warning 后正常返回,不阻塞
      Twin 构建。`build_twin` 主流程走这条:红线只是 Twin 的一个分区,填不上不该
      让整个 Twin 构建失败(通用报告仍要韧性)。
    - `raise_on_error=True` —— **不吞,向上抛**。安全关键路径(如腕上症状裁决)走这条:
      红线没填全 = 个性化安全筛查不完整,调用方必须能感知,绝不能静默留空 → 早返回
      → 看似绿灯(under-alarm = 医疗危险)。
    """
    try:
        from app.services import health_problem_service as prob_svc
        from app.twin.schema import ProblemRedLine

        red_lines = []
        # active_only=True 保留 active + monitoring(只排除 resolved):
        # 愈合转「随访监测」的问题红线仍要兜(如胃溃疡黑便复发),不能收窄到只 active。
        for p in prob_svc.list_problems(db, user_id, active_only=True):
            for rl in (p.red_lines or []):
                cond = (rl.get("condition") or "").strip()
                action = (rl.get("action") or "").strip()
                if not cond or not action:
                    continue
                red_lines.append(ProblemRedLine(
                    problem_name=p.name or "健康问题",
                    condition=cond,
                    action=action,
                    risk_level=p.risk_level or "P1",
                ))
        if red_lines:
            twin.acute.problem_red_lines = red_lines
            sources.add("problem_red_lines")
    except Exception as e:
        logger.warning(f"[twin] problem_red_lines 失败: {e}")
        if raise_on_error:
            # 安全关键路径:不吞,让调用方把「红线未填全」当作安全筛查不完整处理。
            raise


def _fill_cross_source(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    """R3 多源置信度回灌:跨设备一致性指数 + 偏离指标,构 Twin 时算一次写进 physiological。

    决策灯/specialist/agenda 统一从 Twin 读,不各自重算。单源(<2 设备)→ index=None,
    不产偏离项。失败降级(不阻塞 Twin 构建)。
    """
    try:
        from app.services.recovery_decision import device_agreement_index
        from app.services.cross_source_validator import detect_cross_source_anomalies
        from app.twin.schema import CrossSourceDivergence

        idx, detail = device_agreement_index(db, user_id)
        srcs = list(detail.get("sources") or [])
        if idx is None and len(srcs) < 2:
            return  # 单源用户:无跨源置信可言,不写(保持 None 默认)

        twin.physiological.device_agreement_index = idx
        twin.physiological.device_sources = srcs

        anomalies = detect_cross_source_anomalies(db, user_id)
        twin.physiological.divergent_metrics = [
            CrossSourceDivergence(
                metric=a["metric"], label=a["label"],
                trusted_source=a.get("trusted_source") or "",
                outlier_source=a.get("outlier_source") or "",
                deviation_pct=a.get("deviation_pct") or 0.0,
                hint=a.get("hint") or "",
            )
            for a in anomalies[:5]
        ]
        sources.add("cross_source")
    except Exception as e:
        logger.warning(f"[twin] cross_source 失败: {e}")


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

        # 仅当最近一晚睡眠时长还没从 garmin merge 填上时,才回退到 7 日均值。
        # (sleep-deep analysis 偶发失败会返回 None,别用它覆盖掉已有的 latest 值。)
        if twin.physiological.sleep_duration_h_latest is None:
            twin.physiological.sleep_duration_h_latest = _as_float(
                analysis.get("duration_avg_hours")
            )

        if arch or consistency or hrv_recovery:
            sources.add("sleep")
    except Exception as e:
        # 仍降级不上抛(一个分区崩不该打死整个 Twin),但**必须留下可分辨的失败痕迹**:
        # 只 log warning 的话,失败与「无睡眠数据」在 Twin 上长得一模一样 → 静默 5 周。
        logger.error(f"[twin] sleep_deep 失败: {e}", exc_info=True)
        twin.meta.failed_partitions.append("sleep_deep")


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


def fill_medication_safety_partitions(
    db: Session,
    user_id: int,
    twin: HealthTwin,
    *,
    raise_on_error: bool = False,
) -> None:
    """只填用药安全预检(DDI/PGx/DSI)需要的分区,**全部用传入的请求 db**。

    为什么不走 build_twin(memory project_build_twin_sessionlocal_ignores_db):
      build_twin 的 Phase-B 并行 filler 各自 `SessionLocal()` 自开**生产引擎**连接、
      忽略传入 db。请求事务里 flush/commit 的药、在请求内构 twin 时:
        - 测试/CI:生产引擎指向另一个空 in-memory DB → 看不到任何药 → 预检空跑 = under-alarm;
        - 生产:在写事务内再开 N=16 个第二连接,既无必要也增加竞争面。
      故安全预检改用本函数:HealthTwin() + 只填 DDI/PGx/DSI 三类规则实际读的分区,
      全部走传入 db(看得见请求事务的数据、零第二连接)。

    DDI/PGx/DSI 实际读取(grep ddi.py/pgx.py/dsi.py 确认,改规则读取面前必复核):
      - medication.active_meds                                    → DDI / DSI
      - genetic.{drug_sensitivity, risk_variants, protective_variants} → PGx
      - supplement.active_supplements                             → DSI
      - labs.{flagged_abnormal, last_exam_date}                   → DSI(长期抑酸×化验感知)

    raise_on_error=True:任一分区填充抛错则向上抛(让调用方置 evaluation_failed,
      绝不静默把"填充失败"退化成"无药 → 无告警 → 安全")。默认 False 保持 build_twin
      内既有的旁路降级语义。
    """
    sources: Set[str] = set()

    # ① medication.active_meds —— DDI/DSI/PGx 三类规则全部 gate 在此分区上(空药单 →
    #    所有规则早返回 None → 看似无相互作用 = 安全)。这是最 load-bearing 的分区。
    #    _fill_medication 自带内部 try/except 旁路降级(供 build_twin 用):读药失败会
    #    静默留空 active_meds、不抛 —— 那样 raise_on_error 对本分区形同虚设,读药崩溃就
    #    退化成 under-alarm(与本次要消除的 SessionLocal 盲读同一 bug 类,只是触发源不同)。
    #    故 raise_on_error 时绕过吞异常 helper、直接 fail-loud 读药(读失败抛 → 调用方
    #    置 evaluation_failed → 注入 fail-safe advisory,绝不静默当无药)。
    if raise_on_error:
        from app.services.medication_service import MedicationService

        active = MedicationService().get_today_status(db, user_id) or []
        twin.medication.active_meds = active
        twin.medication.has_any = len(active) > 0
        if active:
            sources.add("medication")
    else:
        _fill_medication(db, user_id, twin, sources)

    # ② genetic 三类(PGx 读取):用与 _fill_collectors 同一套 collector + classify。
    try:
        gen = _collectors.fetch_genetic_variants_categorized(
            db, user_id, raise_on_error=raise_on_error
        )
        if gen and gen.get("total", 0) > 0:
            g = twin.genetic
            g.has_profile = True
            g.total_variants = gen["total"]
            g.drug_sensitivity = gen.get("drug_sensitivity", [])
            g.risk_variants = gen.get("risk", [])
            g.protective_variants = gen.get("protective", [])
            _classify_genetic_variants(g)
            sources.add("genetic")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[twin.safety] genetic 分区填充失败: {e}")
        if raise_on_error:
            raise

    # ③ supplement.active_supplements(DSI 读取)。
    try:
        supp = _collectors.fetch_supplement_today(
            db, user_id, raise_on_error=raise_on_error
        )
        twin.supplement = SupplementState(**supp)
        if supp.get("total_active_count", 0) > 0:
            sources.add("supplement")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[twin.safety] supplement 分区填充失败: {e}")
        if raise_on_error:
            raise

    # ④ labs.{flagged_abnormal, last_exam_date}(DSI 长期抑酸×化验感知读取)。
    try:
        abnormal, latest_exam = _collectors.fetch_medical_exam_abnormal(
            db, user_id, raise_on_error=raise_on_error
        )
        if abnormal:
            twin.labs.flagged_abnormal = abnormal
            sources.add("medical_exam")
        if latest_exam:
            twin.labs.last_exam_date = latest_exam.get("exam_date")
            twin.labs.last_exam_type = latest_exam.get("exam_type")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[twin.safety] labs 分区填充失败: {e}")
        if raise_on_error:
            raise

    twin.meta.data_sources = sorted(set(twin.meta.data_sources) | sources)


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
        twin.behavioral.acwr_reliable = load.get("acwr_reliable")
        twin.behavioral.acwr_unavailable_reason = load.get("acwr_unavailable_reason")
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

    # 7 天 WorkoutRecord 摘要 (供 movement_coach / fuel_strategist 读细粒度)
    try:
        from datetime import timedelta as _td
        from app.models.daily_health import WorkoutRecord
        from app.twin.schema import WorkoutSummary as _WS

        cutoff = date.today() - _td(days=7)
        wrs = (
            db.query(WorkoutRecord)
            .filter(
                WorkoutRecord.user_id == user_id,
                WorkoutRecord.workout_date >= cutoff,
            )
            .order_by(WorkoutRecord.workout_date.desc())
            .limit(20)
            .all()
        )
        summaries = []
        for w in wrs:
            # hr_zone 分布: 秒 → 分钟, 取最长
            zones = {}
            for i in range(1, 6):
                sec = getattr(w, f"hr_zone_{i}_seconds", None)
                if sec and sec > 0:
                    zones[f"z{i}"] = round(sec / 60.0, 1)
            dominant = None
            if zones:
                dominant = int(max(zones.items(), key=lambda kv: kv[1])[0][1:])  # "z3" → 3

            summaries.append(_WS(
                workout_date=w.workout_date.isoformat() if w.workout_date else None,
                workout_type=w.workout_type,
                duration_min=round(w.duration_seconds / 60.0, 1) if w.duration_seconds else None,
                distance_km=round(w.distance_meters / 1000.0, 2) if w.distance_meters else None,
                calories=w.calories,
                avg_hr=w.avg_heart_rate,
                max_hr=w.max_heart_rate,
                hr_zone_dominant=dominant,
                hr_zone_minutes=zones or None,
                training_effect_aerobic=w.training_effect_aerobic,
                training_effect_anaerobic=w.training_effect_anaerobic,
                training_load=w.training_load,
                perceived_exertion=w.perceived_exertion,
                feeling=w.feeling,
                avg_cadence=w.avg_cadence,
                avg_power_watts=w.avg_power_watts,
                elevation_gain_m=w.elevation_gain_meters,
            ))
        if summaries:
            twin.behavioral.recent_workouts = summaries
            sources.add("workout")
    except Exception as e:
        logger.warning(f"[twin] workout_summary 填充失败: {e}")


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

        # available=False → 里面的 aqi/pm25 是 `_get_default_aqi()` 的占位常量(aqi=50
        # "良"),不是测得的真值。写进 Twin 就会被 RhinitisSpecialist 当真做症状-环境
        # 因果归因、被 formatter 讲给用户 —— 编造。宁可没有,不可编造 → 当作无环境数据。
        # 只在**显式** False 时丢弃(不是 `not aqi_data.get("available")`):上游 shape
        # 不确定时缺 key 不该误杀真实 AQI(get_comprehensive_advice 恒显式给该键)。
        if isinstance(aqi_data, dict) and aqi_data.get("available") is False:
            aqi_data = {}

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
            latest_measured_at=summary.latest_measured_at,
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


# ─────────────────────────── 10. SpO2 夜间 ───────────────────────────


def _fill_spo2_overnight(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    """从 SpO2Sample 计算最近一晚的 ODI 和 below-90 占比。"""
    try:
        from sqlalchemy import desc

        from app.models.daily_health import GarminData, SpO2Sample
        from app.services.device_source_priority import excluded_sources

        # 血氧排除源(garmin):SpO2Sample 由 garmin 采集器 + HealthKit 导入
        # (apple-watch / ringconn 等贴肤光路, 见 healthkit.HealthKitAdapter._save_spo2_samples)
        # 共同写入。这条主路径喂夜间低氧 CRITICAL,必须按 source 过滤掉 garmin / garmin-app
        # (同一块腕式反射传感器的假性低值,后者是 Garmin→HealthKit 镜像),否则会漏进。
        # notin_ 同时把 source 为 NULL(历史/默认 garmin)的行排除,与"默认 garmin"一致;
        # apple-watch / ringconn / unknown 等贴肤光路源正常纳入。
        _ex_spo2 = list(excluded_sources("spo2_min"))

        latest_row = (
            db.query(SpO2Sample.record_date)
            .filter(SpO2Sample.user_id == user_id)
            .filter(SpO2Sample.source.notin_(_ex_spo2) if _ex_spo2 else True)
            .order_by(desc(SpO2Sample.record_date))
            .first()
        )
        if not latest_row:
            # 无逐秒 SpO2Sample (仅 Garmin Connect 写)。RingConn / Apple Watch 用户的夜间
            # 血氧低点落在 GarminData.spo2_min 里,但夜间严重低氧规则 (spo2_min_overnight)
            # 只读 SpO2Sample → 戒指/手表用户的夜间血氧下降永不告警。这里兜底:
            # 取最新一天跨源最小 spo2_min 喂给该规则(worst-value,不掩盖危险低值)。
            # 仅当存在非 garmin 源时启用 → 纯 garmin 用户行为完全不变(back-compat)。
            # 血氧整源剔除被排除源(garmin 腕式反射不准),与 pick_value 一致 —— 否则这条
            # 直查 SQL 兜底会把 garmin 假性低值漏进夜间低氧 CRITICAL 规则(安全评审阻断项)。
            # excluded_sources 已在函数顶部 import。
            ex_min = excluded_sources("spo2_min")
            min_rows = [
                r for r in (
                    db.query(GarminData)
                    .filter(GarminData.user_id == user_id, GarminData.spo2_min.isnot(None))
                    .order_by(desc(GarminData.record_date))
                    .all()
                )
                if (r.data_source or "garmin") not in ex_min
            ]
            if min_rows:  # 过滤后只剩可信源;garmin-only → 空 → 保持 None(宁可无数据)
                latest_min_date = min_rows[0].record_date
                day_mins = [
                    r.spo2_min for r in min_rows
                    if r.record_date == latest_min_date and r.spo2_min is not None
                ]
                if day_mins and twin.physiological.spo2_min_overnight is None:
                    twin.physiological.spo2_min_overnight = min(day_mins)

            # spo2_avg 兜底:跨源取最差(最小)日均,同样剔除被排除源。
            ex_avg = excluded_sources("spo2_avg")
            avg_rows = [
                r for r in (
                    db.query(GarminData)
                    .filter(GarminData.user_id == user_id, GarminData.spo2_avg.isnot(None))
                    .order_by(desc(GarminData.record_date))
                    .all()
                )
                if (r.data_source or "garmin") not in ex_avg
            ]
            if avg_rows:
                latest_avg_date = avg_rows[0].record_date
                day_avgs = [
                    r.spo2_avg for r in avg_rows
                    if r.record_date == latest_avg_date and r.spo2_avg is not None
                ]
                if day_avgs and not twin.physiological.spo2_avg:
                    twin.physiological.spo2_avg = min(day_avgs)
            return

        rd = latest_row[0]
        samples = (
            db.query(SpO2Sample)
            .filter(SpO2Sample.user_id == user_id, SpO2Sample.record_date == rd)
            .filter(SpO2Sample.source.notin_(_ex_spo2) if _ex_spo2 else True)
            .order_by(SpO2Sample.epoch_ms.asc())
            .all()
        )
        if not samples:
            return

        values = [s.spo2_value for s in samples]
        twin.physiological.spo2_min_overnight = min(values)
        twin.physiological.spo2_below_90_pct = round(
            sum(1 for v in values if v < 90) / len(values) * 100, 1
        )

        from app.api.spo2 import _compute_desaturation_events

        desat = _compute_desaturation_events(values)
        garmin = (
            db.query(GarminData)
            .filter(GarminData.user_id == user_id, GarminData.record_date == rd)
            .first()
        )
        sleep_hours = garmin.total_sleep_duration / 60.0 if garmin and garmin.total_sleep_duration else len(values) / 60.0
        if sleep_hours > 0:
            twin.physiological.spo2_odi = round(desat / sleep_hours, 1)

        if not twin.physiological.spo2_avg:
            twin.physiological.spo2_avg = round(sum(values) / len(values), 1)

        sources.add("spo2_samples")

    except Exception as e:  # noqa: BLE001
        logger.warning(f"[twin] spo2_overnight 失败: {e}")


def _fill_hrv_nightly(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    """从 hrv_readings 表聚合最近 7-14 夜的 HRV 平均 → twin.physiological.hrv_nightly_series。

    P2: RecoveryCoach 用这个做真 baseline，比单点 hrv_7d_avg 精确。
    """
    try:
        from app.models.garmin_timeseries import HrvReading
        from sqlalchemy import func as sa_func
        from datetime import date as _date, timedelta as _td

        # 最近 14 天的夜间平均
        cutoff = _date.today() - _td(days=14)
        rows = (
            db.query(
                HrvReading.record_date,
                sa_func.avg(HrvReading.hrv_value).label("avg_hrv"),
                sa_func.count(HrvReading.id).label("cnt"),
            )
            .filter(
                HrvReading.user_id == user_id,
                HrvReading.record_date >= cutoff,
            )
            .group_by(HrvReading.record_date)
            .order_by(HrvReading.record_date)
            .all()
        )
        if not rows:
            return

        series = [
            {
                "date": r.record_date.isoformat(),
                "hrv_avg": round(float(r.avg_hrv), 1),
                "count": int(r.cnt),
            }
            for r in rows
            if r.avg_hrv is not None
        ]
        twin.physiological.hrv_nightly_series = series
        if sources is not None:
            sources.add("hrv_readings_timeseries")
    except Exception as e:
        logger.warning(f"[twin] hrv_nightly 失败: {e}")


def _fill_respiration_nightly(db: Session, user_id: int, twin: HealthTwin, sources: Set[str]) -> None:
    """夜间 22:00-07:00 呼吸率平均 + 变异度 (OSAHS 筛查信号).

    策略:
    - 取最新有 respiration_samples 的一天 (用户 record_date)
    - 聚合 22:00-07:00 样本 (Time 列比较)
    - 若样本 < 20 视为数据不足 (睡眠期 Garmin 应至少每 5 分钟一个点, 9 小时 ~100 点)
    """
    try:
        from app.models.garmin_timeseries import RespirationSample
        from sqlalchemy import func as sa_func
        from datetime import time as _time

        # 找最新有数据的日期
        latest_date = (
            db.query(sa_func.max(RespirationSample.record_date))
            .filter(RespirationSample.user_id == user_id)
            .scalar()
        )
        if not latest_date:
            return

        # 该 record_date 的夜间窗: 22:00-24:00 (前一天晚) + 00:00-07:00 (本日早)
        # 简化: 只用同 record_date 内 22:00-24:00 和 00:00-07:00 的样本.
        # Garmin 的 record_date 归属逻辑: 睡眠主日期 = 起床那天.
        # 实际 Garmin 样本 record_date=N 可能横跨 前晚 22:00 和 次晨 07:00.
        night_samples = (
            db.query(RespirationSample.respiration_rate)
            .filter(
                RespirationSample.user_id == user_id,
                RespirationSample.record_date == latest_date,
                (RespirationSample.sample_time >= _time(22, 0))
                | (RespirationSample.sample_time <= _time(7, 0)),
            )
            .all()
        )
        rates = [float(r.respiration_rate) for r in night_samples if r.respiration_rate is not None]
        if len(rates) < 20:
            return

        avg = sum(rates) / len(rates)
        var = sum((x - avg) ** 2 for x in rates) / len(rates)
        stddev = var ** 0.5

        twin.physiological.respiration_nightly_avg = round(avg, 1)
        twin.physiological.respiration_nightly_stddev = round(stddev, 2)
        twin.physiological.respiration_nightly_samples = len(rates)
        sources.add("respiration_samples")
    except Exception as e:
        logger.warning(f"[twin] respiration_nightly 失败: {e}")


# ─────────────────────────── 11. 直接收集器 ───────────────────────────


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

    # — Chronic conditions (active user_disease_profiles)
    # 让 SupplementAdvisor 等 specialist 能拿到"肾结石/高血压/糖尿病"等病史做剂量调整
    try:
        from app.models.disease_tracking import UserDiseaseProfile
        active_profiles = (
            db.query(UserDiseaseProfile)
            .filter(
                UserDiseaseProfile.user_id == user_id,
                UserDiseaseProfile.status.in_(["chronic", "improving", "controlled"]),
            )
            .all()
        )
        condition_names = [p.disease_name for p in active_profiles if p.disease_name]
        if condition_names:
            twin.chronic.active_conditions = condition_names
            sources.add("chronic_conditions")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[twin] 拉 chronic conditions 失败 (旁路): {e}")

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

    # — ECG (Apple Watch 房颤筛查信号, 非诊断) → physiological
    ecg = _collectors.fetch_ecg_latest(db, user_id)
    if ecg:
        twin.physiological.ecg_classification = ecg.get("ecg_classification")
        twin.physiological.ecg_recorded_at = ecg.get("ecg_recorded_at")
        twin.physiological.afib_event_count = ecg.get("afib_event_count", 0)
        twin.physiological.afib_recent = ecg.get("afib_recent", False)
        sources.add("ecg")

    # — Waist circumference (metabolic syndrome should not rely on BMI only)
    waist = _collectors.fetch_waist_latest(db, user_id)
    if waist:
        twin.body_composition.waist_cm = waist.get("waist_cm")
        twin.body_composition.last_waist_measured = waist.get("record_date")
        twin.body_composition.waist_to_height_ratio = waist.get("waist_to_height_ratio")
        twin.body_composition.central_obesity_flag = waist.get("central_obesity_flag")
        sources.add("waist")

    # — Medical exam abnormal + latest meta (单次 joinedload 查询)
    abnormal, latest_exam = _collectors.fetch_medical_exam_abnormal(db, user_id)
    if abnormal:
        twin.labs.flagged_abnormal = abnormal
        sources.add("medical_exam")

    if latest_exam:
        twin.labs.last_exam_date = latest_exam.get("exam_date")
        twin.labs.last_exam_type = latest_exam.get("exam_type")

    # — Specific lab values (cross-review 依赖: alt / ast / ggt / creatinine / egfr / ldl / ...)
    # 不覆盖 integrated_profile 已填的, 只补缺失项
    latest_labs = _collectors.fetch_latest_labs(db, user_id)
    if latest_labs:
        for key, val in latest_labs.items():
            if hasattr(twin.labs, key) and getattr(twin.labs, key, None) is None:
                setattr(twin.labs, key, val)
        sources.add("medical_indicators")

    # — Genetic (细分类别覆盖 integrated_profile 的字符串列表)
    gen = _collectors.fetch_genetic_variants_categorized(db, user_id)
    if gen and gen.get("total", 0) > 0:
        twin.genetic.has_profile = True
        twin.genetic.total_variants = gen["total"]
        twin.genetic.drug_sensitivity = gen.get("drug_sensitivity", [])
        twin.genetic.risk_variants = gen.get("risk", [])
        twin.genetic.protective_variants = gen.get("protective", [])
        twin.genetic.cognition_variants = gen.get("cognition_variants", [])
        twin.genetic.personality_variants = gen.get("personality_variants", [])
        twin.genetic.sleep_variants = gen.get("sleep_variants", [])
        twin.genetic.recovery_variants = gen.get("recovery_variants", [])
        twin.genetic.exercise_variants = gen.get("exercise_variants", [])
        twin.genetic.nutrition_variants = gen.get("nutrition_variants", [])
        _classify_genetic_variants(twin.genetic)
        sources.add("genetic")

    # — Pending genetic profiles (PDF 解析中: profile 已建但 variant 尚未抽完)
    try:
        from app.models.genetic_data import GeneticProfile, GeneticVariant
        from sqlalchemy import func, and_
        pending = (
            db.query(func.count(GeneticProfile.id))
            .outerjoin(GeneticVariant, GeneticVariant.profile_id == GeneticProfile.id)
            .filter(
                GeneticProfile.user_id == user_id,
                ~(GeneticProfile.notes.contains("失败")),
            )
            .group_by(GeneticProfile.id)
            .having(func.count(GeneticVariant.id) == 0)
            .count()
        )
        twin.genetic.pending_profile_count = int(pending or 0)
    except Exception:  # noqa: BLE001
        pass

    # — PhenoAge (Levine 2018): labs 9 项 + 实足年龄齐才算; 任一缺失 → 留 None,不猜算
    _fill_phenoage(db, user_id, twin)


def _classify_genetic_variants(genetic: GeneticContext) -> None:
    """Phase 1: tag each variant dict with (actionability, evidence_grade).

    Pure static lookup via genetic_registry.classify_variant — no LLM, no DB.
    Resolves by rsid first, falling back to gene_name. Idempotent: re-running
    overwrites the same two keys. Never raises (classification is best-effort
    metadata; a missing import must not break Twin build).
    """
    try:
        from app.services.genetic_registry import classify_variant
    except Exception:  # noqa: BLE001
        return

    variant_lists = (
        genetic.drug_sensitivity,
        genetic.risk_variants,
        genetic.protective_variants,
        genetic.cognition_variants,
        genetic.personality_variants,
        genetic.sleep_variants,
        genetic.recovery_variants,
        genetic.exercise_variants,
        genetic.nutrition_variants,
    )
    for variants in variant_lists:
        for v in variants:
            if not isinstance(v, dict):
                continue
            key = v.get("rsid") or v.get("gene_name") or ""
            actionability, evidence_grade = classify_variant(
                str(key), gene_name=v.get("gene_name")
            )
            v["actionability"] = actionability
            v["evidence_grade"] = evidence_grade


def _fill_phenoage(db: Session, user_id: int, twin: HealthTwin) -> None:
    """聚合完 labs 后调用 compute_phenoage 填 LabsContext 派生字段。

    设计纪律 (docs/design-longevity-mvp.md §3):
      - 9 项血检任一缺失 → compute_phenoage 返回 None,这里全字段留 None,不写
      - 单位假设与 LabsContext 字段注释一致 (collector 不做单位转换)
      - 成功时同步写入 evidence_tier="validated" + claim_boundary,展示侧 must show
    """
    try:
        from app.services.phenoage import phenoage_from_labs

        age = _collectors.fetch_user_age(db, user_id)
        L = twin.labs
        result = phenoage_from_labs(L, age)
        if result is None:
            # 缺值 — 不写;只在所有 9 项 + age 都到位时再算
            return
        L.phenotypic_age = result.phenotypic_age
        L.phenotypic_age_delta_years = result.delta_years
        L.phenotypic_age_inputs_complete = result.inputs_complete
        L.phenoage_evidence_tier = result.evidence_tier
        L.phenoage_claim_boundary = result.claim_boundary
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[twin] phenoage 计算失败: {e}")


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
