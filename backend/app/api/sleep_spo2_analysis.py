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
    ask_questions: List[str] = []  # 数据缺口追问（如：是否饮酒、是否服药）


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
            "alcohol_units": (
                float(r.alcohol_units)
                if r.alcohol_units is not None
                else _estimate_alcohol_units(r.food_items or r.food_name or '')
            ),
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
        ss = gd.sleep_start_time
        # 某些历史数据是字符串形式，先统一转成 time
        if isinstance(ss, str):
            ss_parsed = _parse_time_str_local(ss)
        else:
            ss_parsed = ss
        if ss_parsed:
            if ss_parsed >= time(12, 0):
                sleep_start_ts = datetime.combine(night_date - timedelta(days=1), ss_parsed)
            else:
                sleep_start_ts = datetime.combine(night_date, ss_parsed)

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


def _parse_time_str_local(s: str) -> Optional[time]:
    """容错把 'HH:MM' / 'HH:MM:SS' / 完整 ISO 等转成 time。"""
    import re as _re
    m = _re.match(r'(\d{1,2}):(\d{2})', str(s))
    if not m:
        return None
    try:
        return time(int(m.group(1)), int(m.group(2)))
    except (ValueError, TypeError):
        return None


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


def _compute_ask_questions(night: NightAnalysis, ctx: NightContext) -> List[str]:
    """夜间有问题但关键数据缺口时返回追问列表。

    触发前提：ODI ≥ 5 OR min_spo2 < 88（即夜间真有事），否则不追问。
    缺口判定：
      - 无饮食记录 OR 饮食记录里 alcohol_units 全部为 0 → 问饮酒
      - 用户在 active_meds 有异丙托溴铵 + 当日无服药记录 → 问用药
      - 当日无运动记录 → 问晚间运动
    """
    night_has_issue = (
        (night.odi is not None and night.odi >= 5)
        or (night.min_spo2 is not None and night.min_spo2 < 88)
    )
    if not night_has_issue:
        return []

    questions: List[str] = []

    # 饮酒缺口：只要有一条 diet_record 显式记录了 alcohol_units（0 或 >0），就不再问
    # 0 = 用户明确说没喝 (占位) 或 MealForm 没填（走估算为 0）
    # None = 尚未录入
    alcohol_recorded = any(
        d.get('alcohol_units') is not None for d in ctx.diet_records
    )
    if not alcohol_recorded:
        questions.append("昨晚是否饮酒？酒精会松弛上气道，是夜间血氧下降的常见诱因。")

    # 异丙托溴铵漏录
    has_ipra_active = any(
        '异丙托溴铵' in (m.get('name') or '') or 'ipratropium' in (m.get('name') or '').lower()
        for m in ctx.active_meds
    )
    has_ipra_log = any(
        '异丙托溴铵' in (m.get('name') or '') or 'ipratropium' in (m.get('name') or '').lower()
        for m in ctx.med_logs if m.get('status') == 'taken'
    )
    if has_ipra_active and not has_ipra_log:
        questions.append("昨日是否使用了异丙托溴铵？最后一次使用时间是几点？")

    # 运动缺口
    if not ctx.workouts:
        questions.append("昨日是否有运动？尤其是入睡前 3 小时内的高强度训练？")

    return questions[:3]


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
        ask_questions=_compute_ask_questions(night, ctx),
    )


@router.post("/reanalyze", response_model=NightAnalysisOut)
def reanalyze_night(
    night_date: date = Query(...),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> NightAnalysisOut:
    """与 GET /analysis 行为等价（analyze_night 本身幂等，每次重跑）。"""
    return get_night_analysis(night_date=night_date, current_user=current_user, db=db)


@router.get("/longitudinal", summary="近 N 天 SpO2 longitudinal + OSAHS pattern")
def get_longitudinal(
    days: int = Query(30, ge=7, le=180),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """汇总近 N 天夜间 SpO2 事件与 OSAHS 模式指标.

    不诊断 OSAHS, 仅做趋势呈现. 数据来自 nocturnal_spo2_events 表 + GarminData
    睡眠时长 (ODI 分母). 不重跑分析, 读已落盘结果.
    """
    from app.services.sleep.nocturnal_spo2_longitudinal import build_longitudinal
    return build_longitudinal(db, current_user.id, days=days)


@router.post("/confirm-no-alcohol")
def confirm_no_alcohol(
    night_date: date = Query(..., description="确认哪夜未饮酒 YYYY-MM-DD"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """用户明确回答"昨晚没喝酒"时调用 —— 写一条占位 DietRecord(alcohol_units=0)
    让 rule_alcohol 不再触发 + ask_questions 不再问。

    幂等：当日已有 alcohol_units=0 占位则不重复写。
    """
    from app.models.daily_health import DietRecord
    existing = db.query(DietRecord).filter(
        DietRecord.user_id == current_user.id,
        DietRecord.record_date == night_date,
        DietRecord.food_items == "（已确认无饮酒）",
    ).first()
    if existing:
        return {"ok": True, "created": False, "id": existing.id}

    rec = DietRecord(
        user_id=current_user.id,
        record_date=night_date,
        meal_type="snack",
        food_items="（已确认无饮酒）",
        alcohol_units=0.0,
        notes="auto-confirmed via ask_questions",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return {"ok": True, "created": True, "id": rec.id}


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
