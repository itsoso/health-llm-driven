"""Conversation starters (new-chat prompt chips).

This is used by the web `/ai-assistant` and mobile chat empty state to present
context-aware prompts derived from recent user data (exams/workouts/supplements
and basic recovery metrics).

Design constraints:
- Deterministic & fast: no LLM calls.
- Safe: never returns paid-course raw text; only user-owned data signals.
- Fail-soft: any error falls back to stable defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session


DEFAULT_SUGGESTIONS: list[str] = [
    "分析我最近的代谢健康",
    "今天怎么安排训练和恢复",
    "结合基因和体检给我建议",
    "帮我复盘最近的睡眠质量",
]


@dataclass(frozen=True)
class StarterSignals:
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


def compute_conversation_suggestions(
    db: Session,
    user_id: int,
    *,
    limit: int = 4,
) -> list[str]:
    """Return up to `limit` prompt-chip strings for a new conversation."""
    if limit <= 0:
        return []

    try:
        signals = _collect_signals(db, user_id)
        suggestions: list[str] = []

        exam_hint = _suggest_exam(signals)
        if exam_hint:
            suggestions.append(exam_hint)

        goal_hint = _suggest_goal(signals)
        if goal_hint:
            suggestions.append(goal_hint)

        workout_hint = _suggest_workout(signals)
        if workout_hint:
            suggestions.append(workout_hint)

        gene_hint = _suggest_gene(signals)
        if gene_hint:
            suggestions.append(gene_hint)

        water_hint = _suggest_water(signals)
        if water_hint:
            suggestions.append(water_hint)

        diet_hint = _suggest_diet(signals)
        if diet_hint:
            suggestions.append(diet_hint)

        supplement_hint = _suggest_supplement(signals)
        if supplement_hint:
            suggestions.append(supplement_hint)

        recovery_hint = _suggest_recovery(signals)
        if recovery_hint:
            suggestions.append(recovery_hint)

        # Fill with stable defaults (deduped)
        for text in DEFAULT_SUGGESTIONS:
            if len(suggestions) >= limit:
                break
            if text not in suggestions:
                suggestions.append(text)

        return suggestions[:limit]
    except Exception:  # noqa: BLE001
        # Fail-soft: empty-state prompts must never break chat launch.
        return DEFAULT_SUGGESTIONS[:limit]


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

    avg_sleep_score_7d = (
        db.query(func.avg(GarminData.sleep_score))
        .filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start_7d,
            GarminData.record_date <= today,
            GarminData.sleep_score.isnot(None),
        )
        .scalar()
    )
    avg_sleep_score_7d = float(avg_sleep_score_7d) if avg_sleep_score_7d is not None else None

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
    )


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
    )


def _suggest_exam(signals: StarterSignals) -> str | None:
    if not signals.latest_exam_date:
        return None
    if signals.latest_exam_abnormal_items:
        focus = "、".join(signals.latest_exam_abnormal_items[:2])
        return f"解读我最近一次体检（关注: {focus}）"
    return "解读我最近一次体检结果"


def _format_number(value: float | None) -> str | None:
    if value is None:
        return None
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _suggest_goal(signals: StarterSignals) -> str | None:
    if not signals.active_goal_title:
        return None
    title = signals.active_goal_title[:28]
    cur = _format_number(signals.active_goal_current_value)
    target = _format_number(signals.active_goal_target_value)
    unit = signals.active_goal_unit or ""
    if cur and target:
        return f"围绕「{title}」安排接下来7天行动（当前 {cur}{unit} → 目标 {target}{unit}）"
    return f"围绕「{title}」安排接下来7天行动"


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


def _suggest_workout(signals: StarterSignals) -> str | None:
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
        return f"复盘我最近一次{label}{suffix}"
    # Only override defaults when we have a concrete workout history to summarize.
    if signals.workouts_7d <= 0:
        return None
    return "复盘我最近7天训练负荷与恢复情况"


def _suggest_gene(signals: StarterSignals) -> str | None:
    if not signals.top_gene_name:
        return None
    gene = signals.top_gene_name
    genotype = f" {signals.top_gene_genotype}" if signals.top_gene_genotype else ""
    result = f"（{signals.top_gene_result[:18]}）" if signals.top_gene_result else ""
    return f"结合我的 {gene}{genotype} 基因结果{result}制定行动"


def _suggest_water(signals: StarterSignals) -> str | None:
    if signals.water_today_ml is None:
        return None
    target = 2000
    if signals.water_today_ml >= target:
        return "今天饮水已达标，帮我安排后续补水和睡前注意事项"
    return f"今天饮水 {signals.water_today_ml}/{target}ml，帮我安排剩余补水"


def _suggest_diet(signals: StarterSignals) -> str | None:
    if not _has_any_user_signal(signals):
        return None
    if signals.diet_records_today is None or signals.diet_records_today > 0:
        return None
    return "今天还没记录饮食，帮我快速补录并估算"


def _suggest_supplement(signals: StarterSignals) -> str | None:
    if signals.active_supplements <= 0:
        return None
    rate = signals.supplement_completion_7d_pct
    if rate is None:
        return "帮我复盘最近的补剂服用情况并优化计划"
    if rate < 60:
        return f"帮我提升补剂依从率（近7天完成率 {rate:.1f}%）"
    return "检查我的补剂方案是否需要调整"


def _suggest_recovery(signals: StarterSignals) -> str | None:
    # Only override defaults when there's a clear signal (missing data or low sleep score).
    if signals.missing_hrv_days_7d is not None and signals.missing_hrv_days_7d >= 3:
        return "我的HRV数据不太完整，帮我排查并告诉我如何补齐"
    if signals.avg_sleep_score_7d is not None and signals.avg_sleep_score_7d < 70:
        return "帮我复盘最近的睡眠质量并给出可执行改进"
    return None
