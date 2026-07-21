"""用户 API Key API - 允许外部系统访问用户健康数据和写入建议"""
import hashlib
import secrets
import logging
from datetime import datetime, date, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel, ConfigDict, field_validator

from app.database import get_db
from app.models.user import User
from app.models.user_api_key import UserApiKey
from app.models.user_profile import UserProfile
from app.models.daily_health import GarminData, WorkoutRecord, DietRecord, SupplementIntake
from app.models.weight import WeightRecord
from app.api.deps import (
    API_KEY_ALLOWED_SCOPES,
    get_current_user_required,
    normalize_api_key_scopes,
)
from app.utils.timezone import CHINA_TIMEZONE

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Schemas ====================

class ApiKeyCreate(BaseModel):
    """创建 API Key 请求"""
    name: str
    scopes: str = "read,write"

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: str) -> str:
        requested = {item.strip().lower() for item in (value or "").split(",") if item.strip()}
        invalid = requested - API_KEY_ALLOWED_SCOPES
        if not requested or invalid:
            raise ValueError("scopes 只能包含 read 和 write")
        return ",".join(scope for scope in ("read", "write") if scope in requested)


class ApiKeyResponse(BaseModel):
    """API Key 响应"""
    id: int
    name: str
    api_key: Optional[str] = None  # 只在创建时返回
    scopes: str
    is_active: bool
    last_used_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


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
    return required_scope.strip().lower() in normalize_api_key_scopes(api_key.scopes)


# ==================== API Key 验证依赖 ====================

async def verify_user_api_key(
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
) -> UserApiKey:
    """验证用户 API Key"""
    logger.info("API Key 验证请求")

    key_hash = hash_api_key(x_api_key)
    api_key = db.query(UserApiKey).filter(
        UserApiKey.api_key == key_hash,
        UserApiKey.is_active == True
    ).first()

    if not api_key:
        logger.warning("API Key 验证失败: 无效或未激活")
        raise HTTPException(status_code=401, detail="Invalid API Key")

    request.state.auth_type = "api_key"
    request.state.api_key_id = api_key.id
    request.state.auth_scopes = normalize_api_key_scopes(api_key.scopes)

    # 更新最后使用时间
    api_key.last_used_at = datetime.now(CHINA_TIMEZONE)
    db.commit()

    logger.info(f"API Key 验证成功: user_id={api_key.user_id}, key_name={api_key.name}")
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
    try:
        logger.info(f"用户 {current_user.id} 尝试创建 API Key: name={key_data.name}, scopes={key_data.scopes}")

        # 验证 name 不为空
        if not key_data.name or not key_data.name.strip():
            raise HTTPException(status_code=400, detail="API Key 名称不能为空")

        # 限制每个用户最多 10 个 API Key（增加到10个）
        existing_count = db.query(UserApiKey).filter(
            UserApiKey.user_id == current_user.id,
            UserApiKey.is_active == True
        ).count()

        if existing_count >= 10:
            raise HTTPException(
                status_code=400,
                detail=f"每个用户最多创建 10 个 API Key，您已创建 {existing_count} 个。请删除不需要的 Key 后再试。"
            )

        # 生成随机 API Key
        raw_key = secrets.token_urlsafe(32)
        key_hash = hash_api_key(raw_key)

        db_key = UserApiKey(
            user_id=current_user.id,
            name=key_data.name.strip(),
            api_key=key_hash,
            scopes=key_data.scopes,
        )
        db.add(db_key)
        db.commit()
        db.refresh(db_key)

        logger.info(f"用户 {current_user.id} 成功创建 API Key: {key_data.name} (id={db_key.id})")

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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建 API Key 失败: user={current_user.id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建 API Key 失败: {str(e)}")


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

def _build_user_profile_for_external(profile: UserProfile, db: Session = None, user_id: int = None) -> dict:
    """
    根据隐私设置构建对外公开的用户画像信息

    Args:
        profile: UserProfile 对象
        db: 数据库会话（用于查询最新体重记录）
        user_id: 用户ID

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
    # 体重：优先使用体重记录表中的最新数据
    if privacy.get("weight", True):
        latest_weight = None
        if db and user_id:
            latest_weight_record = db.query(WeightRecord).filter(
                WeightRecord.user_id == user_id
            ).order_by(desc(WeightRecord.record_date)).first()
            if latest_weight_record:
                latest_weight = latest_weight_record.weight

        # 如果没有体重记录，回退到 profile 中的数据
        if not latest_weight:
            latest_weight = profile.current_weight_kg

        if latest_weight:
            result["weight_kg"] = latest_weight

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

    if privacy.get("city", True) or privacy.get("location", True):
        from app.services.location_resolver import resolve_effective_location
        loc = resolve_effective_location(profile)
        if privacy.get("city", True) and loc["city"]:
            result["city"] = loc["city"]
        if privacy.get("location", True) and loc["city"]:
            result["location"] = {
                "city": loc["city"],
                "lat": loc["lat"],
                "lon": loc["lon"],
                "source": loc["source"],  # 'manual' | 'gps' | 'ip' | 'unknown'
                "updated_at": loc["updated_at"],
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
    外部系统读取用户健康数据

    - 使用 X-API-Key 头部认证
    - 支持单日查询 (?date=2024-01-25) 或日期范围 (?start_date=...&end_date=...)
    - 最多可查询最近 365 天的数据
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
    min_date = today - timedelta(days=365)

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
        raise HTTPException(status_code=400, detail="只能查询最近 365 天的数据")
    if (end_date - start_date).days > 365:
        raise HTTPException(status_code=400, detail="日期范围不能超过 365 天")

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
            garmin_data = {
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
                "body_battery_high": garmin.body_battery_most_charged,
                "body_battery_low": garmin.body_battery_lowest,
                "body_battery_current": garmin.body_battery_current,
                "body_battery_charged": garmin.body_battery_charged,
                "body_battery_drained": garmin.body_battery_drained,
                "stress_avg": garmin.stress_level,
                "calories_total": garmin.calories_burned,
                "calories_active": garmin.active_calories,
                "active_minutes": garmin.active_minutes or ((garmin.moderate_intensity_minutes or 0) + (garmin.vigorous_intensity_minutes or 0)),
                "floors_climbed": garmin.floors_climbed,
                "spo2_avg": garmin.spo2_avg,
            }
            day_data["garmin"] = {k: v for k, v in garmin_data.items() if v is not None}

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

        # 体重记录
        weight_record = db.query(WeightRecord).filter(
            WeightRecord.user_id == api_key.user_id,
            WeightRecord.record_date == current_date
        ).first()

        if weight_record:
            weight_data = {
                "weight_kg": weight_record.weight,
                "body_fat_percentage": weight_record.body_fat_percentage,
                "muscle_mass_kg": weight_record.muscle_mass_kg,
            }
            day_data["weight"] = {k: v for k, v in weight_data.items() if v is not None}

        result_data.append(day_data)
        current_date += timedelta(days=1)

    # 过滤空天（只有 date 字段的天不返回）
    result_data = [d for d in result_data if len(d) > 1]

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
    user_profile_data = _build_user_profile_for_external(profile, db, api_key.user_id)
    if user_profile_data:
        response["user_profile"] = user_profile_data

    # 添加基因检测数据（不随日期变化，放在顶层）
    try:
        from app.models.genetic_data import GeneticVariant
        variants = db.query(GeneticVariant).filter(
            GeneticVariant.user_id == api_key.user_id
        ).order_by(
            GeneticVariant.risk_level.desc(),
            GeneticVariant.category
        ).all()
        if variants:
            # 按 gene_name + variant_name 去重
            seen = {}
            for v in variants:
                key = (v.gene_name, v.variant_name)
                if key not in seen:
                    seen[key] = v
            unique_variants = list(seen.values())

            # 只返回可操作变异（high/medium/drug_sensitivity），info/low 用摘要代替
            actionable = [v for v in unique_variants
                          if v.risk_level in ("high", "medium")
                          or "drug" in (v.category or "").lower()]
            skipped = [v for v in unique_variants if v not in actionable]

            from collections import Counter
            skipped_summary = Counter(v.category for v in skipped)

            response["genetic_profile"] = {
                "total_variants": len(unique_variants),
                "high_risk_count": sum(1 for v in unique_variants if v.risk_level == "high"),
                "returned_variants": len(actionable),
                "omitted_low_risk": len(skipped),
                "omitted_categories": dict(skipped_summary),
                "variants": [
                    {k: v for k, v in {
                        "gene": v.gene_name,
                        "variant": v.variant_name,
                        "genotype": v.genotype,
                        "result": v.result_label,
                        "risk_level": v.risk_level,
                        "category": v.category,
                    }.items() if v is not None}
                    for v in actionable
                ]
            }
    except Exception:
        pass  # 基因表未创建或查询失败时不影响主流程

    # 添加当前补剂清单（不随日期变化，放在顶层）
    try:
        from app.models.supplement import SupplementDefinition
        active_supps = db.query(SupplementDefinition).filter(
            SupplementDefinition.user_id == api_key.user_id,
            SupplementDefinition.is_active == True
        ).order_by(SupplementDefinition.sort_order).all()
        if active_supps:
            response["active_supplements"] = [
                {
                    "name": s.name,
                    "dosage": s.dosage,
                    "timing": s.timing,
                    "category": s.category,
                    "description": s.description,
                }
                for s in active_supps
            ]
    except Exception:
        pass

    # 添加当前用药清单（不随日期变化，放在顶层）
    try:
        from app.models.medication import Medication
        active_meds = db.query(Medication).filter(
            Medication.user_id == api_key.user_id,
            Medication.is_active == True
        ).all()
        if active_meds:
            response["active_medications"] = [
                {
                    "name": m.name,
                    "dosage": m.dosage,
                    "frequency": m.frequency,
                    "times_per_day": m.times_per_day,
                    "category": m.category,
                    "purpose": m.purpose,
                    "side_effects": m.side_effects,
                    "interactions": m.interactions,
                    "start_date": m.start_date.isoformat() if m.start_date else None,
                    "end_date": m.end_date.isoformat() if m.end_date else None,
                    "notes": m.notes,
                }
                for m in active_meds
            ]
    except Exception:
        pass

    return response
