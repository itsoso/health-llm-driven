"""metric_fetchers —— P5-2 N-of-1 验证用的 metric 取数适配器.

每个函数返回 user 在 [start, end] 窗口的指标值 (mean / latest), 没数据返 None.
窗口策略: 取 verify_window 末尾 3 天均值, 单点波动不算 (噪声大).

支持的 metric_key (覆盖 weekly_advisor 默认建议范围):
- hrv / hrv_7d_avg
- sleep_score
- rhr (resting_hr)
- weight
- systolic_bp / diastolic_bp / bp (复合)
- spo2_avg
- fasting_glucose
"""

import logging
from datetime import date, timedelta
from typing import Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.daily_health import GarminData

logger = logging.getLogger(__name__)

# 末尾窗口取 N 天均值, 防单点抖
TAIL_DAYS = 3


def _avg(values):
    nums = [v for v in values if v is not None]
    return sum(nums) / len(nums) if nums else None


def _fetch_garmin_field(
    db: Session, user_id: int, field_name: str, end_date: date,
) -> Optional[float]:
    """通用: 拿 GarminData 末尾 TAIL_DAYS 天里某字段的均值."""
    start = end_date - timedelta(days=TAIL_DAYS - 1)
    rows = (
        db.query(GarminData)
        .filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start,
            GarminData.record_date <= end_date,
        )
        .order_by(desc(GarminData.record_date))
        .all()
    )
    if not rows:
        return None
    return _avg(getattr(r, field_name, None) for r in rows)


def fetch_hrv(db: Session, user_id: int, end_date: date) -> Optional[float]:
    """HRV (ms) — 优先 hrv_7day_avg, 否则末尾 3 天 hrv 均值."""
    val = _fetch_garmin_field(db, user_id, "hrv_7day_avg", end_date)
    if val is not None:
        return val
    return _fetch_garmin_field(db, user_id, "hrv", end_date)


def fetch_sleep_score(db: Session, user_id: int, end_date: date) -> Optional[float]:
    return _fetch_garmin_field(db, user_id, "sleep_score", end_date)


def fetch_rhr(db: Session, user_id: int, end_date: date) -> Optional[float]:
    return _fetch_garmin_field(db, user_id, "resting_heart_rate", end_date)


def fetch_spo2_avg(db: Session, user_id: int, end_date: date) -> Optional[float]:
    return _fetch_garmin_field(db, user_id, "spo2_avg", end_date)


def fetch_weight(db: Session, user_id: int, end_date: date) -> Optional[float]:
    """体重 (kg) — WeightRecord 末尾 3 天均值."""
    try:
        from app.models.basic_health import WeightRecord
    except ImportError:
        return None
    start = end_date - timedelta(days=TAIL_DAYS - 1)
    rows = (
        db.query(WeightRecord)
        .filter(
            WeightRecord.user_id == user_id,
            WeightRecord.record_date >= start,
            WeightRecord.record_date <= end_date,
        )
        .all()
    )
    if not rows:
        return None
    return _avg(r.weight for r in rows)


def fetch_systolic_bp(db: Session, user_id: int, end_date: date) -> Optional[float]:
    """收缩压 (mmHg) — BloodPressureRecord 末尾 3 天均值."""
    try:
        from app.models.basic_health import BloodPressureRecord
    except ImportError:
        return None
    start = end_date - timedelta(days=TAIL_DAYS - 1)
    rows = (
        db.query(BloodPressureRecord)
        .filter(
            BloodPressureRecord.user_id == user_id,
            BloodPressureRecord.record_date >= start,
            BloodPressureRecord.record_date <= end_date,
        )
        .all()
    )
    if not rows:
        return None
    return _avg(r.systolic for r in rows)


def fetch_diastolic_bp(db: Session, user_id: int, end_date: date) -> Optional[float]:
    try:
        from app.models.basic_health import BloodPressureRecord
    except ImportError:
        return None
    start = end_date - timedelta(days=TAIL_DAYS - 1)
    rows = (
        db.query(BloodPressureRecord)
        .filter(
            BloodPressureRecord.user_id == user_id,
            BloodPressureRecord.record_date >= start,
            BloodPressureRecord.record_date <= end_date,
        )
        .all()
    )
    if not rows:
        return None
    return _avg(r.diastolic for r in rows)


def fetch_bp_composite(db: Session, user_id: int, end_date: date) -> Optional[float]:
    """复合 BP — 用 systolic 作主指标 (临床更重要)."""
    return fetch_systolic_bp(db, user_id, end_date)


def fetch_fasting_glucose(db: Session, user_id: int, end_date: date) -> Optional[float]:
    """空腹血糖 — 从 medical_exam_items 拉, 找最近的 fasting_glucose 项."""
    try:
        from app.models.medical_exam import MedicalExamItem, MedicalExamRecord
    except ImportError:
        return None
    start = end_date - timedelta(days=14)  # 化验窗口宽一些, 14 天内任一 fasting_glucose
    item = (
        db.query(MedicalExamItem)
        .join(MedicalExamRecord, MedicalExamRecord.id == MedicalExamItem.exam_record_id)
        .filter(
            MedicalExamRecord.user_id == user_id,
            MedicalExamRecord.exam_date >= start,
            MedicalExamRecord.exam_date <= end_date,
            MedicalExamItem.item_name.ilike("%fasting%glucose%"),
        )
        .order_by(desc(MedicalExamRecord.exam_date))
        .first()
    )
    if item is None or item.value is None:
        return None
    try:
        return float(item.value)
    except (ValueError, TypeError):
        return None


# ── 注册表: metric_key → fetcher ───────────────────────────────────────
FETCHERS = {
    "hrv": fetch_hrv,
    "hrv_7d_avg": fetch_hrv,
    "sleep_score": fetch_sleep_score,
    "rhr": fetch_rhr,
    "resting_hr": fetch_rhr,
    "weight": fetch_weight,
    "systolic_bp": fetch_systolic_bp,
    "diastolic_bp": fetch_diastolic_bp,
    "bp": fetch_bp_composite,
    "spo2_avg": fetch_spo2_avg,
    "spo2_odi": fetch_spo2_avg,  # 同源, 复用
    "fasting_glucose": fetch_fasting_glucose,
    "blood_glucose": fetch_fasting_glucose,
}


def fetch_metric(
    db: Session, user_id: int, metric_key: str, end_date: date,
) -> Optional[float]:
    """统一入口. 不支持的 metric_key 返 None."""
    fn = FETCHERS.get((metric_key or "").lower())
    if fn is None:
        return None
    try:
        return fn(db, user_id, end_date)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[metric_fetcher] {metric_key} user={user_id} 失败: {e}")
        return None


# ── outcome 判定: improved / unchanged / worsened ────────────────────
# higher_is_better=True → 上升好 (HRV/sleep_score/spo2)
# higher_is_better=False → 下降好 (RHR/weight/BP/FBG)
HIGHER_IS_BETTER = {
    "hrv": True,
    "hrv_7d_avg": True,
    "sleep_score": True,
    "spo2_avg": True,
    "spo2_odi": False,  # ODI 是低氧指数, 反向
    "rhr": False,
    "resting_hr": False,
    "weight": False,
    "systolic_bp": False,
    "diastolic_bp": False,
    "bp": False,
    "fasting_glucose": False,
    "blood_glucose": False,
}

# 变化阈值: ≥5% 朝目标方向 = improved, ≥5% 反方向 = worsened
EFFECT_THRESHOLD = 0.05


def grade_outcome(
    metric_key: str,
    baseline_value: Optional[str],
    actual_value: Optional[float],
) -> Tuple[str, Optional[float]]:
    """返回 (outcome, effect_size).

    outcome: improved / unchanged / worsened / inconclusive
    effect_size: (actual - baseline) / baseline, 标准化方向: 正 = 朝目标方向
    """
    if actual_value is None or baseline_value is None:
        return ("inconclusive", None)
    try:
        baseline = float(baseline_value)
    except (ValueError, TypeError):
        return ("inconclusive", None)
    if baseline == 0:
        return ("inconclusive", None)

    delta = (actual_value - baseline) / baseline
    higher_better = HIGHER_IS_BETTER.get((metric_key or "").lower(), False)
    # 如果 lower_is_better, delta 取反 让 effect_size 正 = 改善
    effect = delta if higher_better else -delta

    if effect >= EFFECT_THRESHOLD:
        return ("improved", round(effect, 4))
    if effect <= -EFFECT_THRESHOLD:
        return ("worsened", round(effect, 4))
    return ("unchanged", round(effect, 4))
