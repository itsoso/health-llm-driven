"""每日健康分析与建议API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional
from app.database import get_db
from app.services.daily_recommendation import DailyRecommendationService
from app.services.llm_health_analyzer import llm_analyzer
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/user/{user_id}/recommendations")
def get_recommendations(
    user_id: int,
    use_llm: bool = Query(default=True, description="是否使用大模型增强分析"),
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
    service = DailyRecommendationService()
    
    try:
        result = service.get_or_generate_recommendations(db, user_id, use_llm)
        
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
def get_today_recommendations(
    user_id: int,
    use_llm: bool = Query(default=True, description="是否使用大模型增强分析"),
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
    service = DailyRecommendationService()
    
    if use_llm:
        result = service.generate_daily_summary_with_llm(db, user_id)
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
    db: Session = Depends(get_db)
):
    """
    获取今日健康建议（仅规则分析，速度更快）
    
    不使用大模型，仅返回基于规则的分析结果
    """
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
        "message": "LLM服务可用" if llm_analyzer.is_available() else "LLM服务不可用，请配置OpenAI API Key"
    }


@router.get("/user/{user_id}/analysis/{target_date}")
def get_analysis_for_date(
    user_id: int,
    target_date: date,
    db: Session = Depends(get_db)
):
    """
    获取指定日期的健康分析
    
    分析target_date前一天的数据，生成target_date当天的建议
    
    Args:
        user_id: 用户ID
        target_date: 目标日期（会分析这天前一天的数据）
    """
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
    db: Session = Depends(get_db)
):
    """
    获取简要健康摘要
    
    返回最核心的信息，适合快速查看
    """
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
    db: Session = Depends(get_db)
):
    """获取详细的睡眠分析"""
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
    db: Session = Depends(get_db)
):
    """获取详细的活动分析"""
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
    db: Session = Depends(get_db)
):
    """获取详细的心率分析"""
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
    db: Session = Depends(get_db)
):
    """获取恢复状态分析"""
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

