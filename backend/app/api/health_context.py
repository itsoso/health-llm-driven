"""健康上下文 API — 暴露交叉分析数据供内部 Agent/Skills 调用"""
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.daily_health import GarminData, DietRecord, WaterIntake
from app.models.weight import WeightRecord
from app.models.user_profile import UserProfile
from app.utils.timezone import get_china_today

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health-context", tags=["health-context"])


@router.get("/me/cross-analysis", summary="获取交叉分析数据")
async def get_cross_analysis(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    返回结构化的交叉分析数据：
    - 睡眠↔运动关联
    - 恢复就绪度
    - 能量平衡
    - 饮水充足度
    """
    today = get_china_today()
    seven_days_ago = today - timedelta(days=7)

    # 查询数据
    garmin = db.query(GarminData).filter(
        GarminData.user_id == current_user.id,
    ).order_by(GarminData.record_date.desc()).first()

    sleep_7days = db.query(GarminData).filter(
        GarminData.user_id == current_user.id,
        GarminData.record_date >= seven_days_ago,
    ).order_by(GarminData.record_date.desc()).all()

    diet_7d = db.query(DietRecord).filter(
        DietRecord.user_id == current_user.id,
        DietRecord.record_date >= seven_days_ago,
    ).all()

    water_today = db.query(WaterIntake).filter(
        WaterIntake.user_id == current_user.id,
        WaterIntake.record_date == today,
    ).all()
    water_today_ml = sum(w.amount for w in water_today) if water_today else 0

    weight = db.query(WeightRecord).filter(
        WeightRecord.user_id == current_user.id,
    ).order_by(WeightRecord.record_date.desc()).first()

    profile = db.query(UserProfile).filter(
        UserProfile.user_id == current_user.id,
    ).first()

    result = {}

    # 1. 睡眠↔运动关联
    sleep_exercise = _calc_sleep_exercise_correlation(sleep_7days)
    if sleep_exercise:
        result["sleep_exercise_correlation"] = sleep_exercise

    # 2. 恢复就绪度
    recovery = _calc_recovery_readiness(garmin)
    if recovery:
        result["recovery_readiness"] = recovery

    # 3. 能量平衡
    energy = _calc_energy_balance(diet_7d, weight, profile)
    if energy:
        result["energy_balance"] = energy

    # 4. 饮水充足度
    hydration = _calc_hydration(water_today_ml, garmin)
    if hydration:
        result["hydration"] = hydration

    return result


def _calc_sleep_exercise_correlation(sleep_7days):
    """睡眠↔运动关联分析"""
    if not sleep_7days or len(sleep_7days) < 3:
        return None

    active_deep = []
    rest_deep = []
    for r in sleep_7days:
        if r.deep_sleep_duration is not None:
            is_active = (r.steps and r.steps > 8000) or (r.active_minutes and r.active_minutes > 30)
            if is_active:
                active_deep.append(r.deep_sleep_duration)
            else:
                rest_deep.append(r.deep_sleep_duration)

    if not active_deep or not rest_deep:
        return None

    avg_active = sum(active_deep) / len(active_deep)
    avg_rest = sum(rest_deep) / len(rest_deep)
    diff = avg_active - avg_rest
    diff_pct = round(diff / avg_rest * 100) if avg_rest > 0 else 0

    return {
        "active_day_deep_sleep_avg_min": round(avg_active),
        "rest_day_deep_sleep_avg_min": round(avg_rest),
        "diff_min": round(diff),
        "diff_pct": diff_pct,
        "insight": f"活跃日深睡比静息日{'多' if diff > 0 else '少'}{abs(round(diff))}分钟({abs(diff_pct)}%)" if abs(diff) > 5 else "活跃日与静息日深睡差异不大",
    }


def _calc_recovery_readiness(garmin):
    """恢复就绪度计算"""
    if not garmin:
        return None

    factors = {}
    score = 0
    has_data = False

    if garmin.hrv and garmin.hrv_7day_avg and garmin.hrv_7day_avg > 0:
        hrv_ratio = garmin.hrv / garmin.hrv_7day_avg
        score += hrv_ratio * 40
        factors["hrv"] = "正常" if 0.85 <= hrv_ratio <= 1.15 else ("偏低" if hrv_ratio < 0.85 else "偏高")
        factors["hrv_value"] = garmin.hrv
        factors["hrv_7day_avg"] = round(garmin.hrv_7day_avg, 1)
        has_data = True

    if garmin.body_battery_most_charged:
        battery = garmin.body_battery_most_charged
        score += battery * 0.3
        factors["body_battery"] = "充足" if battery >= 60 else ("中等" if battery >= 30 else "不足")
        factors["body_battery_value"] = battery
        has_data = True

    if garmin.stress_level:
        stress = garmin.stress_level
        score += (100 - stress) * 0.3
        factors["stress"] = "低" if stress < 40 else ("中等" if stress < 60 else "偏高")
        factors["stress_value"] = stress
        has_data = True

    if not has_data:
        return None

    grade = "优秀" if score >= 80 else ("良好" if score >= 60 else ("一般" if score >= 40 else "较差"))
    suggestion = (
        "适合高强度训练" if score >= 70
        else ("建议中等强度运动" if score >= 50
              else "建议轻度活动或休息")
    )

    return {
        "score": round(score),
        "grade": grade,
        "factors": factors,
        "suggestion": suggestion,
    }


def _calc_energy_balance(diet_7d, weight, profile):
    """能量平衡计算"""
    if not diet_7d or not weight or not profile:
        return None
    if not profile.height_cm or not profile.birth_date:
        return None

    days_with_calories = {}
    for r in diet_7d:
        if r.calories:
            d = r.record_date
            days_with_calories[d] = days_with_calories.get(d, 0) + r.calories

    if len(days_with_calories) < 3:
        return None

    avg_intake = sum(days_with_calories.values()) / len(days_with_calories)
    w = weight.weight
    h = profile.height_cm
    age = (date.today() - profile.birth_date).days // 365

    if profile.gender == "male":
        bmr = 10 * w + 6.25 * h - 5 * age + 5
    else:
        bmr = 10 * w + 6.25 * h - 5 * age - 161

    tdee = bmr * 1.4
    gap = avg_intake - tdee

    return {
        "avg_intake_kcal": round(avg_intake),
        "estimated_bmr_kcal": round(bmr),
        "estimated_tdee_kcal": round(tdee),
        "daily_gap_kcal": round(gap),
        "direction": "surplus" if gap > 0 else "deficit",
        "days_with_data": len(days_with_calories),
    }


def _calc_hydration(water_today_ml, garmin):
    """饮水充足度"""
    is_active = garmin and garmin.active_minutes and garmin.active_minutes > 30
    target = 2500 if is_active else 2000

    return {
        "today_ml": water_today_ml,
        "target_ml": target,
        "is_active_day": bool(is_active),
        "remaining_ml": max(0, target - water_today_ml),
        "pct": round(water_today_ml / target * 100) if target > 0 else 0,
    }


@router.get("/me/summary", summary="紧凑健康摘要 — 给外部模板/LLM (替代逐日导出 JSON)")
def get_health_summary(
    detail: str = Query("standard", pattern="^(brief|standard|full)$"),
    format: str = Query("compact", pattern="^(compact|json)$"),
    max_chars: int = Query(3000, ge=300, le=8000),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """把 Digital Twin 压成一段紧凑摘要(现状 + 7/14/30 日均 + 封顶异常项/基因),
    给"健康建议"这类外部模板/LLM 用 —— 替代把整份 twin / 导出 JSON(2 万+ 字符)
    塞进 prompt 的做法(逐日流水账,LLM 看不过来、又贵又慢)。

    - detail: brief(~500 字符) / standard(~1.5k) / full(~3k) —— 控制异常项 + 基因条数
    - format: compact(纯文本 blob,直插模板) / json(结构化 {summary, chars, truncated})
    - max_chars: 硬上限,超出截断并标注,永不再炸上下文
    """
    from app.twin.builder import build_twin
    from app.twin.formatter import twin_to_prompt_blob

    twin = build_twin(db, current_user.id, use_cache=True)
    # detail → (max_abnormal, max_genes);封顶,异常项/基因不会无限堆长
    caps = {"brief": (3, 4), "standard": (5, 8), "full": (12, 15)}
    max_abn, max_genes = caps[detail]
    blob = twin_to_prompt_blob(twin, max_abnormal=max_abn, max_genes=max_genes) or "(暂无足够健康数据)"

    truncated = False
    if len(blob) > max_chars:
        blob = blob[:max_chars].rstrip() + "\n…(已截断;需要更多请提高 detail)"
        truncated = True

    if format == "json":
        return {"summary": blob, "detail": detail, "chars": len(blob), "truncated": truncated}
    return PlainTextResponse(blob)
