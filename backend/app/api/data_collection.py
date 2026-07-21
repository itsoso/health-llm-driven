"""数据收集API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, timedelta
import asyncio
import logging
from app.database import get_db
from app.services.data_collection import DataCollectionService
from app.models.daily_health import GarminData
from app.models.user import User, GarminCredential
from app.api.deps import get_current_user_required, require_self_or_admin
from app.services.auth import garmin_credential_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/garmin/sync")
async def sync_garmin_data(
    user_id: int,
    target_date: date,
    access_token: Optional[str] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    同步Garmin数据

    注意：需要Garmin API的access_token
    如果使用Garmin Connect导出，可以使用手动导入接口
    """
    require_self_or_admin(current_user, user_id, resource="Garmin 数据")
    service = DataCollectionService()
    result = await service.sync_garmin_data(db, user_id, target_date, access_token)

    if not result:
        raise HTTPException(
            status_code=400,
            detail="同步失败，请检查Garmin API配置和access_token。如果没有access_token，可以使用手动导入接口：POST /api/v1/daily-health/garmin"
        )

    return {
        "message": "同步成功",
        "data_id": result.id,
        "record_date": result.record_date.isoformat()
    }


@router.post("/garmin/sync-range")
async def sync_garmin_data_range(
    user_id: int,
    start_date: date,
    end_date: date,
    access_token: Optional[str] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """批量同步指定日期范围的Garmin数据"""
    require_self_or_admin(current_user, user_id, resource="Garmin 数据")
    service = DataCollectionService()
    results = []
    errors = []

    current_date = start_date
    while current_date <= end_date:
        try:
            result = await service.sync_garmin_data(db, user_id, current_date, access_token)
            if result:
                results.append({
                    "date": current_date.isoformat(),
                    "data_id": result.id,
                    "status": "success"
                })
            else:
                errors.append({
                    "date": current_date.isoformat(),
                    "status": "failed",
                    "reason": "无数据或同步失败"
                })
        except Exception as e:
            errors.append({
                "date": current_date.isoformat(),
                "status": "error",
                "error": str(e)
            })

        current_date += timedelta(days=1)

    return {
        "message": f"批量同步完成：成功 {len(results)} 条，失败 {len(errors)} 条",
        "success_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors
    }


@router.get("/garmin/sync-status/{user_id}")
def get_sync_status(
    user_id: int,
    days: int = 30,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取Garmin数据同步状态（检查哪些日期有数据）"""
    require_self_or_admin(current_user, user_id, resource="Garmin 数据")
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    # 获取已有数据的日期
    existing_dates = db.query(GarminData.record_date).filter(
        GarminData.user_id == user_id,
        GarminData.record_date >= start_date,
        GarminData.record_date <= end_date
    ).distinct().all()

    existing_dates_set = {d[0] for d in existing_dates}

    # 生成所有日期列表
    all_dates = []
    current_date = start_date
    while current_date <= end_date:
        all_dates.append({
            "date": current_date.isoformat(),
            "has_data": current_date in existing_dates_set
        })
        current_date += timedelta(days=1)

    return {
        "user_id": user_id,
        "date_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        "total_days": len(all_dates),
        "days_with_data": len(existing_dates_set),
        "days_without_data": len(all_dates) - len(existing_dates_set),
        "coverage_percentage": round(len(existing_dates_set) / len(all_dates) * 100, 1) if all_dates else 0,
        "dates": all_dates
    }


@router.get("/garmin/me/credential-status")
def get_credential_status(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Garmin 凭证 + 同步健康度（给 UI 显示绿点/红点用）。

    返回字段：
      - bound: 是否绑定了 Garmin
      - last_sync_at: 最后一次同步时间 (ISO)
      - minutes_since_last_sync: 距今多少分钟
      - credentials_valid: 凭证是否还能登录
      - requires_mfa: 是否需要 MFA
      - last_error: 最近错误信息（脱敏）
      - error_count: 连续错误次数
      - health: "healthy" | "stale" | "error" | "unbound"
    """
    from datetime import datetime, timezone

    cred = db.query(GarminCredential).filter(
        GarminCredential.user_id == current_user.id
    ).first()

    if not cred:
        return {
            "bound": False,
            "health": "unbound",
            "last_sync_at": None,
            "minutes_since_last_sync": None,
            "credentials_valid": None,
            "requires_mfa": False,
            "last_error": None,
            "error_count": 0,
        }

    minutes_since = None
    if cred.last_sync_at:
        now = datetime.now(timezone.utc)
        last = cred.last_sync_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        minutes_since = max(0, int((now - last).total_seconds() / 60))

    # health 判定
    if not cred.credentials_valid:
        health = "error"
    elif cred.error_count >= 3:
        health = "error"
    elif minutes_since is None:
        health = "unbound"
    elif minutes_since > 60 * 12:  # 12h 没同步
        health = "stale"
    else:
        health = "healthy"

    # 脱敏错误信息（去掉密码/邮箱）
    err = cred.last_error
    if err and len(err) > 200:
        err = err[:200] + "..."

    return {
        "bound": True,
        "health": health,
        "last_sync_at": cred.last_sync_at.isoformat() if cred.last_sync_at else None,
        "minutes_since_last_sync": minutes_since,
        "credentials_valid": bool(cred.credentials_valid),
        "requires_mfa": bool(cred.requires_mfa),
        "last_error": err,
        "error_count": cred.error_count or 0,
        "sync_enabled": bool(cred.sync_enabled),
    }


@router.get("/garmin/me/sync-status")
def get_my_sync_status(
    days: int = 30,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的Garmin数据同步状态（需要登录）"""
    user_id = current_user.id
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    # 获取已有数据的日期
    existing_dates = db.query(GarminData.record_date).filter(
        GarminData.user_id == user_id,
        GarminData.record_date >= start_date,
        GarminData.record_date <= end_date
    ).distinct().all()

    existing_dates_set = {d[0] for d in existing_dates}

    # 生成所有日期列表
    all_dates = []
    current_date = start_date
    while current_date <= end_date:
        all_dates.append({
            "date": current_date.isoformat(),
            "has_data": current_date in existing_dates_set
        })
        current_date += timedelta(days=1)

    return {
        "user_id": user_id,
        "date_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        "total_days": len(all_dates),
        "days_with_data": len(existing_dates_set),
        "days_without_data": len(all_dates) - len(existing_dates_set),
        "coverage_percentage": round(len(existing_dates_set) / len(all_dates) * 100, 1) if all_dates else 0,
        "dates": all_dates
    }


@router.post("/garmin/me/sync")
async def sync_my_garmin_data(
    days: int = 1,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    使用已保存的凭据同步当前用户的 Garmin 数据

    - days: 同步最近几天的数据，默认为 1（今天）
    """
    from app.scheduler import sync_user_garmin_data

    user_id = current_user.id

    # 获取用户的 Garmin 凭据
    credential = db.query(GarminCredential).filter(
        GarminCredential.user_id == user_id
    ).first()

    if not credential:
        raise HTTPException(
            status_code=404,
            detail="未绑定 Garmin 账号，请先在设置中绑定"
        )

    if not credential.sync_enabled:
        raise HTTPException(
            status_code=400,
            detail="Garmin 同步已禁用，请在设置中启用"
        )

    if not credential.credentials_valid:
        raise HTTPException(
            status_code=400,
            detail="Garmin 凭据无效，请重新绑定账号"
        )

    if credential.requires_mfa:
        raise HTTPException(
            status_code=400,
            detail="该账号需要 MFA 验证，暂不支持自动同步"
        )

    # 解密密码
    try:
        password = garmin_credential_service.decrypt_password(credential.encrypted_password)
    except Exception as e:
        logger.error("解密用户 %s 的 Garmin 凭据失败 (%s): %r", user_id, type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="凭据解密失败，请重新绑定账号"
        )

    # 执行同步
    try:
        result = await sync_user_garmin_data(
            db,
            user_id,
            credential.garmin_email,
            password,
            days=days,
            is_cn=credential.is_cn if hasattr(credential, 'is_cn') else True
        )

        if result.get("success_count", 0) > 0:
            # Garmin 数据更新后 invalidate Twin cache，确保下次读到最新数据
            try:
                from app.twin.cache import invalidate_twin
                invalidate_twin(user_id)
            except Exception:
                pass
            return {
                "status": "success",
                "message": result.get("message", "同步成功"),
                "success_count": result.get("success_count", 0),
                "error_count": result.get("error_count", 0),
                "activities_count": result.get("activities_count", 0)
            }
        elif result.get("skipped"):
            return {
                "status": "skipped",
                "message": result.get("message", "同步被跳过")
            }
        else:
            return {
                "status": "no_data",
                "message": result.get("message", "未找到新数据")
            }

    except Exception as e:
        logger.error(f"用户 {user_id} Garmin 同步失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"同步失败: {str(e)}"
        )
