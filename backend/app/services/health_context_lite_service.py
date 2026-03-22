"""轻量健康上下文服务 — 为 OpenClaw 模式提供精简的用户健康摘要

设计目标：
- 200-300 tokens 输出，5 次 DB 查询
- 5 分钟内存缓存，命中 0ms
- 任何失败优雅降级，不影响对话
"""
import logging
import time
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── 内存缓存 ──────────────────────────────────────────
_context_cache: dict[int, tuple[float, str]] = {}  # user_id -> (timestamp, context_str)
_CACHE_TTL = 300  # 5 分钟

# ── 系统规则（注入到 system message） ────────────────────
OPENCLAW_HEALTH_SYSTEM_RULES = (
    "你是用户的AI健康助理，具备通过Skills查询数据和执行操作的能力。"
    "以下是用户的实时健康档案，请据此提供个性化、科学的建议。\n\n"
    "关键规则：\n"
    "1. HRV状态为low或SpO2<95%时，在回复中主动提醒用户注意休息或就医\n"
    "2. 回答需考虑用户的慢性病史和当前用药\n"
    "3. 运动建议需参考用户年龄对应的最大心率\n"
    "4. 严重健康问题务必建议就医，不要自行诊断\n"
    "5. 用中文回复，简洁务实"
)


def _get_time_period() -> tuple[str, str]:
    """返回当前时间和时段标签"""
    from datetime import datetime, timezone, timedelta as td
    beijing = timezone(td(hours=8))
    now = datetime.now(beijing)
    hour = now.hour
    if 5 <= hour < 8:
        period = "清晨"
    elif 8 <= hour < 12:
        period = "上午"
    elif 12 <= hour < 14:
        period = "中午"
    elif 14 <= hour < 18:
        period = "下午"
    elif 18 <= hour < 21:
        period = "晚上"
    else:
        period = "深夜"
    return now.strftime("%H:%M"), period


async def build_lite_health_context(db: Session, user_id: int) -> Optional[str]:
    """构建轻量健康上下文（~200 tokens）

    数据来源：
    1. User + UserProfile — 基本信息
    2. GarminData latest — 今日实时数据
    3. GarminData 7 天 — 趋势均值
    4. WeightRecord latest — 最新体重
    5. IllnessEpisode active — 活跃病症
    """
    # 缓存检查
    cached = _context_cache.get(user_id)
    if cached and (time.time() - cached[0]) < _CACHE_TTL:
        return cached[1]

    try:
        context = _build_context(db, user_id)
        _context_cache[user_id] = (time.time(), context)
        return context
    except Exception as e:
        logger.error(f"构建轻量健康上下文失败(user={user_id}): {e}", exc_info=True)
        return None


def _build_context(db: Session, user_id: int) -> str:
    """同步构建上下文（由 async 包装器调用）"""
    from app.models.user import User
    from app.models.user_profile import UserProfile
    from app.models.daily_health import GarminData
    from app.models.weight import WeightRecord
    from app.models.illness import IllnessEpisode

    parts = []
    time_str, period = _get_time_period()
    today = date.today()

    # ── 1. 用户基本信息 ──────────────────────────────────
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return ""

    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

    name = user.name or user.username or "用户"
    parts.append(f"[用户健康档案]")

    # 时间 + 位置
    city = ""
    if profile:
        city = profile.manual_city or getattr(profile, "detected_city", "") or ""
    location_str = f" | 位置: {city}" if city else ""
    parts.append(f"时间: {time_str} ({period}){location_str}")

    # 个人信息
    age_str = ""
    max_hr_str = ""
    if profile and profile.age:
        age = profile.age
        age_str = f", {age}岁"
        max_hr = 220 - age
        max_hr_str = f", 最大心率{max_hr}bpm"

    gender_map = {"male": "男", "female": "女"}
    gender = gender_map.get(profile.gender, "") if profile else ""
    if gender:
        gender = f", {gender}"

    parts.append(f"用户: {name}{gender}{age_str}{max_hr_str}")

    # 身体数据
    if profile:
        body_parts = []
        if profile.height_cm:
            body_parts.append(f"{profile.height_cm:.0f}cm")

        # 体重：优先用最新称重记录
        weight_val = None
        latest_weight = db.query(WeightRecord).filter(
            WeightRecord.user_id == user_id
        ).order_by(WeightRecord.record_date.desc()).first()
        if latest_weight:
            weight_val = latest_weight.weight
        elif profile.current_weight_kg:
            weight_val = profile.current_weight_kg

        if weight_val:
            target = profile.target_weight_kg
            w_str = f"{weight_val:.1f}kg"
            if target:
                w_str += f"(目标{target:.0f}kg)"
            body_parts.append(w_str)

        if weight_val and profile.height_cm:
            h_m = profile.height_cm / 100
            bmi = weight_val / (h_m * h_m)
            body_parts.append(f"BMI {bmi:.1f}")

        if body_parts:
            parts.append(f"身体: {', '.join(body_parts)}")

        # 慢性病 + 用药
        conditions = profile.chronic_conditions or []
        meds = profile.current_medications or []
        med_names = [m["name"] if isinstance(m, dict) else str(m) for m in meds]

        health_info = []
        if conditions:
            health_info.append(f"慢性病: {', '.join(conditions)}")
        if med_names:
            health_info.append(f"用药: {', '.join(med_names)}")
        if health_info:
            parts.append(" | ".join(health_info))

    # ── 2. 今日 Garmin 数据 ──────────────────────────────
    latest_garmin = db.query(GarminData).filter(
        GarminData.user_id == user_id
    ).order_by(GarminData.record_date.desc()).first()

    if latest_garmin:
        g = latest_garmin
        garmin_items = []
        if g.steps is not None:
            garmin_items.append(f"步数{g.steps}")
        if g.resting_heart_rate is not None:
            garmin_items.append(f"静息心率{g.resting_heart_rate}")
        if g.sleep_score is not None:
            sleep_h = f"({g.total_sleep_duration / 60:.1f}h)" if g.total_sleep_duration else ""
            garmin_items.append(f"睡眠{g.sleep_score}分{sleep_h}")
        if g.stress_level is not None:
            garmin_items.append(f"压力{g.stress_level}")
        if g.body_battery_current is not None:
            garmin_items.append(f"电量{g.body_battery_current}")
        if g.hrv is not None:
            status = f"({g.hrv_status})" if g.hrv_status else ""
            garmin_items.append(f"HRV{g.hrv:.0f}ms{status}")
        if g.spo2_avg is not None:
            garmin_items.append(f"SpO2:{g.spo2_avg:.0f}%")

        if garmin_items:
            date_label = "今日" if g.record_date == today else f"{g.record_date}"
            parts.append(f"{date_label}: {', '.join(garmin_items)}")

    # ── 3. 7 日趋势 ─────────────────────────────────────
    week_ago = today - timedelta(days=7)
    garmin_7d = db.query(GarminData).filter(
        GarminData.user_id == user_id,
        GarminData.record_date >= week_ago,
    ).all()

    if len(garmin_7d) >= 3:  # 至少 3 天数据才有意义
        steps_list = [g.steps for g in garmin_7d if g.steps is not None]
        sleep_list = [g.total_sleep_duration for g in garmin_7d if g.total_sleep_duration is not None]
        rhr_list = [g.resting_heart_rate for g in garmin_7d if g.resting_heart_rate is not None]

        trend_parts = []
        if steps_list:
            trend_parts.append(f"步数{sum(steps_list) // len(steps_list)}")
        if sleep_list:
            avg_h = sum(sleep_list) / len(sleep_list) / 60
            trend_parts.append(f"睡眠{avg_h:.1f}h")
        if rhr_list:
            trend_parts.append(f"静息心率{sum(rhr_list) // len(rhr_list)}")

        if trend_parts:
            parts.append(f"7日均值: {', '.join(trend_parts)}")

    # ── 4. 活跃病症 ─────────────────────────────────────
    illnesses = db.query(IllnessEpisode).filter(
        IllnessEpisode.user_id == user_id,
        IllnessEpisode.status != "resolved",
    ).all()

    if illnesses:
        illness_strs = []
        for ill in illnesses:
            days = (today - ill.start_date).days if ill.start_date else 0
            illness_strs.append(f"{ill.name}(第{days}天, {ill.severity}/10)")
        parts.append(f"当前病症: {', '.join(illness_strs)}")

    return "\n".join(parts)
