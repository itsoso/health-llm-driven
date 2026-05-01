"""月度复盘报告 API."""
import logging
from datetime import date
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.monthly_report import MonthlyReport
from app.models.user import User
from app.services.monthly_report_service import MonthlyReportService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/monthly-report", tags=["monthly-report"])

_service = MonthlyReportService()


def _serialize(row: MonthlyReport) -> Dict[str, Any]:
    return {
        "id": row.id,
        "year": row.year,
        "month": row.month,
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "version": row.version,
        "report": row.report_data or {},
    }


def _summary(row: MonthlyReport) -> Dict[str, Any]:
    """列表视图用的小摘要，不含详细趋势数组."""
    data = row.report_data or {}
    sc = (data.get("ai_scorecard") or {}).get("overall", {})
    cov = data.get("coverage", {})
    return {
        "year": row.year,
        "month": row.month,
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "coverage_pct": cov.get("pct", 0.0),
        "hit_rate": sc.get("hit_rate", 0.0),
        "total_graded": sc.get("total_graded", 0),
        "narrative": data.get("narrative", ""),
    }


@router.get("/me", summary="月报列表 (摘要)")
def list_my_reports(
    limit: int = Query(24, ge=1, le=60),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    rows = _service.list_reports(db, current_user.id, limit=limit)
    return {"reports": [_summary(r) for r in rows]}


@router.get("/me/{year}/{month}", summary="获取指定月份的复盘 (缺失时 lazy-generate)")
def get_my_report(
    year: int,
    month: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    if not (1 <= month <= 12):
        raise HTTPException(400, "month 必须在 1..12")
    today = date.today()
    # 不允许查询未来月份
    if (year, month) > (today.year, today.month):
        raise HTTPException(400, "不能查询未来月份")

    row = _service.get_or_generate(db, current_user.id, year, month)
    return _serialize(row)


@router.post("/me/{year}/{month}/regenerate", summary="强制重新生成")
def regenerate_my_report(
    year: int,
    month: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    if not (1 <= month <= 12):
        raise HTTPException(400, "month 必须在 1..12")
    today = date.today()
    if (year, month) > (today.year, today.month):
        raise HTTPException(400, "不能查询未来月份")

    row = _service.get_or_generate(db, current_user.id, year, month, force=True)
    return _serialize(row)
