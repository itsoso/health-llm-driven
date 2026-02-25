"""Kids每日计划 API"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.kids_plan import KidsDailyPlan
from app.schemas.kids_plan import (
    PlanItemSchema, KidsPlanSaveRequest, KidsPlanResponse, KidsPlanCopyRequest
)

router = APIRouter(prefix="/kids-plan", tags=["kids-plan"])


def _get_points_tier(rate: float) -> int:
    """根据完成率计算积分阶梯"""
    if rate >= 1.0:
        return 5
    if rate >= 0.9:
        return 4
    if rate >= 0.8:
        return 3
    if rate >= 0.7:
        return 2
    if rate >= 0.6:
        return 1
    return 0


@router.get("/{plan_date}", response_model=KidsPlanResponse, summary="获取某天计划")
async def get_plan(
    plan_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(KidsDailyPlan).filter(
        KidsDailyPlan.user_id == current_user.id,
        KidsDailyPlan.plan_date == plan_date,
    ).first()

    items = record.items if record else []
    awarded_tier = record.awarded_tier if record else 0

    return KidsPlanResponse(
        plan_date=plan_date,
        items=[PlanItemSchema(**item) for item in items] if items else [],
        awarded_tier=awarded_tier,
        points_awarded=0,
        total_kids_points=current_user.kids_points or 0,
    )


@router.put("/{plan_date}", response_model=KidsPlanResponse, summary="保存/更新计划")
async def save_plan(
    plan_date: date,
    payload: KidsPlanSaveRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    items_data = [item.model_dump() for item in payload.items]

    record = db.query(KidsDailyPlan).filter(
        KidsDailyPlan.user_id == current_user.id,
        KidsDailyPlan.plan_date == plan_date,
    ).first()

    if not record:
        record = KidsDailyPlan(
            user_id=current_user.id,
            plan_date=plan_date,
            items=items_data,
            awarded_tier=0,
        )
        db.add(record)
    else:
        record.items = items_data

    # 计算积分奖励
    points_awarded = 0
    total_items = len(items_data)
    if total_items > 0:
        done_count = sum(1 for item in items_data if item.get("done"))
        rate = done_count / total_items
        new_tier = _get_points_tier(rate)
        already_awarded = record.awarded_tier or 0
        delta = new_tier - already_awarded
        if delta > 0:
            points_awarded = delta
            record.awarded_tier = new_tier
            current_user.kids_points = (current_user.kids_points or 0) + delta

    db.commit()
    db.refresh(record)
    db.refresh(current_user)

    return KidsPlanResponse(
        plan_date=plan_date,
        items=[PlanItemSchema(**item) for item in record.items] if record.items else [],
        awarded_tier=record.awarded_tier or 0,
        points_awarded=points_awarded,
        total_kids_points=current_user.kids_points or 0,
    )


@router.post("/copy", response_model=KidsPlanResponse, summary="复制计划到指定日期")
async def copy_plan(
    payload: KidsPlanCopyRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    source = db.query(KidsDailyPlan).filter(
        KidsDailyPlan.user_id == current_user.id,
        KidsDailyPlan.plan_date == payload.from_date,
    ).first()

    if not source or not source.items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="源日期无计划数据",
        )

    # 复制 items，重置 done 状态
    new_items = []
    for i, item in enumerate(source.items):
        new_item = {**item, "done": False, "id": f"{int(__import__('time').time() * 1000)}_{i}"}
        new_items.append(new_item)

    target = db.query(KidsDailyPlan).filter(
        KidsDailyPlan.user_id == current_user.id,
        KidsDailyPlan.plan_date == payload.to_date,
    ).first()

    if target:
        target.items = new_items
        target.awarded_tier = 0
    else:
        target = KidsDailyPlan(
            user_id=current_user.id,
            plan_date=payload.to_date,
            items=new_items,
            awarded_tier=0,
        )
        db.add(target)

    db.commit()
    db.refresh(target)

    return KidsPlanResponse(
        plan_date=payload.to_date,
        items=[PlanItemSchema(**item) for item in target.items] if target.items else [],
        awarded_tier=0,
        points_awarded=0,
        total_kids_points=current_user.kids_points or 0,
    )
