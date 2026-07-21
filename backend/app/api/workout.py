"""运动训练记录 API"""
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
import json
import logging

from app.database import get_db
from app.models.user import User
from app.models.daily_health import WorkoutRecord, WorkoutAnalysisResult
from app.api.deps import get_current_user_required
from app.services.pre_workout_guidance import PreWorkoutGuidanceService
from app.services.post_workout_analysis import PostWorkoutAnalysisService
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
    start_date: Optional[date] = Query(default=None, description="开始日期(优先于days参数)"),
    end_date: Optional[date] = Query(default=None, description="结束日期"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的运动记录列表"""
    today = get_china_today()

    # 如果指定了日期范围，使用日期范围查询
    if start_date:
        query_start = start_date
        query_end = end_date or today
    else:
        # days=1 表示只查询今天，days=7 表示查询最近7天(包括今天)
        query_start = today - timedelta(days=days - 1) if days > 1 else today
        query_end = today

    query = db.query(WorkoutRecord).filter(
        WorkoutRecord.user_id == current_user.id,
        WorkoutRecord.workout_date >= query_start,
        WorkoutRecord.workout_date <= query_end
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
    from fastapi.responses import JSONResponse

    # 刷新数据库会话以确保获取最新数据
    db.expire_all()

    record = db.query(WorkoutRecord).filter(
        WorkoutRecord.id == workout_id,
        WorkoutRecord.user_id == current_user.id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="运动记录不存在")

    logger.info(f"用户 {current_user.id} 获取运动记录 {workout_id}, route_data存在: {bool(record.route_data)}, updated_at: {record.updated_at}")

    # 转换为响应模型，使用mode='json'确保日期和datetime字段被正确序列化
    response_data = WorkoutRecordResponse.model_validate(record).model_dump(mode='json')

    # 使用JSONResponse并设置禁用缓存的头部
    response = JSONResponse(content=response_data)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    # 添加ETag防止缓存
    updated_timestamp = record.updated_at.timestamp() if record.updated_at else (record.created_at.timestamp() if record.created_at else 0)
    response.headers["ETag"] = f'"{workout_id}-{updated_timestamp}"'

    return response


class WorkoutVoiceCoachResponse(BaseModel):
    script: str
    char_count: int
    has_analysis: bool


@router.get("/me/{workout_id}/voice-coach", response_model=WorkoutVoiceCoachResponse)
def get_workout_voice_coach(
    workout_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    获取运动记录的语音教练短稿 (150-200 字, TTS 用).

    mobile 'voice-coach 按钮' 流程:
      GET 本 API → script → cloudTts.synthesize → expo-audio 播

    fallback 优先级:
      1. 有 WorkoutAnalysisResult.aggregation → workout_voice_script 蒸
      2. 无分析但有 record → 只说"本次 X 公里 Y 分钟, 暂无分析"
    """
    from app.services.workout_coach_copy import workout_voice_script
    from app.services.workout_analysis import WorkoutAnalysisService

    record = db.query(WorkoutRecord).filter(
        WorkoutRecord.id == workout_id,
        WorkoutRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="运动记录不存在")

    analysis = db.query(WorkoutAnalysisResult).filter(
        WorkoutAnalysisResult.workout_id == workout_id,
    ).first()

    activity = WorkoutAnalysisService()._get_workout_type_name(record.workout_type or "other")
    has_analysis = bool(analysis and analysis.aggregation)
    aggregation = (analysis.aggregation if has_analysis else "") or ""

    script = workout_voice_script(
        activity=activity,
        distance_meters=record.distance_meters,
        duration_seconds=record.duration_seconds,
        aggregation=aggregation,
    )
    return WorkoutVoiceCoachResponse(
        script=script,
        char_count=len(script),
        has_analysis=has_analysis,
    )


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

    lap_data_json = None
    if workout.lap_data:
        lap_data_json = json.dumps([p.model_dump() for p in workout.lap_data])

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
        route_data=route_data_json,
        lap_data=lap_data_json
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
        raise HTTPException(status_code=404, detail="该运动记录尚未进行智能分析")

    try:
        analysis_data = json.loads(record.ai_analysis)
        return WorkoutAnalysisResponse(
            workout_id=workout_id,
            analysis_date=record.updated_at or record.created_at,
            **analysis_data
        )
    except:
        raise HTTPException(status_code=500, detail="分析数据格式错误")


@router.get("/me/{workout_id}/multi-analyses")
def get_workout_multi_analyses(
    workout_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取运动记录的所有多模型分析结果"""
    record = db.query(WorkoutRecord).filter(
        WorkoutRecord.id == workout_id,
        WorkoutRecord.user_id == current_user.id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="运动记录不存在")

    results = db.query(WorkoutAnalysisResult).filter(
        WorkoutAnalysisResult.workout_id == workout_id,
        WorkoutAnalysisResult.user_id == current_user.id,
    ).order_by(WorkoutAnalysisResult.created_at.desc()).all()

    return {
        "workout_id": workout_id,
        "count": len(results),
        "analyses": [
            {
                "id": r.id,
                "source": r.source,
                "status": r.status,
                "aggregation": r.aggregation,
                "model_results": json.loads(r.model_results) if r.model_results else [],
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in results
        ],
    }


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

                # 如果心率区间数据为空，从心率采样计算
                total_zone_seconds = sum([
                    record.hr_zone_1_seconds or 0,
                    record.hr_zone_2_seconds or 0,
                    record.hr_zone_3_seconds or 0,
                    record.hr_zone_4_seconds or 0,
                    record.hr_zone_5_seconds or 0
                ])

                if total_zone_seconds == 0:
                    logger.info(f"运动 {workout_id} 心率区间数据为空，从心率采样计算")
                    max_hr = record.max_heart_rate or 180
                    zone_seconds = sync_service._calculate_hr_zones_from_samples(hr_points, max_hr)
                    record.hr_zone_1_seconds = zone_seconds[0]
                    record.hr_zone_2_seconds = zone_seconds[1]
                    record.hr_zone_3_seconds = zone_seconds[2]
                    record.hr_zone_4_seconds = zone_seconds[3]
                    record.hr_zone_5_seconds = zone_seconds[4]
                    logger.info(f"计算得到心率区间: {zone_seconds}")

                db.commit()
                logger.info(f"用户 {current_user.id} 刷新运动 {workout_id} 心率数据: {len(hr_points)} 点")
                return {
                    "status": "success",
                    "message": f"获取到 {len(hr_points)} 个心率采样点",
                    "points_count": len(hr_points),
                    "zones_calculated": total_zone_seconds == 0
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


@router.post("/me/{workout_id}/refresh-gps")
async def refresh_workout_gps(
    workout_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """刷新运动记录的GPS路线数据"""
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

        if details_data and details_data.get("gps_data"):
            route_points = sync_service._parse_gps_route(details_data["gps_data"], record.start_time)

            if route_points:
                record.route_data = json.dumps(route_points)
                db.commit()
                logger.info(f"用户 {current_user.id} 刷新运动 {workout_id} GPS数据: {len(route_points)} 点")
                return {
                    "status": "success",
                    "message": f"获取到 {len(route_points)} 个GPS路线点",
                    "points_count": len(route_points)
                }

        return {
            "status": "no_data",
            "message": "无法获取GPS数据（可能是室内运动或Garmin未提供GPS数据）",
            "points_count": 0
        }

    except Exception as e:
        logger.error(f"刷新GPS数据失败: {e}")
        raise HTTPException(status_code=500, detail=f"刷新失败: {str(e)}")


@router.post("/me/{workout_id}/refresh-laps")
async def refresh_workout_laps(
    workout_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """刷新运动记录的计圈数据"""
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

        if details_data and details_data.get("lap_data"):
            lap_points = sync_service._parse_lap_data(details_data["lap_data"])

            if lap_points:
                record.lap_data = json.dumps(lap_points)
                db.commit()
                logger.info(f"用户 {current_user.id} 刷新运动 {workout_id} 计圈数据: {len(lap_points)} 圈")
                return {
                    "status": "success",
                    "message": f"获取到 {len(lap_points)} 圈数据",
                    "laps_count": len(lap_points)
                }

        return {
            "status": "no_data",
            "message": "无法获取计圈数据（可能Garmin未提供分段数据）",
            "laps_count": 0
        }

    except Exception as e:
        logger.error(f"刷新计圈数据失败: {e}")
        raise HTTPException(status_code=500, detail=f"刷新失败: {str(e)}")


@router.post("/me/refresh-gps-batch")
async def refresh_workout_gps_batch(
    days: int = Query(default=30, ge=1, le=365, description="刷新最近N天的记录"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """批量刷新运动记录的GPS路线数据"""
    from app.services.auth import GarminCredentialService
    from app.services.workout_sync import WorkoutSyncService
    from app.utils.timezone import get_china_today

    # 获取Garmin凭证
    cred_service = GarminCredentialService()
    credentials = cred_service.get_decrypted_credentials(db, current_user.id)

    if not credentials:
        raise HTTPException(status_code=400, detail="请先配置Garmin账号")

    # 查找需要刷新的记录（Garmin来源、有external_id、没有route_data）
    today = get_china_today()
    start_date = today - timedelta(days=days)

    records = db.query(WorkoutRecord).filter(
        WorkoutRecord.user_id == current_user.id,
        WorkoutRecord.source == "garmin",
        WorkoutRecord.external_id.isnot(None),
        WorkoutRecord.workout_date >= start_date
    ).all()

    if not records:
        return {
            "status": "no_records",
            "message": "没有需要刷新的记录",
            "refreshed_count": 0,
            "total_count": 0
        }

    try:
        sync_service = WorkoutSyncService(
            email=credentials["email"],
            password=credentials["password"],
            is_cn=credentials.get("is_cn", False),
            user_id=current_user.id
        )

        refreshed_count = 0
        failed_count = 0

        for record in records:
            try:
                # 获取活动详情
                details_data = await sync_service.get_activity_details(int(record.external_id))

                if details_data and details_data.get("gps_data"):
                    route_points = sync_service._parse_gps_route(details_data["gps_data"], record.start_time)

                    if route_points:
                        record.route_data = json.dumps(route_points)
                        refreshed_count += 1
                        logger.debug(f"刷新运动 {record.id} GPS数据: {len(route_points)} 点")

                # 添加小延迟，避免请求过快
                import asyncio
                await asyncio.sleep(0.5)

            except Exception as e:
                failed_count += 1
                logger.error(f"刷新运动 {record.id} GPS数据失败: {e}")
                continue

        db.commit()

        return {
            "status": "success",
            "message": f"成功刷新 {refreshed_count} 条记录的GPS数据",
            "refreshed_count": refreshed_count,
            "failed_count": failed_count,
            "total_count": len(records)
        }

    except Exception as e:
        logger.error(f"批量刷新GPS数据失败: {e}")
        raise HTTPException(status_code=500, detail=f"刷新失败: {str(e)}")


limiter = Limiter(key_func=get_remote_address)

@router.post("/me/sync-garmin")
@limiter.limit("5/minute")  # Garmin 运动同步每分钟最多5次
async def sync_garmin_activities(
    request: Request,
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

    # 获取同步锁（防止并发同步）
    from app.services.sync_lock import acquire_sync_lock, release_sync_lock
    if not acquire_sync_lock(db, current_user.id):
        raise HTTPException(status_code=409, detail="同步正在进行中，请稍后再试")

    try:
        # 先用 GarminConnectService 登录（优先从 DB 加载缓存的 OAuth Token）
        from app.services.data_collection.garmin_connect import GarminConnectService
        garmin_service = GarminConnectService(
            email=credentials["email"],
            password=credentials["password"],
            is_cn=credentials.get("is_cn", False),
            user_id=current_user.id
        )
        garmin_service._ensure_authenticated(db)

        # 复用已认证的 client，避免重复登录触发 Garmin 限流
        sync_service = WorkoutSyncService(
            email=credentials["email"],
            password=credentials["password"],
            is_cn=credentials.get("is_cn", False),
            user_id=current_user.id,
            client=garmin_service.client if garmin_service._authenticated else None
        )

        result = await sync_service.sync_activities(db, current_user.id, days)

        return {
            "status": "success",
            "synced_count": result["synced_count"],
            "message": f"成功同步 {result['synced_count']} 条运动记录"
        }
    except Exception as e:
        import traceback
        logger.error(f"Garmin活动同步失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")
    finally:
        release_sync_lock(db, current_user.id)


# ========== 运动前指导 ==========

@router.post("/pre-workout-guidance", response_model=Dict[str, Any])
async def get_pre_workout_guidance(
    goal_id: Optional[int] = None,
    workout_type: Optional[str] = None,
    debug: bool = Query(default=False, description="是否返回调试信息"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取运动前指导

    Args:
        goal_id: 目标ID（可选）
        workout_type: 运动类型（可选，如 RUNNING, CARDIO 等）
        debug: 是否返回调试信息，展示AI决策过程（默认False）

    Returns:
        运动前指导信息（debug模式下包含决策过程）
    """
    logger.info(f"[运动前指导API] 收到请求 - user_id={current_user.id}, goal_id={goal_id}, workout_type={workout_type}, debug={debug}")

    try:
        # 检查用户基本信息
        from app.models.user_profile import UserProfile
        profile = db.query(UserProfile).filter_by(user_id=current_user.id).first()
        logger.info(f"[运动前指导API] 用户资料: profile_exists={profile is not None}, age={profile.age if profile else None}, gender={profile.gender if profile else None}")

        # 检查健康数据
        from app.models.daily_health import GarminData
        from datetime import datetime, timedelta
        today = datetime.now().date()
        recent_data = db.query(GarminData).filter(
            GarminData.user_id == current_user.id,
            GarminData.record_date >= today - timedelta(days=7)
        ).order_by(GarminData.record_date.desc()).first()
        logger.info(f"[运动前指导API] 健康数据: data_exists={recent_data is not None}, latest_date={recent_data.record_date if recent_data else None}")

        service = PreWorkoutGuidanceService()
        guidance = await service.generate_pre_workout_guidance(
            db=db,
            user_id=current_user.id,
            goal_id=goal_id,
            workout_type=workout_type,
            debug=debug
        )

        logger.info(f"[运动前指导API] 生成成功 - success={guidance.get('success')}, has_user_status={('user_status' in guidance)}")
        return guidance
    except Exception as e:
        logger.error(f"[运动前指导API] 生成失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"生成运动前指导失败: {str(e)}"
        )


# ========== 运动后分析 ==========

@router.post("/post-workout-analysis/{workout_id}", response_model=Dict[str, Any])
async def get_post_workout_analysis(
    workout_id: int,
    force_regenerate: bool = False,
    cache_only: bool = Query(default=False, description="仅返回缓存结果，不生成新分析"),
    debug: bool = Query(default=False, description="是否返回调试信息"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取运动后分析

    Args:
        workout_id: 运动记录ID
        force_regenerate: 是否强制重新生成（默认False，使用缓存）
        cache_only: 仅返回缓存结果，如果没有缓存则返回 success=false（默认False）
        debug: 是否返回调试信息，展示AI决策过程（默认False）

    Returns:
        运动后分析结果（debug模式下包含决策过程）
    """
    try:
        # 获取运动记录
        record = db.query(WorkoutRecord).filter(
            WorkoutRecord.id == workout_id,
            WorkoutRecord.user_id == current_user.id
        ).first()

        if not record:
            raise HTTPException(status_code=404, detail="运动记录不存在")

        # 检查是否有缓存
        if record.post_workout_analysis and not force_regenerate and not debug:
            logger.info(f"用户 {current_user.id} 使用缓存的运动后分析 (workout_id={workout_id})")
            cached_analysis = json.loads(record.post_workout_analysis)
            cached_analysis["from_cache"] = True
            return cached_analysis

        # cache_only 时, 没有 post_workout_analysis 也再看一眼 WorkoutAnalysisResult
        # (W3 auto_analyze_workout 写的是 WorkoutAnalysisResult.aggregation, 不是 record.post_workout_analysis)
        # 这是历史遗留分裂, 这里桥接, 让 mobile 能渲染.
        if cache_only and not force_regenerate and not debug:
            wa = db.query(WorkoutAnalysisResult).filter(
                WorkoutAnalysisResult.workout_id == workout_id,
                WorkoutAnalysisResult.user_id == current_user.id,
            ).order_by(WorkoutAnalysisResult.id.desc()).first()
            if wa and wa.aggregation:
                logger.info(f"用户 {current_user.id} 用 WorkoutAnalysisResult 桥接 (workout_id={workout_id})")
                return {
                    "success": True,
                    "from_cache": True,
                    "has_cache": True,
                    # 直接给 markdown 字符串走 mobile 的"老格式 fallback"分支
                    "analysis": wa.aggregation,
                    "content": wa.aggregation,
                }

        # 如果仅请求缓存但没有缓存，返回无缓存响应
        if cache_only:
            logger.info(f"用户 {current_user.id} 请求缓存的运动后分析但无缓存 (workout_id={workout_id})")
            return {
                "success": False,
                "has_cache": False,
                "message": "暂无缓存的分析结果，请点击科学分析按钮生成"
            }

        # 生成新的分析
        logger.info(f"用户 {current_user.id} 生成新的运动后分析 (workout_id={workout_id}, force={force_regenerate}, debug={debug})")
        service = PostWorkoutAnalysisService()
        analysis = service.generate_post_workout_analysis(
            db=db,
            user_id=current_user.id,
            workout_id=workout_id,
            debug=debug
        )
        analysis["from_cache"] = False
        return analysis
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成运动后分析失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"生成运动后分析失败: {str(e)}"
        )


# ========== 跑后智能分析（多模型）==========

@router.post("/post-run-analyze")
async def post_run_analyze(
    format: str = Query(default="full", description="full=完整报告 brief=Siri简洁摘要"),
    workout_type: Optional[str] = Query(default=None, description="运动类型过滤，如 running/cycling"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    跑后智能分析：同步Garmin → 检测最新运动 → 多模型分析

    支持三种触发方式：
    1. AI助手对话（通过 action 系统）
    2. AI助手快捷按钮（前端直接调用）
    3. Siri快捷指令（format=brief，使用 X-API-Key 认证）
    """
    if format not in ("full", "brief"):
        format = "full"

    from app.services.post_run_analyze import PostRunAnalyzeService

    service = PostRunAnalyzeService(db)
    try:
        result = await service.analyze(
            user_id=current_user.id,
            workout_type=workout_type,
            format=format,
        )
        return result
    except Exception as e:
        logger.error(f"跑后分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@router.post("/post-run-analyze-siri")
async def post_run_analyze_siri(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """Siri 快捷指令专用端点，支持 X-API-Key 认证"""
    del x_api_key  # Shared auth validates the value; this keeps Siri clients discoverable.
    from app.services.post_run_analyze import PostRunAnalyzeService
    service = PostRunAnalyzeService(db)
    try:
        result = await service.analyze(user_id=current_user.id, format="brief")
        return result
    except Exception as e:
        logger.error(f"Siri跑后分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")
