"""
打卡系统 API - executor.life
"""
from datetime import date, datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.database import get_db
from app.models.user import User
from app.models.checkin import CheckinTemplate, CheckinRecord, DEFAULT_CHECKIN_TEMPLATES
from app.schemas.checkin import (
    CheckinTemplateCreate, CheckinTemplateUpdate, CheckinTemplateResponse, CheckinTemplateListResponse,
    CheckinRecordCreate, CheckinRecordQuick, CheckinRecordUpdate, CheckinRecordResponse,
    CheckinDailySummary, CheckinStats, CheckinCalendar
)
from app.api.auth import get_current_user_required
from app.models.smart_plan import WeeklyPlan, PlanItem

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/checkin", tags=["打卡系统"])


def _auto_complete_plan_items(user_id: int, template_id: int, checkin_date: date, db: Session):
    """打卡后自动标记匹配的计划项为完成"""
    try:
        week_start = checkin_date - timedelta(days=checkin_date.weekday())
        day_of_week = checkin_date.weekday() + 1  # 1=周一 ... 7=周日

        plan = db.query(WeeklyPlan).filter(
            WeeklyPlan.user_id == user_id,
            WeeklyPlan.week_start == week_start,
            WeeklyPlan.status == "active"
        ).first()
        if not plan:
            return

        items = db.query(PlanItem).filter(
            PlanItem.plan_id == plan.id,
            PlanItem.day_of_week == day_of_week,
            PlanItem.checkin_template_id == template_id,
            PlanItem.is_completed == False
        ).all()

        if not items:
            return

        for item in items:
            item.is_completed = True
            item.completed_at = datetime.utcnow()

        # 更新完成率
        total = db.query(func.count(PlanItem.id)).filter(PlanItem.plan_id == plan.id).scalar()
        completed = db.query(func.count(PlanItem.id)).filter(
            PlanItem.plan_id == plan.id, PlanItem.is_completed == True
        ).scalar()
        plan.completion_rate = round(completed / total * 100, 1) if total > 0 else 0.0
        if plan.completion_rate >= 100:
            plan.status = "completed"

        db.commit()
        logger.info(f"Auto-completed {len(items)} plan items for user {user_id}, template {template_id}")
    except Exception as e:
        logger.error(f"Auto-complete plan items failed: {e}")


# =====================================================
# 打卡模板 API
# =====================================================

@router.get("/templates", response_model=CheckinTemplateListResponse)
async def get_templates(
    category: Optional[str] = None,
    include_archived: bool = False,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取用户的打卡模板列表"""
    query = db.query(CheckinTemplate).filter(CheckinTemplate.user_id == current_user.id)
    
    if not include_archived:
        query = query.filter(CheckinTemplate.is_archived == False)
    
    if category:
        query = query.filter(CheckinTemplate.category == category)
    
    templates = query.order_by(CheckinTemplate.sort_order, CheckinTemplate.created_at).all()

    # 检查今日是否已完成 - 批量加载今日记录避免 N+1 查询
    today = date.today()
    template_ids = [t.id for t in templates]
    today_records = db.query(CheckinRecord.template_id).filter(
        CheckinRecord.template_id.in_(template_ids),
        CheckinRecord.checkin_date == today
    ).all()
    completed_template_ids = {r.template_id for r in today_records}

    result = []
    for template in templates:
        response = CheckinTemplateResponse.model_validate(template)
        response.today_completed = template.id in completed_template_ids
        result.append(response)
    
    # 统计各分类数量
    categories = {}
    for t in templates:
        categories[t.category] = categories.get(t.category, 0) + 1
    
    return CheckinTemplateListResponse(
        templates=result,
        total=len(result),
        categories=categories
    )


@router.post("/templates", response_model=CheckinTemplateResponse)
async def create_template(
    template_data: CheckinTemplateCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建打卡模板"""
    template = CheckinTemplate(
        user_id=current_user.id,
        **template_data.model_dump()
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    
    return CheckinTemplateResponse.model_validate(template)


@router.post("/templates/init-defaults")
async def init_default_templates(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """初始化默认打卡模板"""
    # 检查是否已有模板
    existing = db.query(CheckinTemplate).filter(
        CheckinTemplate.user_id == current_user.id
    ).count()

    if existing > 0:
        return {"message": f"已有 {existing} 个模板，跳过初始化", "created": 0}

    # 创建默认模板
    created = 0
    for tmpl_data in DEFAULT_CHECKIN_TEMPLATES:
        template = CheckinTemplate(
            user_id=current_user.id,
            **tmpl_data
        )
        db.add(template)
        created += 1

    db.commit()

    return {"message": f"已创建 {created} 个默认模板", "created": created}


@router.post("/templates/sync-defaults")
async def sync_default_templates(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """同步默认打卡模板（添加新增的默认模板）"""
    # 获取用户现有模板的名称
    existing_templates = db.query(CheckinTemplate).filter(
        CheckinTemplate.user_id == current_user.id
    ).all()
    existing_names = {t.name for t in existing_templates}

    # 添加缺失的默认模板
    created = 0
    new_templates = []
    for tmpl_data in DEFAULT_CHECKIN_TEMPLATES:
        if tmpl_data["name"] not in existing_names:
            template = CheckinTemplate(
                user_id=current_user.id,
                **tmpl_data
            )
            db.add(template)
            new_templates.append(tmpl_data["name"])
            created += 1

    if created > 0:
        db.commit()

    return {
        "message": f"已同步 {created} 个新模板" if created > 0 else "所有默认模板已存在",
        "created": created,
        "new_templates": new_templates
    }


@router.get("/templates/{template_id}", response_model=CheckinTemplateResponse)
async def get_template(
    template_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取打卡模板详情"""
    template = db.query(CheckinTemplate).filter(
        CheckinTemplate.id == template_id,
        CheckinTemplate.user_id == current_user.id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    return CheckinTemplateResponse.model_validate(template)


@router.put("/templates/{template_id}", response_model=CheckinTemplateResponse)
async def update_template(
    template_id: int,
    template_data: CheckinTemplateUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新打卡模板"""
    template = db.query(CheckinTemplate).filter(
        CheckinTemplate.id == template_id,
        CheckinTemplate.user_id == current_user.id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    update_data = template_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(template, key, value)
    
    db.commit()
    db.refresh(template)
    
    return CheckinTemplateResponse.model_validate(template)


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除打卡模板"""
    template = db.query(CheckinTemplate).filter(
        CheckinTemplate.id == template_id,
        CheckinTemplate.user_id == current_user.id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    db.delete(template)
    db.commit()
    
    return {"message": "模板已删除"}


# =====================================================
# 打卡记录 API
# =====================================================

@router.post("/records", response_model=CheckinRecordResponse)
async def create_record(
    record_data: CheckinRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建打卡记录"""
    # 验证模板存在
    template = db.query(CheckinTemplate).filter(
        CheckinTemplate.id == record_data.template_id,
        CheckinTemplate.user_id == current_user.id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="打卡模板不存在")
    
    # 检查是否已打卡
    existing = db.query(CheckinRecord).filter(
        CheckinRecord.template_id == record_data.template_id,
        CheckinRecord.checkin_date == record_data.checkin_date
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="今日已打卡，请使用更新接口")
    
    # 计算完成率
    target = record_data.target or template.default_target
    completion_rate = (record_data.value / target * 100) if target > 0 else 100
    
    # 创建记录
    record = CheckinRecord(
        user_id=current_user.id,
        completion_rate=completion_rate,
        **record_data.model_dump()
    )
    if record.target is None:
        record.target = template.default_target
    
    db.add(record)
    
    # 更新模板统计
    template.total_checkins += 1
    template.total_value += record_data.value
    template.last_checkin_date = record_data.checkin_date
    
    # 更新连续打卡天数
    _update_streak(template, record_data.checkin_date, db)
    
    db.commit()
    db.refresh(record)

    # 自动标记匹配的计划项为完成
    _auto_complete_plan_items(current_user.id, template.id, record_data.checkin_date, db)

    response = CheckinRecordResponse.model_validate(record)
    response.template_name = template.name
    response.template_icon = template.icon
    response.template_category = template.category

    return response


@router.post("/records/quick", response_model=CheckinRecordResponse)
async def quick_checkin(
    record_data: CheckinRecordQuick,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """快速打卡"""
    template = db.query(CheckinTemplate).filter(
        CheckinTemplate.id == record_data.template_id,
        CheckinTemplate.user_id == current_user.id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="打卡模板不存在")
    
    today = date.today()
    
    # 检查是否已打卡
    existing = db.query(CheckinRecord).filter(
        CheckinRecord.template_id == record_data.template_id,
        CheckinRecord.checkin_date == today
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="今日已打卡")
    
    # 使用默认值或指定值
    value = record_data.value if record_data.value is not None else template.default_target
    completion_rate = (value / template.default_target * 100) if template.default_target > 0 else 100
    
    record = CheckinRecord(
        template_id=record_data.template_id,
        user_id=current_user.id,
        checkin_date=today,
        value=value,
        target=template.default_target,
        completion_rate=completion_rate,
        notes=record_data.notes
    )
    db.add(record)
    
    # 更新模板统计
    template.total_checkins += 1
    template.total_value += value
    template.last_checkin_date = today
    _update_streak(template, today, db)
    
    db.commit()
    db.refresh(record)

    # 自动标记匹配的计划项为完成
    _auto_complete_plan_items(current_user.id, template.id, today, db)

    # 触发成就检查
    unlocked_badges = []
    try:
        from app.services.achievement_service import AchievementService
        newly = AchievementService(db).check_and_award(current_user.id, trigger="checkin")
        if newly:
            badge_defs = {d.id: d for d in AchievementService(db).get_all_definitions()}
            unlocked_badges = [
                {"name": badge_defs[ub.badge_id].name, "icon": badge_defs[ub.badge_id].icon}
                for ub in newly if ub.badge_id in badge_defs
            ]
    except Exception as e:
        logger.warning(f"成就检查失败 user={current_user.id}: {e}")

    response = CheckinRecordResponse.model_validate(record)
    response.template_name = template.name
    response.template_icon = template.icon
    response.template_category = template.category

    # 附加解锁成就信息
    result = response.model_dump()
    if unlocked_badges:
        result["unlocked_badges"] = unlocked_badges
    return result


@router.get("/records/today", response_model=CheckinDailySummary)
async def get_today_records(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取今日打卡记录"""
    today = date.today()
    
    # 获取所有活动模板
    templates = db.query(CheckinTemplate).filter(
        CheckinTemplate.user_id == current_user.id,
        CheckinTemplate.is_active == True,
        CheckinTemplate.is_archived == False
    ).all()
    
    # 获取今日记录
    records = db.query(CheckinRecord).filter(
        CheckinRecord.user_id == current_user.id,
        CheckinRecord.checkin_date == today
    ).all()
    
    completed_template_ids = {r.template_id for r in records}
    
    # 构建响应
    record_responses = []
    for record in records:
        template = next((t for t in templates if t.id == record.template_id), None)
        response = CheckinRecordResponse.model_validate(record)
        if template:
            response.template_name = template.name
            response.template_icon = template.icon
            response.template_category = template.category
        record_responses.append(response)
    
    completion_rate = (len(completed_template_ids) / len(templates) * 100) if templates else 0
    
    return CheckinDailySummary(
        date=today,
        total_templates=len(templates),
        completed_templates=len(completed_template_ids),
        completion_rate=round(completion_rate, 1),
        records=record_responses
    )


@router.get("/records", response_model=List[CheckinRecordResponse])
async def get_records(
    template_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(50, le=100),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取打卡记录列表"""
    query = db.query(CheckinRecord).filter(CheckinRecord.user_id == current_user.id)
    
    if template_id:
        query = query.filter(CheckinRecord.template_id == template_id)
    if start_date:
        query = query.filter(CheckinRecord.checkin_date >= start_date)
    if end_date:
        query = query.filter(CheckinRecord.checkin_date <= end_date)
    
    records = query.order_by(CheckinRecord.checkin_date.desc()).limit(limit).all()
    
    # 获取模板信息
    template_ids = list(set(r.template_id for r in records))
    templates = {t.id: t for t in db.query(CheckinTemplate).filter(
        CheckinTemplate.id.in_(template_ids)
    ).all()}
    
    result = []
    for record in records:
        response = CheckinRecordResponse.model_validate(record)
        template = templates.get(record.template_id)
        if template:
            response.template_name = template.name
            response.template_icon = template.icon
            response.template_category = template.category
        result.append(response)
    
    return result


# =====================================================
# 统计 API
# =====================================================

@router.get("/stats", response_model=CheckinStats)
async def get_stats(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取打卡统计"""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    
    # 获取模板
    templates = db.query(CheckinTemplate).filter(
        CheckinTemplate.user_id == current_user.id
    ).all()
    
    active_templates = [t for t in templates if t.is_active and not t.is_archived]
    
    # 获取今日记录数
    today_count = db.query(CheckinRecord).filter(
        CheckinRecord.user_id == current_user.id,
        CheckinRecord.checkin_date == today
    ).count()
    
    # 获取本周记录数
    week_count = db.query(CheckinRecord).filter(
        CheckinRecord.user_id == current_user.id,
        CheckinRecord.checkin_date >= week_start
    ).count()
    
    # 获取本月记录数
    month_count = db.query(CheckinRecord).filter(
        CheckinRecord.user_id == current_user.id,
        CheckinRecord.checkin_date >= month_start
    ).count()
    
    # 计算完成率
    completion_rate_today = (today_count / len(active_templates) * 100) if active_templates else 0

    # 计算本周完成率：本周有打卡的天数 / 已过天数
    if active_templates:
        days_in_week = (today - week_start).days + 1
        week_day_count = db.query(
            func.count(func.distinct(CheckinRecord.checkin_date))
        ).filter(
            CheckinRecord.user_id == current_user.id,
            CheckinRecord.checkin_date >= week_start,
            CheckinRecord.checkin_date <= today
        ).scalar() or 0
        completion_rate_week = round(week_day_count / days_in_week * 100, 1)
    else:
        completion_rate_week = 0.0

    # 计算本月完成率
    if active_templates:
        days_in_month = (today - month_start).days + 1
        month_day_count = db.query(
            func.count(func.distinct(CheckinRecord.checkin_date))
        ).filter(
            CheckinRecord.user_id == current_user.id,
            CheckinRecord.checkin_date >= month_start,
            CheckinRecord.checkin_date <= today
        ).scalar() or 0
        completion_rate_month = round(month_day_count / days_in_month * 100, 1)
    else:
        completion_rate_month = 0.0

    # 计算连续打卡
    current_streak = 0
    best_streak = max((t.best_streak for t in templates), default=0)

    # 统计最近7天趋势 - 批量查询避免 N+1
    week_ago = today - timedelta(days=6)
    trend_records = db.query(
        CheckinRecord.checkin_date,
        func.count(CheckinRecord.id).label('count')
    ).filter(
        CheckinRecord.user_id == current_user.id,
        CheckinRecord.checkin_date >= week_ago,
        CheckinRecord.checkin_date <= today
    ).group_by(CheckinRecord.checkin_date).all()

    trend_map = {r.checkin_date: r.count for r in trend_records}
    daily_trend = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_count = trend_map.get(day, 0)
        daily_trend.append({
            "date": day.isoformat(),
            "count": day_count,
            "rate": round(day_count / len(active_templates) * 100, 1) if active_templates else 0
        })
    
    # 分类统计
    by_category = {}
    for template in templates:
        cat = template.category
        if cat not in by_category:
            by_category[cat] = {"count": 0, "total_checkins": 0}
        by_category[cat]["count"] += 1
        by_category[cat]["total_checkins"] += template.total_checkins
    
    return CheckinStats(
        total_checkins=sum(t.total_checkins for t in templates),
        total_templates=len(templates),
        active_templates=len(active_templates),
        current_streak=current_streak,
        best_streak=best_streak,
        checkins_today=today_count,
        checkins_this_week=week_count,
        checkins_this_month=month_count,
        completion_rate_today=round(completion_rate_today, 1),
        completion_rate_week=completion_rate_week,
        completion_rate_month=completion_rate_month,
        by_category=by_category,
        daily_trend=daily_trend
    )


@router.get("/calendar/{year}/{month}", response_model=CheckinCalendar)
async def get_calendar(
    year: int,
    month: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取打卡日历"""
    from calendar import monthrange
    
    _, days_in_month = monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, days_in_month)
    
    # 获取活动模板数
    template_count = db.query(CheckinTemplate).filter(
        CheckinTemplate.user_id == current_user.id,
        CheckinTemplate.is_active == True,
        CheckinTemplate.is_archived == False
    ).count()
    
    # 获取当月所有记录
    records = db.query(
        CheckinRecord.checkin_date,
        func.count(CheckinRecord.id).label('count')
    ).filter(
        CheckinRecord.user_id == current_user.id,
        CheckinRecord.checkin_date >= start_date,
        CheckinRecord.checkin_date <= end_date
    ).group_by(CheckinRecord.checkin_date).all()
    
    # 构建日历数据
    days = {}
    completed_days = 0
    
    for record in records:
        day = record.checkin_date.day
        rate = (record.count / template_count * 100) if template_count > 0 else 0
        completed = rate >= 80  # 80%以上算完成
        
        days[day] = {
            "completed": completed,
            "rate": round(rate, 1),
            "records": record.count
        }
        
        if completed:
            completed_days += 1
    
    return CheckinCalendar(
        year=year,
        month=month,
        days=days,
        total_days=days_in_month,
        completed_days=completed_days,
        completion_rate=round(completed_days / days_in_month * 100, 1)
    )


# =====================================================
# 辅助函数
# =====================================================

def _update_streak(template: CheckinTemplate, checkin_date: date, db: Session):
    """更新连续打卡天数"""
    yesterday = checkin_date - timedelta(days=1)
    
    # 检查昨天是否打卡
    yesterday_record = db.query(CheckinRecord).filter(
        CheckinRecord.template_id == template.id,
        CheckinRecord.checkin_date == yesterday
    ).first()
    
    if yesterday_record or template.last_checkin_date == yesterday:
        # 连续打卡
        template.current_streak += 1
    else:
        # 断了，重新开始
        template.current_streak = 1
    
    # 更新最佳连续天数
    if template.current_streak > template.best_streak:
        template.best_streak = template.current_streak
