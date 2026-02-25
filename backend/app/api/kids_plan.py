"""Kids每日计划 API"""
import logging
from collections import Counter
from datetime import date, timedelta
from typing import List, Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.kids_plan import KidsDailyPlan
from app.schemas.kids_plan import (
    PlanItemSchema, KidsPlanSaveRequest, KidsPlanResponse, KidsPlanCopyRequest,
    KidsPlanDaySummary, KidsPlanHistoryResponse,
    KidsPlanReviewRequest, KidsPlanReviewResponse,
)

logger = logging.getLogger(__name__)

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


def _compute_date_range(range_str: str) -> tuple:
    """根据范围字符串计算起止日期"""
    today = date.today()
    if range_str == "week":
        return today - timedelta(days=6), today
    elif range_str == "month":
        return today - timedelta(days=29), today
    elif range_str == "year":
        return today - timedelta(days=364), today
    elif range_str == "next_day":
        return today, today + timedelta(days=1)
    elif range_str == "next_week":
        return today, today + timedelta(days=7)
    elif range_str == "next_month":
        return today, today + timedelta(days=30)
    elif range_str == "next_year":
        return today, today + timedelta(days=365)
    else:
        return today - timedelta(days=6), today


def _build_history_data(
    records: list, start_date: date, end_date: date
) -> Dict:
    """从数据库记录构建历史统计数据"""
    # 按日期索引
    record_map = {}
    for r in records:
        items = r.items or []
        total = len(items)
        done = sum(1 for it in items if it.get("done"))
        record_map[r.plan_date] = {
            "total_items": total,
            "done_count": done,
            "completion_rate": done / total if total > 0 else 0.0,
            "awarded_tier": r.awarded_tier or 0,
        }

    # 构建每日摘要
    days: List[KidsPlanDaySummary] = []
    d = start_date
    while d <= end_date:
        info = record_map.get(d)
        if info:
            days.append(KidsPlanDaySummary(plan_date=d, **info))
        else:
            days.append(KidsPlanDaySummary(
                plan_date=d, total_items=0, done_count=0,
                completion_rate=0.0, awarded_tier=0,
            ))
        d += timedelta(days=1)

    # 聚合统计
    plan_days = [day for day in days if day.total_items > 0]
    total_plan_days = len(plan_days)
    total_items = sum(day.total_items for day in plan_days)
    total_done = sum(day.done_count for day in plan_days)
    avg_rate = sum(day.completion_rate for day in plan_days) / total_plan_days if total_plan_days > 0 else 0.0

    # Streak 计算（从今天往回数）
    current_streak = 0
    best_streak = 0
    streak = 0
    for day in reversed(days):
        if day.total_items > 0 and day.done_count > 0:
            streak += 1
            best_streak = max(best_streak, streak)
        else:
            if streak > 0 and current_streak == 0:
                current_streak = streak
            streak = 0
    if streak > 0 and current_streak == 0:
        current_streak = streak
    best_streak = max(best_streak, streak)

    # Top 活动
    activity_counter: Counter = Counter()
    for r in records:
        for item in (r.items or []):
            key = (item.get("emoji", ""), item.get("text", ""))
            activity_counter[key] += 1
    top_activities = [
        {"emoji": k[0], "text": k[1], "count": v}
        for k, v in activity_counter.most_common(5)
    ]

    return {
        "days": days,
        "total_plan_days": total_plan_days,
        "total_items": total_items,
        "total_done": total_done,
        "avg_completion_rate": round(avg_rate, 3),
        "current_streak": current_streak,
        "best_streak": best_streak,
        "top_activities": top_activities,
    }


@router.get("/history", response_model=KidsPlanHistoryResponse, summary="获取计划历史统计")
async def get_plan_history(
    range: str = Query("week", pattern="^(week|month|year|next_day|next_week|next_month|next_year)$"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    start_date, end_date = _compute_date_range(range)
    records = db.query(KidsDailyPlan).filter(
        KidsDailyPlan.user_id == current_user.id,
        KidsDailyPlan.plan_date >= start_date,
        KidsDailyPlan.plan_date <= end_date,
    ).order_by(KidsDailyPlan.plan_date.asc()).all()

    data = _build_history_data(records, start_date, end_date)
    return KidsPlanHistoryResponse(
        range=range,
        start_date=start_date,
        end_date=end_date,
        **data,
    )


@router.post("/review", response_model=KidsPlanReviewResponse, summary="AI生成计划复盘")
async def generate_plan_review(
    payload: KidsPlanReviewRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    range_str = payload.range
    if range_str not in ("week", "month", "year"):
        raise HTTPException(status_code=400, detail="range 必须为 week/month/year")

    start_date, end_date = _compute_date_range(range_str)
    records = db.query(KidsDailyPlan).filter(
        KidsDailyPlan.user_id == current_user.id,
        KidsDailyPlan.plan_date >= start_date,
        KidsDailyPlan.plan_date <= end_date,
    ).order_by(KidsDailyPlan.plan_date.asc()).all()

    data = _build_history_data(records, start_date, end_date)

    if data["total_plan_days"] == 0:
        return KidsPlanReviewResponse(
            range=range_str,
            start_date=start_date,
            end_date=end_date,
            review_text="这段时间还没有计划记录哦～快去添加今天的计划吧！🌟",
            stats_summary=data,
        )

    range_labels = {"week": "一周", "month": "一个月", "year": "一年"}
    range_label = range_labels.get(range_str, range_str)

    # 每日详情（只列有计划的天）
    day_details = []
    for day in data["days"]:
        if day.total_items > 0:
            day_details.append(
                f"- {day.plan_date}: {day.done_count}/{day.total_items} "
                f"(完成率{day.completion_rate:.0%})"
            )

    top_str = "、".join(
        f"{a['emoji']}{a['text']}({a['count']}次)" for a in data["top_activities"]
    ) if data["top_activities"] else "暂无"

    system_prompt = (
        "你是一个鼓励型的儿童计划复盘助手。\n"
        "你将收到一个小朋友最近一段时间的每日计划完成数据。\n"
        "请用温暖、鼓励、有趣的语气来分析这些数据，给出复盘总结。\n\n"
        "## 回复要求\n"
        "1. 先表扬做得好的地方（必须找到亮点）\n"
        "2. 用比喻或故事的方式指出可以改进的地方\n"
        "3. 给出1-2个具体的小建议\n"
        "4. 用鼓励的话结尾\n"
        "5. 适当使用emoji让回复更生动\n"
        "6. 回复控制在200字以内\n"
        "7. 使用中文\n"
    )

    user_message = (
        f"以下是小朋友最近{range_label}的计划完成数据：\n"
        f"统计周期：{start_date} 至 {end_date}\n"
        f"有计划的天数：{data['total_plan_days']}天\n"
        f"平均每日完成率：{data['avg_completion_rate']:.0%}\n"
        f"当前连续完成天数：{data['current_streak']}天\n"
        f"最佳连续天数：{data['best_streak']}天\n"
        f"每日详情：\n" + "\n".join(day_details) + "\n"
        f"最常做的事情：{top_str}\n\n"
        f"请给这位小朋友做一个温暖的复盘总结。"
    )

    # 调用 OpenClaw LLM
    try:
        url = f"{settings.openclaw_base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if settings.openclaw_api_key:
            headers["Authorization"] = f"Bearer {settings.openclaw_api_key}"
        llm_payload = {
            "model": settings.openclaw_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=llm_payload, headers=headers)
            resp.raise_for_status()
            result = resp.json()
        review_text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.error(f"AI 复盘生成失败: {e}")
        review_text = "AI 复盘生成失败，请稍后再试～"

    return KidsPlanReviewResponse(
        range=range_str,
        start_date=start_date,
        end_date=end_date,
        review_text=review_text,
        stats_summary={
            "total_plan_days": data["total_plan_days"],
            "avg_completion_rate": data["avg_completion_rate"],
            "current_streak": data["current_streak"],
            "best_streak": data["best_streak"],
        },
    )


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
