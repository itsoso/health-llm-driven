"""Nocturnal SpO2 Analysis API (P1b)。

GET  /sleep/spo2/analysis?night_date=YYYY-MM-DD   单夜分析 + 行为关联
GET  /sleep/spo2/insights?weeks=4                  多周 A/B 对比（行为 vs ODI）
POST /sleep/spo2/reanalyze?night_date=YYYY-MM-DD   强制重跑分析（删旧事件再跑）
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.daily_health import DietRecord, GarminData
from app.models.medication import Medication, MedicationLog
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.disease_tracking import SymptomLog, UserDiseaseProfile
from app.api.deps import get_current_user_required

from app.services.sleep.nocturnal_spo2_analyzer import analyze_night, NightAnalysis, DetectedEvent
from app.services.sleep.correlation_rules import run_rules, NightContext, CorrelationFinding

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class EventOut(BaseModel):
    start_ts: datetime
    end_ts: datetime
    duration_seconds: int
    min_spo2: float
    baseline_spo2: Optional[float] = None
    drop_magnitude: float
    concurrent_hr_delta: Optional[float] = None
    concurrent_respiration_rate: Optional[float] = None
    sleep_stage: Optional[str] = None


class CorrelationOut(BaseModel):
    category: str
    subject: str
    rule: str
    hypothesis: str
    suggested_action: str
    severity: str
    confidence: str
    evidence: Dict[str, Any]


class NightAnalysisOut(BaseModel):
    night_date: date
    odi: float
    events_count: int
    min_spo2: Optional[float] = None
    avg_spo2: Optional[float] = None
    total_sleep_minutes: int
    events: List[EventOut]
    correlations: List[CorrelationOut]
    action_priorities: List[str]


class BehaviorABOut(BaseModel):
    """行为对比结果（同一行为 vs 未发生，ODI 均值差异）。"""
    behavior: str
    with_count: int
    without_count: int
    odi_with: float
    odi_without: float
    delta: float              # with - without (正数 = 行为伴随 ODI 升高)
    effect: str               # "可能加重" / "可能改善" / "不显著"


class InsightsOut(BaseModel):
    weeks: int
    from_date: date
    to_date: date
    total_nights: int
    avg_odi: float
    ab_comparisons: List[BehaviorABOut]


# ---------------------------------------------------------------------------
# Helpers：构建 NightContext
# ---------------------------------------------------------------------------

def _build_night_context(db: Session, user_id: int, night_date: date) -> NightContext:
    # 药物日志
    med_logs = db.query(MedicationLog, Medication).join(
        Medication, MedicationLog.medication_id == Medication.id
    ).filter(
        MedicationLog.user_id == user_id,
        MedicationLog.taken_date == night_date,
    ).all()
    med_logs_out = [
        {
            "name": m.name,
            "taken_time": log.taken_time,
            "status": log.status,
        }
        for log, m in med_logs
    ]

    active_meds = db.query(Medication).filter(
        Medication.user_id == user_id,
        Medication.is_active == True,
    ).all()
    active_meds_out = [{"name": m.name, "frequency": m.frequency} for m in active_meds]

    # 补剂记录
    supp_records = db.query(SupplementRecord, SupplementDefinition).join(
        SupplementDefinition, SupplementRecord.supplement_id == SupplementDefinition.id
    ).filter(
        SupplementRecord.user_id == user_id,
        SupplementRecord.record_date == night_date,
    ).all()
    supp_out = [
        {
            "name": sd.name,
            "taken": sr.taken,
            "taken_time": sr.taken_time,
        }
        for sr, sd in supp_records
    ]

    # Workouts — 复用 workout_records
    from app.models.daily_health import WorkoutRecord
    workouts = db.query(WorkoutRecord).filter(
        WorkoutRecord.user_id == user_id,
        WorkoutRecord.workout_date == night_date,
    ).all()
    workouts_out = []
    for w in workouts:
        hr_max_pct = None
        duration_min = None
        try:
            if w.end_time and w.start_time:
                duration_min = (w.end_time - w.start_time).total_seconds() / 60
        except (AttributeError, TypeError):
            duration_min = None
        workouts_out.append({
            "workout_type": w.workout_type,
            "end_time": w.end_time,
            "start_time": w.start_time,
            "duration_min": duration_min,
            "hr_max_pct": hr_max_pct,
        })

    # 饮食
    diet = db.query(DietRecord).filter(
        DietRecord.user_id == user_id,
        DietRecord.record_date == night_date,
    ).all()
    diet_out = [
        {
            "food_items": r.food_items,
            "meal_type": r.meal_type,
            "meal_time": r.meal_time,
            "alcohol_units": _estimate_alcohol_units(r.food_items or r.food_name or ''),
        }
        for r in diet
    ]

    # 鼻炎严重度（从 SymptomLog）
    rhinitis_sev = None
    rhinitis_log = db.query(SymptomLog).join(
        UserDiseaseProfile, SymptomLog.disease_profile_id == UserDiseaseProfile.id
    ).filter(
        SymptomLog.user_id == user_id,
        SymptomLog.log_date == night_date,
        UserDiseaseProfile.disease_name.ilike("%鼻炎%"),
    ).first()
    if rhinitis_log:
        rhinitis_sev = rhinitis_log.overall_severity

    # Sleep start from GarminData
    gd = db.query(GarminData).filter(
        GarminData.user_id == user_id,
        GarminData.record_date == night_date,
    ).first()
    sleep_start_ts = None
    if gd and gd.sleep_start_time:
        # sleep_start_time 是 Time；如果 < 12:00 归属当天，否则归属前一天
        if gd.sleep_start_time >= time(12, 0):
            sleep_start_ts = datetime.combine(night_date - timedelta(days=1), gd.sleep_start_time)
        else:
            sleep_start_ts = datetime.combine(night_date, gd.sleep_start_time)

    return NightContext(
        night_date=night_date,
        med_logs=med_logs_out,
        active_meds=active_meds_out,
        supplement_records=supp_out,
        workouts=workouts_out,
        diet_records=diet_out,
        rhinitis_severity=rhinitis_sev,
        air_quality_pm25=None,  # 待接卧室传感器
        sleep_start_ts=sleep_start_ts,
    )


def _estimate_alcohol_units(food_desc: str) -> float:
    """粗略从食物描述抽酒精份数。标准杯 ~14g 酒精。"""
    if not food_desc:
        return 0.0
    s = food_desc.lower()
    units = 0.0
    if any(k in food_desc for k in ['啤酒', '啤酒']) or 'beer' in s:
        units += 1.0
    if any(k in food_desc for k in ['红酒', '白酒', '葡萄酒', '黄酒']) or 'wine' in s:
        units += 1.5
    if any(k in food_desc for k in ['威士忌', '伏特加', '洋酒']) or any(k in s for k in ['whiskey', 'vodka', 'gin', 'rum']):
        units += 1.5
    return units


def _action_priorities(findings: List[CorrelationFinding]) -> List[str]:
    """聚焦：只取 severity=alert + warning 且 confidence >= medium 的 action，最多 5 条。"""
    good = [
        f.suggested_action
        for f in findings
        if f.severity in ("alert", "warning") and f.confidence in ("high", "medium")
    ]
    # 去重保持顺序
    seen = set()
    out = []
    for a in good:
        if a not in seen:
            out.append(a)
            seen.add(a)
        if len(out) >= 5:
            break
    return out


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/analysis", response_model=NightAnalysisOut)
def get_night_analysis(
    night_date: date = Query(..., description="哪一夜（YYYY-MM-DD）"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> NightAnalysisOut:
    """单夜分析 + 根因假设。"""
    night = analyze_night(db, current_user.id, night_date)
    ctx = _build_night_context(db, current_user.id, night_date)
    findings = run_rules(night, ctx)

    return NightAnalysisOut(
        night_date=night.night_date,
        odi=night.odi,
        events_count=night.events_count,
        min_spo2=night.min_spo2,
        avg_spo2=night.avg_spo2,
        total_sleep_minutes=night.total_sleep_minutes,
        events=[
            EventOut(
                start_ts=e.start_ts,
                end_ts=e.end_ts,
                duration_seconds=e.duration_seconds,
                min_spo2=e.min_spo2,
                baseline_spo2=e.baseline_spo2,
                drop_magnitude=e.drop_magnitude,
                concurrent_hr_delta=e.concurrent_hr_delta,
                concurrent_respiration_rate=e.concurrent_respiration_rate,
                sleep_stage=e.sleep_stage,
            )
            for e in night.events
        ],
        correlations=[
            CorrelationOut(
                category=f.category,
                subject=f.subject,
                rule=f.rule,
                hypothesis=f.hypothesis,
                suggested_action=f.suggested_action,
                severity=f.severity,
                confidence=f.confidence,
                evidence=f.evidence,
            )
            for f in findings
        ],
        action_priorities=_action_priorities(findings),
    )


@router.post("/reanalyze", response_model=NightAnalysisOut)
def reanalyze_night(
    night_date: date = Query(...),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> NightAnalysisOut:
    """与 GET /analysis 行为等价（analyze_night 本身幂等，每次重跑）。"""
    return get_night_analysis(night_date=night_date, current_user=current_user, db=db)


@router.get("/insights", response_model=InsightsOut)
def get_insights(
    weeks: int = Query(4, ge=1, le=12),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> InsightsOut:
    """N 周 A/B 对比：某行为发生 vs 未发生，ODI 均值差异。

    简化版本：对这 N 周内每一夜调 _build_night_context 收集 (ODI, 行为) 对，再聚合。
    """
    end = date.today()
    start = end - timedelta(weeks=weeks)

    # 读已有事件（不重跑分析，假设已经调过 /analysis 或 /reanalyze）
    from app.models.nocturnal_spo2_event import NocturnalSpO2Event
    from sqlalchemy import func as sa_func

    night_stats = db.query(
        NocturnalSpO2Event.night_date,
        sa_func.count(NocturnalSpO2Event.id).label('cnt'),
    ).filter(
        NocturnalSpO2Event.user_id == current_user.id,
        NocturnalSpO2Event.night_date >= start,
        NocturnalSpO2Event.night_date <= end,
    ).group_by(NocturnalSpO2Event.night_date).all()
    # 每夜 ODI ≈ events_count / 8h （粗略，假设 8h 睡眠）
    odi_by_night: Dict[date, float] = {ns.night_date: ns.cnt / 8.0 for ns in night_stats}

    # 所有被分析过的夜晚（即便 0 事件）
    all_nights = sorted(set(odi_by_night.keys()))
    total_nights = len(all_nights)

    # 每夜的行为标签
    night_contexts: Dict[date, NightContext] = {
        d: _build_night_context(db, current_user.id, d) for d in all_nights
    }

    # A/B 对比
    comparisons: List[BehaviorABOut] = []

    def _ab(name: str, predicate) -> Optional[BehaviorABOut]:
        with_vals, without_vals = [], []
        for d in all_nights:
            ctx = night_contexts[d]
            odi = odi_by_night.get(d, 0.0)
            try:
                if predicate(ctx):
                    with_vals.append(odi)
                else:
                    without_vals.append(odi)
            except Exception:
                continue
        if not with_vals or not without_vals:
            return None
        avg_with = sum(with_vals) / len(with_vals)
        avg_without = sum(without_vals) / len(without_vals)
        delta = avg_with - avg_without
        if delta > 0.8:
            effect = "可能加重"
        elif delta < -0.8:
            effect = "可能改善"
        else:
            effect = "不显著"
        return BehaviorABOut(
            behavior=name,
            with_count=len(with_vals),
            without_count=len(without_vals),
            odi_with=round(avg_with, 2),
            odi_without=round(avg_without, 2),
            delta=round(delta, 2),
            effect=effect,
        )

    def _has_ipra(ctx):
        import re
        return any(re.search(r'异丙托溴铵|ipratropium', m.get('name', ''), re.IGNORECASE)
                   for m in ctx.med_logs if m.get('status') == 'taken')

    def _has_alcohol(ctx):
        return sum(float(d.get('alcohol_units', 0) or 0) for d in ctx.diet_records) >= 1

    def _has_workout(ctx):
        return len(ctx.workouts) > 0

    def _rhinitis_severe(ctx):
        return ctx.rhinitis_severity is not None and ctx.rhinitis_severity >= 5

    for ab in [
        _ab("服用异丙托溴铵", _has_ipra),
        _ab("饮酒", _has_alcohol),
        _ab("当日运动", _has_workout),
        _ab("鼻炎严重", _rhinitis_severe),
    ]:
        if ab:
            comparisons.append(ab)

    avg_odi = (sum(odi_by_night.values()) / total_nights) if total_nights else 0.0
    return InsightsOut(
        weeks=weeks,
        from_date=start,
        to_date=end,
        total_nights=total_nights,
        avg_odi=round(avg_odi, 2),
        ab_comparisons=comparisons,
    )
