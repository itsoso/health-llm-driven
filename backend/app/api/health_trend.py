"""健康趋势预测 API"""
import asyncio
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.health_trend_service import HealthTrendService

router = APIRouter(prefix="/health-trends", tags=["health-trends"])


@router.get("/latest")
async def get_latest_trends(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取最新一期各维度趋势概览"""
    svc = HealthTrendService(db)
    reports = svc.get_latest(current_user.id)
    return {
        "report_date": str(reports[0].report_date) if reports else None,
        "dimensions": [
            {
                "dimension": r.dimension,
                "period": r.period,
                "trend_direction": r.trend_direction,
                "insights": r.insights or [],
                "suggestions": r.suggestions or [],
                "risk_alerts": r.risk_alerts or [],
                "report_date": str(r.report_date),
            }
            for r in reports
        ],
    }


@router.get("/history")
async def get_trend_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取历史报告列表"""
    svc = HealthTrendService(db)
    result = svc.get_history(current_user.id, limit=limit, offset=offset)
    return {
        "total": result["total"],
        "items": [
            {
                "id": r.id,
                "report_date": str(r.report_date),
                "dimension": r.dimension,
                "period": r.period,
                "trend_direction": r.trend_direction,
                "insights": r.insights or [],
                "created_at": str(r.created_at),
            }
            for r in result["items"]
        ],
    }


@router.get("/{dimension}")
async def get_dimension_trend(
    dimension: str,
    period: str = Query(default="7d"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取指定维度详细报告"""
    if dimension not in ("weight", "sleep", "exercise", "overall"):
        return {"error": "无效维度，支持: weight, sleep, exercise, overall"}

    svc = HealthTrendService(db)
    report = svc.get_dimension_report(current_user.id, dimension, period)
    if not report:
        return {"error": "暂无该维度的趋势报告"}

    return {
        "id": report.id,
        "user_id": report.user_id,
        "report_date": str(report.report_date),
        "dimension": report.dimension,
        "period": report.period,
        "trend_direction": report.trend_direction,
        "raw_data_summary": report.raw_data_summary,
        "insights": report.insights or [],
        "suggestions": report.suggestions or [],
        "risk_alerts": report.risk_alerts or [],
        "full_report": report.full_report,
        "created_at": str(report.created_at),
    }


@router.post("/generate")
async def generate_trends(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """手动触发趋势分析（调试用）"""
    svc = HealthTrendService(db)
    analyzed = await svc.analyze_trends(current_user.id)
    return {"analyzed_dimensions": analyzed}
