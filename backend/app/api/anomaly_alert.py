"""健康异常预警 API"""
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.anomaly_alert import AnomalyAlert
from app.utils.timezone import get_china_today

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/anomaly-alerts", tags=["anomaly-alerts"])


@router.get("/me", summary="获取我的异常预警")
async def get_my_anomaly_alerts(
    days: int = Query(default=7, ge=1, le=90, description="查询天数"),
    acknowledged: Optional[bool] = Query(default=None, description="是否已确认: true/false/不传=全部"),
    severity: Optional[str] = Query(default=None, description="严重程度: info/warning/critical"),
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户的健康异常预警"""
    today = get_china_today()
    start_date = today - timedelta(days=days)

    query = db.query(AnomalyAlert).filter(
        AnomalyAlert.user_id == current_user.id,
        AnomalyAlert.detection_date >= start_date,
        AnomalyAlert.is_suppressed == False,
    )

    if acknowledged is not None:
        query = query.filter(AnomalyAlert.acknowledged == acknowledged)

    if severity:
        query = query.filter(AnomalyAlert.severity == severity)

    alerts = query.order_by(
        AnomalyAlert.severity.desc(),
        AnomalyAlert.detection_date.desc(),
    ).limit(limit).all()

    return {
        "alerts": [
            {
                "id": a.id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "metric_name": a.metric_name,
                "current_value": a.current_value,
                "baseline_value": a.baseline_value,
                "threshold_value": a.threshold_value,
                "deviation_pct": a.deviation_pct,
                "detection_date": a.detection_date.isoformat() if a.detection_date else None,
                "message": a.message,
                "acknowledged": a.acknowledged,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in alerts
        ],
        "count": len(alerts),
    }


@router.patch("/{alert_id}/acknowledge", summary="确认预警")
async def acknowledge_alert(
    alert_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """标记预警为已确认"""
    alert = db.query(AnomalyAlert).filter(
        AnomalyAlert.id == alert_id,
        AnomalyAlert.user_id == current_user.id,
    ).first()

    if not alert:
        raise HTTPException(status_code=404, detail="预警不存在")

    if alert.acknowledged:
        return {"success": True, "message": "预警已经确认过了"}

    alert.acknowledged = True
    db.commit()

    return {"success": True, "message": f"已确认预警: {alert.message}"}


@router.patch("/acknowledge-all", summary="确认所有预警")
async def acknowledge_all_alerts(
    days: int = Query(default=7, ge=1, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """批量确认所有未确认的预警"""
    today = get_china_today()
    start_date = today - timedelta(days=days)

    count = db.query(AnomalyAlert).filter(
        AnomalyAlert.user_id == current_user.id,
        AnomalyAlert.detection_date >= start_date,
        AnomalyAlert.acknowledged == False,
    ).update({"acknowledged": True})

    db.commit()

    return {"success": True, "message": f"已确认 {count} 条预警", "count": count}
