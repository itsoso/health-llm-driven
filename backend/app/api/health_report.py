"""健康报告 API"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.user import User
from app.schemas.health_report import (
    HealthReportResponse,
    GenerateReportRequest,
)
from app.api.deps import get_current_user_required
from app.services.health_report_service import health_report_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health-report", tags=["健康报告"])


@router.post("/generate", response_model=HealthReportResponse)
async def generate_report(
    data: GenerateReportRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """生成健康报告"""
    logger.info(f"[ReportAPI] 用户 {current_user.id} 请求生成 {data.report_type} 报告")

    if data.report_type not in ("weekly", "monthly", "yearly"):
        raise HTTPException(status_code=400, detail="无效的报告类型，支持: weekly, monthly, yearly")

    report = health_report_service.generate_report(
        db=db,
        user_id=current_user.id,
        report_type=data.report_type,
        start_date=data.start_date,
    )
    return HealthReportResponse.model_validate(report)


@router.get("/list/me", response_model=List[HealthReportResponse])
async def list_my_reports(
    report_type: Optional[str] = None,
    limit: int = Query(default=20, le=50),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取我的报告列表"""
    reports = health_report_service.list_reports(
        db=db,
        user_id=current_user.id,
        report_type=report_type,
        limit=limit,
    )
    return [HealthReportResponse.model_validate(r) for r in reports]


@router.get("/detail/{report_id}", response_model=HealthReportResponse)
async def get_report_detail(
    report_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取报告详情"""
    report = health_report_service.get_report(db=db, report_id=report_id, user_id=current_user.id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return HealthReportResponse.model_validate(report)


@router.delete("/{report_id}")
async def delete_report(
    report_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """删除报告"""
    success = health_report_service.delete_report(db=db, report_id=report_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="报告不存在")
    return {"message": "报告已删除"}
