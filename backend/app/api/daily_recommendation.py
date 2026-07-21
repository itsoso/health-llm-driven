"""每日健康分析与建议API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional
from app.config import settings
from app.database import get_db
from app.services.daily_recommendation import DailyRecommendationService
from app.services.llm_health_analyzer import llm_analyzer
from app.models.user import User
from app.models.daily_recommendation import DailyRecommendation
from app.api.deps import get_current_user_required, require_self_or_admin
from app.utils.timezone import get_china_today
from app.utils.redis_cache import get_cached_daily_recommendation, cache_daily_recommendation, invalidate_user_cache
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ========== /me 端点必须在 /user/{user_id} 之前定义 ==========

@router.delete("/me/cache")
def clear_my_recommendations_cache(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    清除当前用户的建议缓存（Redis + 数据库，需要登录）

    清除后下次获取建议时会重新生成
    """
    today = get_china_today()

    # 1. 清除 Redis 缓存
    invalidate_user_cache(current_user.id)

    # 2. 删除数据库缓存
    deleted = db.query(DailyRecommendation).filter(
        DailyRecommendation.user_id == current_user.id,
        DailyRecommendation.recommendation_date == today
    ).delete()

    db.commit()

    logger.info(f"用户 {current_user.id} 清除了建议缓存（Redis + DB），删除 {deleted} 条数据库记录")

    return {
        "status": "success",
        "message": "缓存已清除（包括 Redis 和数据库），下次访问时将重新生成建议",
        "deleted_count": deleted
    }


@router.post("/me/refresh")
async def refresh_my_recommendations(
    use_llm: bool = Query(default=True, description="是否使用大模型增强分析"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    清除缓存并重新生成建议（Redis + 数据库，需要登录）

    会先清除今天的缓存（Redis 和数据库），然后立即重新生成建议
    """
    today = get_china_today()

    # 1. 清除 Redis 缓存
    invalidate_user_cache(current_user.id)

    # 2. 删除数据库缓存
    db.query(DailyRecommendation).filter(
        DailyRecommendation.user_id == current_user.id,
        DailyRecommendation.recommendation_date == today
    ).delete()
    db.commit()

    logger.info(f"用户 {current_user.id} 请求刷新建议（已清除 Redis + DB 缓存）")

    # 3. 重新生成建议
    service = DailyRecommendationService()
    date_str = today.strftime('%Y-%m-%d')

    try:
        result = await service.get_or_generate_recommendations(db, current_user.id, use_llm)

        if result.get("status") == "no_data":
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "暂无数据，请先同步Garmin数据",
                    "suggestion": "请在设置页面配置并同步Garmin数据"
                }
            )

        # 4. 将新结果缓存到 Redis
        if result.get("status") != "no_data":
            cache_daily_recommendation(current_user.id, date_str, result, ttl=3600)

        result["refreshed"] = True
        result["cache_source"] = "none"  # 刚生成的，不是从缓存获取的
        return result
    except Exception as e:
        logger.error(f"刷新建议失败: {e}")
        raise HTTPException(status_code=500, detail=f"刷新建议失败: {str(e)}")


@router.get("/me")
async def get_my_recommendations(
    use_llm: bool = Query(default=True, description="是否使用大模型增强分析"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取当前用户今日健康建议（1天和7天，带 Redis + 数据库双层缓存，需要登录）

    返回基于昨天数据的1天建议和基于最近7天数据的7天建议
    缓存策略：
    1. 先查 Redis 缓存（1小时过期）
    2. Redis 未命中则查数据库缓存
    3. 数据库未命中则重新生成并缓存

    Args:
        use_llm: 是否使用大模型增强分析（默认True）

    Returns:
        - one_day: 基于昨天数据的建议
        - seven_day: 基于最近7天数据的建议
        - cached: 是否使用了缓存
        - cache_source: 缓存来源（redis/database/none）
    """
    today = get_china_today()
    date_str = today.strftime('%Y-%m-%d')

    # 1. 尝试从 Redis 获取缓存
    cached_result = get_cached_daily_recommendation(current_user.id, date_str)
    if cached_result:
        logger.info(f"✅ Redis 缓存命中：用户 {current_user.id} 日期 {date_str}")
        cached_result["cached"] = True
        cached_result["cache_source"] = "redis"
        return cached_result

    # 1.5 防止并发重复生成 — Redis 分布式锁
    import redis
    try:
        r = redis.from_url(settings.redis_url)
        lock_key = f"rec_gen_lock:{current_user.id}:{date_str}"
        acquired = r.set(lock_key, "1", nx=True, ex=90)  # 90s 锁
        if not acquired:
            # 另一个请求正在生成，等待结果
            import asyncio
            for _ in range(30):  # 最多等 30s
                await asyncio.sleep(1)
                cached_result = get_cached_daily_recommendation(current_user.id, date_str)
                if cached_result:
                    cached_result["cached"] = True
                    cached_result["cache_source"] = "redis"
                    return cached_result
            return {"status": "generating", "message": "正在生成中，请稍后刷新"}
    except Exception:
        pass  # Redis 不可用时不阻塞

    # 2. Redis 未命中，从数据库获取或生成
    service = DailyRecommendationService()

    try:
        result = await service.get_or_generate_recommendations(db, current_user.id, use_llm)

        if result.get("status") == "no_data":
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "暂无数据，请先同步Garmin数据",
                    "suggestion": "请在设置页面配置并同步Garmin数据"
                }
            )

        # 3. 将结果缓存到 Redis（1小时过期）
        if result.get("status") != "no_data":
            cache_daily_recommendation(current_user.id, date_str, result, ttl=3600)
            result["cache_source"] = "database" if result.get("cached") else "none"

        # 释放生成锁
        try:
            r = redis.from_url(settings.redis_url)
            r.delete(f"rec_gen_lock:{current_user.id}:{date_str}")
        except Exception as e:
            logger.warning("[daily_rec] 释放生成锁失败 user=%s: %s", current_user.id, e)

        return result
    except Exception as e:
        # 释放锁
        try:
            r = redis.from_url(settings.redis_url)
            r.delete(f"rec_gen_lock:{current_user.id}:{date_str}")
        except Exception as le:
            logger.warning("[daily_rec] 释放生成锁失败 user=%s: %s", current_user.id, le)
        logger.error(f"获取建议失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取建议失败: {str(e)}")


@router.get("/me/history")
def get_my_recommendations_history(
    start_date: Optional[date] = Query(None, description="开始日期（包含）"),
    end_date: Optional[date] = Query(None, description="结束日期（包含）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=50, description="每页数量"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取当前用户的每日建议历史记录（需要登录）

    支持按日期范围筛选和分页

    Args:
        start_date: 开始日期（包含）
        end_date: 结束日期（包含）
        page: 页码，从1开始
        page_size: 每页数量，最大50

    Returns:
        - items: 建议列表
        - total: 总数
        - page: 当前页码
        - page_size: 每页数量
        - total_pages: 总页数
    """
    query = db.query(DailyRecommendation).filter(
        DailyRecommendation.user_id == current_user.id
    )

    # 日期范围筛选
    if start_date:
        query = query.filter(DailyRecommendation.recommendation_date >= start_date)
    if end_date:
        query = query.filter(DailyRecommendation.recommendation_date <= end_date)

    # 获取总数
    total = query.count()

    # 按日期倒序排序
    query = query.order_by(DailyRecommendation.recommendation_date.desc())

    # 分页
    offset = (page - 1) * page_size
    records = query.offset(offset).limit(page_size).all()

    total_pages = (total + page_size - 1) // page_size

    return {
        "items": [
            {
                "id": rec.id,
                "recommendation_date": rec.recommendation_date.isoformat() if rec.recommendation_date else None,
                "analysis_date": rec.analysis_date.isoformat() if rec.analysis_date else None,
                "one_day": rec.one_day_recommendation,
                "seven_day": rec.seven_day_recommendation,
                "created_at": rec.created_at.isoformat() if rec.created_at else None,
                "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
            }
            for rec in records
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/me/history/{target_date}")
def get_my_recommendation_by_date(
    target_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取当前用户指定日期的每日建议（需要登录）

    Args:
        target_date: 目标日期

    Returns:
        该日期的建议记录，如果不存在则返回404
    """
    record = db.query(DailyRecommendation).filter(
        DailyRecommendation.user_id == current_user.id,
        DailyRecommendation.recommendation_date == target_date
    ).first()

    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"未找到 {target_date} 的建议记录"
        )

    return {
        "id": record.id,
        "recommendation_date": record.recommendation_date.isoformat() if record.recommendation_date else None,
        "analysis_date": record.analysis_date.isoformat() if record.analysis_date else None,
        "one_day": record.one_day_recommendation,
        "seven_day": record.seven_day_recommendation,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


@router.get("/me/sleep-insights", summary="获取我的睡眠洞察")
def get_my_sleep_insights(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户的详细睡眠分析"""
    return get_sleep_insights(current_user.id, current_user=current_user, db=db)


@router.get("/me/activity-insights", summary="获取我的活动洞察")
def get_my_activity_insights(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户的详细活动分析"""
    return get_activity_insights(current_user.id, current_user=current_user, db=db)


@router.get("/me/heart-insights", summary="获取我的心率洞察")
def get_my_heart_insights(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户的详细心率分析"""
    return get_heart_insights(current_user.id, current_user=current_user, db=db)


@router.get("/me/recovery-status", summary="获取我的恢复状态")
def get_my_recovery_status(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户的恢复状态分析"""
    return get_recovery_status(current_user.id, current_user=current_user, db=db)


@router.get("/user/{user_id}/recommendations")
async def get_recommendations(
    user_id: int,
    use_llm: bool = Query(default=True, description="是否使用大模型增强分析"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取今日健康建议（1天和7天，带缓存）

    返回基于昨天数据的1天建议和基于最近7天数据的7天建议
    结果会缓存到数据库，避免重复计算

    Args:
        user_id: 用户ID
        use_llm: 是否使用大模型增强分析（默认True）

    Returns:
        - one_day: 基于昨天数据的建议
        - seven_day: 基于最近7天数据的建议
        - cached: 是否使用了缓存
    """
    require_self_or_admin(current_user, user_id, resource="健康建议")
    service = DailyRecommendationService()

    try:
        result = await service.get_or_generate_recommendations(db, user_id, use_llm)

        if result.get("status") == "no_data":
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "暂无数据，请先同步Garmin数据",
                    "suggestion": "运行: python scripts/sync_garmin.py <email> <password> <user_id>"
                }
            )

        return result
    except Exception as e:
        logger.error(f"获取建议失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取建议失败: {str(e)}")


@router.get("/user/{user_id}/today")
async def get_today_recommendations(
    user_id: int,
    use_llm: bool = Query(default=True, description="是否使用大模型增强分析"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取今日健康建议（规则分析 + 大模型分析）

    基于昨天的Garmin数据（睡眠、运动、心率等），生成今天的个性化建议

    Args:
        user_id: 用户ID
        use_llm: 是否使用大模型增强分析（默认True）

    Returns:
        - 睡眠分析：质量评估、问题、建议
        - 活动分析：步数、活动时间、趋势
        - 心率分析：静息心率、HRV、健康状况
        - 压力分析：压力水平、身体电量、恢复状态
        - 综合建议：优先级排序的建议列表
        - 今日目标：具体可执行的目标
        - AI洞察：大模型生成的个性化建议（如启用）
    """
    require_self_or_admin(current_user, user_id, resource="健康建议")
    service = DailyRecommendationService()

    if use_llm:
        result = await service.generate_daily_summary_with_llm(db, user_id)
    else:
        result = service.generate_daily_summary(db, user_id)
        # 清理内部字段
        result.pop("_rule_analysis", None)
        result.pop("_yesterday_data", None)
        result.pop("_recent_data", None)

    if result.get("status") == "no_data":
        raise HTTPException(
            status_code=404,
            detail={
                "message": "暂无昨日数据，请先同步Garmin数据",
                "suggestion": "运行: python scripts/sync_garmin.py <email> <password> <user_id>"
            }
        )

    return result


@router.get("/user/{user_id}/today-simple")
def get_today_recommendations_simple(
    user_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取今日健康建议（仅规则分析，速度更快）

    不使用大模型，仅返回基于规则的分析结果
    """
    require_self_or_admin(current_user, user_id, resource="健康建议")
    service = DailyRecommendationService()
    result = service.generate_daily_summary(db, user_id)

    # 清理内部字段
    result.pop("_rule_analysis", None)
    result.pop("_yesterday_data", None)
    result.pop("_recent_data", None)

    if result.get("status") == "no_data":
        raise HTTPException(
            status_code=404,
            detail="暂无昨日数据，请先同步Garmin数据"
        )

    return result


@router.get("/llm-status")
def get_llm_status():
    """
    检查大模型服务状态
    """
    return {
        "available": llm_analyzer.is_available(),
        "message": "LLM服务可用" if llm_analyzer.is_available() else "LLM服务不可用，请配置 LLM Provider"
    }


@router.get("/user/{user_id}/analysis/{target_date}")
def get_analysis_for_date(
    user_id: int,
    target_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取指定日期的健康分析

    分析target_date前一天的数据，生成target_date当天的建议

    Args:
        user_id: 用户ID
        target_date: 目标日期（会分析这天前一天的数据）
    """
    require_self_or_admin(current_user, user_id, resource="健康建议")
    service = DailyRecommendationService()
    result = service.generate_daily_summary(db, user_id, reference_date=target_date)

    if result.get("status") == "no_data":
        raise HTTPException(
            status_code=404,
            detail=f"没有找到 {target_date} 前一天的数据"
        )

    return result


@router.get("/user/{user_id}/quick-summary")
def get_quick_summary(
    user_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取简要健康摘要

    返回最核心的信息，适合快速查看
    """
    require_self_or_admin(current_user, user_id, resource="健康建议")
    service = DailyRecommendationService()
    result = service.generate_daily_summary(db, user_id)

    if result.get("status") == "no_data":
        return {
            "status": "no_data",
            "message": "暂无数据"
        }

    # 返回简化版本
    return {
        "status": "success",
        "date": result.get("date"),
        "overall_status": result.get("overall_status"),
        "quick_stats": {
            "sleep_score": result.get("raw_data", {}).get("sleep_score"),
            "sleep_hours": round(result.get("raw_data", {}).get("sleep_duration_minutes", 0) / 60, 1) if result.get("raw_data", {}).get("sleep_duration_minutes") else None,
            "steps": result.get("raw_data", {}).get("steps"),
            "resting_hr": result.get("raw_data", {}).get("resting_heart_rate"),
            "body_battery": result.get("raw_data", {}).get("body_battery_highest")
        },
        "top_recommendation": result.get("priority_recommendations", ["暂无建议"])[0] if result.get("priority_recommendations") else "继续保持良好习惯",
        "today_focus": result.get("daily_goals", [{}])[0].get("goal", "保持日常活动") if result.get("daily_goals") else "保持日常活动"
    }


@router.get("/user/{user_id}/sleep-insights")
def get_sleep_insights(
    user_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取详细的睡眠分析"""
    require_self_or_admin(current_user, user_id, resource="健康建议")
    service = DailyRecommendationService()
    yesterday = service.get_yesterday_data(db, user_id)
    recent_data = service.get_recent_data(db, user_id, 7)

    if not yesterday:
        raise HTTPException(status_code=404, detail="暂无睡眠数据")

    analysis = service.analyze_sleep(yesterday, recent_data)

    return {
        "date": yesterday.record_date.isoformat(),
        "analysis": analysis,
        "raw_data": {
            "sleep_score": yesterday.sleep_score,
            "total_sleep_minutes": yesterday.total_sleep_duration,
            "deep_sleep_minutes": yesterday.deep_sleep_duration,
            "rem_sleep_minutes": yesterday.rem_sleep_duration,
            "light_sleep_minutes": yesterday.light_sleep_duration,
            "awake_minutes": yesterday.awake_duration
        }
    }


@router.get("/user/{user_id}/activity-insights")
def get_activity_insights(
    user_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取详细的活动分析"""
    require_self_or_admin(current_user, user_id, resource="健康建议")
    service = DailyRecommendationService()
    yesterday = service.get_yesterday_data(db, user_id)
    recent_data = service.get_recent_data(db, user_id, 7)

    if not yesterday:
        raise HTTPException(status_code=404, detail="暂无活动数据")

    analysis = service.analyze_activity(yesterday, recent_data)

    return {
        "date": yesterday.record_date.isoformat(),
        "analysis": analysis,
        "raw_data": {
            "steps": yesterday.steps,
            "active_minutes": yesterday.active_minutes,
            "calories_burned": yesterday.calories_burned
        }
    }


@router.get("/user/{user_id}/heart-insights")
def get_heart_insights(
    user_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取详细的心率分析"""
    require_self_or_admin(current_user, user_id, resource="健康建议")
    service = DailyRecommendationService()
    yesterday = service.get_yesterday_data(db, user_id)
    recent_data = service.get_recent_data(db, user_id, 7)

    if not yesterday:
        raise HTTPException(status_code=404, detail="暂无心率数据")

    analysis = service.analyze_heart_rate(yesterday, recent_data)

    return {
        "date": yesterday.record_date.isoformat(),
        "analysis": analysis,
        "raw_data": {
            "resting_heart_rate": yesterday.resting_heart_rate,
            "avg_heart_rate": yesterday.avg_heart_rate,
            "max_heart_rate": yesterday.max_heart_rate,
            "min_heart_rate": yesterday.min_heart_rate,
            "hrv": yesterday.hrv
        }
    }


@router.get("/user/{user_id}/recovery-status")
def get_recovery_status(
    user_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取恢复状态分析"""
    require_self_or_admin(current_user, user_id, resource="健康建议")
    service = DailyRecommendationService()
    yesterday = service.get_yesterday_data(db, user_id)

    if not yesterday:
        raise HTTPException(status_code=404, detail="暂无数据")

    analysis = service.analyze_stress_and_energy(yesterday)

    return {
        "date": yesterday.record_date.isoformat(),
        "analysis": analysis,
        "raw_data": {
            "stress_level": yesterday.stress_level,
            "body_battery_charged": yesterday.body_battery_charged,
            "body_battery_drained": yesterday.body_battery_drained,
            "body_battery_highest": yesterday.body_battery_most_charged,
            "body_battery_lowest": yesterday.body_battery_lowest
        }
    }
