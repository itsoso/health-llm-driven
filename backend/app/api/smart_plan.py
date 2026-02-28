from datetime import date, datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.user import User
from app.models.smart_plan import WeeklyPlan, PlanItem
from app.schemas.smart_plan import (
    WeeklyPlanResponse, WeeklyPlanListItem,
    GeneratePlanRequest, PlanItemUpdate, PlanFeedbackRequest, PlanItemResponse
)
from app.api.auth import get_current_user_required
from app.services.smart_plan_service import SmartPlanService

router = APIRouter(prefix="/smart-plan", tags=["智能计划"])


def _plan_to_response(plan: WeeklyPlan) -> WeeklyPlanResponse:
    items = [PlanItemResponse.model_validate(item) for item in plan.items]
    return WeeklyPlanResponse(
        id=plan.id,
        user_id=plan.user_id,
        week_start=plan.week_start,
        status=plan.status,
        focus_areas=plan.focus_areas or [],
        weekly_summary=plan.weekly_summary,
        completion_rate=plan.completion_rate,
        ai_model=plan.ai_model,
        user_feedback=plan.user_feedback,
        items=sorted(items, key=lambda x: (x.day_of_week, x.sort_order)),
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.post("/generate", response_model=WeeklyPlanResponse)
async def generate_plan(
    request: GeneratePlanRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """生成周计划（手动触发）"""
    service = SmartPlanService(db)
    try:
        plan = await service.generate_plan(current_user.id, request.target_week)
        return _plan_to_response(plan)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/current", response_model=Optional[WeeklyPlanResponse])
async def get_current_plan(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前周计划"""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    plan = db.query(WeeklyPlan).filter(
        WeeklyPlan.user_id == current_user.id,
        WeeklyPlan.week_start == week_start,
        WeeklyPlan.status.in_(["active", "draft"])
    ).first()

    if not plan:
        return None
    return _plan_to_response(plan)


@router.get("/history", response_model=List[WeeklyPlanListItem])
async def get_plan_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取历史计划列表"""
    plans = db.query(WeeklyPlan).filter(
        WeeklyPlan.user_id == current_user.id
    ).order_by(WeeklyPlan.week_start.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    result = []
    for plan in plans:
        item_count = len(plan.items)
        completed_count = sum(1 for i in plan.items if i.is_completed)
        result.append(WeeklyPlanListItem(
            id=plan.id,
            week_start=plan.week_start,
            status=plan.status,
            focus_areas=plan.focus_areas or [],
            completion_rate=plan.completion_rate,
            user_feedback=plan.user_feedback,
            item_count=item_count,
            completed_count=completed_count,
            created_at=plan.created_at,
        ))
    return result


@router.get("/{plan_id}", response_model=WeeklyPlanResponse)
async def get_plan_detail(
    plan_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取计划详情"""
    plan = db.query(WeeklyPlan).filter(
        WeeklyPlan.id == plan_id,
        WeeklyPlan.user_id == current_user.id
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    return _plan_to_response(plan)


@router.patch("/{plan_id}/items/{item_id}", response_model=PlanItemResponse)
async def update_plan_item(
    plan_id: int,
    item_id: int,
    update: PlanItemUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """手动标记计划项完成/取消"""
    plan = db.query(WeeklyPlan).filter(
        WeeklyPlan.id == plan_id,
        WeeklyPlan.user_id == current_user.id
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")

    item = db.query(PlanItem).filter(
        PlanItem.id == item_id,
        PlanItem.plan_id == plan_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="计划项不存在")

    item.is_completed = update.is_completed
    item.completed_at = datetime.utcnow() if update.is_completed else None
    db.commit()

    service = SmartPlanService(db)
    service.update_completion_rate(plan_id)

    db.refresh(item)
    return PlanItemResponse.model_validate(item)


@router.post("/{plan_id}/feedback")
async def submit_feedback(
    plan_id: int,
    feedback: PlanFeedbackRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """提交计划评分反馈"""
    plan = db.query(WeeklyPlan).filter(
        WeeklyPlan.id == plan_id,
        WeeklyPlan.user_id == current_user.id
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")

    plan.user_feedback = feedback.score
    db.commit()
    return {"message": "反馈已提交", "score": feedback.score}


@router.delete("/{plan_id}")
async def delete_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除计划"""
    plan = db.query(WeeklyPlan).filter(
        WeeklyPlan.id == plan_id,
        WeeklyPlan.user_id == current_user.id
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")

    db.delete(plan)
    db.commit()
    return {"message": "计划已删除"}
