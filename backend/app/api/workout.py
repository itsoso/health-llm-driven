"""运动训练记录 API"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime, timedelta
from typing import List, Optional
import json
import logging

from app.database import get_db
from app.models.user import User
from app.models.daily_health import WorkoutRecord
from app.api.deps import get_current_user_required
from app.schemas.workout import (
    WorkoutRecordCreate,
    WorkoutRecordUpdate,
    WorkoutRecordResponse,
    WorkoutSummary,
    WorkoutStats,
    WorkoutChartData,
    WorkoutAnalysisResponse,
    HeartRateZoneDistribution,
    HeartRatePoint,
    PacePoint,
    ElevationPoint
)
from app.utils.timezone import get_china_today

logger = logging.getLogger(__name__)

router = APIRouter()


# ========== 工具函数 ==========

def format_pace(seconds_per_km: int) -> str:
    """将秒/公里转换为 分:秒/km 格式"""
    if not seconds_per_km:
        return "--:--"
    minutes = seconds_per_km // 60
    seconds = seconds_per_km % 60
    return f"{minutes}:{seconds:02d}/km"


def calculate_hr_zone_distribution(record: WorkoutRecord) -> Optional[HeartRateZoneDistribution]:
    """计算心率区间分布"""
    zones = [
        record.hr_zone_1_seconds or 0,
        record.hr_zone_2_seconds or 0,
        record.hr_zone_3_seconds or 0,
        record.hr_zone_4_seconds or 0,
        record.hr_zone_5_seconds or 0
    ]
    total = sum(zones)
    if total == 0:
        return None
    
    return HeartRateZoneDistribution(
        zone_1_percent=round(zones[0] / total * 100, 1),
        zone_2_percent=round(zones[1] / total * 100, 1),
        zone_3_percent=round(zones[2] / total * 100, 1),
        zone_4_percent=round(zones[3] / total * 100, 1),
        zone_5_percent=round(zones[4] / total * 100, 1)
    )


# ========== /me 端点 ==========

@router.get("/me", response_model=List[WorkoutSummary])
def get_my_workouts(
    days: int = Query(default=30, ge=1, le=365, description="获取最近N天的记录"),
    workout_type: Optional[str] = Query(default=None, description="按运动类型筛选"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的运动记录列表"""
    today = get_china_today()
    start_date = today - timedelta(days=days)
    
    query = db.query(WorkoutRecord).filter(
        WorkoutRecord.user_id == current_user.id,
        WorkoutRecord.workout_date >= start_date
    )
    
    if workout_type:
        query = query.filter(WorkoutRecord.workout_type == workout_type)
    
    records = query.order_by(WorkoutRecord.workout_date.desc(), WorkoutRecord.start_time.desc()).all()
    
    return [
        WorkoutSummary(
            id=r.id,
            workout_date=r.workout_date,
            workout_type=r.workout_type,
            workout_name=r.workout_name,
            duration_seconds=r.duration_seconds,
            distance_meters=r.distance_meters,
            avg_heart_rate=r.avg_heart_rate,
            calories=r.calories,
            feeling=r.feeling,
            has_ai_analysis=r.ai_analysis is not None
        )
        for r in records
    ]


@router.get("/me/stats", response_model=WorkoutStats)
def get_my_workout_stats(
    days: int = Query(default=30, ge=1, le=365, description="统计最近N天"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的运动统计"""
    today = get_china_today()
    start_date = today - timedelta(days=days)
    
    records = db.query(WorkoutRecord).filter(
        WorkoutRecord.user_id == current_user.id,
        WorkoutRecord.workout_date >= start_date
    ).all()
    
    if not records:
        return WorkoutStats(
            total_workouts=0,
            total_duration_minutes=0,
            total_distance_km=0,
            total_calories=0,
            avg_duration_minutes=0,
            avg_distance_km=0,
            workouts_by_type={},
            recent_trend="stable"
        )
    
    total_duration = sum(r.duration_seconds or 0 for r in records)
    total_distance = sum(r.distance_meters or 0 for r in records)
    total_calories = sum(r.calories or 0 for r in records)
    
    # 按类型统计
    workouts_by_type = {}
    for r in records:
        wtype = r.workout_type
        if wtype not in workouts_by_type:
            workouts_by_type[wtype] = {"count": 0, "duration_minutes": 0}
        workouts_by_type[wtype]["count"] += 1
        workouts_by_type[wtype]["duration_minutes"] += (r.duration_seconds or 0) // 60
    
    # 分析趋势（对比前后两周）
    mid_date = start_date + timedelta(days=days // 2)
    first_half = [r for r in records if r.workout_date < mid_date]
    second_half = [r for r in records if r.workout_date >= mid_date]
    
    first_count = len(first_half)
    second_count = len(second_half)
    
    if second_count > first_count * 1.2:
        trend = "improving"
    elif second_count < first_count * 0.8:
        trend = "declining"
    else:
        trend = "stable"
    
    return WorkoutStats(
        total_workouts=len(records),
        total_duration_minutes=total_duration // 60,
        total_distance_km=round(total_distance / 1000, 2),
        total_calories=total_calories,
        avg_duration_minutes=round(total_duration / 60 / len(records), 1),
        avg_distance_km=round(total_distance / 1000 / len(records), 2) if total_distance > 0 else 0,
        workouts_by_type=workouts_by_type,
        recent_trend=trend
    )


@router.get("/me/{workout_id}", response_model=WorkoutRecordResponse)
def get_my_workout(
    workout_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取单条运动记录详情"""
    record = db.query(WorkoutRecord).filter(
        WorkoutRecord.id == workout_id,
        WorkoutRecord.user_id == current_user.id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="运动记录不存在")
    
    return record


@router.get("/me/{workout_id}/chart", response_model=WorkoutChartData)
def get_workout_chart_data(
    workout_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取运动记录的图表数据"""
    record = db.query(WorkoutRecord).filter(
        WorkoutRecord.id == workout_id,
        WorkoutRecord.user_id == current_user.id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="运动记录不存在")
    
    # 解析时间序列数据
    heart_rate_timeline = None
    if record.heart_rate_data:
        try:
            hr_data = json.loads(record.heart_rate_data)
            heart_rate_timeline = [HeartRatePoint(**p) for p in hr_data]
        except:
            pass
    
    pace_timeline = None
    if record.pace_data:
        try:
            pace = json.loads(record.pace_data)
            pace_timeline = [PacePoint(**p) for p in pace]
        except:
            pass
    
    elevation_timeline = None
    if record.elevation_data:
        try:
            elev = json.loads(record.elevation_data)
            elevation_timeline = [ElevationPoint(**p) for p in elev]
        except:
            pass
    
    return WorkoutChartData(
        workout_id=record.id,
        workout_type=record.workout_type,
        duration_seconds=record.duration_seconds or 0,
        heart_rate_timeline=heart_rate_timeline,
        heart_rate_zones=calculate_hr_zone_distribution(record),
        pace_timeline=pace_timeline,
        elevation_timeline=elevation_timeline,
        avg_heart_rate=record.avg_heart_rate,
        max_heart_rate=record.max_heart_rate,
        avg_pace_display=format_pace(record.avg_pace_seconds_per_km) if record.avg_pace_seconds_per_km else None,
        total_distance_km=round(record.distance_meters / 1000, 2) if record.distance_meters else None,
        calories=record.calories
    )


@router.post("/me", response_model=WorkoutRecordResponse, status_code=status.HTTP_201_CREATED)
def create_workout(
    workout: WorkoutRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建运动记录"""
    # 转换时间序列数据为JSON
    hr_data_json = None
    if workout.heart_rate_data:
        hr_data_json = json.dumps([p.model_dump() for p in workout.heart_rate_data])
    
    pace_data_json = None
    if workout.pace_data:
        pace_data_json = json.dumps([p.model_dump() for p in workout.pace_data])
    
    elevation_data_json = None
    if workout.elevation_data:
        elevation_data_json = json.dumps([p.model_dump() for p in workout.elevation_data])
    
    route_data_json = None
    if workout.route_data:
        route_data_json = json.dumps([p.model_dump() for p in workout.route_data])
    
    db_record = WorkoutRecord(
        user_id=current_user.id,
        workout_date=workout.workout_date,
        start_time=workout.start_time,
        end_time=workout.end_time,
        workout_type=workout.workout_type.value,
        workout_name=workout.workout_name,
        duration_seconds=workout.duration_seconds,
        moving_duration_seconds=workout.moving_duration_seconds,
        distance_meters=workout.distance_meters,
        avg_pace_seconds_per_km=workout.avg_pace_seconds_per_km,
        best_pace_seconds_per_km=workout.best_pace_seconds_per_km,
        avg_speed_kmh=workout.avg_speed_kmh,
        max_speed_kmh=workout.max_speed_kmh,
        avg_heart_rate=workout.avg_heart_rate,
        max_heart_rate=workout.max_heart_rate,
        min_heart_rate=workout.min_heart_rate,
        hr_zone_1_seconds=workout.hr_zone_1_seconds,
        hr_zone_2_seconds=workout.hr_zone_2_seconds,
        hr_zone_3_seconds=workout.hr_zone_3_seconds,
        hr_zone_4_seconds=workout.hr_zone_4_seconds,
        hr_zone_5_seconds=workout.hr_zone_5_seconds,
        calories=workout.calories,
        active_calories=workout.active_calories,
        steps=workout.steps,
        avg_stride_length_cm=workout.avg_stride_length_cm,
        avg_cadence=workout.avg_cadence,
        max_cadence=workout.max_cadence,
        avg_power_watts=workout.avg_power_watts,
        max_power_watts=workout.max_power_watts,
        normalized_power_watts=workout.normalized_power_watts,
        pool_length_meters=workout.pool_length_meters,
        laps=workout.laps,
        strokes=workout.strokes,
        avg_strokes_per_length=workout.avg_strokes_per_length,
        swim_style=workout.swim_style.value if workout.swim_style else None,
        elevation_gain_meters=workout.elevation_gain_meters,
        elevation_loss_meters=workout.elevation_loss_meters,
        min_elevation_meters=workout.min_elevation_meters,
        max_elevation_meters=workout.max_elevation_meters,
        training_effect_aerobic=workout.training_effect_aerobic,
        training_effect_anaerobic=workout.training_effect_anaerobic,
        vo2max=workout.vo2max,
        training_load=workout.training_load,
        perceived_exertion=workout.perceived_exertion,
        feeling=workout.feeling.value if workout.feeling else None,
        notes=workout.notes,
        source="manual",
        heart_rate_data=hr_data_json,
        pace_data=pace_data_json,
        elevation_data=elevation_data_json,
        route_data=route_data_json
    )
    
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    
    logger.info(f"用户 {current_user.id} 创建运动记录: {db_record.workout_type} on {db_record.workout_date}")
    
    return db_record


@router.put("/me/{workout_id}", response_model=WorkoutRecordResponse)
def update_workout(
    workout_id: int,
    update_data: WorkoutRecordUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新运动记录"""
    record = db.query(WorkoutRecord).filter(
        WorkoutRecord.id == workout_id,
        WorkoutRecord.user_id == current_user.id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="运动记录不存在")
    
    if update_data.workout_name is not None:
        record.workout_name = update_data.workout_name
    if update_data.perceived_exertion is not None:
        record.perceived_exertion = update_data.perceived_exertion
    if update_data.feeling is not None:
        record.feeling = update_data.feeling.value
    if update_data.notes is not None:
        record.notes = update_data.notes
    
    db.commit()
    db.refresh(record)
    
    return record


@router.delete("/me/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workout(
    workout_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除运动记录"""
    record = db.query(WorkoutRecord).filter(
        WorkoutRecord.id == workout_id,
        WorkoutRecord.user_id == current_user.id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="运动记录不存在")
    
    db.delete(record)
    db.commit()
    
    logger.info(f"用户 {current_user.id} 删除运动记录 ID: {workout_id}")


@router.post("/me/{workout_id}/analyze", response_model=WorkoutAnalysisResponse)
async def analyze_workout(
    workout_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """对运动记录进行AI分析"""
    record = db.query(WorkoutRecord).filter(
        WorkoutRecord.id == workout_id,
        WorkoutRecord.user_id == current_user.id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="运动记录不存在")
    
    # 导入分析服务
    from app.services.workout_analysis import WorkoutAnalysisService
    
    analysis_service = WorkoutAnalysisService()
    
    # 获取历史记录用于对比
    history = db.query(WorkoutRecord).filter(
        WorkoutRecord.user_id == current_user.id,
        WorkoutRecord.workout_type == record.workout_type,
        WorkoutRecord.id != record.id
    ).order_by(WorkoutRecord.workout_date.desc()).limit(10).all()
    
    try:
        analysis_result = await analysis_service.analyze_workout(record, history)
        
        # 保存分析结果到数据库
        record.ai_analysis = json.dumps(analysis_result, ensure_ascii=False)
        db.commit()
        
        return WorkoutAnalysisResponse(
            workout_id=workout_id,
            analysis_date=datetime.now(),
            **analysis_result
        )
    except Exception as e:
        logger.error(f"运动分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@router.get("/me/{workout_id}/analysis", response_model=WorkoutAnalysisResponse)
def get_workout_analysis(
    workout_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取已保存的运动分析结果"""
    record = db.query(WorkoutRecord).filter(
        WorkoutRecord.id == workout_id,
        WorkoutRecord.user_id == current_user.id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="运动记录不存在")
    
    if not record.ai_analysis:
        raise HTTPException(status_code=404, detail="该运动记录尚未进行AI分析")
    
    try:
        analysis_data = json.loads(record.ai_analysis)
        return WorkoutAnalysisResponse(
            workout_id=workout_id,
            analysis_date=record.updated_at or record.created_at,
            **analysis_data
        )
    except:
        raise HTTPException(status_code=500, detail="分析数据格式错误")


# ========== Garmin 同步 ==========

@router.post("/me/{workout_id}/refresh-hr")
async def refresh_workout_heart_rate(
    workout_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """刷新运动记录的心率数据"""
    record = db.query(WorkoutRecord).filter(
        WorkoutRecord.id == workout_id,
        WorkoutRecord.user_id == current_user.id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="运动记录不存在")
    
    if not record.external_id or record.source != "garmin":
        raise HTTPException(status_code=400, detail="仅支持 Garmin 同步的运动记录")
    
    from app.services.auth import GarminCredentialService
    from app.services.workout_sync import WorkoutSyncService
    
    # 获取Garmin凭证
    cred_service = GarminCredentialService()
    credentials = cred_service.get_decrypted_credentials(db, current_user.id)
    
    if not credentials:
        raise HTTPException(status_code=400, detail="请先配置Garmin账号")
    
    try:
        sync_service = WorkoutSyncService(
            email=credentials["email"],
            password=credentials["password"],
            is_cn=credentials.get("is_cn", False),
            user_id=current_user.id
        )
        
        # 获取活动详情
        details_data = await sync_service.get_activity_details(int(record.external_id))
        
        if details_data and details_data.get("heart_rate_data"):
            duration = record.duration_seconds or 3600
            hr_points = sync_service._parse_heart_rate_samples(details_data["heart_rate_data"], duration)
            
            if hr_points:
                record.heart_rate_data = json.dumps(hr_points)
                db.commit()
                logger.info(f"用户 {current_user.id} 刷新运动 {workout_id} 心率数据: {len(hr_points)} 点")
                return {
                    "status": "success",
                    "message": f"获取到 {len(hr_points)} 个心率采样点",
                    "points_count": len(hr_points)
                }
        
        # 如果无法获取详细心率，使用模拟曲线
        if record.avg_heart_rate and record.duration_seconds:
            hr_points = sync_service._generate_simulated_hr_curve(
                record.avg_heart_rate,
                record.max_heart_rate,
                record.duration_seconds
            )
            if hr_points:
                record.heart_rate_data = json.dumps(hr_points)
                db.commit()
                return {
                    "status": "simulated",
                    "message": f"使用模拟心率曲线 ({len(hr_points)} 点)",
                    "points_count": len(hr_points)
                }
        
        return {
            "status": "no_data",
            "message": "无法获取心率数据",
            "points_count": 0
        }
        
    except Exception as e:
        logger.error(f"刷新心率数据失败: {e}")
        raise HTTPException(status_code=500, detail=f"刷新失败: {str(e)}")


@router.post("/me/sync-garmin")
async def sync_garmin_activities(
    days: int = Query(default=7, ge=1, le=30, description="同步最近N天的活动"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """从Garmin同步运动活动"""
    from app.services.auth import GarminCredentialService
    from app.services.workout_sync import WorkoutSyncService
    
    # 获取Garmin凭证
    cred_service = GarminCredentialService()
    credentials = cred_service.get_decrypted_credentials(db, current_user.id)
    
    if not credentials:
        raise HTTPException(
            status_code=400, 
            detail="请先在设置中配置Garmin账号"
        )
    
    try:
        sync_service = WorkoutSyncService(
            email=credentials["email"],
            password=credentials["password"],
            is_cn=credentials.get("is_cn", False),
            user_id=current_user.id
        )
        
        result = await sync_service.sync_activities(db, current_user.id, days)
        
        return {
            "status": "success",
            "synced_count": result["synced_count"],
            "message": f"成功同步 {result['synced_count']} 条运动记录"
        }
    except Exception as e:
        logger.error(f"Garmin活动同步失败: {e}")
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")

