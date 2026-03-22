"""排泄记录 API"""
from datetime import date, time, timedelta
from collections import defaultdict, Counter
from typing import Optional, List
from statistics import stdev

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.excretion import ExcretionRecord
from app.schemas.excretion import (
    ExcretionRecordCreate, ExcretionRecordUpdate, ExcretionRecordResponse,
    ExcretionStats, ExcretionDailySummary,
)

router = APIRouter(prefix="/excretion", tags=["排泄记录"])


@router.post("/records", response_model=ExcretionRecordResponse, summary="创建排泄记录")
async def create_record(
    data: ExcretionRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = ExcretionRecord(
        user_id=current_user.id,
        **data.model_dump(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return ExcretionRecordResponse.model_validate(record)


@router.get("/records/me", response_model=List[ExcretionRecordResponse], summary="获取排泄记录列表")
async def get_my_records(
    type: Optional[str] = Query(None, pattern="^(bowel|urine)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    query = db.query(ExcretionRecord).filter(ExcretionRecord.user_id == current_user.id)
    if type:
        query = query.filter(ExcretionRecord.type == type)
    if start_date:
        query = query.filter(ExcretionRecord.record_date >= start_date)
    if end_date:
        query = query.filter(ExcretionRecord.record_date <= end_date)
    records = query.order_by(desc(ExcretionRecord.record_date), desc(ExcretionRecord.record_time)).limit(limit).all()
    return [ExcretionRecordResponse.model_validate(r) for r in records]


@router.get("/records/me/today", response_model=List[ExcretionRecordResponse], summary="获取今日排泄记录")
async def get_today_records(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    today = date.today()
    records = db.query(ExcretionRecord).filter(
        ExcretionRecord.user_id == current_user.id,
        ExcretionRecord.record_date == today,
    ).order_by(desc(ExcretionRecord.record_time)).all()
    return [ExcretionRecordResponse.model_validate(r) for r in records]


@router.get("/records/{record_id}", response_model=ExcretionRecordResponse, summary="获取单条排泄记录")
async def get_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(ExcretionRecord).filter(
        ExcretionRecord.id == record_id,
        ExcretionRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return ExcretionRecordResponse.model_validate(record)


@router.put("/records/{record_id}", response_model=ExcretionRecordResponse, summary="更新排泄记录")
async def update_record(
    record_id: int,
    data: ExcretionRecordUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(ExcretionRecord).filter(
        ExcretionRecord.id == record_id,
        ExcretionRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return ExcretionRecordResponse.model_validate(record)


@router.delete("/records/{record_id}", summary="删除排泄记录")
async def delete_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(ExcretionRecord).filter(
        ExcretionRecord.id == record_id,
        ExcretionRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(record)
    db.commit()
    return {"message": "记录已删除"}


@router.get("/stats/me", response_model=ExcretionStats, summary="获取排泄统计")
async def get_stats(
    days: int = Query(default=7, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    start_date = date.today() - timedelta(days=days - 1)
    records = db.query(ExcretionRecord).filter(
        ExcretionRecord.user_id == current_user.id,
        ExcretionRecord.record_date >= start_date,
    ).order_by(ExcretionRecord.record_date).all()

    if not records:
        return ExcretionStats()

    bowel_records = [r for r in records if r.type == "bowel"]
    urine_records = [r for r in records if r.type == "urine"]

    # 按日分组
    day_bowel = defaultdict(int)
    day_urine = defaultdict(int)
    for r in bowel_records:
        day_bowel[r.record_date] += 1
    for r in urine_records:
        day_urine[r.record_date] += 1

    all_dates = set(r.record_date for r in records)
    num_days = max(len(all_dates), 1)

    stool_types = [r.stool_type for r in bowel_records if r.stool_type]
    colors = [r.color for r in bowel_records if r.color]
    blood_count = sum(1 for r in bowel_records if r.blood_present)

    # 每日汇总
    daily = []
    for d in sorted(all_dates):
        day_records = [r for r in records if r.record_date == d]
        day_bowels = [r for r in day_records if r.type == "bowel"]
        day_st = [r.stool_type for r in day_bowels if r.stool_type]
        daily.append(ExcretionDailySummary(
            date=d,
            bowel_count=len([r for r in day_records if r.type == "bowel"]),
            urine_count=len([r for r in day_records if r.type == "urine"]),
            avg_stool_type=round(sum(day_st) / len(day_st), 1) if day_st else None,
            has_blood=any(r.blood_present for r in day_bowels),
            has_pain=any((r.pain_level or 0) > 0 for r in day_records),
        ))

    return ExcretionStats(
        total_records=len(records),
        bowel_count=len(bowel_records),
        urine_count=len(urine_records),
        avg_bowel_per_day=round(len(bowel_records) / num_days, 1),
        avg_urine_per_day=round(len(urine_records) / num_days, 1),
        avg_stool_type=round(sum(stool_types) / len(stool_types), 1) if stool_types else None,
        stool_type_distribution=dict(Counter(stool_types)),
        color_distribution=dict(Counter(colors)),
        blood_count=blood_count,
        daily_summary=daily,
    )


@router.get("/patterns/me")
async def get_excretion_patterns(
    days: int = Query(30, ge=7, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """排泄规律分析 — 基于 N 天数据生成频率、时段、规律性洞察"""
    since = date.today() - timedelta(days=days)
    records = db.query(ExcretionRecord).filter(
        ExcretionRecord.user_id == current_user.id,
        ExcretionRecord.record_date >= since,
    ).order_by(ExcretionRecord.record_date, ExcretionRecord.record_time).all()

    bowel_records = [r for r in records if r.type == "bowel"]
    urine_records = [r for r in records if r.type == "urine"]
    num_days = max(days, 1)

    result = {
        "period_days": days,
        "total_records": len(records),
        "bowel": _analyze_bowel(bowel_records, num_days),
        "urine": _analyze_urine(urine_records, num_days),
        "insights": [],
    }

    # 生成洞察
    insights = []
    b = result["bowel"]
    u = result["urine"]

    if b["total_count"] > 0:
        if b["regularity_score"] >= 70:
            insights.append(f"排便规律性良好（{b['regularity_score']}分），主要集中在{b['most_common_period']}")
        elif b["regularity_score"] >= 40:
            insights.append(f"排便规律性一般（{b['regularity_score']}分），时间比较分散")
        else:
            insights.append(f"排便不太规律（{b['regularity_score']}分），建议固定每天同一时间段排便")

        if b["avg_frequency_per_day"] < 0.5:
            insights.append(f"近{days}天排便频率偏低（{b['avg_frequency_per_day']}次/天），建议增加膳食纤维和饮水量")
        elif b["avg_frequency_per_day"] > 3:
            insights.append(f"排便频率较高（{b['avg_frequency_per_day']}次/天），如伴有不适建议就医")

        if b["avg_duration_minutes"] and b["avg_duration_minutes"] > 15:
            insights.append(f"平均排便时间较长（{b['avg_duration_minutes']}分钟），建议缩短如厕时间，避免痔疮风险")

    if u["total_count"] > 0:
        if u["avg_frequency_per_day"] > 8:
            insights.append(f"排尿频率偏高（{u['avg_frequency_per_day']}次/天），注意是否有尿频症状")
        if u["nighttime_avg"] and u["nighttime_avg"] >= 2:
            insights.append(f"夜尿次数偏多（平均{u['nighttime_avg']}次/晚），影响睡眠质量")

    result["insights"] = insights
    return result


def _analyze_bowel(records: list, num_days: int) -> dict:
    """分析大便规律"""
    if not records:
        return {
            "total_count": 0,
            "avg_frequency_per_day": 0,
            "most_common_period": None,
            "most_common_hour": None,
            "avg_duration_minutes": None,
            "regularity_score": 0,
            "hour_distribution": {},
        }

    # 时段分布
    hours = [r.record_time.hour for r in records if r.record_time]
    period_counts = defaultdict(int)
    for h in hours:
        if 5 <= h < 9:
            period_counts["早晨(5-9点)"] += 1
        elif 9 <= h < 12:
            period_counts["上午(9-12点)"] += 1
        elif 12 <= h < 14:
            period_counts["中午(12-14点)"] += 1
        elif 14 <= h < 18:
            period_counts["下午(14-18点)"] += 1
        elif 18 <= h < 22:
            period_counts["晚上(18-22点)"] += 1
        else:
            period_counts["深夜/凌晨"] += 1

    most_common_period = max(period_counts, key=period_counts.get) if period_counts else None

    # 平均时长
    durations = [r.duration_minutes for r in records if r.duration_minutes is not None]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else None

    # 规律性评分（基于每天排便次数的标准差 + 时间集中度）
    daily_counts = defaultdict(int)
    for r in records:
        daily_counts[r.record_date] += 1
    counts_list = list(daily_counts.values())

    # 补充没有排便的天数
    all_dates = set()
    if records:
        d = records[0].record_date
        end = records[-1].record_date
        while d <= end:
            all_dates.add(d)
            d += timedelta(days=1)
    for d in all_dates:
        if d not in daily_counts:
            counts_list.append(0)

    regularity = 50  # 基础分
    if len(counts_list) >= 3:
        sd = stdev(counts_list)
        # 标准差越小越规律
        regularity = max(0, min(100, int(100 - sd * 40)))
    # 时间集中度加分
    if period_counts and most_common_period:
        concentration = period_counts[most_common_period] / len(hours) if hours else 0
        regularity = min(100, int(regularity + concentration * 20))

    hour_dist = dict(Counter(hours))

    return {
        "total_count": len(records),
        "avg_frequency_per_day": round(len(records) / num_days, 1),
        "most_common_period": most_common_period,
        "most_common_hour": max(hour_dist, key=hour_dist.get) if hour_dist else None,
        "avg_duration_minutes": avg_duration,
        "regularity_score": regularity,
        "hour_distribution": hour_dist,
    }


def _analyze_urine(records: list, num_days: int) -> dict:
    """分析小便规律"""
    if not records:
        return {
            "total_count": 0,
            "avg_frequency_per_day": 0,
            "peak_hours": [],
            "nighttime_avg": None,
        }

    hours = [r.record_time.hour for r in records if r.record_time]
    hour_counts = Counter(hours)

    # 高峰时段（前 3 个小时）
    peak_hours = [h for h, _ in hour_counts.most_common(3)]

    # 夜间排尿（22:00 - 06:00）
    nighttime = [r for r in records if r.record_time and (r.record_time.hour >= 22 or r.record_time.hour < 6)]
    night_dates = set(r.record_date for r in nighttime)
    nighttime_avg = round(len(nighttime) / max(len(night_dates), 1), 1) if nighttime else 0

    return {
        "total_count": len(records),
        "avg_frequency_per_day": round(len(records) / num_days, 1),
        "peak_hours": sorted(peak_hours),
        "nighttime_avg": nighttime_avg,
    }
