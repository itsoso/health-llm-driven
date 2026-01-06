"""Garmin Connect集成API（使用社区库）"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, timedelta
from pydantic import BaseModel
from app.database import get_db
from app.services.data_collection.garmin_connect import GarminConnectService

router = APIRouter()


class GarminConnectCredentials(BaseModel):
    """Garmin Connect登录凭据"""
    email: str  # Garmin Connect账号邮箱
    password: str  # Garmin Connect账号密码


class GarminConnectSyncRequest(BaseModel):
    """Garmin Connect同步请求"""
    user_id: int
    target_date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


@router.post("/connect/login")
def login_garmin_connect(
    credentials: GarminConnectCredentials
):
    """
    测试Garmin Connect登录
    
    注意：这只是测试登录，不会保存凭据
    实际使用时，建议在前端处理登录，然后传递session token
    """
    try:
        service = GarminConnectService(credentials.email, credentials.password, user_id=0)
        service._ensure_authenticated()
        return {
            "status": "success",
            "message": "登录成功",
            "note": "这只是测试登录，实际使用时请在前端处理认证"
        }
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"garminconnect库未安装: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"登录失败: {str(e)}"
        )


@router.post("/connect/sync")
def sync_garmin_connect_data(
    request: GarminConnectSyncRequest,
    credentials: GarminConnectCredentials = Body(...),
    db: Session = Depends(get_db)
):
    """
    使用Garmin Connect账号同步数据
    
    需要提供Garmin Connect的邮箱和密码
    注意：建议使用环境变量或安全的凭据管理，不要在前端直接传递密码
    """
    try:
        service = GarminConnectService(credentials.email, credentials.password, user_id=request.user_id)
        
        if request.target_date:
            # 同步单日数据
            result = service.sync_daily_data(db, request.user_id, request.target_date)
            if result:
                return {
                    "status": "success",
                    "message": "同步成功",
                    "data_id": result.id,
                    "record_date": result.record_date.isoformat()
                }
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"未找到 {request.target_date} 的数据"
                )
        elif request.start_date and request.end_date:
            # 批量同步日期范围
            result = service.sync_date_range(
                db, request.user_id, request.start_date, request.end_date
            )
            return {
                "status": "success",
                "message": f"批量同步完成：成功 {result['success_count']} 条，失败 {result['error_count']} 条",
                **result
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="请提供target_date或start_date+end_date"
            )
            
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"garminconnect库未安装。请运行: pip install garminconnect"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"同步失败: {str(e)}"
        )


@router.post("/connect/sync-today")
def sync_today_garmin_data(
    user_id: int,
    credentials: GarminConnectCredentials = Body(...),
    db: Session = Depends(get_db)
):
    """同步今日Garmin数据"""
    today = date.today()
    try:
        service = GarminConnectService(credentials.email, credentials.password, user_id=user_id)
        result = service.sync_daily_data(db, user_id, today)
        if result:
            return {
                "status": "success",
                "message": "今日数据同步成功",
                "data_id": result.id,
                "record_date": result.record_date.isoformat()
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="未找到今日的数据"
            )
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"garminconnect库未安装。请运行: pip install garminconnect"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"同步失败: {str(e)}"
        )

