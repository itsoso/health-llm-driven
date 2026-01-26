"""用户 API Key API - 允许外部系统访问用户健康数据和写入建议"""
import hashlib
import secrets
import logging
from datetime import datetime, date, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User
from app.models.user_api_key import UserApiKey
from app.models.user_profile import UserProfile
from app.models.external_recommendation import ExternalRecommendation
from app.models.daily_health import GarminData, WorkoutRecord, DietRecord, SupplementIntake
from app.api.deps import get_current_user_required
from app.utils.timezone import CHINA_TIMEZONE

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Schemas ====================

class ApiKeyCreate(BaseModel):
    """创建 API Key 请求"""
    name: str
    scopes: str = "read,write"


class ApiKeyResponse(BaseModel):
    """API Key 响应"""
    id: int
    name: str
    api_key: Optional[str] = None  # 只在创建时返回
    scopes: str
    is_active: bool
    last_used_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RecommendationCreate(BaseModel):
    """创建外部建议请求"""
    category: str  # exercise, diet, sleep, supplement, general
    title: str
    content: str
    source_name: str
    recommendation_date: Optional[date] = None


class RecommendationResponse(BaseModel):
    """外部建议响应"""
    id: int
    category: str
    title: str
    content: str
    source_name: str
    recommendation_date: date
    created_at: datetime

    class Config:
        from_attributes = True


class HealthDataResponse(BaseModel):
    """健康数据响应"""
    user_name: str
    date_range: dict
    data: List[dict]


# ==================== 工具函数 ====================

def hash_api_key(key: str) -> str:
    """对 API Key 进行 SHA256 哈希"""
    return hashlib.sha256(key.encode()).hexdigest()


def check_scope(api_key: UserApiKey, required_scope: str) -> bool:
    """检查 API Key 是否有指定权限"""
    if not api_key.scopes:
        return False
    scopes = api_key.scopes.split(",")
    return required_scope in scopes


# ==================== API Key 验证依赖 ====================

async def verify_user_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
) -> UserApiKey:
    """验证用户 API Key"""
    key_hash = hash_api_key(x_api_key)
    api_key = db.query(UserApiKey).filter(
        UserApiKey.api_key == key_hash,
        UserApiKey.is_active == True
    ).first()

    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    # 更新最后使用时间
    api_key.last_used_at = datetime.now(CHINA_TIMEZONE)
    db.commit()

    return api_key


# ==================== 用户管理自己的 API Key ====================

@router.get("/user-api-keys", response_model=List[ApiKeyResponse])
async def list_user_api_keys(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """列出当前用户的所有 API Key"""
    keys = db.query(UserApiKey).filter(
        UserApiKey.user_id == current_user.id
    ).order_by(desc(UserApiKey.created_at)).all()

    return [
        {
            "id": k.id,
            "name": k.name,
            "api_key": None,  # 不返回密钥
            "scopes": k.scopes,
            "is_active": k.is_active,
            "last_used_at": k.last_used_at,
            "created_at": k.created_at,
        }
        for k in keys
    ]


@router.post("/user-api-keys", response_model=ApiKeyResponse)
async def create_user_api_key(
    key_data: ApiKeyCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建新的 API Key"""
    # 限制每个用户最多 5 个 API Key
    existing_count = db.query(UserApiKey).filter(
        UserApiKey.user_id == current_user.id,
        UserApiKey.is_active == True
    ).count()

    if existing_count >= 5:
        raise HTTPException(status_code=400, detail="每个用户最多创建 5 个 API Key")

    # 生成随机 API Key
    raw_key = secrets.token_urlsafe(32)
    key_hash = hash_api_key(raw_key)

    db_key = UserApiKey(
        user_id=current_user.id,
        name=key_data.name,
        api_key=key_hash,
        scopes=key_data.scopes,
    )
    db.add(db_key)
    db.commit()
    db.refresh(db_key)

    logger.info(f"用户 {current_user.id} 创建了 API Key: {key_data.name}")

    # 只在创建时返回原始 key
    return {
        "id": db_key.id,
        "name": db_key.name,
        "api_key": raw_key,  # 原始 key，只返回一次
        "scopes": db_key.scopes,
        "is_active": db_key.is_active,
        "last_used_at": db_key.last_used_at,
        "created_at": db_key.created_at,
    }


@router.delete("/user-api-keys/{key_id}")
async def delete_user_api_key(
    key_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除 API Key"""
    key = db.query(UserApiKey).filter(
        UserApiKey.id == key_id,
        UserApiKey.user_id == current_user.id
    ).first()

    if not key:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    db.delete(key)
    db.commit()

    logger.info(f"用户 {current_user.id} 删除了 API Key: {key.name}")

    return {"ok": True, "message": "API Key 已删除"}


# ==================== 外部系统接口 (通过 X-API-Key 认证) ====================

def _build_user_profile_for_external(profile: UserProfile) -> dict:
    """
    根据隐私设置构建对外公开的用户画像信息

    Args:
        profile: UserProfile 对象

    Returns:
        符合隐私设置的用户画像字典
    """
    if not profile:
        return None

    # 获取隐私设置，默认全部公开
    privacy = profile.privacy_settings or {
        "weight": True, "height": True, "age": True,
        "gender": True, "city": True, "location": True
    }

    result = {}

    # 根据隐私设置决定返回哪些字段
    if privacy.get("weight", True) and profile.current_weight_kg:
        result["weight_kg"] = profile.current_weight_kg

    if privacy.get("height", True) and profile.height_cm:
        result["height_cm"] = profile.height_cm

    if privacy.get("age", True) and profile.age:
        result["age"] = profile.age

    if privacy.get("gender", True) and profile.gender:
        result["gender"] = profile.gender

    # BMI 需要身高和体重都公开
    if privacy.get("weight", True) and privacy.get("height", True) and profile.bmi:
        result["bmi"] = profile.bmi
        result["bmi_category"] = profile.bmi_category

    if privacy.get("city", True) and profile.city:
        result["city"] = profile.city

    # IP 定位信息
    if privacy.get("location", True):
        if profile.detected_city or profile.detected_region or profile.detected_country:
            result["detected_location"] = {
                "city": profile.detected_city,
                "region": profile.detected_region,
                "country": profile.detected_country
            }

    return result if result else None


@router.get("/external/health-data")
async def get_external_health_data(
    date_param: Optional[date] = Query(None, alias="date"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    api_key: UserApiKey = Depends(verify_user_api_key),
    db: Session = Depends(get_db)
):
    """
    外部系统读取用户健康数据（最近 30 天）

    - 使用 X-API-Key 头部认证
    - 支持单日查询 (?date=2024-01-25) 或日期范围 (?start_date=...&end_date=...)
    - 最多只能查询最近 30 天的数据
    - 返回用户画像信息（根据用户隐私设置）
    """
    if not check_scope(api_key, "read"):
        raise HTTPException(status_code=403, detail="API Key 没有读取权限")

    user = db.query(User).filter(User.id == api_key.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 获取用户画像
    profile = db.query(UserProfile).filter(UserProfile.user_id == api_key.user_id).first()

    # 处理日期参数
    today = date.today()
    min_date = today - timedelta(days=30)

    if date_param:
        start_date = date_param
        end_date = date_param
    elif not start_date:
        start_date = today - timedelta(days=7)
        end_date = today

    if not end_date:
        end_date = today

    # 验证日期范围
    if start_date < min_date:
        raise HTTPException(status_code=400, detail="只能查询最近 30 天的数据")
    if (end_date - start_date).days > 30:
        raise HTTPException(status_code=400, detail="日期范围不能超过 30 天")

    # 查询数据
    result_data = []
    current_date = start_date
    while current_date <= end_date:
        day_data = {"date": current_date.isoformat()}

        # Garmin 数据
        garmin = db.query(GarminData).filter(
            GarminData.user_id == api_key.user_id,
            GarminData.record_date == current_date
        ).first()

        if garmin:
            day_data["garmin"] = {
                "steps": garmin.steps,
                "sleep_score": garmin.sleep_score,
                "sleep_duration_hours": round(garmin.total_sleep_duration / 60, 1) if garmin.total_sleep_duration else None,
                "deep_sleep_hours": round(garmin.deep_sleep_duration / 60, 2) if garmin.deep_sleep_duration else None,
                "light_sleep_hours": round(garmin.light_sleep_duration / 60, 2) if garmin.light_sleep_duration else None,
                "rem_sleep_hours": round(garmin.rem_sleep_duration / 60, 2) if garmin.rem_sleep_duration else None,
                "heart_rate_avg": garmin.avg_heart_rate,
                "heart_rate_resting": garmin.resting_heart_rate,
                "heart_rate_max": garmin.max_heart_rate,
                "hrv": garmin.hrv_7day_avg,
                "body_battery_high": garmin.body_battery_charged,
                "body_battery_low": garmin.body_battery_drained,
                "stress_avg": garmin.stress_level,
                "calories_total": garmin.calories_burned,
                "calories_active": garmin.active_calories,
                "active_minutes": garmin.moderate_intensity_minutes,
                "floors_climbed": garmin.floors_climbed,
                "spo2_avg": garmin.spo2_avg,
            }

        # 运动记录
        workouts = db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == api_key.user_id,
            WorkoutRecord.start_time >= datetime.combine(current_date, datetime.min.time()),
            WorkoutRecord.start_time < datetime.combine(current_date + timedelta(days=1), datetime.min.time())
        ).all()

        if workouts:
            day_data["workouts"] = [
                {
                    "type": w.workout_type,
                    "duration_minutes": round(w.duration_seconds / 60) if w.duration_seconds else None,
                    "distance_km": round(w.distance_meters / 1000, 2) if w.distance_meters else None,
                    "calories": w.calories,
                    "avg_heart_rate": w.avg_heart_rate,
                    "max_heart_rate": w.max_heart_rate,
                }
                for w in workouts
            ]

        # 饮食记录
        diets = db.query(DietRecord).filter(
            DietRecord.user_id == api_key.user_id,
            DietRecord.record_date == current_date
        ).all()

        if diets:
            total_calories = sum(d.calories or 0 for d in diets)
            total_protein = sum(d.protein or 0 for d in diets)
            total_carbs = sum(d.carbs or 0 for d in diets)
            total_fat = sum(d.fat or 0 for d in diets)

            day_data["diet"] = {
                "total_calories": total_calories,
                "total_protein_g": total_protein,
                "total_carbs_g": total_carbs,
                "total_fat_g": total_fat,
                "meals": [
                    {
                        "meal_type": d.meal_type,
                        "food_items": d.food_items,
                        "calories": d.calories,
                    }
                    for d in diets
                ]
            }

        # 补剂记录
        supplements = db.query(SupplementIntake).filter(
            SupplementIntake.user_id == api_key.user_id,
            SupplementIntake.record_date == current_date
        ).all()

        if supplements:
            day_data["supplements"] = [
                {
                    "name": s.supplement_name,
                    "dosage": s.dosage,
                    "unit": s.unit,
                }
                for s in supplements
            ]

        result_data.append(day_data)
        current_date += timedelta(days=1)

    # 构建响应
    response = {
        "user_name": user.name,
        "date_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "data": result_data,
    }

    # 添加用户画像（如果有且有公开字段）
    user_profile_data = _build_user_profile_for_external(profile)
    if user_profile_data:
        response["user_profile"] = user_profile_data

    return response


@router.post("/external/recommendations")
async def create_external_recommendation(
    rec: RecommendationCreate,
    api_key: UserApiKey = Depends(verify_user_api_key),
    db: Session = Depends(get_db)
):
    """
    外部系统写入健康建议

    - 使用 X-API-Key 头部认证
    - category: exercise, diet, sleep, supplement, general
    """
    if not check_scope(api_key, "write"):
        raise HTTPException(status_code=403, detail="API Key 没有写入权限")

    # 验证 category
    valid_categories = ["exercise", "diet", "sleep", "supplement", "general"]
    if rec.category not in valid_categories:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 category，必须是: {', '.join(valid_categories)}"
        )

    rec_date = rec.recommendation_date or date.today()

    # 检查是否已存在相同来源、相同日期、相同类别的建议
    existing = db.query(ExternalRecommendation).filter(
        ExternalRecommendation.user_id == api_key.user_id,
        ExternalRecommendation.source_name == rec.source_name,
        ExternalRecommendation.recommendation_date == rec_date,
        ExternalRecommendation.category == rec.category
    ).first()

    if existing:
        # 更新现有建议
        existing.title = rec.title
        existing.content = rec.content
        db.commit()
        logger.info(f"更新外部建议: user={api_key.user_id}, source={rec.source_name}, category={rec.category}")
        return {"id": existing.id, "message": "建议已更新"}

    # 创建新建议
    db_rec = ExternalRecommendation(
        user_id=api_key.user_id,
        category=rec.category,
        title=rec.title,
        content=rec.content,
        source_name=rec.source_name,
        source_api_key_id=api_key.id,
        recommendation_date=rec_date,
    )
    db.add(db_rec)
    db.commit()
    db.refresh(db_rec)

    logger.info(f"创建外部建议: user={api_key.user_id}, source={rec.source_name}, category={rec.category}")

    return {"id": db_rec.id, "message": "建议已保存"}


# ==================== 用户查看外部建议 ====================

@router.get("/external-recommendations")
async def list_external_recommendations(
    date_param: Optional[date] = Query(None, alias="date"),
    start_date: Optional[date] = Query(None, description="开始日期（包含），用于日期范围筛选"),
    end_date: Optional[date] = Query(None, description="结束日期（包含），用于日期范围筛选"),
    category: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    limit: int = Query(None, ge=1, le=100),  # 保留兼容旧参数
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的外部建议（支持分页和日期范围筛选）"""
    query = db.query(ExternalRecommendation).filter(
        ExternalRecommendation.user_id == current_user.id
    )

    # 精确日期筛选（兼容旧参数）
    if date_param:
        query = query.filter(ExternalRecommendation.recommendation_date == date_param)
    # 日期范围筛选
    elif start_date:
        query = query.filter(ExternalRecommendation.recommendation_date >= start_date)
        if end_date:
            query = query.filter(ExternalRecommendation.recommendation_date <= end_date)

    if category:
        query = query.filter(ExternalRecommendation.category == category)

    # 获取总数
    total = query.count()

    # 排序
    query = query.order_by(
        desc(ExternalRecommendation.recommendation_date),
        desc(ExternalRecommendation.created_at)
    )

    # 兼容旧的 limit 参数
    if limit is not None:
        recs = query.limit(limit).all()
        return recs

    # 分页
    offset = (page - 1) * page_size
    recs = query.offset(offset).limit(page_size).all()

    total_pages = (total + page_size - 1) // page_size

    return {
        "items": [
            {
                "id": rec.id,
                "category": rec.category,
                "title": rec.title,
                "content": rec.content,
                "source_name": rec.source_name,
                "recommendation_date": rec.recommendation_date.isoformat() if rec.recommendation_date else None,
                "created_at": rec.created_at.isoformat() if rec.created_at else None,
            }
            for rec in recs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/external-recommendations/today")
async def get_today_external_recommendations(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取今日的外部建议（按类别分组）"""
    today = date.today()

    recs = db.query(ExternalRecommendation).filter(
        ExternalRecommendation.user_id == current_user.id,
        ExternalRecommendation.recommendation_date == today
    ).order_by(ExternalRecommendation.category).all()

    # 按类别分组
    grouped = {}
    for rec in recs:
        if rec.category not in grouped:
            grouped[rec.category] = []
        grouped[rec.category].append({
            "id": rec.id,
            "title": rec.title,
            "content": rec.content,
            "source_name": rec.source_name,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
        })

    return {
        "date": today.isoformat(),
        "has_recommendations": len(recs) > 0,
        "categories": grouped,
    }
