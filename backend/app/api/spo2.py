"""SpO2 血氧时间序列 API"""
from datetime import date, timedelta
from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models.user import User
from app.models.daily_health import SpO2Sample, GarminData, SleepLevelInterval
from app.api.deps import get_current_user_required
from app.schemas.spo2 import (
    SpO2Point,
    SpO2NightSummary,
    SpO2NightlyResponse,
    SpO2TrendResponse,
    SleepStageSpO2Stats,
    NightCorrelation,
    SpO2SleepCorrelationResponse,
)

router = APIRouter()


def _compute_desaturation_events(values: List[int]) -> int:
    if len(values) < 2:
        return 0
    events = 0
    baseline = values[0]
    in_desat = False
    for v in values[1:]:
        if not in_desat and baseline - v >= 3:
            events += 1
            in_desat = True
        elif v >= baseline - 1:
            in_desat = False
            baseline = v
        if v > baseline:
            baseline = v
    return events


def _build_night_summary(
    record_date: date,
    samples: List[SpO2Sample],
    sleep_hours: Optional[float] = None,
) -> SpO2NightSummary:
    if not samples:
        return SpO2NightSummary(record_date=record_date)

    values = [s.spo2_value for s in samples]
    avg_val = sum(values) / len(values)
    below_90 = sum(1 for v in values if v < 90)
    desat = _compute_desaturation_events(values)

    hours = sleep_hours
    if hours is None and len(values) > 1:
        hours = len(values) / 60.0

    odi = round(desat / hours, 1) if hours and hours > 0 else None

    return SpO2NightSummary(
        record_date=record_date,
        avg_spo2=round(avg_val, 1),
        min_spo2=min(values),
        max_spo2=max(values),
        below_90_count=below_90,
        desaturation_events=desat,
        odi=odi,
        data_points=len(values),
    )


def _get_sleep_times(db: Session, user_id: int, record_date: date):
    garmin = (
        db.query(GarminData)
        .filter(GarminData.user_id == user_id, GarminData.record_date == record_date)
        .first()
    )
    if not garmin:
        return None, None, None
    start = garmin.sleep_start_time.strftime("%H:%M") if hasattr(garmin.sleep_start_time, 'strftime') else (str(garmin.sleep_start_time)[:5] if garmin.sleep_start_time else None)
    end = garmin.sleep_end_time.strftime("%H:%M") if hasattr(garmin.sleep_end_time, 'strftime') else (str(garmin.sleep_end_time)[:5] if garmin.sleep_end_time else None)
    duration_h = garmin.total_sleep_duration / 60.0 if garmin.total_sleep_duration else None
    return start, end, duration_h


@router.get("/me/nightly/{record_date}", response_model=SpO2NightlyResponse)
def get_nightly_spo2(
    record_date: date,
    window: str = Query(
        "sleep",
        pattern="^(sleep|all)$",
        description="timeline 时间窗口: 'sleep'=仅睡眠期间 (默认, 避免日间采样干扰); 'all'=整晚全部采样",
    ),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """返回指定日期的夜间 SpO2 时间序列.

    重要: `record_date=D` 的 Garmin 采样范围实际是 `D-1 下午 ~ D 凌晨`,
    因为 Garmin 按"入睡那天"归类. 默认 `window=sleep` 会截断 timeline 到
    `sleep_start ~ sleep_end` 之间, 只保留真正的睡眠期间数据, 避免 LLM
    把下午日间的 SpO2 点误认作凌晨低氧事件.
    """
    samples_q = (
        db.query(SpO2Sample)
        .filter(
            SpO2Sample.user_id == current_user.id,
            SpO2Sample.record_date == record_date,
        )
        .order_by(SpO2Sample.epoch_ms.asc())
    )
    samples = samples_q.all()

    sleep_start, sleep_end, sleep_hours = _get_sleep_times(db, current_user.id, record_date)

    # 截断到 sleep window: sleep_start/end 是 HH:MM 本地 CST.
    # 采集器修复后 sample_time 也是 CST HH:MM, 直接字符串比即可.
    def in_sleep_window(s) -> bool:
        if not sleep_start or not sleep_end:
            return True
        tstr = s.sample_time.strftime("%H:%M") if hasattr(s.sample_time, "strftime") else str(s.sample_time)[:5]
        if sleep_start <= sleep_end:
            return sleep_start <= tstr <= sleep_end
        # 跨日: sleep_start (22:00) > sleep_end (06:00)
        return tstr >= sleep_start or tstr <= sleep_end

    filtered = [s for s in samples if in_sleep_window(s)] if window == "sleep" else samples

    # summary 跟 timeline 保持一致, 否则 "timeline 只有睡眠期, 但 summary min=83
    # 其实是白天体动噪声" 会让 LLM 错误归因
    summary = _build_night_summary(record_date, filtered, sleep_hours)

    timeline = [
        SpO2Point(
            timestamp=s.epoch_ms or 0,
            time=s.sample_time.strftime("%H:%M") if hasattr(s.sample_time, 'strftime') else str(s.sample_time)[:5],
            value=s.spo2_value,
        )
        for s in filtered
    ]

    window_start = timeline[0].time if timeline else None
    window_end = timeline[-1].time if timeline else None

    return SpO2NightlyResponse(
        record_date=record_date,
        summary=summary,
        timeline=timeline,
        sleep_start=sleep_start,
        sleep_end=sleep_end,
        window=window,
        window_start=window_start,
        window_end=window_end,
    )


@router.get("/me/latest-night", response_model=SpO2NightlyResponse)
def get_latest_night_spo2(
    window: str = Query("sleep", pattern="^(sleep|all)$"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    latest = (
        db.query(SpO2Sample.record_date)
        .filter(SpO2Sample.user_id == current_user.id)
        .order_by(desc(SpO2Sample.record_date))
        .first()
    )
    if not latest:
        raise HTTPException(status_code=404, detail="暂无血氧采样数据")
    return get_nightly_spo2(latest[0], window, current_user, db)


@router.get("/me/trend", response_model=SpO2TrendResponse)
def get_spo2_trend(
    days: int = Query(default=7, ge=1, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    dates_with_data = (
        db.query(SpO2Sample.record_date)
        .filter(
            SpO2Sample.user_id == current_user.id,
            SpO2Sample.record_date >= start_date,
            SpO2Sample.record_date <= end_date,
        )
        .distinct()
        .order_by(SpO2Sample.record_date)
        .all()
    )

    daily: List[SpO2NightSummary] = []
    for (rd,) in dates_with_data:
        samples = (
            db.query(SpO2Sample)
            .filter(
                SpO2Sample.user_id == current_user.id,
                SpO2Sample.record_date == rd,
            )
            .order_by(SpO2Sample.epoch_ms.asc())
            .all()
        )
        _, _, sleep_hours = _get_sleep_times(db, current_user.id, rd)
        daily.append(_build_night_summary(rd, samples, sleep_hours))

    summaries_with_avg = [d for d in daily if d.avg_spo2 is not None]
    summaries_with_odi = [d for d in daily if d.odi is not None]

    return SpO2TrendResponse(
        days=days,
        daily_data=daily,
        avg_nightly_spo2=(
            round(sum(d.avg_spo2 for d in summaries_with_avg) / len(summaries_with_avg), 1)
            if summaries_with_avg
            else None
        ),
        avg_odi=(
            round(sum(d.odi for d in summaries_with_odi) / len(summaries_with_odi), 1)
            if summaries_with_odi
            else None
        ),
        nights_with_odi_above_5=sum(1 for d in daily if d.odi is not None and d.odi >= 5),
    )


def _correlate_single_night(
    db: Session,
    user_id: int,
    record_date: date,
) -> Optional[NightCorrelation]:
    """对单晚的睡眠阶段和 SpO2 采样建立关联"""
    samples = (
        db.query(SpO2Sample)
        .filter(SpO2Sample.user_id == user_id, SpO2Sample.record_date == record_date)
        .order_by(SpO2Sample.epoch_ms.asc())
        .all()
    )
    intervals = (
        db.query(SleepLevelInterval)
        .filter(SleepLevelInterval.user_id == user_id, SleepLevelInterval.record_date == record_date)
        .order_by(SleepLevelInterval.start_epoch_ms.asc())
        .all()
    )

    if not samples or not intervals:
        return None

    stage_samples: Dict[str, List[int]] = {"deep": [], "light": [], "rem": [], "awake": []}
    stage_durations: Dict[str, float] = {"deep": 0, "light": 0, "rem": 0, "awake": 0}

    for iv in intervals:
        if iv.activity_level in stage_durations:
            stage_durations[iv.activity_level] += (iv.end_epoch_ms - iv.start_epoch_ms) / 60000.0

    for s in samples:
        if not s.epoch_ms:
            continue
        for iv in intervals:
            if iv.start_epoch_ms <= s.epoch_ms < iv.end_epoch_ms:
                if iv.activity_level in stage_samples:
                    stage_samples[iv.activity_level].append(s.spo2_value)
                break

    stages = []
    for stage_name in ["deep", "rem", "light", "awake"]:
        vals = stage_samples[stage_name]
        if not vals:
            stages.append(SleepStageSpO2Stats(
                stage=stage_name,
                duration_minutes=round(stage_durations[stage_name], 1),
            ))
            continue
        desat = _compute_desaturation_events(vals)
        stages.append(SleepStageSpO2Stats(
            stage=stage_name,
            avg_spo2=round(sum(vals) / len(vals), 1),
            min_spo2=min(vals),
            desaturation_events=desat,
            below_90_count=sum(1 for v in vals if v < 90),
            duration_minutes=round(stage_durations[stage_name], 1),
            data_points=len(vals),
        ))

    all_values = [s.spo2_value for s in samples]
    total_hours = sum(stage_durations.values()) / 60.0
    total_desat = _compute_desaturation_events(all_values)
    overall_odi = round(total_desat / total_hours, 1) if total_hours > 0 else None

    stages_with_data = [st for st in stages if st.data_points > 0 and st.avg_spo2 is not None]
    worst = min(stages_with_data, key=lambda s: s.avg_spo2, default=None) if stages_with_data else None

    risk = "normal"
    risk_detail = None
    if overall_odi is not None:
        if overall_odi >= 30:
            risk = "severe"
            risk_detail = f"ODI {overall_odi} 次/小时，重度异常，强烈建议尽快就医"
        elif overall_odi >= 15:
            risk = "moderate"
            risk_detail = f"ODI {overall_odi} 次/小时，中度异常，建议进行多导睡眠监测 (PSG)"
        elif overall_odi >= 5:
            risk = "mild"
            risk_detail = f"ODI {overall_odi} 次/小时，轻度异常，可能存在轻度 OSAHS"

    rem_data = stage_samples.get("rem", [])
    if rem_data and len(rem_data) >= 5:
        rem_below = sum(1 for v in rem_data if v < 90)
        if rem_below / len(rem_data) > 0.1 and risk == "normal":
            risk = "mild"
            risk_detail = f"REM 期间 {round(rem_below/len(rem_data)*100)}% 血氧 <90%，需关注"

    return NightCorrelation(
        record_date=record_date,
        stages=stages,
        overall_odi=overall_odi,
        worst_stage=worst.stage if worst else None,
        apnea_risk=risk,
        apnea_risk_detail=risk_detail,
    )


@router.get("/me/sleep-correlation", response_model=SpO2SleepCorrelationResponse)
def get_spo2_sleep_correlation(
    days: int = Query(default=7, ge=1, le=30),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """睡眠阶段 × SpO2 关联分析：按 deep/rem/light/awake 分段统计血氧"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    dates_with_data = (
        db.query(SpO2Sample.record_date)
        .filter(
            SpO2Sample.user_id == current_user.id,
            SpO2Sample.record_date >= start_date,
            SpO2Sample.record_date <= end_date,
        )
        .distinct()
        .order_by(SpO2Sample.record_date)
        .all()
    )

    nights = []
    for (rd,) in dates_with_data:
        nc = _correlate_single_night(db, current_user.id, rd)
        if nc:
            nights.append(nc)

    summary = None
    if nights:
        stage_agg: Dict[str, List[float]] = {"deep": [], "rem": [], "light": [], "awake": []}
        odi_list = []
        risk_counts = {"normal": 0, "mild": 0, "moderate": 0, "severe": 0}

        for n in nights:
            if n.overall_odi is not None:
                odi_list.append(n.overall_odi)
            risk_counts[n.apnea_risk] = risk_counts.get(n.apnea_risk, 0) + 1
            for st in n.stages:
                if st.avg_spo2 is not None and st.stage in stage_agg:
                    stage_agg[st.stage].append(st.avg_spo2)

        per_stage_avg = {}
        for stage, vals in stage_agg.items():
            if vals:
                per_stage_avg[stage] = round(sum(vals) / len(vals), 1)

        worst_stage = min(per_stage_avg, key=per_stage_avg.get) if per_stage_avg else None

        summary = {
            "nights_analyzed": len(nights),
            "avg_odi": round(sum(odi_list) / len(odi_list), 1) if odi_list else None,
            "per_stage_avg_spo2": per_stage_avg,
            "worst_stage": worst_stage,
            "risk_distribution": risk_counts,
            "overall_assessment": (
                "重度风险" if risk_counts.get("severe", 0) > 0
                else "中度风险" if risk_counts.get("moderate", 0) > 0
                else "轻度风险" if risk_counts.get("mild", 0) > 0
                else "正常"
            ),
            "disclaimer": "腕表 SpO2 仅供筛查参考，确诊 OSAHS 需多导睡眠监测 (PSG)",
        }

    return SpO2SleepCorrelationResponse(days=days, nights=nights, summary=summary)
