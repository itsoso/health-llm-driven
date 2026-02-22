"""每日健康积分 API"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.daily_health import GarminData, WaterIntake
from app.models.activity_status import ActivityStatus
from app.models.checkin import CheckinRecord, CheckinTemplate
from app.utils.timezone import get_china_today
from pydantic import BaseModel, Field

router = APIRouter(prefix="/points", tags=["积分"])

# 默认饮水目标 (ml)
WATER_DAILY_TARGET = 2000


# ===== Schemas =====

class PointItem(BaseModel):
    """单项积分"""
    category: str       # exercise / sleep / water / checkin
    name: str           # 显示名称
    points: int         # 获得积分
    max_points: int     # 该项满分
    detail: str         # 达成说明


class DailyPointsResponse(BaseModel):
    """每日积分汇总"""
    date: date
    total_points: int
    items: List[PointItem]


class PointsHistoryItem(BaseModel):
    date: date
    total_points: int


class PointsSummaryResponse(BaseModel):
    """积分总览"""
    today_points: int
    week_points: int
    month_points: int
    streak_days: int          # 连续获得积分天数
    today_detail: DailyPointsResponse


# ===== 积分计算 =====

def _calc_exercise_points(db: Session, user_id: int, target_date: date) -> List[PointItem]:
    """运动积分：每日运动 ≥30 分钟 → 10 分"""
    total_minutes = 0

    # 1. Garmin 运动数据
    garmin = db.query(GarminData).filter(
        GarminData.user_id == user_id,
        GarminData.record_date == target_date,
    ).first()
    if garmin:
        total_minutes += (garmin.moderate_intensity_minutes or 0) + (garmin.vigorous_intensity_minutes or 0)

    # 2. ActivityStatus 手动记录的运动
    from datetime import datetime, timezone as tz
    day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=tz.utc)
    day_end = day_start + timedelta(days=1)
    activities = db.query(ActivityStatus).filter(
        ActivityStatus.user_id == user_id,
        ActivityStatus.category == "exercising",
        ActivityStatus.start_time >= day_start,
        ActivityStatus.start_time < day_end,
    ).all()
    for a in activities:
        end_time = a.actual_end_time or a.estimated_end_time
        if end_time and a.start_time:
            delta = end_time - a.start_time
            total_minutes += max(0, int(delta.total_seconds() // 60))

    pts = 10 if total_minutes >= 30 else 0
    detail = f"{total_minutes}分钟" if total_minutes > 0 else "未运动"
    return [PointItem(
        category="exercise",
        name="每日运动",
        points=pts,
        max_points=10,
        detail=detail,
    )]


def _calc_sleep_points(db: Session, user_id: int, target_date: date) -> List[PointItem]:
    """睡眠积分：≥80分 5分，≥90分 10分"""
    garmin = db.query(GarminData).filter(
        GarminData.user_id == user_id,
        GarminData.record_date == target_date,
    ).first()

    score = garmin.sleep_score if garmin and garmin.sleep_score else 0
    if score >= 90:
        pts = 10
    elif score >= 80:
        pts = 5
    else:
        pts = 0

    detail = f"睡眠评分 {score}" if score > 0 else "无数据"
    return [PointItem(
        category="sleep",
        name="睡眠质量",
        points=pts,
        max_points=10,
        detail=detail,
    )]


def _calc_water_points(db: Session, user_id: int, target_date: date) -> List[PointItem]:
    """饮水积分：达标90% → 8分，100% → 10分"""
    total_ml = db.query(sa_func.coalesce(sa_func.sum(WaterIntake.amount_ml), 0)).filter(
        WaterIntake.user_id == user_id,
        WaterIntake.record_date == target_date,
    ).scalar() or 0

    pct = round(total_ml / WATER_DAILY_TARGET * 100) if WATER_DAILY_TARGET > 0 else 0
    if pct >= 100:
        pts = 10
    elif pct >= 90:
        pts = 8
    else:
        pts = 0

    detail = f"{total_ml}ml ({pct}%)" if total_ml > 0 else "未记录"
    return [PointItem(
        category="water",
        name="饮水达标",
        points=pts,
        max_points=10,
        detail=detail,
    )]


def _calc_checkin_points(db: Session, user_id: int, target_date: date) -> List[PointItem]:
    """打卡积分：每个完成目标的打卡项 → 10分"""
    records = db.query(CheckinRecord, CheckinTemplate).join(
        CheckinTemplate, CheckinRecord.template_id == CheckinTemplate.id,
    ).filter(
        CheckinRecord.user_id == user_id,
        CheckinRecord.checkin_date == target_date,
    ).all()

    items = []
    for record, template in records:
        target = record.target or template.default_target or 1
        reached = (record.value or 0) >= target
        pts = 10 if reached else 0
        detail = f"{record.value or 0}{template.unit}"
        if not reached:
            detail += f" (目标 {target}{template.unit})"
        items.append(PointItem(
            category="checkin",
            name=template.name,
            points=pts,
            max_points=10,
            detail=detail,
        ))
    return items


def calc_daily_points(db: Session, user_id: int, target_date: date) -> DailyPointsResponse:
    """计算指定日期的所有积分"""
    items: List[PointItem] = []
    items.extend(_calc_exercise_points(db, user_id, target_date))
    items.extend(_calc_sleep_points(db, user_id, target_date))
    items.extend(_calc_water_points(db, user_id, target_date))
    items.extend(_calc_checkin_points(db, user_id, target_date))

    total = sum(i.points for i in items)
    return DailyPointsResponse(date=target_date, total_points=total, items=items)


# ===== API 端点 =====

@router.get("/today", response_model=DailyPointsResponse, summary="今日积分")
async def get_today_points(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    today = get_china_today()
    return calc_daily_points(db, current_user.id, today)


@router.get("/date/{target_date}", response_model=DailyPointsResponse, summary="指定日期积分")
async def get_date_points(
    target_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return calc_daily_points(db, current_user.id, target_date)


@router.get("/summary", response_model=PointsSummaryResponse, summary="积分总览")
async def get_points_summary(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    today = get_china_today()

    # 今日详情
    today_detail = calc_daily_points(db, current_user.id, today)

    # 本周积分 (周一到今天)
    weekday = today.weekday()  # 0=Monday
    week_start = today - timedelta(days=weekday)
    week_points = 0
    for i in range((today - week_start).days + 1):
        d = week_start + timedelta(days=i)
        day_result = calc_daily_points(db, current_user.id, d)
        week_points += day_result.total_points

    # 本月积分
    month_start = today.replace(day=1)
    month_points = 0
    for i in range((today - month_start).days + 1):
        d = month_start + timedelta(days=i)
        day_result = calc_daily_points(db, current_user.id, d)
        month_points += day_result.total_points

    # 连续天数 (往前数连续有积分的天数)
    streak = 0
    check_date = today
    while True:
        day_result = calc_daily_points(db, current_user.id, check_date)
        if day_result.total_points > 0:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break
        if streak > 365:  # 安全上限
            break

    return PointsSummaryResponse(
        today_points=today_detail.total_points,
        week_points=week_points,
        month_points=month_points,
        streak_days=streak,
        today_detail=today_detail,
    )


@router.get("/history", response_model=List[PointsHistoryItem], summary="积分历史")
async def get_points_history(
    days: int = Query(default=7, ge=1, le=30),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    today = get_china_today()
    result = []
    for i in range(days):
        d = today - timedelta(days=i)
        day_result = calc_daily_points(db, current_user.id, d)
        result.append(PointsHistoryItem(date=d, total_points=day_result.total_points))
    return result
