"""Conversation starters (new-chat prompt chips).

This is used by the web `/ai-assistant` and mobile chat empty state to present
context-aware prompts derived from recent user data (exams/workouts/supplements,
current body state from Twin, and live weather/AQI).

Design constraints:
- Deterministic & fast: no LLM calls. Twin is Redis-cached (5min).
- Safe: never returns paid-course raw text; only user-owned data signals.
- Fail-soft: any error falls back to stable defaults; Twin failure falls back
  to DB-only signals (existing behavior pre-2026-05).
- Per-visit variety: when more candidates exist than slots, critical signals
  (priority >= 100) are always included; remaining slots are randomly sampled
  from the rest, weighted by priority. RNG is injectable for tests.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session


CHINA_TZ = ZoneInfo("Asia/Shanghai")


DEFAULT_SUGGESTIONS: list[str] = [
    "分析我最近的代谢健康",
    "今天怎么安排训练和恢复",
    "结合基因和体检给我建议",
    "帮我复盘最近的睡眠质量",
]

# 冷启动: 零数据新用户没有可分析的信号,DEFAULT_SUGGESTIONS 的"分析我的 X"对他们是空的。
# 这组 onboarding chip 驱动首次价值兑现(连设备 / 记一顿饭 / 传体检 / 定目标)。
# key="onboarding" → 可用 starter CTR 埋点直接量化冷启动激活率。
ONBOARDING_SUGGESTIONS: list[str] = [
    "连接 Garmin 或 Apple 健康，马上看到你的恢复评分和睡眠质量",
    "拍张餐照或说一句吃了什么，我帮你记录并估算热量营养",
    "上传一份体检报告，我来逐项解读异常指标",
    "告诉我你最想改善的健康目标，我帮你拆解第一步",
]

# Priority bands (higher = more likely to appear, critical always included):
#   100+  critical / safety — readiness<40, BP severe reading, AQI hazardous, ACWR danger
#    80   today body state — readiness/HRV/body battery/stress notable
#    70   today environment — AQI/UV/weather opportunity
#    60   personalized data signals — exam abnormal, gene, active goal
#    50   personalized routine — workout history, supplement, water, diet
#    30   data quality nudges — missing HRV
#    10   stable defaults — fallback only
_CRITICAL_PRIORITY = 100
_DEFAULT_PRIORITY = 10


@dataclass(frozen=True)
class SuggestionCandidate:
    priority: int
    text: str
    # Stable generator identity for analytics (CTR by generator). Derived from
    # the generator function name in `_build_candidates`; generators don't set it.
    # "default" for fallback suggestions.
    key: str = ""


@dataclass(frozen=True)
class StarterSignals:
    # ── Historical / aggregate (DB) ──────────────────────────────────────
    latest_exam_date: Optional[date]
    latest_exam_abnormal_items: list[str]
    active_goal_title: Optional[str]
    active_goal_current_value: Optional[float]
    active_goal_target_value: Optional[float]
    active_goal_unit: Optional[str]
    water_today_ml: Optional[int]
    diet_records_today: Optional[int]
    latest_workout_type: Optional[str]
    latest_workout_distance_km: Optional[float]
    latest_workout_duration_min: Optional[int]
    latest_workout_avg_hr: Optional[int]
    top_gene_name: Optional[str]
    top_gene_genotype: Optional[str]
    top_gene_result: Optional[str]
    workouts_7d: int
    active_supplements: int
    supplement_completion_7d_pct: Optional[float]
    avg_sleep_score_7d: Optional[float]
    missing_hrv_days_7d: Optional[int]

    # ── Follow-up signal reused from the push engine (#4b 增量) ──────────
    # 顶部的"该复查"化验项,来自 open_loop_manager._detect_lab_overdue,让 chips 也
    # 跟进随访(此前 chips 只看当前状态,push 才看随访)。
    overdue_lab_name: Optional[str] = None

    # ── Registered chronic problems (HealthProblem · R13) ────────────────
    # 慢病/结节登记是 Health OS 的分水岭 —— 用户已登记的鼻炎/胃溃疡/结节等,即使今天
    # 没有急性发作 (should_rest_from_training=False),也应能开一条"管理/复查"对话线。
    # 此前 chips/opener 只在 Twin.acute.illness_names 命中时才提慢病,导致 data-rich
    # 用户 (有登记问题但当下无急症) 反而拿不到接地的慢病提示 → 回落泛泛模板。
    top_problem_name: Optional[str] = None          # 最高优先级 active 问题名 (P0 在前)
    top_problem_risk_level: Optional[str] = None    # P0/P1/P2
    problem_followup_name: Optional[str] = None     # 到期/逾期随访的问题名
    problem_followup_overdue: bool = False
    problem_followup_risk_level: Optional[str] = None
    problem_followup_what_to_check: Optional[str] = None

    # ── Today / current (Twin — physiological + behavioral + env + labs) ─
    readiness_score: Optional[int] = None
    readiness_level: Optional[str] = None  # poor/low/moderate/high/prime
    hrv_today: Optional[float] = None
    hrv_7d_avg_twin: Optional[float] = None
    sleep_score_today: Optional[int] = None
    body_battery: Optional[int] = None
    stress_today: Optional[int] = None
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    acwr_zone: Optional[str] = None  # under/optimal/risky/danger
    training_status: Optional[str] = None
    should_rest_from_training: bool = False
    illness_names: list[str] = field(default_factory=list)
    aqi: Optional[int] = None
    aqi_level: Optional[str] = None
    pm25: Optional[float] = None
    uv_index: Optional[float] = None
    temperature_c: Optional[float] = None
    weather_description: Optional[str] = None
    city: Optional[str] = None
    outdoor_exercise_suitability: Optional[str] = None  # suitable/caution/avoid

    # ── Time context (Asia/Shanghai) ─────────────────────────────────────
    local_hour: Optional[int] = None        # 0–23
    local_weekday: Optional[int] = None     # 0=Mon … 6=Sun
    is_weekend: bool = False


def compute_conversation_suggestion_cards(
    db: Session,
    user_id: int,
    *,
    limit: int = 4,
    rng: Optional[random.Random] = None,
) -> list[SuggestionCandidate]:
    """Return up to `limit` suggestion cards (text + generator `key` + priority).

    Same selection as `compute_conversation_suggestions`, but keeps the generator
    identity so callers can attribute clicks/impressions per generator.

    Selection:
      1) Collect candidates (priority, text, key) from all generators.
      2) Critical (priority >= 100) are always taken (up to limit).
      3) Remaining slots: weighted random sample from non-critical pool.
      4) Result is sorted by priority desc for stable display ordering.
      5) DEFAULT_SUGGESTIONS fill any leftover slot (priority 10, key="default").
    """
    if limit <= 0:
        return []

    try:
        signals = _collect_signals(db, user_id)
        # 冷启动: 零数据新用户 → onboarding chips(驱动首次价值兑现),而不是泛泛的
        # "分析我的 X"(他们还没有 X 可分析)。
        if not _has_any_user_signal(signals):
            return _onboarding_cards(limit)
        candidates = _build_candidates(signals)
        return _select_cards(candidates, limit=limit, rng=rng)
    except Exception:  # noqa: BLE001
        # Fail-soft: empty-state prompts must never break chat launch.
        return _default_cards(limit)


def compute_conversation_suggestions(
    db: Session,
    user_id: int,
    *,
    limit: int = 4,
    rng: Optional[random.Random] = None,
) -> list[str]:
    """Return up to `limit` prompt-chip strings for a new conversation (text only)."""
    return [
        c.text
        for c in compute_conversation_suggestion_cards(db, user_id, limit=limit, rng=rng)
    ]


def compute_salient_signals(
    db: Session,
    user_id: int,
    *,
    limit: int = 8,
) -> list[SuggestionCandidate]:
    """Shared "what matters now" engine — ranked health-state signals (priority desc).

    This is the SINGLE source of salience, consumed by both surfaces that ask
    "what's most important for this user right now":
      - reactive chips: `compute_conversation_suggestion_cards` (this module)
      - proactive push: `open_loop_manager._detect_salient_state`

    Both run the same generators (`_collect_signals` → `_build_candidates`); they
    differ only in PRESENTATION (chips do per-visit weighted-random + defaults;
    push takes top criticals). Returning the raw ranked candidates here lets each
    caller apply its own selection without re-deriving thresholds.

    Critical signals carry priority >= 100 (readiness crash, acute illness, severe
    BP reading, ACWR danger, hazardous AQI). Fail-soft: returns [] on any error.
    """
    try:
        candidates = _build_candidates(_collect_signals(db, user_id))
    except Exception:  # noqa: BLE001
        return []
    candidates.sort(key=lambda c: -c.priority)
    return candidates[:limit] if limit else candidates


def _default_cards(limit: int) -> list[SuggestionCandidate]:
    return [
        SuggestionCandidate(_DEFAULT_PRIORITY, text, "default")
        for text in DEFAULT_SUGGESTIONS[:limit]
    ]


def _onboarding_cards(limit: int) -> list[SuggestionCandidate]:
    """Cold-start prompts for a zero-data user (key="onboarding" for CTR tracking)."""
    return [
        SuggestionCandidate(_DEFAULT_PRIORITY, text, "onboarding")
        for text in ONBOARDING_SUGGESTIONS[:limit]
    ]


# ───────────────────────────── Signal collection ────────────────────────


def _collect_signals(db: Session, user_id: int) -> StarterSignals:
    from app.models.medical_exam import MedicalExam, MedicalExamItem
    from app.models.daily_health import DietRecord, GarminData, WaterIntake, WorkoutRecord
    from app.models.genetic_data import GeneticVariant
    from app.models.goal import Goal, GoalStatus
    from app.models.supplement import SupplementDefinition, SupplementRecord

    today = date.today()
    start_7d = today - timedelta(days=6)
    start_14d = today - timedelta(days=13)

    latest_exam = (
        db.query(MedicalExam)
        .filter(MedicalExam.user_id == user_id)
        .order_by(MedicalExam.exam_date.desc(), MedicalExam.id.desc())
        .first()
    )
    latest_exam_date = latest_exam.exam_date if latest_exam else None
    abnormal_items: list[str] = []
    if latest_exam:
        rows = (
            db.query(MedicalExamItem.item_name)
            .filter(
                MedicalExamItem.exam_id == latest_exam.id,
                MedicalExamItem.is_abnormal.isnot(None),
                MedicalExamItem.is_abnormal != "normal",
            )
            .order_by(MedicalExamItem.id.asc())
            .limit(3)
            .all()
        )
        abnormal_items = [str(r[0]) for r in rows if r and r[0]]

    active_goal = (
        db.query(Goal)
        .filter(
            Goal.user_id == user_id,
            Goal.status == GoalStatus.ACTIVE,
        )
        .order_by(Goal.priority.desc(), Goal.updated_at.desc().nullslast(), Goal.created_at.desc())
        .first()
    )

    water_today_ml = (
        db.query(func.sum(WaterIntake.amount_ml))
        .filter(
            WaterIntake.user_id == user_id,
            WaterIntake.record_date == today,
        )
        .scalar()
    )
    water_today_ml = int(water_today_ml) if water_today_ml is not None else None

    diet_records_today = (
        db.query(func.count(DietRecord.id))
        .filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date == today,
        )
        .scalar()
    )
    diet_records_today = int(diet_records_today or 0)

    workouts_7d = (
        db.query(func.count(WorkoutRecord.id))
        .filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.workout_date >= start_7d,
            WorkoutRecord.workout_date <= today,
        )
        .scalar()
    ) or 0

    latest_workout = (
        db.query(WorkoutRecord)
        .filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.workout_date >= start_14d,
            WorkoutRecord.workout_date <= today,
        )
        .order_by(WorkoutRecord.workout_date.desc(), WorkoutRecord.start_time.desc().nullslast(), WorkoutRecord.id.desc())
        .first()
    )

    top_gene = (
        db.query(GeneticVariant)
        .filter(
            GeneticVariant.user_id == user_id,
            GeneticVariant.risk_level.in_(["high", "medium"]),
        )
        .order_by(
            GeneticVariant.risk_level.asc(),
            GeneticVariant.updated_at.desc().nullslast(),
            GeneticVariant.created_at.desc(),
        )
        .first()
    )

    active_supplements = (
        db.query(func.count(SupplementDefinition.id))
        .filter(
            SupplementDefinition.user_id == user_id,
            SupplementDefinition.is_active.is_(True),
        )
        .scalar()
    ) or 0

    supplement_completion_7d_pct: Optional[float] = None
    if active_supplements > 0:
        taken_week = (
            db.query(func.count(SupplementRecord.id))
            .filter(
                SupplementRecord.user_id == user_id,
                SupplementRecord.record_date >= start_7d,
                SupplementRecord.record_date <= today,
                SupplementRecord.taken.is_(True),
            )
            .scalar()
        ) or 0
        total_expected = active_supplements * 7
        supplement_completion_7d_pct = round(taken_week / total_expected * 100, 1) if total_expected > 0 else 0.0

    # 多源按日合并后再平均 (否则报睡眠分的设备多 → 均值被重复计入拉偏)
    from app.services.garmin_daily_merged import merged_metric_series
    _sleep_series = merged_metric_series(
        db, user_id, "sleep_score", since=start_7d, until=today,
    )
    _sleep_vals = [v for _, v in _sleep_series]
    avg_sleep_score_7d = float(sum(_sleep_vals) / len(_sleep_vals)) if _sleep_vals else None

    # HRV missing days in the last 7 days (data completeness signal)
    total_garmin_rows_7d = (
        db.query(func.count(GarminData.id))
        .filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start_7d,
            GarminData.record_date <= today,
        )
        .scalar()
    ) or 0
    hrv_dates = (
        db.query(GarminData.record_date)
        .filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start_7d,
            GarminData.record_date <= today,
            GarminData.hrv.isnot(None),
        )
        .all()
    )
    available_dates = {r[0] for r in hrv_dates if r and r[0]}
    expected_dates = {start_7d + timedelta(days=i) for i in range(7)}
    missing_hrv_days_7d = None if total_garmin_rows_7d == 0 else len(expected_dates - available_dates)

    # ── Follow-up: 复用 push 侧的化验复查检测 (#4b 增量, chips↔push 双向统一)。
    # 只取最高分的一项,fail-soft。注意只调 _detect_lab_overdue(不调 collect_open_loops,
    # 后者含 _detect_salient_state → compute_salient_signals → _collect_signals 会递归)。
    overdue_lab_name: Optional[str] = None
    try:
        from app.tasks.open_loop_manager import _detect_lab_overdue

        _loops = _detect_lab_overdue(db, user_id) or []
        if _loops:
            overdue_lab_name = max(_loops, key=lambda lp: lp.score).signal_key or None
    except Exception:  # noqa: BLE001
        overdue_lab_name = None

    # ── Registered chronic problems (HealthProblem · R13). Deterministic reads;
    # reuses the SAME due-follow-up detection (health_problem_service.due_followups)
    # that projects onto the agenda/timeline, so a chip↔timeline can't disagree.
    # fail-soft: any error leaves all problem_* fields None/False.
    top_problem_name: Optional[str] = None
    top_problem_risk_level: Optional[str] = None
    problem_followup_name: Optional[str] = None
    problem_followup_overdue = False
    problem_followup_risk_level: Optional[str] = None
    problem_followup_what_to_check: Optional[str] = None
    try:
        from app.services import health_problem_service as _prob_svc

        _problems = _prob_svc.list_problems(db, user_id, active_only=True)
        if _problems:
            # list_problems already sorts P0 first → most salient registered problem.
            _top = _problems[0]
            top_problem_name = (_top.name or None)
            top_problem_risk_level = _top.risk_level or None

        # Due/overdue chronic follow-up (most urgent first: due_followups sorts by
        # next_due asc; take the earliest so an overdue one wins over a merely-due one).
        _fus = _prob_svc.due_followups(db, user_id, within_days=14)
        if _fus:
            _fu = _fus[0]
            problem_followup_name = _fu.get("name") or None
            problem_followup_overdue = bool(_fu.get("overdue"))
            problem_followup_risk_level = _fu.get("risk_level") or None
            problem_followup_what_to_check = _fu.get("what_to_check") or None
    except Exception:  # noqa: BLE001
        top_problem_name = None
        top_problem_risk_level = None
        problem_followup_name = None
        problem_followup_overdue = False
        problem_followup_risk_level = None
        problem_followup_what_to_check = None

    # ── Twin overlay (today / current state). Fail-soft. ─────────────────
    twin_kwargs: dict = {}
    try:
        from app.twin.builder import build_twin

        twin = build_twin(db, user_id, use_cache=True)
        phys = twin.physiological
        labs = twin.labs
        beh = twin.behavioral
        env = twin.environment
        acute = twin.acute

        twin_kwargs = {
            "readiness_score": phys.training_readiness_score,
            "readiness_level": phys.training_readiness_level,
            "hrv_today": phys.hrv_latest,
            "hrv_7d_avg_twin": phys.hrv_7d_avg,
            "sleep_score_today": phys.sleep_score_latest,
            "body_battery": phys.body_battery_current,
            "stress_today": phys.stress_level_current,
            "systolic_bp": labs.blood_pressure_systolic,
            "diastolic_bp": labs.blood_pressure_diastolic,
            "acwr_zone": beh.acwr_zone,
            "training_status": beh.training_status,
            "should_rest_from_training": bool(acute.should_rest_from_training),
            "illness_names": list(acute.illness_names or []),
            "aqi": env.aqi,
            "aqi_level": env.aqi_level,
            "pm25": env.pm25,
            "uv_index": env.uv_index,
            "temperature_c": env.temperature_c,
            "weather_description": env.weather_description,
            "city": env.city,
            "outdoor_exercise_suitability": env.outdoor_exercise_suitability,
        }
    except Exception:  # noqa: BLE001
        # Twin unavailable — keep historical-only signals.
        twin_kwargs = {}

    # ── Time context (Asia/Shanghai). Always populated. ──────────────────
    now_local = datetime.now(CHINA_TZ)
    time_kwargs = {
        "local_hour": now_local.hour,
        "local_weekday": now_local.weekday(),
        "is_weekend": now_local.weekday() >= 5,
    }

    return StarterSignals(
        latest_exam_date=latest_exam_date,
        latest_exam_abnormal_items=abnormal_items,
        active_goal_title=active_goal.title if active_goal else None,
        active_goal_current_value=active_goal.current_value if active_goal else None,
        active_goal_target_value=active_goal.target_value if active_goal else None,
        active_goal_unit=active_goal.target_unit if active_goal else None,
        water_today_ml=water_today_ml,
        diet_records_today=diet_records_today,
        latest_workout_type=latest_workout.workout_type if latest_workout else None,
        latest_workout_distance_km=(
            round(float(latest_workout.distance_meters) / 1000, 1)
            if latest_workout and latest_workout.distance_meters is not None else None
        ),
        latest_workout_duration_min=(
            round(latest_workout.duration_seconds / 60)
            if latest_workout and latest_workout.duration_seconds is not None else None
        ),
        latest_workout_avg_hr=latest_workout.avg_heart_rate if latest_workout else None,
        top_gene_name=top_gene.gene_name if top_gene else None,
        top_gene_genotype=top_gene.genotype if top_gene else None,
        top_gene_result=top_gene.result_label if top_gene else None,
        workouts_7d=int(workouts_7d),
        active_supplements=int(active_supplements),
        supplement_completion_7d_pct=supplement_completion_7d_pct,
        avg_sleep_score_7d=avg_sleep_score_7d,
        missing_hrv_days_7d=missing_hrv_days_7d,
        overdue_lab_name=overdue_lab_name,
        top_problem_name=top_problem_name,
        top_problem_risk_level=top_problem_risk_level,
        problem_followup_name=problem_followup_name,
        problem_followup_overdue=problem_followup_overdue,
        problem_followup_risk_level=problem_followup_risk_level,
        problem_followup_what_to_check=problem_followup_what_to_check,
        **twin_kwargs,
        **time_kwargs,
    )


def is_cold_start_user(db: Session, user_id: int) -> bool:
    """True iff this user has zero usable health signal (cold-start / onboarding).

    Reuses the SAME zero-signal determination (`_collect_signals` +
    `_has_any_user_signal`) that decides onboarding chips, so the top-level
    `onboarding` flag and the onboarding chip branch can never disagree.

    Fail-soft: on any error, returns False (NOT cold-start). A brand-new user
    who errors here just loses the synthetic opener and falls back to the normal
    (empty) opener — safer than injecting a synthetic opener onto an established
    user whose signal collection transiently failed.
    """
    try:
        return not _has_any_user_signal(_collect_signals(db, user_id))
    except Exception:  # noqa: BLE001
        return False


def _has_any_user_signal(signals: StarterSignals) -> bool:
    return bool(
        signals.latest_exam_date
        or signals.active_goal_title
        or signals.water_today_ml is not None
        or signals.diet_records_today
        or signals.latest_workout_type
        or signals.top_gene_name
        or signals.workouts_7d > 0
        or signals.active_supplements > 0
        or signals.avg_sleep_score_7d is not None
        or signals.missing_hrv_days_7d is not None
        or signals.readiness_score is not None
        or signals.sleep_score_today is not None
        or signals.body_battery is not None
        or signals.stress_today is not None
        or signals.hrv_today is not None
        or signals.systolic_bp is not None
        or signals.overdue_lab_name is not None
        or signals.top_problem_name is not None
    )


# ─────────────────────────── Candidate generators ───────────────────────


def _suggest_exam(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    if not signals.latest_exam_date:
        return None
    if signals.latest_exam_abnormal_items:
        focus = "、".join(signals.latest_exam_abnormal_items[:2])
        return SuggestionCandidate(60, f"解读我最近一次体检（关注: {focus}）")
    return SuggestionCandidate(50, "解读我最近一次体检结果")


def _format_number(value: float | None) -> str | None:
    if value is None:
        return None
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _suggest_goal(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    if not signals.active_goal_title:
        return None
    title = signals.active_goal_title[:28]
    cur = _format_number(signals.active_goal_current_value)
    target = _format_number(signals.active_goal_target_value)
    unit = signals.active_goal_unit or ""
    if cur and target:
        return SuggestionCandidate(60, f"围绕「{title}」安排接下来7天行动（当前 {cur}{unit} → 目标 {target}{unit}）")
    return SuggestionCandidate(60, f"围绕「{title}」安排接下来7天行动")


def _workout_type_label(value: str | None) -> str:
    return {
        "running": "跑步",
        "cycling": "骑行",
        "swimming": "游泳",
        "strength": "力量训练",
        "walking": "步行",
        "hiking": "徒步",
        "yoga": "瑜伽",
        "hiit": "HIIT",
        "cardio": "有氧训练",
    }.get(value or "", value or "运动")


def _suggest_workout(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    if signals.latest_workout_type:
        label = _workout_type_label(signals.latest_workout_type)
        details: list[str] = []
        if signals.latest_workout_distance_km is not None:
            details.append(f"{signals.latest_workout_distance_km:g}km")
        if signals.latest_workout_duration_min is not None:
            details.append(f"{signals.latest_workout_duration_min}min")
        if signals.latest_workout_avg_hr is not None:
            details.append(f"均心率 {signals.latest_workout_avg_hr}")
        suffix = f"（{' / '.join(details)}）" if details else ""
        return SuggestionCandidate(50, f"复盘我最近一次{label}{suffix}")
    if signals.workouts_7d <= 0:
        return None
    return SuggestionCandidate(50, "复盘我最近7天训练负荷与恢复情况")


def _suggest_gene(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    if not signals.top_gene_name:
        return None
    gene = signals.top_gene_name
    genotype = f" {signals.top_gene_genotype}" if signals.top_gene_genotype else ""
    result = f"（{signals.top_gene_result[:18]}）" if signals.top_gene_result else ""
    return SuggestionCandidate(60, f"结合我的 {gene}{genotype} 基因结果{result}制定行动")


def _suggest_water(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    if signals.water_today_ml is None:
        return None
    target = 2000
    if signals.water_today_ml >= target:
        return SuggestionCandidate(40, "今天饮水已达标，帮我安排后续补水和睡前注意事项")
    return SuggestionCandidate(50, f"今天饮水 {signals.water_today_ml}/{target}ml，帮我安排剩余补水")


def _suggest_diet(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    if not _has_any_user_signal(signals):
        return None
    if signals.diet_records_today is None or signals.diet_records_today > 0:
        return None
    return SuggestionCandidate(50, "今天还没记录饮食，帮我快速补录并估算")


def _suggest_supplement(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    if signals.active_supplements <= 0:
        return None
    rate = signals.supplement_completion_7d_pct
    if rate is None:
        return SuggestionCandidate(50, "帮我复盘最近的补剂服用情况并优化计划")
    if rate < 60:
        return SuggestionCandidate(70, f"帮我提升补剂依从率（近7天完成率 {rate:.1f}%）")
    return SuggestionCandidate(40, "检查我的补剂方案是否需要调整")


def _suggest_recovery_history(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    if signals.missing_hrv_days_7d is not None and signals.missing_hrv_days_7d >= 3:
        return SuggestionCandidate(30, "我的HRV数据不太完整，帮我排查并告诉我如何补齐")
    if signals.avg_sleep_score_7d is not None and signals.avg_sleep_score_7d < 70:
        return SuggestionCandidate(60, "帮我复盘最近的睡眠质量并给出可执行改进")
    return None


def _suggest_lab_recheck(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    """随访: 关键化验已超期未复查(来自 push 侧 _detect_lab_overdue 同一检测)。"""
    if not signals.overdue_lab_name:
        return None
    return SuggestionCandidate(
        60,
        f"我的 {signals.overdue_lab_name} 上次检查已超期，帮我安排复查并对比上次结果",
    )


# ── Registered chronic problems (HealthProblem · R13) ────────────────────

# 结节/分期类框架的括注 ("(Hp 阴性,胃窦后壁)" / "(TI-RADS 3)") 对 chip 太长且偏诊断,
# 展示时剥掉,只留问题主名。名过长再截。
_PROBLEM_PAREN_RE = re.compile(r"[（(][^）)]*[）)]")
_PROBLEM_NAME_MAX = 18


def _short_problem_name(name: Optional[str]) -> str:
    if not name:
        return ""
    s = _PROBLEM_PAREN_RE.sub("", name).strip()
    s = s.rstrip("，,。；;、：: ").strip()
    return s[:_PROBLEM_NAME_MAX]


def _suggest_problem_followup(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    """随访到期/逾期的登记问题 (慢病/结节) → 复查决策线。

    复用 health_problem_service.due_followups(同一投影到时间线的检测),让 chip 与
    议程复查项一致。P0/P1 逾期是高优先级(90),其余按到期/逾期给中高分。
    """
    name = _short_problem_name(signals.problem_followup_name)
    if not name:
        return None
    risk = (signals.problem_followup_risk_level or "").upper()
    what = (signals.problem_followup_what_to_check or "").strip()
    focus = f"(重点看 {what[:14]})" if what else ""
    if signals.problem_followup_overdue:
        prio = 90 if risk in ("P0", "P1") else 70
        return SuggestionCandidate(prio, f"「{name}」的复查已到期{focus}，帮我安排并对比上次")
    prio = 70 if risk in ("P0", "P1") else 55
    return SuggestionCandidate(prio, f"「{name}」快到复查时间了{focus}，帮我提前准备")


def _suggest_health_problem(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    """已登记的慢病/结节 (无当下急症、无临期随访) → 日常管理/近况回顾线。

    这是 data-rich 用户此前的接地盲区:登记了鼻炎/胃溃疡等问题,但今天既没有 Twin
    acute 发作、随访也没到期时,之前一条相关 chip 都没有 → 回落泛泛模板。
    与 followup chip 互斥:随访到期时让 followup 那条(更可执行)出场,避免两条同问题。
    """
    name = _short_problem_name(signals.top_problem_name)
    if not name:
        return None
    # 若该问题正好有临期随访, 交给 _suggest_problem_followup(更具体), 这里让位避免重复。
    if signals.problem_followup_name and _short_problem_name(
        signals.problem_followup_name
    ) == name:
        return None
    risk = (signals.top_problem_risk_level or "").upper()
    prio = 65 if risk in ("P0", "P1") else 55
    return SuggestionCandidate(prio, f"围绕我的「{name}」,最近该注意什么、怎么管理?")


# ── Today body state (Twin-driven) ──────────────────────────────────────


def _suggest_readiness(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    score = signals.readiness_score
    if score is None:
        return None
    if score < 40:
        return SuggestionCandidate(100, f"今天恢复评分 {score}，帮我安排轻负荷或休息日方案")
    if score >= 85:
        return SuggestionCandidate(80, f"今天恢复评分 {score}，能上多大强度的训练？")
    if score < 60:
        return SuggestionCandidate(80, f"今天恢复评分 {score}，怎么把训练调整成中低强度？")
    return SuggestionCandidate(60, f"今天恢复评分 {score}，给我一份今日训练与恢复建议")


def _suggest_hrv_today(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    hrv = signals.hrv_today
    avg = signals.hrv_7d_avg_twin
    if hrv is None or avg is None or avg <= 0:
        return None
    delta_pct = (hrv - avg) / avg * 100
    if delta_pct <= -15:
        return SuggestionCandidate(
            90,
            f"今天HRV {hrv:.0f}（较7日均值低 {abs(delta_pct):.0f}%），可能是什么原因？",
        )
    if delta_pct >= 15:
        return SuggestionCandidate(
            60,
            f"今天HRV {hrv:.0f}（较7日均值高 {delta_pct:.0f}%），怎么用好这天？",
        )
    return None


def _suggest_body_battery_stress(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    bb = signals.body_battery
    stress = signals.stress_today
    if bb is not None and bb < 30:
        return SuggestionCandidate(80, f"身体电量只剩 {bb}，怎么快速恢复精力？")
    if stress is not None and stress >= 75:
        return SuggestionCandidate(80, f"今天压力指数 {stress}，给我一套降压方案")
    if bb is not None and bb >= 80 and (stress is None or stress < 50):
        return SuggestionCandidate(50, f"身体电量 {bb}，今天能怎么高效利用这份精力？")
    return None


def _suggest_bp(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    sys_bp = signals.systolic_bp
    dia_bp = signals.diastolic_bp
    if sys_bp is None and dia_bp is None:
        return None
    if (sys_bp is not None and sys_bp >= 180) or (dia_bp is not None and dia_bp >= 120):
        bp_text = f"{sys_bp or '?'}/{dia_bp or '?'}"
        return SuggestionCandidate(
            100,
            f"最近一次血压 {bp_text} 严重升高，请先复测；如伴胸痛、气促、视力或言语变化请立即求助",
        )
    if (sys_bp is not None and sys_bp >= 140) or (dia_bp is not None and dia_bp >= 90):
        bp_text = f"{sys_bp or '?'}/{dia_bp or '?'}"
        return SuggestionCandidate(80, f"最近一次血压 {bp_text}，帮我分析趋势和生活方式调整")
    if sys_bp is not None and sys_bp < 130 and (dia_bp is None or dia_bp < 80):
        return SuggestionCandidate(40, "血压控制不错，帮我看看怎么继续保持")
    return None


def _suggest_acwr(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    zone = (signals.acwr_zone or "").lower()
    if zone in ("danger", "overtraining", "risky"):
        return SuggestionCandidate(100, "训练负荷进入风险区，帮我减量并安排恢复")
    # "undertraining" 只在用户确实有训练记录时才提示加量 —— Twin 对零训练数据的新用户
    # 会把 acwr_zone 默认成 "undertraining",此时说"训练负荷偏低"是冷启动误报。
    if zone == "undertraining" and signals.workouts_7d > 0:
        return SuggestionCandidate(60, "训练负荷偏低，怎么循序加量不受伤？")
    if zone == "optimal":
        return SuggestionCandidate(40, "训练负荷在最佳区，下一周该怎么进阶？")
    return None


def _suggest_acute_illness(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    if signals.should_rest_from_training:
        ill = _format_illness_phrase(signals.illness_names)
        if ill:
            # 若病症名已自带"发作"/"症状"结尾, 不再补"症状" (避免"发作症状"结巴)。
            if ill.endswith(("发作", "症状", "急性发作")):
                return SuggestionCandidate(100, f"我有{ill}，今天该怎么休息和恢复？")
            return SuggestionCandidate(100, f"我有{ill}症状，今天该怎么休息和恢复？")
        return SuggestionCandidate(100, "我身体不太舒服，今天该怎么休息和恢复？")
    return None


def _format_illness_phrase(illness_names: Optional[list[str]]) -> str:
    """把病症名列表整形成短语: 拆分隔符 → 去重 (保序) → 取前 2 → 顿号连接。

    修 "鼻炎发作、鼻炎发作" 类重复: 上游可能有多条同名 active illness,
    也可能单个 name 里已含 顿号/逗号 分隔的多值。
    """
    if not illness_names:
        return ""
    seen: set[str] = set()
    tokens: list[str] = []
    for raw in illness_names:
        if not raw:
            continue
        for tok in re.split(r"[、,，]", raw):
            tok = tok.strip()
            if tok and tok not in seen:
                seen.add(tok)
                tokens.append(tok)
    return "、".join(tokens[:2])


# ── Environment (Twin-driven) ───────────────────────────────────────────


def _suggest_aqi(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    aqi = signals.aqi
    if aqi is None:
        return None
    city = signals.city or "本地"
    if aqi >= 200:
        return SuggestionCandidate(100, f"{city} AQI {aqi}（重污染），今天能不能出门活动？")
    if aqi >= 150:
        return SuggestionCandidate(90, f"{city} AQI {aqi}，怎么把今天的训练换成室内方案？")
    if aqi >= 100:
        return SuggestionCandidate(70, f"{city} AQI {aqi}，户外运动该注意什么？")
    if aqi <= 50:
        return SuggestionCandidate(50, f"{city} 空气质量很好（AQI {aqi}），适合什么户外活动？")
    return None


def _suggest_uv(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    uv = signals.uv_index
    if uv is None:
        return None
    if uv >= 8:
        return SuggestionCandidate(70, f"今天UV指数 {uv:g}（很强），户外训练怎么防晒？")
    if uv >= 6:
        return SuggestionCandidate(50, f"今天UV指数 {uv:g}，户外该几点出门更合适？")
    return None


def _suggest_weather(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    temp = signals.temperature_c
    desc = signals.weather_description
    if temp is None and not desc:
        return None
    city = signals.city or "本地"
    if temp is not None and temp >= 32:
        return SuggestionCandidate(70, f"{city}今天 {temp:.0f}℃ 高温，运动和补水怎么安排？")
    if temp is not None and temp <= 5:
        return SuggestionCandidate(70, f"{city}今天只有 {temp:.0f}℃，户外运动要注意什么？")
    if desc and any(k in desc for k in ("雨", "雪", "雷")):
        return SuggestionCandidate(60, f"{city}今天{desc}，给我一套室内训练方案")
    return None


def _suggest_outdoor_suitability(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    s = (signals.outdoor_exercise_suitability or "").lower()
    if s == "avoid":
        return SuggestionCandidate(80, "今天不适合户外运动，给我一份室内方案")
    if s == "suitable":
        return SuggestionCandidate(50, "今天适合户外运动，建议练什么、什么时段？")
    return None


# ── Time of day / weekday (Asia/Shanghai) ───────────────────────────────


def _suggest_morning(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    """早晨 6-10 点：复盘昨晚睡眠、规划今日。仅在用户已有数据时触发。"""
    if signals.local_hour is None or not (6 <= signals.local_hour < 10):
        return None
    if not _has_any_user_signal(signals):
        return None
    if signals.sleep_score_today is not None:
        return SuggestionCandidate(50, f"昨晚睡眠分 {signals.sleep_score_today}，帮我安排今天的节奏")
    return SuggestionCandidate(40, "早安，帮我规划今天的训练、饮食和补剂时间表")


def _suggest_noon(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    """午饭点 11-13 点：午餐推荐（结合是否已记录）。"""
    if signals.local_hour is None or not (11 <= signals.local_hour < 14):
        return None
    if not _has_any_user_signal(signals):
        return None
    if signals.diet_records_today is not None and signals.diet_records_today > 0:
        return SuggestionCandidate(40, "结合今天已经吃的，午餐怎么补能更均衡？")
    return SuggestionCandidate(50, "午餐吃点什么合适？给我 2-3 个搭配选项")


def _suggest_evening(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    """晚 20-23 点：今日总结 + 睡前准备。"""
    if signals.local_hour is None or not (20 <= signals.local_hour < 24):
        return None
    if not _has_any_user_signal(signals):
        return None
    return SuggestionCandidate(50, "总结一下我今天的健康数据，并给睡前几个小建议")


def _suggest_late_night(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    """深夜 0-5 点：睡眠节律提醒。"""
    if signals.local_hour is None or not (0 <= signals.local_hour < 5):
        return None
    if not _has_any_user_signal(signals):
        return None
    return SuggestionCandidate(60, "这个点还没睡，对身体影响有多大？怎么补救？")


def _suggest_week_rhythm(signals: StarterSignals) -> Optional[SuggestionCandidate]:
    """周末 / 周日晚 / 周一早 的节律提醒。"""
    if signals.local_weekday is None or signals.local_hour is None:
        return None
    if not _has_any_user_signal(signals):
        return None
    wd, hr = signals.local_weekday, signals.local_hour
    if wd == 6 and 18 <= hr < 24:
        return SuggestionCandidate(60, "帮我规划下一周的训练 / 饮食 / 复查安排")
    if wd == 0 and 6 <= hr < 12:
        return SuggestionCandidate(50, "复盘一下周末的训练和饮食，给本周开个头")
    if signals.is_weekend and 9 <= hr < 18:
        return SuggestionCandidate(40, "周末时间宽裕，安排一次长训练或户外活动")
    return None


_GENERATORS = (
    # Historical / aggregate
    _suggest_exam,
    _suggest_goal,
    _suggest_workout,
    _suggest_gene,
    _suggest_water,
    _suggest_diet,
    _suggest_supplement,
    _suggest_recovery_history,
    _suggest_lab_recheck,
    _suggest_problem_followup,
    _suggest_health_problem,
    # Today body state
    _suggest_readiness,
    _suggest_hrv_today,
    _suggest_body_battery_stress,
    _suggest_bp,
    _suggest_acwr,
    _suggest_acute_illness,
    # Environment
    _suggest_aqi,
    _suggest_uv,
    _suggest_weather,
    _suggest_outdoor_suitability,
    # Time / weekday
    _suggest_morning,
    _suggest_noon,
    _suggest_evening,
    _suggest_late_night,
    _suggest_week_rhythm,
)


# Coarse theme per generator key — used ONLY to diversify the 4 served chips so a
# user doesn't get 4 recovery/training variations. Keys not listed default to
# their own name (so each is its own theme = never over-collapsed).
_CATEGORY_BY_KEY: dict[str, str] = {
    # recovery / training load / body readiness
    "readiness": "recovery",
    "hrv_today": "recovery",
    "body_battery_stress": "recovery",
    "acwr": "training",
    "workout": "training",
    "recovery_history": "recovery",
    # intake gaps: hydration and diet are both daily core signals, so they should
    # not collapse each other out of the four starter slots.
    "water": "hydration",
    "diet": "nutrition",
    "supplement": "supplement",
    # labs / exams / chronic problems (the grounded "check/compare" threads)
    "exam": "labs",
    "lab_recheck": "labs",
    "bp": "labs",
    "problem_followup": "chronic",
    "health_problem": "chronic",
    "acute_illness": "chronic",
    "gene": "genetics",
    "goal": "goal",
    # environment
    "aqi": "environment",
    "uv": "environment",
    "weather": "environment",
    "outdoor_suitability": "environment",
    # time-of-day rhythm
    "morning": "rhythm",
    "noon": "rhythm",
    "evening": "rhythm",
    "late_night": "rhythm",
    "week_rhythm": "rhythm",
}


def _category_of(card: SuggestionCandidate) -> str:
    return _CATEGORY_BY_KEY.get(card.key, card.key or "other")


def _build_candidates(signals: StarterSignals) -> list[SuggestionCandidate]:
    out: list[SuggestionCandidate] = []
    seen: set[str] = set()
    for gen in _GENERATORS:
        cand = gen(signals)
        if cand is None or cand.text in seen:
            continue
        # Stamp generator identity (e.g. "readiness", "aqi") for click analytics.
        key = gen.__name__.removeprefix("_suggest_")
        out.append(replace(cand, key=key))
        seen.add(cand.text)
    return out


# ────────────────────────────── Selection ───────────────────────────────


def _select(
    candidates: list[SuggestionCandidate],
    *,
    limit: int,
    rng: Optional[random.Random],
) -> list[str]:
    """Text-only selection (legacy shape, kept for tests/back-compat)."""
    return [c.text for c in _select_cards(candidates, limit=limit, rng=rng)]


def _select_cards(
    candidates: list[SuggestionCandidate],
    *,
    limit: int,
    rng: Optional[random.Random],
) -> list[SuggestionCandidate]:
    rng = rng or random.Random()

    critical = [c for c in candidates if c.priority >= _CRITICAL_PRIORITY]
    rest = [c for c in candidates if c.priority < _CRITICAL_PRIORITY]

    # Critical first (sorted desc by priority, deterministic).
    critical.sort(key=lambda c: -c.priority)
    chosen: list[SuggestionCandidate] = list(critical[:limit])

    # Fill remaining slots from non-critical pool — weighted random sample, but
    # DIVERSIFIED so the served chips span distinct themes (no 4 recovery variants).
    slots = limit - len(chosen)
    if slots > 0 and rest:
        used_categories = {_category_of(c) for c in chosen}
        picked = _diverse_weighted_sample(
            rest, k=min(slots, len(rest)), rng=rng, used_categories=used_categories
        )
        chosen.extend(picked)

    # Fall back to defaults if still short.
    if len(chosen) < limit:
        existing_texts = {c.text for c in chosen}
        for text in DEFAULT_SUGGESTIONS:
            if len(chosen) >= limit:
                break
            if text in existing_texts:
                continue
            chosen.append(SuggestionCandidate(_DEFAULT_PRIORITY, text, "default"))
            existing_texts.add(text)

    # Display order: highest priority first.
    chosen.sort(key=lambda c: -c.priority)
    return chosen[:limit]


def _weighted_sample(
    pool: list[SuggestionCandidate],
    *,
    k: int,
    rng: random.Random,
) -> list[SuggestionCandidate]:
    """Sample k items without replacement, biased by priority.

    Uses the Efraimidis-Spirakis A-Res method (sort by `u**(1/w)`) — small `k`
    and `len(pool)` here (both < 20) so a plain sort is fine.
    """
    if k >= len(pool):
        return list(pool)
    keyed = []
    for c in pool:
        w = max(c.priority, 1)  # guard against zero/negative
        u = rng.random() or 1e-9
        keyed.append((u ** (1.0 / w), c))
    keyed.sort(key=lambda kv: kv[0], reverse=True)
    return [c for _, c in keyed[:k]]


def _diverse_weighted_sample(
    pool: list[SuggestionCandidate],
    *,
    k: int,
    rng: random.Random,
    used_categories: set[str],
) -> list[SuggestionCandidate]:
    """Pick k items, priority-weighted, but preferring UNUSED categories first.

    Greedy round-based: at each step the eligible sub-pool is candidates whose
    theme (`_category_of`) hasn't been chosen yet; we priority-weighted-sample ONE
    from it. When every remaining candidate repeats an already-used category (the
    user simply doesn't have 4 distinct themes), we relax and sample from the full
    remainder. This keeps per-visit variety (RNG-driven within a tier) while
    guaranteeing the served chips fan across themes when the supply allows —
    fixing "4 recovery chips" for a training-heavy day.
    """
    if k >= len(pool):
        return list(pool)
    picked: list[SuggestionCandidate] = []
    remaining = list(pool)
    used = set(used_categories)
    while len(picked) < k and remaining:
        fresh = [c for c in remaining if _category_of(c) not in used]
        tier = fresh if fresh else remaining
        one = _weighted_sample(tier, k=1, rng=rng)[0]
        picked.append(one)
        remaining.remove(one)
        used.add(_category_of(one))
    return picked
