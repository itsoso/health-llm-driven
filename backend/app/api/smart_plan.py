from datetime import UTC, date, datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.user import User
from app.models.smart_plan import WeeklyPlan, PlanItem
from app.models.health_goal_plan import PeriodGoal, PeriodGoalMetric
from app.schemas.smart_plan import (
    WeeklyPlanResponse, WeeklyPlanListItem,
    GeneratePlanRequest, PlanItemUpdate, PlanFeedbackRequest, PlanItemResponse,
    PeriodGoalResponse, PeriodGoalListItem, PeriodGoalMetricResponse,
    GenerateGoalRequest, UpdateMetricRequest,
)
from app.api.auth import get_current_user_required
from app.services.smart_plan_service import SmartPlanService
from app.services.period_goal_service import PeriodGoalService

router = APIRouter(prefix="/smart-plan", tags=["智能计划"])


def _plan_to_response(plan: WeeklyPlan) -> WeeklyPlanResponse:
    items = [PlanItemResponse.model_validate(item) for item in plan.items]
    return WeeklyPlanResponse(
        id=plan.id,
        user_id=plan.user_id,
        week_start=plan.week_start,
        status=plan.status,
        focus_areas=plan.focus_areas or [],
        ai_insights=plan.ai_insights or [],
        ai_risks=plan.ai_risks or [],
        weekly_summary=plan.weekly_summary,
        completion_rate=plan.completion_rate,
        ai_model=plan.ai_model,
        user_feedback=plan.user_feedback,
        items=sorted(items, key=lambda x: (x.day_of_week, x.sort_order)),
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.get("/analyze")
async def analyze_for_plan(
    target_week: str = Query("current", description="'current' 或 'next'"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取计划生成前的数据分析（不调用LLM）"""
    service = SmartPlanService(db)
    return await service.analyze_context(current_user.id, target_week)


@router.post("/generate")
async def generate_plan(
    request: GeneratePlanRequest,
    debug: bool = Query(default=False, description="是否返回调试信息"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """生成周计划（手动触发）"""
    service = SmartPlanService(db)
    try:
        result = await service.generate_plan(
            current_user.id,
            request.target_week,
            user_focus=request.user_focus,
            user_notes=request.user_notes,
            intensity=request.intensity,
            debug=debug,
        )
        plan = result["plan"]
        response = _plan_to_response(plan).model_dump(mode="json")
        if debug and result.get("debug"):
            response["debug"] = result["debug"]
        return response
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/current", response_model=Optional[WeeklyPlanResponse])
async def get_current_plan(
    week: str = Query("current", description="'current' 或 'next'"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前/下周计划"""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    if week == "next":
        week_start += timedelta(weeks=1)

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


@router.get("/today")
async def get_today_plan(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取今日计划项（用于首页快速卡片）"""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    day_of_week = today.weekday() + 1

    plan = db.query(WeeklyPlan).filter(
        WeeklyPlan.user_id == current_user.id,
        WeeklyPlan.week_start == week_start,
        WeeklyPlan.status == "active"
    ).first()

    if not plan:
        return {"has_plan": False, "items": []}

    today_items = sorted(
        [i for i in plan.items if i.day_of_week == day_of_week],
        key=lambda x: x.sort_order
    )
    return {
        "has_plan": True,
        "plan_id": plan.id,
        "completion_rate": plan.completion_rate,
        "total": len(today_items),
        "completed": sum(1 for i in today_items if i.is_completed),
        "items": [PlanItemResponse.model_validate(i) for i in today_items],
    }


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
    item.completed_at = datetime.now(UTC) if update.is_completed else None
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


# ===== 阶段性目标（月度/年度）=====

def _goal_to_response(goal: PeriodGoal) -> PeriodGoalResponse:
    metrics = [PeriodGoalMetricResponse.model_validate(m) for m in goal.metrics]
    return PeriodGoalResponse(
        id=goal.id,
        user_id=goal.user_id,
        period_type=goal.period_type,
        period_start=goal.period_start,
        period_end=goal.period_end,
        status=goal.status,
        focus_areas=goal.focus_areas or [],
        summary=goal.summary,
        ai_model=goal.ai_model,
        user_feedback=goal.user_feedback,
        metrics=metrics,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
    )


@router.post("/goals/generate")
async def generate_goal(
    request: GenerateGoalRequest,
    debug: bool = Query(default=False, description="是否返回调试信息"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """生成月度/年度目标"""
    if request.period_type not in ("monthly", "yearly"):
        raise HTTPException(status_code=400, detail="period_type 只能是 'monthly' 或 'yearly'")

    service = PeriodGoalService(db)
    try:
        result = await service.generate_goal(
            current_user.id, request.period_type, request.target_period, debug=debug
        )
        goal = result["goal"]
        response = _goal_to_response(goal).model_dump(mode="json")
        if debug and result.get("debug"):
            response["debug"] = result["debug"]
        return response
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/goals/active", response_model=List[PeriodGoalListItem])
async def get_active_goals(
    period_type: Optional[str] = Query(None, description="筛选周期类型: monthly/yearly"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取活跃目标列表"""
    service = PeriodGoalService(db)
    goals = service.get_active_goals(current_user.id, period_type)
    return [
        PeriodGoalListItem(
            id=g.id,
            period_type=g.period_type,
            period_start=g.period_start,
            period_end=g.period_end,
            status=g.status,
            focus_areas=g.focus_areas or [],
            summary=g.summary,
            user_feedback=g.user_feedback,
            metric_count=len(g.metrics),
            created_at=g.created_at,
        )
        for g in goals
    ]


@router.get("/goals/{goal_id}", response_model=PeriodGoalResponse)
async def get_goal_detail(
    goal_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取目标详情"""
    goal = db.query(PeriodGoal).filter(
        PeriodGoal.id == goal_id,
        PeriodGoal.user_id == current_user.id
    ).first()
    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在")
    return _goal_to_response(goal)


@router.patch("/goals/{goal_id}/metrics/{metric_id}")
async def update_metric_progress(
    goal_id: int,
    metric_id: int,
    update: UpdateMetricRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新指标进度"""
    goal = db.query(PeriodGoal).filter(
        PeriodGoal.id == goal_id,
        PeriodGoal.user_id == current_user.id
    ).first()
    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在")

    metric = db.query(PeriodGoalMetric).filter(
        PeriodGoalMetric.id == metric_id,
        PeriodGoalMetric.goal_id == goal_id
    ).first()
    if not metric:
        raise HTTPException(status_code=404, detail="指标不存在")

    metric.current_value = update.current_value
    db.commit()
    db.refresh(metric)
    return PeriodGoalMetricResponse.model_validate(metric)


@router.delete("/goals/{goal_id}")
async def delete_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除目标"""
    goal = db.query(PeriodGoal).filter(
        PeriodGoal.id == goal_id,
        PeriodGoal.user_id == current_user.id
    ).first()
    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在")

    db.delete(goal)
    db.commit()
    return {"message": "目标已删除"}
