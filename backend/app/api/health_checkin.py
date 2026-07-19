"""健康打卡API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from app.database import get_db
from app.schemas.health_checkin import HealthCheckinCreate, HealthCheckinResponse
from app.models.health_checkin import HealthCheckin
from app.models.user import User
from app.api.deps import get_current_user_required

router = APIRouter()


@router.post("/", response_model=HealthCheckinResponse)
def create_health_checkin(
    checkin: HealthCheckinCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建健康打卡（需要登录）"""
    import logging
    logger = logging.getLogger(__name__)

    # 强制使用当前用户ID
    user_id = current_user.id
    logger.info(f"用户 {user_id} 保存打卡记录: {checkin.checkin_date}, notes={checkin.notes}")

    # 检查是否已存在该日期的打卡
    existing = db.query(HealthCheckin).filter(
        HealthCheckin.user_id == user_id,
        HealthCheckin.checkin_date == checkin.checkin_date
    ).first()

    if existing:
        # 更新现有记录
        logger.info(f"更新现有记录 ID={existing.id}")
        checkin_dict = checkin.model_dump(exclude={"user_id", "checkin_date"})

        # 特殊处理数组字段：如果提供了新值，则合并或替换
        for key, value in checkin_dict.items():
            if value is not None:
                # 对于数组字段（sneeze_times, nasal_wash_times），如果提供了新值，则合并
                if key in ['sneeze_times', 'nasal_wash_times'] and isinstance(value, list):
                    existing_value = getattr(existing, key) or []
                    # 合并数组（去重基于时间）
                    existing_times = {item.get('time'): item for item in existing_value}
                    for item in value:
                        existing_times[item.get('time')] = item
                    setattr(existing, key, list(existing_times.values()))
                else:
                    setattr(existing, key, value)

        # rhinitis 单条/日:带了 sneeze_times 时,sneeze_count 从合并后的 ledger 求和并
        # **单调递增**派生 —— 防止"增量口语"经 last-writer-wins 把当天累计写小(under-count
        # 会压掉 rhinitis_trend 的 worsening 就医推送)。前端/移动/chat 三端统一为
        # "增量入账、count=总和";只发 count 无 sneeze_times 的移动端 +1 路径不受影响。
        if checkin.sneeze_times:
            merged_times = getattr(existing, "sneeze_times", None) or []
            derived = sum(
                int(it.get("count") or 0) for it in merged_times if isinstance(it, dict)
            )
            existing.sneeze_count = max(existing.sneeze_count or 0, derived)

        db.commit()
        db.refresh(existing)
        return existing

    # 创建新记录
    checkin_data = checkin.model_dump()
    checkin_data["user_id"] = user_id

    # 首次当日打卡:带 sneeze_times 但没显式 sneeze_count → 从 times 求和派生(与更新分支一致)。
    if checkin.sneeze_times and not checkin_data.get("sneeze_count"):
        checkin_data["sneeze_count"] = sum(
            int(it.get("count") or 0) for it in checkin.sneeze_times if isinstance(it, dict)
        )

    # 个性化建议改为异步生成（不阻塞打卡保存）
    # 同步 LLM 调用曾导致 POST /checkin/ 耗时 20-35 秒
    checkin_data["personalized_advice"] = None

    logger.info(f"创建新记录: {checkin_data}")
    db_checkin = HealthCheckin(**checkin_data)
    db.add(db_checkin)
    db.commit()
    db.refresh(db_checkin)
    return db_checkin


@router.delete("/{checkin_id}/rhinitis/latest")
def undo_latest_rhinitis_checkin(
    checkin_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """撤销当前用户指定打卡日最近一次鼻炎事件,不删除整日打卡。"""
    checkin = db.query(HealthCheckin).filter(
        HealthCheckin.id == checkin_id,
        HealthCheckin.user_id == current_user.id,
    ).first()
    if not checkin:
        raise HTTPException(status_code=404, detail="打卡记录不存在")

    entries = list(checkin.sneeze_times or [])
    if not entries:
        raise HTTPException(status_code=404, detail="没有可撤销的鼻炎事件")

    removed = entries.pop()
    checkin.sneeze_times = entries or None
    remaining_total = sum(
        int(item.get("count") or 0) for item in entries if isinstance(item, dict)
    )
    checkin.sneeze_count = remaining_total or None
    db.commit()
    db.refresh(checkin)
    return {
        "id": checkin.id,
        "record_id": checkin.id,
        "resource_type": "health_checkin",
        "status": "recorded",
        "message": "已撤销最近一次鼻炎打卡",
        "undone": removed,
    }


# ========== /me 端点必须在 /user/{user_id} 之前定义 ==========

@router.get("/me/today", response_model=Optional[HealthCheckinResponse])
def get_my_today_checkin(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户今日健康打卡（需要登录）- 如果未打卡返回 null"""
    today = date.today()
    checkin = db.query(HealthCheckin).filter(
        HealthCheckin.user_id == current_user.id,
        HealthCheckin.checkin_date == today
    ).first()
    # 未打卡时返回 None，不抛出错误
    return checkin


@router.get("/me/history", response_model=List[HealthCheckinResponse])
def get_my_checkin_history(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    days: int = 30,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的健康打卡历史记录（需要登录）"""
    from datetime import timedelta

    query = db.query(HealthCheckin).filter(HealthCheckin.user_id == current_user.id)

    if start_date:
        query = query.filter(HealthCheckin.checkin_date >= start_date)
    elif not end_date:
        # 如果没有指定日期范围，默认获取最近N天
        start_date = date.today() - timedelta(days=days)
        query = query.filter(HealthCheckin.checkin_date >= start_date)

    if end_date:
        query = query.filter(HealthCheckin.checkin_date <= end_date)

    checkins = query.order_by(HealthCheckin.checkin_date.desc()).all()
    return checkins


@router.get("/me/stats")
def get_my_checkin_stats(
    days: int = 30,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的健康打卡统计（需要登录）"""
    from datetime import timedelta

    today = date.today()
    start_date = today - timedelta(days=days)

    # 获取历史记录
    checkins = db.query(HealthCheckin).filter(
        HealthCheckin.user_id == current_user.id,
        HealthCheckin.checkin_date >= start_date
    ).order_by(HealthCheckin.checkin_date).all()

    if not checkins:
        return {
            "days": days,
            "total_records": 0,
            "sneeze_stats": {
                "total_count": 0,
                "avg_per_day": 0,
                "max_per_day": 0,
                "trend": []
            },
            "nasal_wash_stats": {
                "total_count": 0,
                "avg_per_day": 0,
                "max_per_day": 0,
                "trend": []
            },
            "daily_trend": []
        }

    # 计算打喷嚏统计
    sneeze_counts = [c.sneeze_count for c in checkins if c.sneeze_count]
    total_sneeze = sum(sneeze_counts) if sneeze_counts else 0
    avg_sneeze = total_sneeze / len(sneeze_counts) if sneeze_counts else 0
    max_sneeze = max(sneeze_counts) if sneeze_counts else 0

    # 计算洗鼻统计
    nasal_wash_counts = [c.nasal_wash_count for c in checkins if c.nasal_wash_count]
    total_nasal_wash = sum(nasal_wash_counts) if nasal_wash_counts else 0
    avg_nasal_wash = total_nasal_wash / len(nasal_wash_counts) if nasal_wash_counts else 0
    max_nasal_wash = max(nasal_wash_counts) if nasal_wash_counts else 0

    # 构建每日趋势数据
    daily_trend = []
    sneeze_trend = []
    nasal_wash_trend = []

    for checkin in checkins:
        daily_trend.append({
            "date": checkin.checkin_date.isoformat(),
            "sneeze_count": checkin.sneeze_count or 0,
            "nasal_wash_count": checkin.nasal_wash_count or 0,
            "notes": checkin.notes
        })
        sneeze_trend.append({
            "date": checkin.checkin_date.isoformat(),
            "count": checkin.sneeze_count or 0
        })
        nasal_wash_trend.append({
            "date": checkin.checkin_date.isoformat(),
            "count": checkin.nasal_wash_count or 0
        })

    return {
        "days": days,
        "total_records": len(checkins),
        "sneeze_stats": {
            "total_count": total_sneeze,
            "avg_per_day": round(avg_sneeze, 1),
            "max_per_day": max_sneeze,
            "trend": sneeze_trend
        },
        "nasal_wash_stats": {
            "total_count": total_nasal_wash,
            "avg_per_day": round(avg_nasal_wash, 1),
            "max_per_day": max_nasal_wash,
            "trend": nasal_wash_trend
        },
        "daily_trend": daily_trend
    }


@router.get("/user/{user_id}", response_model=List[HealthCheckinResponse])
def get_user_checkins(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取用户的健康打卡记录（需要登录，只能查看自己的）"""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问其他用户的数据")

    query = db.query(HealthCheckin).filter(HealthCheckin.user_id == current_user.id)

    if start_date:
        query = query.filter(HealthCheckin.checkin_date >= start_date)
    if end_date:
        query = query.filter(HealthCheckin.checkin_date <= end_date)

    checkins = query.order_by(HealthCheckin.checkin_date.desc()).offset(skip).limit(limit).all()
    return checkins


@router.get("/user/{user_id}/today", response_model=Optional[HealthCheckinResponse])
def get_today_checkin(
    user_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取今日健康打卡（需要登录，只能查看自己的）- 如果未打卡返回 null"""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问其他用户的数据")

    today = date.today()
    checkin = db.query(HealthCheckin).filter(
        HealthCheckin.user_id == current_user.id,
        HealthCheckin.checkin_date == today
    ).first()

    # 未打卡时返回 None，不抛出错误
    return checkin
