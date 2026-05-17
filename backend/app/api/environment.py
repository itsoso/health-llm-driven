"""
环境数据 API

提供天气、空气质量和综合健康建议接口
"""

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field
import logging

from app.database import get_db
from app.models.user import User
from app.models.user_profile import UserProfile
from app.api.deps import get_current_user_required
from app.services.environment import weather_service, air_quality_service, environment_advisor
from app.services.location_resolver import resolve_effective_location

router = APIRouter(prefix="/environment", tags=["environment"])
logger = logging.getLogger(__name__)


def _resolve_location(db: Session, user_id: int) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """位置统一入口 — 用 location_resolver 单一事实之主.

    返回 (lat, lon, city). 调用方先用 lat/lon (区/县精度), 没有再 fallback city.
    manual 模式只返回 city, lat/lon=None — 因 manual_city 是字符串无对应坐标.
    """
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    loc = resolve_effective_location(profile)
    return loc["lat"], loc["lon"], loc["city"]


class EnvironmentQuery(BaseModel):
    """环境查询参数"""
    city: Optional[str] = Field(None, description="城市名称")
    lat: Optional[float] = Field(None, description="纬度")
    lon: Optional[float] = Field(None, description="经度")


@router.get("/weather", summary="获取当前天气")
async def get_weather(
    city: Optional[str] = Query(None, description="城市名称，如：北京"),
    lat: Optional[float] = Query(None, description="纬度"),
    lon: Optional[float] = Query(None, description="经度"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取当前天气数据

    支持通过城市名或经纬度查询
    """
    # 如果没有提供位置，智能解析用户当前城市 — 天气要市级, 不是区级
    if not city and (lat is None or lon is None):
        lat, lon, city = _resolve_location(db, current_user.id)
        # lat/lon 优先 (区/县精度); 没有走 city; 还是 None 让 service 自己 fallback
        if lat is not None and lon is not None:
            city = None  # 有坐标就清掉 city, 避免 service 再做 city→coord 反查

    weather = await weather_service.get_current_weather(city, lat, lon)
    exercise_advice = weather_service.get_exercise_advice(weather)

    return {
        "weather": weather,
        "exercise_advice": exercise_advice
    }


@router.get("/weather/forecast", summary="获取天气预报")
async def get_weather_forecast(
    city: Optional[str] = Query(None, description="城市名称"),
    lat: Optional[float] = Query(None, description="纬度"),
    lon: Optional[float] = Query(None, description="经度"),
    days: int = Query(3, ge=1, le=7, description="预报天数"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取未来几天的天气预报
    """
    if not city and (lat is None or lon is None):
        lat, lon, city = _resolve_location(db, current_user.id)
        if lat is not None and lon is not None:
            city = None

    forecast = await weather_service.get_weather_forecast(city, lat, lon, days)
    return forecast


@router.get("/air-quality", summary="获取空气质量")
async def get_air_quality(
    city: Optional[str] = Query(None, description="城市名称"),
    lat: Optional[float] = Query(None, description="纬度"),
    lon: Optional[float] = Query(None, description="经度"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取当前空气质量数据

    包含 AQI、PM2.5、PM10 等指标及健康建议
    """
    if not city and (lat is None or lon is None):
        # 优先用 profile 里 GPS 实测坐标 (区/县精度); 没有再 fallback 城市字典
        lat, lon, city = _resolve_location(db, current_user.id)
        if lat is not None and lon is not None:
            city = None

    # 优先使用和风天气空气质量API
    aqi = await weather_service.get_air_quality(city, lat, lon)
    if not aqi.get("available"):
        # 回退到 AQICN / Open-Meteo
        aqi = await air_quality_service.get_air_quality(city, lat, lon)
    return aqi


@router.get("/advice", summary="获取综合环境健康建议")
async def get_environment_advice(
    city: Optional[str] = Query(None, description="城市名称"),
    lat: Optional[float] = Query(None, description="纬度"),
    lon: Optional[float] = Query(None, description="经度"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取综合环境健康建议

    结合天气、空气质量和用户健康状况，生成个性化建议
    """
    # 获取用户画像中的城市和健康状况
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    if not city and (lat is None or lon is None):
        lat, lon, city = _resolve_location(db, current_user.id)
        if lat is not None and lon is not None:
            city = None

    # 获取用户的慢性病列表
    user_conditions = []
    if profile:
        user_conditions = profile.chronic_conditions or []

    advice = await environment_advisor.get_comprehensive_advice(
        city=city,
        lat=lat,
        lon=lon,
        user_conditions=user_conditions
    )

    return advice


@router.get("/morning-briefing", summary="获取早间健康简报")
async def get_morning_briefing(
    city: Optional[str] = Query(None, description="城市名称"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取早间健康简报

    适合每天早上查看的简洁环境健康信息
    """
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    if not city:
        _, _, city = _resolve_location(db, current_user.id)

    user_conditions = []
    if profile:
        user_conditions = profile.chronic_conditions or []

    briefing = await environment_advisor.get_morning_briefing(
        city=city,
        user_conditions=user_conditions
    )

    return briefing


@router.get("/exercise-suitability", summary="获取户外运动适宜度")
async def get_exercise_suitability(
    city: Optional[str] = Query(None, description="城市名称"),
    lat: Optional[float] = Query(None, description="纬度"),
    lon: Optional[float] = Query(None, description="经度"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取户外运动适宜度评估

    返回综合评分和推荐活动
    """
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    if not city and (lat is None or lon is None):
        lat, lon, city = _resolve_location(db, current_user.id)
        if lat is not None and lon is not None:
            city = None

    user_conditions = profile.chronic_conditions if profile else []

    advice = await environment_advisor.get_comprehensive_advice(
        city=city,
        lat=lat,
        lon=lon,
        user_conditions=user_conditions
    )

    return {
        "score": advice["exercise"]["score"],
        "status": advice["exercise"]["status"],
        "outdoor_suitable": advice["exercise"]["outdoor_suitable"],
        "recommended_activities": advice["exercise"]["recommended_activities"],
        "weather_summary": advice["weather"].get("summary", ""),
        "aqi": advice["air_quality"].get("aqi"),
        "aqi_description": advice["air_quality"].get("description"),
        "advices": advice["advices"][:3],
        "warnings": advice["warnings"]
    }
