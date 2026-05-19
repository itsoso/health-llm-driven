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

        workout_hint = _suggest_workout(signals)
        if workout_hint:
            suggestions.append(workout_hint)

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
    from app.models.daily_health import GarminData, WorkoutRecord
    from app.models.supplement import SupplementDefinition, SupplementRecord

    today = date.today()
    start_7d = today - timedelta(days=6)

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

    workouts_7d = (
        db.query(func.count(WorkoutRecord.id))
        .filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.workout_date >= start_7d,
            WorkoutRecord.workout_date <= today,
        )
        .scalar()
    ) or 0

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
        workouts_7d=int(workouts_7d),
        active_supplements=int(active_supplements),
        supplement_completion_7d_pct=supplement_completion_7d_pct,
        avg_sleep_score_7d=avg_sleep_score_7d,
        missing_hrv_days_7d=missing_hrv_days_7d,
    )


def _suggest_exam(signals: StarterSignals) -> str | None:
    if not signals.latest_exam_date:
        return None
    if signals.latest_exam_abnormal_items:
        focus = "、".join(signals.latest_exam_abnormal_items[:2])
        return f"解读我最近一次体检（关注: {focus}）"
    return "解读我最近一次体检结果"


def _suggest_workout(signals: StarterSignals) -> str | None:
    # Only override defaults when we have a concrete workout history to summarize.
    if signals.workouts_7d <= 0:
        return None
    return "复盘我最近7天训练负荷与恢复情况"


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
