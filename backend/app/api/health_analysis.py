"""健康分析API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date
from app.database import get_db
from app.services.health_analysis import HealthAnalysisService
from app.models.user import User
from app.api.deps import get_current_user_required

router = APIRouter()


# ========== /me 端点必须在 /user/{user_id} 之前定义 ==========

@router.get("/me/issues")
def analyze_my_health_issues(
    force_refresh: bool = Query(default=False, description="是否强制刷新缓存"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    分析当前用户的健康问题（带缓存，需要登录）
    
    - 默认使用当天缓存的分析结果
    - 第二天自动重新分析
    - 可通过 force_refresh=true 强制刷新
    """
    service = HealthAnalysisService()
    return service.analyze_health_issues(db, current_user.id, force_refresh)


@router.get("/me/advice")
def get_my_personalized_advice(
    checkin_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的个性化建议（需要登录）"""
    service = HealthAnalysisService()
    advice = service.generate_personalized_advice(db, current_user.id, checkin_date)
    return {"advice": advice}


# ========== /user/{user_id} 端点 ==========

@router.get("/user/{user_id}/issues")
def analyze_health_issues(
    user_id: int,
    force_refresh: bool = Query(default=False, description="是否强制刷新缓存"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """分析健康问题（需要登录，只能查看自己或被管理用户的数据）"""
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="无权访问")
    service = HealthAnalysisService()
    return service.analyze_health_issues(db, user_id, force_refresh)


@router.get("/user/{user_id}/advice")
def get_personalized_advice(
    user_id: int,
    checkin_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取个性化建议（需要登录，只能查看自己或被管理用户的数据）"""
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="无权访问")
    service = HealthAnalysisService()
    advice = service.generate_personalized_advice(db, user_id, checkin_date)
    return {"advice": advice}


# ========== 结构化分析端点（Phase 2 新增） ==========

@router.get("/me/structured")
def analyze_my_health_structured(
    force_refresh: bool = Query(default=False, description="是否强制刷新"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    结构化多维健康分析（新版本）

    按 5 个维度（心血管、代谢、睡眠恢复、运动体能、营养）分别分析，
    返回各维度评分、趋势、跨维度协同效应和数据质量评估。
    """
    service = HealthAnalysisService()
    return service.analyze_health_structured(db, current_user.id, force_refresh)


@router.get("/me/trends")
def get_my_metric_trends(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取关键指标的趋势数据（过去 90 天线性回归）"""
    service = HealthAnalysisService()
    health_data = service.collect_user_health_data(db, current_user.id, days=90)
    return service._compute_metric_trends(health_data)
