"""
数据健康仪表盘 API

提供各数据源的状态概览，帮助用户了解数据完整性。
"""
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.data_collection.garmin_native_auth import has_native_token_store

logger = logging.getLogger(__name__)
router = APIRouter()


def _ensure_utc(dt: datetime | None) -> datetime | None:
    """把 naive datetime 当作 UTC 处理, 避免 tz-aware vs naive 比较 TypeError.

    SQLAlchemy DateTime(timezone=True) 在某些 psycopg2 版本下仍可能返回 naive,
    防御性兜底.
    """
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


@router.get("/status")
def get_data_health_status(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    获取当前用户各数据源的健康状态

    返回 Garmin 连接、HRV、饮食、饮水、推送、基因等模块的状态。
    """
    user_id = current_user.id
    today = date.today()
    now = datetime.now(UTC)

    return {
        "garmin": _garmin_status(db, user_id, now),
        "hrv": _hrv_status(db, user_id, today),
        "diet": _diet_status(db, user_id, today),
        "water": _water_status(db, user_id, today),
        "notifications": _notification_status(db, user_id, now),
        "genetic": _genetic_status(db, user_id),
    }


@router.get("/integrity", summary="数据正确性自检(量纲/范围/层断连;系统自我监控)")
def get_data_integrity(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """区别于 /status(完整度):这里查**正确性**——HRV 量纲错、SpO2 小数存、
    归一层断连、周期空目标等静默损坏。空 issues = 健康。"""
    from app.services.data_integrity import check_user_integrity
    issues = check_user_integrity(db, current_user.id)
    return {"healthy": len(issues) == 0, "issue_count": len(issues), "issues": issues}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _garmin_status(db: Session, user_id: int, now: datetime) -> dict:
    """Garmin 连接 & session 状态"""
    from app.models.user import GarminCredential

    cred = db.query(GarminCredential).filter(
        GarminCredential.user_id == user_id,
    ).first()

    if not cred:
        return {
            "status": "error",
            "last_sync": None,
            "session_valid": False,
            "session_expires": None,
            "message": "未绑定 Garmin 账号",
        }

    # SQLAlchemy DateTime(timezone=True) 有时返回 naive, 强制 normalize
    session_expires = _ensure_utc(cred.session_expires_at)
    last_sync = _ensure_utc(cred.last_sync_at)

    session_valid = has_native_token_store(cred.garth_session)

    if not cred.sync_enabled:
        status = "error"
        message = "同步已关闭"
    elif not cred.credentials_valid:
        status = "error"
        message = cred.last_error or "凭证无效"
    elif not session_valid:
        status = "warning"
        message = "Session 已过期，等待自动续期"
    else:
        # 检查最近是否有成功同步
        if last_sync and (now - last_sync).total_seconds() < 86400:
            status = "ok"
            message = "正常同步中"
        else:
            status = "warning"
            message = "超过24小时未同步"

    return {
        "status": status,
        "last_sync": last_sync.isoformat() if last_sync else None,
        "session_valid": session_valid,
        "session_expires": session_expires.isoformat() if session_expires else None,
        "message": message,
    }


def _hrv_status(db: Session, user_id: int, today: date) -> dict:
    """最近 7 天 HRV 数据完整性"""
    from app.models.daily_health import GarminData

    seven_days_ago = today - timedelta(days=6)  # 含今天共 7 天

    rows = (
        db.query(GarminData.record_date)
        .filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= seven_days_ago,
            GarminData.record_date <= today,
            GarminData.hrv.isnot(None),
        )
        .all()
    )

    available_dates = {r.record_date for r in rows}
    expected_dates = {seven_days_ago + timedelta(days=i) for i in range(7)}
    missing_days = len(expected_dates - available_dates)

    last_available = max(available_dates) if available_dates else None

    if missing_days == 0:
        status = "ok"
        message = "最近7天HRV数据完整"
    elif missing_days <= 2:
        status = "warning"
        message = f"最近7天缺失{missing_days}天HRV数据"
    else:
        status = "error"
        message = f"最近7天缺失{missing_days}天HRV数据"

    return {
        "status": status,
        "missing_days": missing_days,
        "last_available": last_available.isoformat() if last_available else None,
        "message": message,
    }


def _diet_status(db: Session, user_id: int, today: date) -> dict:
    """今日饮食记录状态"""
    from app.models.daily_health import DietRecord

    today_count = (
        db.query(func.count(DietRecord.id))
        .filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date == today,
        )
        .scalar()
    ) or 0

    # 过去 7 天每日平均
    seven_days_ago = today - timedelta(days=6)
    week_total = (
        db.query(func.count(DietRecord.id))
        .filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date >= seven_days_ago,
            DietRecord.record_date <= today,
        )
        .scalar()
    ) or 0
    week_avg = round(week_total / 7, 1)

    if today_count >= 2:
        status = "ok"
        message = f"今天已记录{today_count}餐"
    elif today_count == 1:
        status = "warning"
        message = "今天仅记录1餐"
    else:
        status = "warning"
        message = "今天尚未记录饮食"

    return {
        "status": status,
        "today_count": today_count,
        "week_avg": week_avg,
        "message": message,
    }


def _water_status(db: Session, user_id: int, today: date) -> dict:
    """今日饮水状态"""
    from app.models.daily_health import WaterIntake

    today_amount = (
        db.query(func.coalesce(func.sum(WaterIntake.amount_ml), 0))
        .filter(
            WaterIntake.user_id == user_id,
            WaterIntake.record_date == today,
        )
        .scalar()
    ) or 0

    target = 2000  # 默认目标 2000ml

    if today_amount >= target:
        status = "ok"
        message = f"今日饮水{today_amount}ml，已达标"
    elif today_amount >= target * 0.5:
        status = "warning"
        message = f"今日饮水{today_amount}ml/{target}ml"
    else:
        status = "warning" if today_amount > 0 else "warning"
        message = f"今日饮水{today_amount}ml/{target}ml"

    return {
        "status": status,
        "today_amount": today_amount,
        "target": target,
        "message": message,
    }


def _notification_status(db: Session, user_id: int, now: datetime) -> dict:
    """推送通知状态 — 只查 DB，不阻塞 Celery ping"""
    from app.models.notification import NotificationLog

    twenty_four_hours_ago = now - timedelta(hours=24)

    last_24h_count = (
        db.query(func.count(NotificationLog.id))
        .filter(
            NotificationLog.user_id == user_id,
            NotificationLog.created_at >= twenty_four_hours_ago,
        )
        .scalar()
    ) or 0

    # 用最近一条 NotificationLog 的时间推断 worker 是否存活，
    # 避免同步 celery.control.ping(timeout=2s) 阻塞整个请求
    latest_any = (
        db.query(NotificationLog.sent_at)
        .order_by(NotificationLog.sent_at.desc())
        .first()
    )
    # 如果全局最新一条推送在 25 小时内，说明 worker 最近正常运行过
    worker_likely_ok = False
    if latest_any is not None and latest_any[0] is not None:
        ts = _ensure_utc(latest_any[0])
        worker_likely_ok = (now - ts).total_seconds() < 90000  # 25h

    if last_24h_count > 0:
        status = "ok"
        message = "推送正常"
    elif worker_likely_ok:
        status = "warning"
        message = "过去24小时无推送记录"
    else:
        status = "warning"
        message = "推送服务可能未启动"

    return {
        "status": status,
        "last_24h_count": last_24h_count,
        "message": message,
    }


def _genetic_status(db: Session, user_id: int) -> dict:
    """基因数据状态"""
    from app.models.genetic_data import GeneticVariant

    variant_count = (
        db.query(func.count(GeneticVariant.id))
        .filter(GeneticVariant.user_id == user_id)
        .scalar()
    ) or 0

    if variant_count > 0:
        status = "ok"
        message = f"已录入{variant_count}个基因位点"
    else:
        status = "warning"
        message = "尚未录入基因数据"

    return {
        "status": status,
        "variant_count": variant_count,
        "message": message,
    }
