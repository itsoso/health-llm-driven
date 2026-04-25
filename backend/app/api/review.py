"""
复盘 API 路由
"""
import logging
from datetime import date, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.review import DailyReview, PeriodReview, ReviewPeriod
from app.schemas.review import (
    DailyReviewCreate, DailyReviewUpdate, DailyReviewResponse,
    PeriodReviewCreate, PeriodReviewUpdate, PeriodReviewResponse,
    DailyHealthSummary, ReviewListItem, ReviewPeriodType
)
from app.services.review_service import ReviewService
from app.api.deps import get_current_user_required

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/review", tags=["复盘"])


# ========== 每日复盘 ==========

@router.get("/daily/today", response_model=DailyReviewResponse, summary="获取今日复盘")
async def get_today_review(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取今日复盘，如果不存在则自动创建"""
    service = ReviewService(db)
    today = date.today()

    review = service.get_daily_review(current_user.id, today)
    if not review:
        # 自动创建并填充健康数据
        review = service.create_or_update_daily_review(current_user.id, today)

    return review


@router.get("/daily/{review_date}", response_model=DailyReviewResponse, summary="获取指定日期复盘")
async def get_daily_review(
    review_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取指定日期的复盘"""
    service = ReviewService(db)

    review = service.get_daily_review(current_user.id, review_date)
    if not review:
        # 自动创建并填充健康数据
        review = service.create_or_update_daily_review(current_user.id, review_date)

    return review


@router.put("/daily/{review_date}", response_model=DailyReviewResponse, summary="更新每日复盘")
async def update_daily_review(
    review_date: date,
    update_data: DailyReviewUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新每日复盘（用户手动输入部分）"""
    service = ReviewService(db)

    user_input = update_data.model_dump(exclude_unset=True)
    review = service.create_or_update_daily_review(current_user.id, review_date, user_input)

    return review


@router.post("/daily/{review_date}/refresh", response_model=DailyReviewResponse, summary="刷新健康数据")
async def refresh_daily_review(
    review_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """刷新指定日期的健康数据汇总"""
    service = ReviewService(db)
    review = service.create_or_update_daily_review(current_user.id, review_date)
    return review


@router.get("/daily", response_model=List[ReviewListItem], summary="获取复盘列表")
async def list_daily_reviews(
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    limit: int = Query(30, ge=1, le=100, description="返回数量"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取复盘列表"""
    service = ReviewService(db)
    reviews = service.list_daily_reviews(current_user.id, start_date, end_date, limit)

    result = []
    for r in reviews:
        result.append(ReviewListItem(
            id=r.id,
            review_date=r.review_date,
            is_completed=r.is_completed,
            mood_score=r.mood_score,
            summary_preview=r.summary[:50] if r.summary else None
        ))

    return result


@router.get("/daily/{review_date}/summary", response_model=DailyHealthSummary, summary="获取健康数据汇总")
async def get_daily_health_summary(
    review_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取指定日期的健康数据汇总（不创建复盘记录）"""
    service = ReviewService(db)
    return service.get_daily_health_summary(current_user.id, review_date)


# ========== 周期复盘 ==========

@router.get("/period/week/current", response_model=PeriodReviewResponse, summary="获取本周复盘")
async def get_current_week_review(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取本周复盘"""
    service = ReviewService(db)
    start_date, end_date = service.get_current_week_range()

    review = service.create_period_review(
        current_user.id,
        ReviewPeriod.WEEKLY,
        start_date,
        end_date
    )
    return review


@router.get("/period/month/current", response_model=PeriodReviewResponse, summary="获取本月复盘")
async def get_current_month_review(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取本月复盘"""
    service = ReviewService(db)
    start_date, end_date = service.get_current_month_range()

    review = service.create_period_review(
        current_user.id,
        ReviewPeriod.MONTHLY,
        start_date,
        end_date
    )
    return review


@router.get("/period/{period_type}", response_model=List[PeriodReviewResponse], summary="获取周期复盘列表")
async def list_period_reviews(
    period_type: ReviewPeriodType,
    limit: int = Query(12, ge=1, le=52, description="返回数量"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取指定类型的周期复盘列表"""
    reviews = db.query(PeriodReview).filter(
        PeriodReview.user_id == current_user.id,
        PeriodReview.period_type == period_type.value
    ).order_by(PeriodReview.start_date.desc()).limit(limit).all()

    return reviews


@router.put("/period/{period_id}", response_model=PeriodReviewResponse, summary="更新周期复盘")
async def update_period_review(
    period_id: int,
    update_data: PeriodReviewUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新周期复盘（用户手动输入部分）"""
    review = db.query(PeriodReview).filter(
        PeriodReview.id == period_id,
        PeriodReview.user_id == current_user.id
    ).first()

    if not review:
        raise HTTPException(status_code=404, detail="复盘记录不存在")

    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(review, key, value)

    db.commit()
    db.refresh(review)

    return review


# ========== 统计接口 ==========

@router.get("/stats/streak", summary="获取复盘连续天数")
async def get_review_streak(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取复盘连续天数统计"""
    # 获取最近30天的复盘记录
    today = date.today()
    reviews = db.query(DailyReview).filter(
        DailyReview.user_id == current_user.id,
        DailyReview.review_date >= today - timedelta(days=30),
        DailyReview.is_completed == True
    ).order_by(DailyReview.review_date.desc()).all()

    # 计算连续天数
    current_streak = 0
    check_date = today

    review_dates = {r.review_date for r in reviews}

    while check_date in review_dates:
        current_streak += 1
        check_date -= timedelta(days=1)

    # 总复盘天数
    total_reviews = db.query(DailyReview).filter(
        DailyReview.user_id == current_user.id,
        DailyReview.is_completed == True
    ).count()

    return {
        "current_streak": current_streak,
        "total_reviews": total_reviews,
        "last_30_days": len(reviews)
    }


# ========== AI 总结 ==========

from pydantic import BaseModel

class AIReviewRequest(BaseModel):
    date: str
    period: str = "daily"  # daily, weekly, monthly


@router.post("/ai-summary", summary="AI生成复盘总结")
async def generate_ai_summary(
    request: AIReviewRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """使用 AI 生成复盘总结"""
    from datetime import datetime as dt

    try:
        target_date = dt.strptime(request.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

    service = ReviewService(db)
    ai_summary = service.generate_ai_summary(current_user.id, target_date, request.period)

    return {"ai_summary": ai_summary}
