"""
性能监控 API
用于收集和查询性能数据
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from app.database import get_db
from app.models.performance import (
    PerformanceMetric, PerformanceAlert, PerformanceSummary,
    PlatformType, MetricType
)
from app.models.user import User
from app.api.auth import get_current_user_optional, get_current_user_required

router = APIRouter(prefix="/performance", tags=["性能监控"])


# ========== Pydantic 模型 ==========

class PerformanceMetricCreate(BaseModel):
    """性能指标创建"""
    session_id: str
    platform: PlatformType
    metric_type: MetricType
    metric_name: str
    duration: float
    start_time: datetime
    end_time: datetime
    details: Optional[dict] = None
    metadata: Optional[dict] = None
    success: int = 1
    error_message: Optional[str] = None


class PerformanceMetricBatch(BaseModel):
    """批量上报性能指标"""
    metrics: List[PerformanceMetricCreate]


class PerformanceOverview(BaseModel):
    """性能概览"""
    platform: str
    total_metrics: int
    avg_page_load: float
    avg_api_call: float
    error_rate: float
    slow_pages: List[dict]
    slow_apis: List[dict]


class PagePerformance(BaseModel):
    """页面性能"""
    page_name: str
    platform: str
    total_visits: int
    avg_duration: float
    p50_duration: float
    p90_duration: float
    p95_duration: float
    p99_duration: float
    error_rate: float
    trend: List[dict]


class APIPerformance(BaseModel):
    """API 性能"""
    api_name: str
    total_calls: int
    avg_duration: float
    p50_duration: float
    p90_duration: float
    p95_duration: float
    p99_duration: float
    success_rate: float
    error_rate: float


# ========== API 端点 ==========

@router.post("/metrics")
async def report_metric(
    metric: PerformanceMetricCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    上报单个性能指标
    """
    db_metric = PerformanceMetric(
        user_id=current_user.id if current_user else None,
        session_id=metric.session_id,
        platform=metric.platform,
        metric_type=metric.metric_type,
        metric_name=metric.metric_name,
        duration=metric.duration,
        start_time=metric.start_time,
        end_time=metric.end_time,
        details=metric.details,
        metadata=metric.metadata,
        success=metric.success,
        error_message=metric.error_message
    )
    
    db.add(db_metric)
    db.commit()
    
    return {"success": True, "message": "性能指标已记录"}


@router.post("/metrics/batch")
async def report_metrics_batch(
    batch: PerformanceMetricBatch,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    批量上报性能指标
    """
    db_metrics = []
    for metric in batch.metrics:
        db_metric = PerformanceMetric(
            user_id=current_user.id if current_user else None,
            session_id=metric.session_id,
            platform=metric.platform,
            metric_type=metric.metric_type,
            metric_name=metric.metric_name,
            duration=metric.duration,
            start_time=metric.start_time,
            end_time=metric.end_time,
            details=metric.details,
            metadata=metric.metadata,
            success=metric.success,
            error_message=metric.error_message
        )
        db_metrics.append(db_metric)
    
    db.bulk_save_objects(db_metrics)
    db.commit()
    
    return {
        "success": True,
        "message": f"已记录 {len(db_metrics)} 条性能指标"
    }


@router.get("/overview")
async def get_performance_overview(
    platform: Optional[PlatformType] = None,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    获取性能概览
    需要管理员权限
    """
    # TODO: 添加管理员权限检查
    
    start_time = datetime.now() - timedelta(hours=hours)
    
    # 构建查询条件
    conditions = [PerformanceMetric.created_at >= start_time]
    if platform:
        conditions.append(PerformanceMetric.platform == platform)
    
    # 获取各平台的性能数据
    platforms = [PlatformType.MINI_PROGRAM, PlatformType.WEB]
    if platform:
        platforms = [platform]
    
    result = []
    
    for plat in platforms:
        plat_conditions = conditions + [PerformanceMetric.platform == plat]
        
        # 总指标数
        total_metrics = db.query(func.count(PerformanceMetric.id)).filter(
            and_(*plat_conditions)
        ).scalar() or 0
        
        # 平均页面加载时间
        avg_page_load = db.query(func.avg(PerformanceMetric.duration)).filter(
            and_(*plat_conditions, PerformanceMetric.metric_type == MetricType.PAGE_LOAD)
        ).scalar() or 0
        
        # 平均 API 调用时间
        avg_api_call = db.query(func.avg(PerformanceMetric.duration)).filter(
            and_(*plat_conditions, PerformanceMetric.metric_type == MetricType.API_CALL)
        ).scalar() or 0
        
        # 错误率
        error_count = db.query(func.count(PerformanceMetric.id)).filter(
            and_(*plat_conditions, PerformanceMetric.success == 0)
        ).scalar() or 0
        error_rate = (error_count / total_metrics * 100) if total_metrics > 0 else 0
        
        # 慢页面（P95 > 3000ms）
        slow_pages = db.query(
            PerformanceMetric.metric_name,
            func.avg(PerformanceMetric.duration).label('avg_duration'),
            func.count(PerformanceMetric.id).label('count')
        ).filter(
            and_(*plat_conditions, PerformanceMetric.metric_type == MetricType.PAGE_LOAD)
        ).group_by(
            PerformanceMetric.metric_name
        ).having(
            func.avg(PerformanceMetric.duration) > 3000
        ).order_by(
            desc('avg_duration')
        ).limit(5).all()
        
        # 慢 API（P95 > 1000ms）
        slow_apis = db.query(
            PerformanceMetric.metric_name,
            func.avg(PerformanceMetric.duration).label('avg_duration'),
            func.count(PerformanceMetric.id).label('count')
        ).filter(
            and_(*plat_conditions, PerformanceMetric.metric_type == MetricType.API_CALL)
        ).group_by(
            PerformanceMetric.metric_name
        ).having(
            func.avg(PerformanceMetric.duration) > 1000
        ).order_by(
            desc('avg_duration')
        ).limit(5).all()
        
        result.append({
            "platform": plat.value,
            "total_metrics": total_metrics,
            "avg_page_load": round(avg_page_load, 2),
            "avg_api_call": round(avg_api_call, 2),
            "error_rate": round(error_rate, 2),
            "slow_pages": [
                {
                    "name": page[0],
                    "avg_duration": round(page[1], 2),
                    "count": page[2]
                }
                for page in slow_pages
            ],
            "slow_apis": [
                {
                    "name": api[0],
                    "avg_duration": round(api[1], 2),
                    "count": api[2]
                }
                for api in slow_apis
            ]
        })
    
    return result


@router.get("/pages")
async def get_page_performance(
    platform: PlatformType,
    page_name: Optional[str] = None,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    获取页面性能详情
    """
    start_time = datetime.now() - timedelta(hours=hours)
    
    conditions = [
        PerformanceMetric.created_at >= start_time,
        PerformanceMetric.platform == platform,
        PerformanceMetric.metric_type == MetricType.PAGE_LOAD
    ]
    
    if page_name:
        conditions.append(PerformanceMetric.metric_name == page_name)
    
    # 获取所有页面的性能统计
    pages = db.query(
        PerformanceMetric.metric_name,
        func.count(PerformanceMetric.id).label('total_visits'),
        func.avg(PerformanceMetric.duration).label('avg_duration'),
        func.count(func.nullif(PerformanceMetric.success, 1)).label('error_count')
    ).filter(
        and_(*conditions)
    ).group_by(
        PerformanceMetric.metric_name
    ).order_by(
        desc('total_visits')
    ).all()
    
    result = []
    for page in pages:
        # 获取百分位数
        durations = db.query(PerformanceMetric.duration).filter(
            and_(
                PerformanceMetric.created_at >= start_time,
                PerformanceMetric.platform == platform,
                PerformanceMetric.metric_type == MetricType.PAGE_LOAD,
                PerformanceMetric.metric_name == page[0]
            )
        ).order_by(PerformanceMetric.duration).all()
        
        durations_list = [d[0] for d in durations]
        
        def percentile(data, p):
            if not data:
                return 0
            k = (len(data) - 1) * p / 100
            f = int(k)
            c = f + 1 if f < len(data) - 1 else f
            return data[f] + (data[c] - data[f]) * (k - f)
        
        result.append({
            "page_name": page[0],
            "platform": platform.value,
            "total_visits": page[1],
            "avg_duration": round(page[2], 2),
            "p50_duration": round(percentile(durations_list, 50), 2),
            "p90_duration": round(percentile(durations_list, 90), 2),
            "p95_duration": round(percentile(durations_list, 95), 2),
            "p99_duration": round(percentile(durations_list, 99), 2),
            "error_rate": round(page[3] / page[1] * 100, 2) if page[1] > 0 else 0
        })
    
    return result


@router.get("/apis")
async def get_api_performance(
    api_name: Optional[str] = None,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    获取 API 性能详情
    """
    start_time = datetime.now() - timedelta(hours=hours)
    
    conditions = [
        PerformanceMetric.created_at >= start_time,
        PerformanceMetric.metric_type == MetricType.API_CALL
    ]
    
    if api_name:
        conditions.append(PerformanceMetric.metric_name == api_name)
    
    # 获取所有 API 的性能统计
    apis = db.query(
        PerformanceMetric.metric_name,
        func.count(PerformanceMetric.id).label('total_calls'),
        func.avg(PerformanceMetric.duration).label('avg_duration'),
        func.count(func.nullif(PerformanceMetric.success, 1)).label('error_count'),
        func.count(PerformanceMetric.success).label('success_count')
    ).filter(
        and_(*conditions)
    ).group_by(
        PerformanceMetric.metric_name
    ).order_by(
        desc('total_calls')
    ).all()
    
    result = []
    for api in apis:
        # 获取百分位数
        durations = db.query(PerformanceMetric.duration).filter(
            and_(
                PerformanceMetric.created_at >= start_time,
                PerformanceMetric.metric_type == MetricType.API_CALL,
                PerformanceMetric.metric_name == api[0]
            )
        ).order_by(PerformanceMetric.duration).all()
        
        durations_list = [d[0] for d in durations]
        
        def percentile(data, p):
            if not data:
                return 0
            k = (len(data) - 1) * p / 100
            f = int(k)
            c = f + 1 if f < len(data) - 1 else f
            return data[f] + (data[c] - data[f]) * (k - f)
        
        result.append({
            "api_name": api[0],
            "total_calls": api[1],
            "avg_duration": round(api[2], 2),
            "p50_duration": round(percentile(durations_list, 50), 2),
            "p90_duration": round(percentile(durations_list, 90), 2),
            "p95_duration": round(percentile(durations_list, 95), 2),
            "p99_duration": round(percentile(durations_list, 99), 2),
            "success_rate": round(api[4] / api[1] * 100, 2) if api[1] > 0 else 0,
            "error_rate": round(api[3] / api[1] * 100, 2) if api[1] > 0 else 0
        })
    
    return result


@router.get("/trends")
async def get_performance_trends(
    platform: PlatformType,
    metric_type: MetricType,
    metric_name: Optional[str] = None,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    获取性能趋势（按小时聚合）
    """
    start_time = datetime.now() - timedelta(hours=hours)
    
    conditions = [
        PerformanceMetric.created_at >= start_time,
        PerformanceMetric.platform == platform,
        PerformanceMetric.metric_type == metric_type
    ]
    
    if metric_name:
        conditions.append(PerformanceMetric.metric_name == metric_name)
    
    # 按小时聚合
    trends = db.query(
        func.date_trunc('hour', PerformanceMetric.created_at).label('hour'),
        func.count(PerformanceMetric.id).label('count'),
        func.avg(PerformanceMetric.duration).label('avg_duration'),
        func.count(func.nullif(PerformanceMetric.success, 1)).label('error_count')
    ).filter(
        and_(*conditions)
    ).group_by(
        'hour'
    ).order_by(
        'hour'
    ).all()
    
    return [
        {
            "time": trend[0].isoformat(),
            "count": trend[1],
            "avg_duration": round(trend[2], 2),
            "error_count": trend[3],
            "error_rate": round(trend[3] / trend[1] * 100, 2) if trend[1] > 0 else 0
        }
        for trend in trends
    ]


@router.get("/alerts")
async def get_performance_alerts(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    获取性能告警列表
    """
    query = db.query(PerformanceAlert)
    
    if status:
        query = query.filter(PerformanceAlert.status == status)
    
    alerts = query.order_by(
        desc(PerformanceAlert.created_at)
    ).limit(limit).all()
    
    return [
        {
            "id": alert.id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "platform": alert.platform.value,
            "metric_name": alert.metric_name,
            "metric_value": alert.metric_value,
            "threshold": alert.threshold,
            "description": alert.description,
            "status": alert.status,
            "created_at": alert.created_at.isoformat(),
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None
        }
        for alert in alerts
    ]
