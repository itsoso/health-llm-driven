"""心率数据API"""
from datetime import date, datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models.daily_health import GarminData, HeartRateSample
from app.models.user import User, GarminCredential
from app.api.deps import get_current_user_required
from app.schemas.heart_rate import (
    DailyHeartRateResponse,
    HeartRateTrendResponse,
    HeartRateSummary,
    HeartRatePoint,
)
from app.services.auth import garmin_credential_service
from app.services.data_collection.garmin_connect import GarminConnectService, GarminAuthenticationError
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_garmin_heart_rate_data(raw_hr_data: dict) -> List[HeartRatePoint]:
    """
    解析Garmin返回的心率时间序列数据
    
    Garmin心率数据格式:
    {
        "heartRateValues": [[timestamp_ms, heart_rate], ...],
        "startTimestampGMT": ...,
        "endTimestampGMT": ...,
        ...
    }
    """
    heart_rate_points = []
    
    if not raw_hr_data or not isinstance(raw_hr_data, dict):
        return heart_rate_points
    
    hr_values = raw_hr_data.get("heartRateValues") or raw_hr_data.get("heartRateValueDescriptors")
    
    if not hr_values or not isinstance(hr_values, list):
        return heart_rate_points
    
    for item in hr_values:
        try:
            # 格式1: [timestamp_ms, heart_rate]
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                timestamp_ms = item[0]
                hr_value = item[1]
                
                if hr_value is None or hr_value <= 0:
                    continue
                
                # 转换时间戳为时间字符串
                dt = datetime.fromtimestamp(timestamp_ms / 1000)
                time_str = dt.strftime("%H:%M")
                
                heart_rate_points.append(HeartRatePoint(
                    timestamp=timestamp_ms,
                    time=time_str,
                    value=int(hr_value)
                ))
            # 格式2: {"timestamp": ..., "value": ...}
            elif isinstance(item, dict):
                timestamp_ms = item.get("timestamp") or item.get("timestampGMT") or item.get("startTimestampGMT")
                hr_value = item.get("value") or item.get("heartRate") or item.get("heartRateValue")
                
                if timestamp_ms and hr_value and hr_value > 0:
                    dt = datetime.fromtimestamp(timestamp_ms / 1000)
                    time_str = dt.strftime("%H:%M")
                    
                    heart_rate_points.append(HeartRatePoint(
                        timestamp=timestamp_ms,
                        time=time_str,
                        value=int(hr_value)
                    ))
        except (ValueError, TypeError, IndexError) as e:
            logger.debug(f"解析心率数据点失败: {e}")
            continue
    
    # 按时间排序并去重（每15分钟取一个点，减少数据量）
    if len(heart_rate_points) > 200:
        # 按时间采样，保留合理数量的点
        sampled = []
        last_time = None
        for point in sorted(heart_rate_points, key=lambda x: x.timestamp):
            current_time = point.time[:5]  # HH:MM
            if last_time is None or current_time != last_time:
                # 每分钟最多保留一个点
                sampled.append(point)
                last_time = current_time
        heart_rate_points = sampled
    
    return sorted(heart_rate_points, key=lambda x: x.timestamp)


@router.get("/me/daily/{record_date}", response_model=DailyHeartRateResponse)
async def get_my_daily_heart_rate(
    record_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取当前用户指定日期的详细心率数据
    
    - 从数据库读取心率采样数据（每15分钟一个点）
    - 包含HRV数据
    - 包含心率汇总统计
    """
    # 1. 从数据库获取汇总数据
    garmin_data = db.query(GarminData).filter(
        GarminData.user_id == current_user.id,
        GarminData.record_date == record_date
    ).first()
    
    summary = HeartRateSummary(
        record_date=record_date,
        avg_heart_rate=garmin_data.avg_heart_rate if garmin_data else None,
        max_heart_rate=garmin_data.max_heart_rate if garmin_data else None,
        min_heart_rate=garmin_data.min_heart_rate if garmin_data else None,
        resting_heart_rate=garmin_data.resting_heart_rate if garmin_data else None
    )
    
    hrv = garmin_data.hrv if garmin_data else None
    
    # 2. 从数据库获取心率采样数据
    heart_rate_samples = db.query(HeartRateSample).filter(
        HeartRateSample.user_id == current_user.id,
        HeartRateSample.record_date == record_date
    ).order_by(HeartRateSample.sample_time.asc()).all()
    
    # 转换为 HeartRatePoint 格式
    heart_rate_timeline = []
    for sample in heart_rate_samples:
        # 构造时间戳（用于排序和显示）
        sample_datetime = datetime.combine(record_date, sample.sample_time)
        timestamp_ms = int(sample_datetime.timestamp() * 1000)
        
        heart_rate_timeline.append(HeartRatePoint(
            timestamp=timestamp_ms,
            time=sample.sample_time.strftime("%H:%M"),
            value=sample.heart_rate
        ))
    
    logger.info(f"用户 {current_user.id} 获取 {record_date} 的 {len(heart_rate_timeline)} 个心率采样点")
    
    return DailyHeartRateResponse(
        record_date=record_date,
        summary=summary,
        heart_rate_timeline=heart_rate_timeline,
        hrv=hrv
    )


@router.get("/me/trend", response_model=HeartRateTrendResponse)
async def get_my_heart_rate_trend(
    days: int = Query(default=7, ge=1, le=90, description="查询天数"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取当前用户的心率趋势数据（多天）
    
    - 用于绘制趋势曲线图
    - 包含每日心率汇总和HRV数据
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)
    
    # 从数据库获取历史数据
    garmin_records = db.query(GarminData).filter(
        GarminData.user_id == current_user.id,
        GarminData.record_date >= start_date,
        GarminData.record_date <= end_date
    ).order_by(GarminData.record_date.asc()).all()
    
    daily_data = []
    hrv_data = []
    
    # 收集统计数据
    all_avg_hr = []
    all_resting_hr = []
    all_hrv = []
    all_max_hr = []
    all_min_hr = []
    
    for record in garmin_records:
        daily_data.append(HeartRateSummary(
            record_date=record.record_date,
            avg_heart_rate=record.avg_heart_rate,
            max_heart_rate=record.max_heart_rate,
            min_heart_rate=record.min_heart_rate,
            resting_heart_rate=record.resting_heart_rate
        ))
        
        if record.hrv:
            hrv_data.append({
                "date": record.record_date.isoformat(),
                "hrv": record.hrv
            })
            all_hrv.append(record.hrv)
        
        if record.avg_heart_rate:
            all_avg_hr.append(record.avg_heart_rate)
        if record.resting_heart_rate:
            all_resting_hr.append(record.resting_heart_rate)
        if record.max_heart_rate:
            all_max_hr.append(record.max_heart_rate)
        if record.min_heart_rate:
            all_min_hr.append(record.min_heart_rate)
    
    return HeartRateTrendResponse(
        days=days,
        daily_data=daily_data,
        hrv_data=hrv_data,
        avg_heart_rate=round(sum(all_avg_hr) / len(all_avg_hr), 1) if all_avg_hr else None,
        avg_resting_heart_rate=round(sum(all_resting_hr) / len(all_resting_hr), 1) if all_resting_hr else None,
        avg_hrv=round(sum(all_hrv) / len(all_hrv), 1) if all_hrv else None,
        max_heart_rate=max(all_max_hr) if all_max_hr else None,
        min_heart_rate=min(all_min_hr) if all_min_hr else None
    )


@router.get("/me/realtime/{record_date}")
async def get_realtime_heart_rate(
    record_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    实时从Garmin获取心率数据（不使用缓存）
    
    用于获取最新的心率时间序列数据
    """
    credentials = garmin_credential_service.get_decrypted_credentials(db, current_user.id)
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未配置Garmin账号，请先在设置中绑定Garmin Connect"
        )
    
    if not credentials.get("sync_enabled", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Garmin同步已禁用"
        )
    
    if not credentials.get("credentials_valid", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Garmin凭证无效，请在设置中重新配置"
        )
    
    try:
        service = GarminConnectService(credentials["email"], credentials["password"], is_cn=credentials.get("is_cn", False), user_id=current_user.id)
        raw_hr_data = service.get_heart_rates(record_date)
        
        if not raw_hr_data:
            return {
                "record_date": record_date.isoformat(),
                "message": "未获取到心率数据",
                "heart_rate_timeline": [],
                "summary": None
            }
        
        heart_rate_timeline = _parse_garmin_heart_rate_data(raw_hr_data)
        
        # 从原始数据提取汇总
        summary = {
            "resting_heart_rate": raw_hr_data.get("restingHeartRate"),
            "max_heart_rate": raw_hr_data.get("maxHeartRate"),
            "min_heart_rate": raw_hr_data.get("minHeartRate"),
        }
        
        # 计算平均心率
        if heart_rate_timeline:
            avg_hr = sum(p.value for p in heart_rate_timeline) / len(heart_rate_timeline)
            summary["avg_heart_rate"] = round(avg_hr)
        
        return {
            "record_date": record_date.isoformat(),
            "heart_rate_timeline": [p.model_dump() for p in heart_rate_timeline],
            "summary": summary,
            "data_points": len(heart_rate_timeline)
        }
    
    except GarminAuthenticationError as e:
        # 认证失败，标记凭证无效
        logger.warning(f"用户 {current_user.id} Garmin认证失败: {e}")
        garmin_credential_service.update_sync_status(
            db, current_user.id,
            credentials_valid=False,
            last_error=str(e),
            increment_error_count=True
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Garmin登录失败，请检查账号密码是否正确"
        )
    except Exception as e:
        logger.error(f"获取实时心率数据失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取心率数据失败: {str(e)}"
        )

