"""数据收集API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, timedelta
from app.database import get_db
from app.services.data_collection import DataCollectionService
from app.models.daily_health import GarminData
from app.models.user import User
from app.api.deps import get_current_user_required

router = APIRouter()


@router.post("/garmin/sync")
async def sync_garmin_data(
    user_id: int,
    target_date: date,
    access_token: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    同步Garmin数据
    
    注意：需要Garmin API的access_token
    如果使用Garmin Connect导出，可以使用手动导入接口
    """
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
    db: Session = Depends(get_db)
):
    """批量同步指定日期范围的Garmin数据"""
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
    db: Session = Depends(get_db)
):
    """获取Garmin数据同步状态（检查哪些日期有数据）"""
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
