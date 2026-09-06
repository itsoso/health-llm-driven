"""用户画像 API - executor.life"""
import json
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.user_profile import UserProfile, HealthGoal
from app.schemas.user_profile import (
    UserProfileCreate, UserProfileUpdate, UserProfileResponse,
    HealthGoalCreate, HealthGoalUpdate, HealthGoalResponse,
    PrivacySettings, DetectedLocation, ManualLocation, ManualLocationUpdate,
    AssistantDashboardLayouts,
    DeviceTimezoneUpdate, ManualTimezoneUpdate, EffectiveTimezone,
)
from app.api.auth import get_current_user_required
from datetime import date

router = APIRouter(prefix="/profile", tags=["用户画像"])


def parse_json_field(field_value: Any, default: Any):
    if field_value is None:
        return default
    if isinstance(field_value, str):
        try:
            return json.loads(field_value)
        except Exception:
            return default
    return field_value


def get_default_assistant_dashboard_layouts() -> dict[str, dict[str, list[str]]]:
    return {
        "web": {"order": [], "hidden": []},
        "mobile": {"order": [], "hidden": []},
    }


def normalize_assistant_dashboard_layouts(field_value: Any) -> AssistantDashboardLayouts:
    return AssistantDashboardLayouts(**parse_json_field(field_value, get_default_assistant_dashboard_layouts()))


def build_profile_response(profile: UserProfile) -> UserProfileResponse:
    from app.utils.timezone import resolve_timezone_name
    _eff_tz_name, _eff_tz_source = resolve_timezone_name(
        profile.manual_timezone, profile.detected_timezone, profile.timezone
    )
    return UserProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        gender=profile.gender,
        birth_date=profile.birth_date,
        height_cm=profile.height_cm,
        blood_type=profile.blood_type,
        current_weight_kg=profile.current_weight_kg,
        target_weight_kg=profile.target_weight_kg,
        body_fat_percentage=profile.body_fat_percentage,
        muscle_mass_kg=profile.muscle_mass_kg,
        target_steps=profile.target_steps if profile.target_steps is not None else 8000,
        target_sleep_hours=profile.target_sleep_hours if profile.target_sleep_hours is not None else 7.5,
        target_water_ml=profile.target_water_ml if profile.target_water_ml is not None else 2000,
        target_calories_burn=profile.target_calories_burn,
        target_exercise_minutes=profile.target_exercise_minutes if profile.target_exercise_minutes is not None else 30,
        chronic_conditions=parse_json_field(profile.chronic_conditions, []),
        allergies=parse_json_field(profile.allergies, []),
        family_history=parse_json_field(profile.family_history, []),
        surgeries=parse_json_field(profile.surgeries, []),
        current_medications=parse_json_field(profile.current_medications, []),
        exercise_frequency=profile.exercise_frequency,
        diet_preference=profile.diet_preference,
        smoking_status=profile.smoking_status,
        alcohol_consumption=profile.alcohol_consumption,
        usual_sleep_time=profile.usual_sleep_time,
        usual_wake_time=profile.usual_wake_time,
        sleep_environment=parse_json_field(profile.sleep_environment, {}),
        work_type=profile.work_type,
        work_hours_per_day=profile.work_hours_per_day,
        sitting_hours_per_day=profile.sitting_hours_per_day,
        work_start_time=profile.work_start_time,
        work_end_time=profile.work_end_time,
        workout_pref_window=profile.workout_pref_window,
        workout_target_minutes=profile.workout_target_minutes,
        city=profile.city,
        timezone=profile.timezone or "Asia/Shanghai",
        devices=parse_json_field(profile.devices, []),
        assistant_dashboard_layouts=normalize_assistant_dashboard_layouts(profile.assistant_dashboard_layouts),
        privacy_settings=PrivacySettings(**{k: v for k, v in parse_json_field(profile.privacy_settings, {
            "weight": True, "height": True, "age": True,
            "gender": True, "city": True, "location": True
        }).items() if k in PrivacySettings.model_fields}),
        age=profile.age,
        bmi=profile.bmi,
        bmi_category=profile.bmi_category,
        detected_location=DetectedLocation(
            city=profile.detected_city,
            region=profile.detected_region,
            country=profile.detected_country
        ) if profile.detected_city or profile.detected_region or profile.detected_country else None,
        location_updated_at=profile.location_updated_at,
        manual_location=ManualLocation(
            city=profile.manual_city,
            region=profile.manual_region,
            country=profile.manual_country
        ) if profile.manual_city or profile.manual_region or profile.manual_country else None,
        use_manual_location=profile.use_manual_location or False,
        detected_timezone=profile.detected_timezone,
        manual_timezone=profile.manual_timezone,
        effective_timezone=_eff_tz_name,
        timezone_source=_eff_tz_source,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


# =====================================================
# 用户画像 API
# =====================================================

@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的画像"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    if not profile:
        # 自动创建空的用户画像
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)

    return build_profile_response(profile)


@router.put("/me", response_model=UserProfileResponse)
async def update_my_profile(
    profile_data: UserProfileUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新当前用户的画像"""
    from app.services.ai_consent import lock_consent_owner, merge_public_privacy
    lock_consent_owner(db, current_user.id)
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).populate_existing().first()

    if not profile:
        # 自动创建
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)

    # 更新非空字段
    update_data = profile_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "privacy_settings":
            profile.privacy_settings = merge_public_privacy(profile.privacy_settings, value)
            continue
        if key == "assistant_dashboard_layouts" and value is not None:
            current_layouts = normalize_assistant_dashboard_layouts(profile.assistant_dashboard_layouts).model_dump()
            for device, layout in value.items():
                current_layouts[device] = {
                    "order": list(layout.get("order", [])),
                    "hidden": list(layout.get("hidden", [])),
                }
            setattr(profile, key, current_layouts)
            continue
        setattr(profile, key, value)

    db.commit()
    db.refresh(profile)

    return build_profile_response(profile)


@router.get("/me/effective-location")
async def get_effective_location(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """位置字段单一事实之主 — 所有 mobile / 后端 reader 应该走这里, 不再各自实现优先级.

    返回: {city, lat, lon, source, updated_at, stale_minutes}
    详细语义见 app/services/location_resolver.py docstring.
    """
    from app.services.location_resolver import resolve_effective_location
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    return resolve_effective_location(profile)


def _effective_timezone_payload(profile: UserProfile) -> EffectiveTimezone:
    from app.utils.timezone import resolve_timezone_name
    name, source = resolve_timezone_name(
        profile.manual_timezone, profile.detected_timezone, profile.timezone
    )
    return EffectiveTimezone(
        timezone=name, source=source,
        detected_timezone=profile.detected_timezone,
        manual_timezone=profile.manual_timezone,
    )


def _get_or_create_profile(db: Session, user_id: int) -> UserProfile:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


@router.get("/me/effective-timezone", response_model=EffectiveTimezone)
async def get_effective_timezone(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """生效时区单一事实之主 —— 优先级 manual → detected → 旧 timezone → 默认中国。

    所有读时区的 reader 应走 get_user_timezone(同一优先级);本端点给 mobile / 设置页展示用。
    """
    return _effective_timezone_payload(_get_or_create_profile(db, current_user.id))


@router.post("/me/device-timezone", response_model=EffectiveTimezone)
async def report_device_timezone(
    body: DeviceTimezoneUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """设备/系统上报当前时区(自动跟随地理位置)。

    写入 detected_timezone;只要用户没手动锁定(manual_timezone 为空),它就是生效时区。
    用户已锁定时仍记录 detected(便于 UI 显示「你在 X,已锁定 Y」),但不改变生效时区。
    """
    from app.utils.timezone import is_valid_timezone
    tz = (body.timezone or "").strip()
    if not is_valid_timezone(tz):
        raise HTTPException(status_code=400, detail=f"未知时区: {body.timezone!r}(需 IANA 名,如 Asia/Shanghai)")
    profile = _get_or_create_profile(db, current_user.id)
    profile.detected_timezone = tz
    db.commit()
    db.refresh(profile)
    return _effective_timezone_payload(profile)


@router.put("/me/manual-timezone", response_model=EffectiveTimezone)
async def set_manual_timezone(
    body: ManualTimezoneUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """用户手动锁定/解锁时区。

    timezone 非空 → 锁定(覆盖自动检测);传 null/空 → 解锁,恢复自动跟随设备/位置。
    """
    from app.utils.timezone import is_valid_timezone
    tz = (body.timezone or "").strip()
    if tz and not is_valid_timezone(tz):
        raise HTTPException(status_code=400, detail=f"未知时区: {body.timezone!r}(需 IANA 名,如 Asia/Shanghai)")
    profile = _get_or_create_profile(db, current_user.id)
    profile.manual_timezone = tz or None
    db.commit()
    db.refresh(profile)
    return _effective_timezone_payload(profile)


@router.post("/me/refresh-location")
async def refresh_my_location(
    request: Request,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    手动刷新用户位置信息（基于IP）

    返回更新后的位置信息
    """
    from app.services.ip_geolocation import get_geolocation_service

    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)

    # 获取客户端 IP
    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.headers.get("X-Real-IP", "")
    if not client_ip:
        client_ip = request.client.host if request.client else ""

    if not client_ip:
        raise HTTPException(status_code=400, detail="无法获取客户端 IP")

    # 强制获取位置（不检查时间间隔）
    service = get_geolocation_service()
    location = await service.get_location_from_ip(client_ip)

    if location:
        from datetime import UTC, datetime
        profile.detected_city = location.city
        profile.detected_region = location.region
        profile.detected_country = location.country
        profile.detected_source = "ip"
        # IP 反查也带时区 —— 自动跟随的兜底来源(app 前台上报的设备时区更准,会覆盖它)
        from app.utils.timezone import is_valid_timezone
        if is_valid_timezone(location.timezone):
            profile.detected_timezone = location.timezone
        profile.location_updated_at = datetime.now(UTC)
        profile.last_ip = client_ip
        db.commit()
        db.refresh(profile)

        return {
            "success": True,
            "location": {
                "city": location.city,
                "region": location.region,
                "country": location.country
            },
            "ip": client_ip,
            "updated_at": profile.location_updated_at
        }
    else:
        return {
            "success": False,
            "message": "无法获取位置信息（可能是本地IP或服务不可用）",
            "ip": client_ip
        }


@router.put("/me/manual-location")
async def update_manual_location(
    location_data: ManualLocationUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    更新手工输入的位置信息

    Args:
        location_data: 包含 use_manual_location 开关和位置信息

    Returns:
        更新后的位置信息
    """
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)

    # 更新手工位置字段
    old_city = profile.manual_city
    profile.use_manual_location = location_data.use_manual_location
    profile.manual_city = location_data.city
    profile.manual_region = location_data.region
    profile.manual_country = location_data.country

    db.commit()
    db.refresh(profile)

    # 用户改 location → 清旧 city 的天气/AQI 缓存, 强制下次拉新数据
    try:
        from app.services.environment import weather_service, air_quality_service
        if old_city and old_city != location_data.city:
            weather_service.invalidate_cache_for(city=old_city)
        if location_data.city:
            weather_service.invalidate_cache_for(city=location_data.city)
        # AQI 服务也清 (它有自己的缓存)
        if hasattr(air_quality_service, "invalidate_cache_for"):
            if old_city:
                air_quality_service.invalidate_cache_for(city=old_city)
            if location_data.city:
                air_quality_service.invalidate_cache_for(city=location_data.city)
    except Exception as e:
        # 清缓存失败不影响 location 更新本身
        import logging
        logging.getLogger(__name__).warning(f"[manual-location] 清天气缓存失败 (不致命): {e}")

    return {
        "success": True,
        "use_manual_location": profile.use_manual_location,
        "manual_location": {
            "city": profile.manual_city,
            "region": profile.manual_region,
            "country": profile.manual_country
        },
        "detected_location": {
            "city": profile.detected_city,
            "region": profile.detected_region,
            "country": profile.detected_country
        }
    }


@router.post("/me/gps-location")
async def update_gps_location(
    payload: dict,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    GPS 定位: 客户端拿到经纬度后写入 profile (auto 模式下立即生效).

    payload: { lat: float, lon: float, city?: str, region?: str, country?: str }

    城市名解析两条路径 (mobile 端优先客户端反查, 去 qweather 依赖):
    1. 客户端用 expo-location `reverseGeocodeAsync` (iOS CLGeocoder 离线可用) 反查 city,
       backend 直接信任 — 跳过 qweather 调用.
    2. 客户端没传 city, 走 qweather GeoAPI 反查 (premium host 必需).

    可靠性: qweather 未配 / 失败 时不再 502 — 仍 200 返回, 但 city=null, lat/lon 仍写入.
    resolver 标记 source='gps', environment.py 优先读 lat/lon, 天气/AQ 仍能正常出.

    Garbage 防御: 客户端送的 city 含非中文且 country=中国 → 视为 CLGeocoder 英文化误差
    (iOS 在 PRC 偶尔返 'Beijing'), 丢弃后兜底 qweather.

    成功后清旧/新 city 的天气/AQI 缓存.
    """
    import httpx
    import logging
    import re
    from datetime import UTC, datetime
    from app.config import settings

    log = logging.getLogger(__name__)

    try:
        lat = float(payload.get("lat"))
        lon = float(payload.get("lon"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="需要 lat 和 lon (数字)")

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise HTTPException(status_code=400, detail="经纬度超出范围")

    # ── 步骤 1: 客户端 hint 优先 ────────────────────────────────────────────
    client_city = (payload.get("city") or "").strip() or None
    client_region = (payload.get("region") or "").strip() or None
    client_country = (payload.get("country") or "").strip() or None

    # garbage 防御: PRC 用户但拿到英文 city → CLGeocoder 失误, 丢弃走 qweather 兜底
    def _is_pure_non_cjk(s: Optional[str]) -> bool:
        return bool(s) and not re.search(r"[一-鿿]", s)
    is_china = bool(client_country and ("中国" in client_country or "China" in client_country))
    if is_china and (_is_pure_non_cjk(client_city) or _is_pure_non_cjk(client_region)):
        log.info(f"[gps-location] 丢弃 CLGeocoder 英文 city/region: city={client_city!r} region={client_region!r}")
        client_city = client_region = None

    city = region = country = ""
    used_qweather = False

    if client_city:
        city = client_city
        region = client_region or ""
        country = client_country or "中国"
    elif settings.qweather_api_key and settings.qweather_api_host:
        # ── 步骤 2: qweather 兜底反查 ─────────────────────────────────────
        geo_base = f"https://{settings.qweather_api_host}/geo/v2"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(
                    f"{geo_base}/city/lookup",
                    params={
                        "location": f"{lon:.4f},{lat:.4f}",
                        "key": settings.qweather_api_key,
                        "number": 1,
                    },
                )
                r.raise_for_status()
                data = r.json()
            if data.get("code") == "200" and data.get("location"):
                loc = data["location"][0]
                city = loc.get("name") or ""
                region = loc.get("adm1") or ""
                country = loc.get("country") or "中国"
                used_qweather = True
            else:
                log.warning(f"[gps-location] qweather 反查无结果: code={data.get('code')}")
        except Exception as e:
            log.warning(f"[gps-location] qweather 反查失败 (回退到只存 lat/lon): {e}")
    else:
        log.info("[gps-location] qweather 未配置 + 客户端无 city hint, 只存 lat/lon")

    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)

    old_city = profile.detected_city
    # 即使 city/region 都没反查到, lat/lon 仍写入 — environment.py 优先读坐标.
    #
    # 原子写入: city/region/country 是同一次反查的结果, 必须整组替换。
    # 旧实现对三者各用独立 if, 当新反查出了 city 但没 region 时, 会保留上一个
    # 不相干位置的旧 region → 出现 "California · 北京市" 这种省市错配。
    # 因此只要这次拿到了 city (有了新位置), 就连 region/country 一起覆盖,
    # 没反查到的字段显式清空, 不让旧值残留。
    if city:
        profile.detected_city = city
        profile.detected_region = region or None
        profile.detected_country = country or None
    elif region or country:
        # 没 city 但有 region/country (罕见): 仍整组更新, 同样不残留旧 city
        profile.detected_city = None
        profile.detected_region = region or None
        profile.detected_country = country or None
    # else: city/region/country 全空 → 只更新 lat/lon, 保留旧文字标签
    # 2026-05-12: 同时存用户实际 GPS 坐标. environment.py 直接透传给 weather/AQ service.
    profile.detected_lat = lat
    profile.detected_lon = lon
    profile.detected_source = "gps"
    # GPS 按钮的语义是"用 GPS 自动定位", 触发时顺手关掉 manual mode
    profile.use_manual_location = False
    profile.location_updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(profile)

    try:
        from app.services.environment import weather_service, air_quality_service
        for c in filter(None, {old_city, city}):
            weather_service.invalidate_cache_for(city=c)
            if hasattr(air_quality_service, "invalidate_cache_for"):
                air_quality_service.invalidate_cache_for(city=c, lat=lat, lon=lon)
        weather_service.invalidate_cache_for(lat=lat, lon=lon)
    except Exception as e:
        log.warning(f"[gps-location] 清缓存失败 (不致命): {e}")

    return {
        "success": True,
        "location": {
            "city": city or None,
            "region": region or None,
            "country": country or None,
            "lat": lat, "lon": lon,
        },
        "detected_location": {
            "city": profile.detected_city,
            "region": profile.detected_region,
            "country": profile.detected_country,
        },
        "use_manual_location": profile.use_manual_location,
        "geocode_source": "client" if client_city else ("qweather" if used_qweather else "none"),
    }


@router.post("/me/chronic-conditions", response_model=UserProfileResponse)
async def add_chronic_condition(
    condition: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """添加慢性病"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        profile = UserProfile(user_id=current_user.id, chronic_conditions=[])
        db.add(profile)

    conditions = profile.chronic_conditions or []
    if condition not in conditions:
        conditions.append(condition)
        profile.chronic_conditions = conditions
        db.commit()
        db.refresh(profile)

    return UserProfileResponse.model_validate(profile)


@router.delete("/me/chronic-conditions/{condition}", response_model=UserProfileResponse)
async def remove_chronic_condition(
    condition: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """移除慢性病"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="用户画像不存在")

    conditions = profile.chronic_conditions or []
    if condition in conditions:
        conditions.remove(condition)
        profile.chronic_conditions = conditions
        db.commit()
        db.refresh(profile)

    return UserProfileResponse.model_validate(profile)


# =====================================================
# 健康目标 API
# =====================================================

@router.get("/goals", response_model=list[HealthGoalResponse])
async def get_my_goals(
    status_filter: Optional[str] = None,
    goal_type: Optional[str] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的健康目标"""
    query = db.query(HealthGoal).filter(HealthGoal.user_id == current_user.id)

    if status_filter:
        query = query.filter(HealthGoal.status == status_filter)
    if goal_type:
        query = query.filter(HealthGoal.goal_type == goal_type)

    goals = query.order_by(HealthGoal.priority, HealthGoal.created_at.desc()).all()

    # 计算进度
    result = []
    for goal in goals:
        response = HealthGoalResponse.model_validate(goal)

        # 计算完成百分比
        if goal.target_value and goal.current_value is not None:
            response.progress_percentage = round((goal.current_value / goal.target_value) * 100, 1)

        # 计算剩余天数
        if goal.target_date:
            remaining = (goal.target_date - date.today()).days
            response.days_remaining = max(0, remaining)

        result.append(response)

    return result


@router.post("/goals", response_model=HealthGoalResponse)
async def create_goal(
    goal_data: HealthGoalCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建健康目标"""
    goal = HealthGoal(
        user_id=current_user.id,
        **goal_data.model_dump()
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)

    return HealthGoalResponse.model_validate(goal)


@router.put("/goals/{goal_id}", response_model=HealthGoalResponse)
async def update_goal(
    goal_id: int,
    goal_data: HealthGoalUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新健康目标"""
    goal = db.query(HealthGoal).filter(
        HealthGoal.id == goal_id,
        HealthGoal.user_id == current_user.id
    ).first()

    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在")

    update_data = goal_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(goal, key, value)

    # 如果状态变为completed，记录完成时间
    if goal_data.status == "completed":
        from datetime import UTC, datetime
        goal.completed_at = datetime.now(UTC)

    db.commit()
    db.refresh(goal)

    return HealthGoalResponse.model_validate(goal)


@router.delete("/goals/{goal_id}")
async def delete_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除健康目标"""
    goal = db.query(HealthGoal).filter(
        HealthGoal.id == goal_id,
        HealthGoal.user_id == current_user.id
    ).first()

    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在")

    db.delete(goal)
    db.commit()

    return {"message": "目标已删除"}


@router.post("/goals/{goal_id}/progress", response_model=HealthGoalResponse)
async def update_goal_progress(
    goal_id: int,
    current_value: float,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新目标进度"""
    goal = db.query(HealthGoal).filter(
        HealthGoal.id == goal_id,
        HealthGoal.user_id == current_user.id
    ).first()

    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在")

    goal.current_value = current_value

    # 检查是否达成目标
    if goal.target_value and current_value >= goal.target_value:
        goal.status = "completed"
        from datetime import UTC, datetime
        goal.completed_at = datetime.now(UTC)

    db.commit()
    db.refresh(goal)

    response = HealthGoalResponse.model_validate(goal)
    if goal.target_value:
        response.progress_percentage = round((goal.current_value / goal.target_value) * 100, 1)

    return response


# =====================================================
# AI 个性化建议 API
# =====================================================

@router.get("/advice/morning")
async def get_morning_advice(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取早间个性化健康建议"""
    from app.services.ai.personalized_advice import get_personalized_advice
    return get_personalized_advice(db, current_user.id, 'morning')


@router.get("/advice/summary")
async def get_daily_summary_advice(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取每日总结和建议"""
    from app.services.ai.personalized_advice import get_personalized_advice
    return get_personalized_advice(db, current_user.id, 'summary')


@router.get("/advice/checkin/{template_name}")
async def get_checkin_advice(
    template_name: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取打卡前的鼓励建议"""
    from app.services.ai.personalized_advice import PersonalizedAdviceService
    service = PersonalizedAdviceService(db, current_user.id)
    return {"advice": service.get_checkin_advice(template_name)}
