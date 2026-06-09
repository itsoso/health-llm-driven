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


def fetch_vo2max(db: Session, user_id: int, end_date: date) -> Optional[float]:
    """VO2max (mL/kg/min) — 抗衰第二信号, 运动 N-of-1 outcome(越高越好)。
    VO2max 变化慢, 用 90 天窗口取最近有值的一天(不取 3 天均值)。"""
    start = end_date - timedelta(days=90)
    row = (
        db.query(GarminData)
        .filter(
            GarminData.user_id == user_id,
            GarminData.vo2max_running.isnot(None),
            GarminData.record_date >= start,
            GarminData.record_date <= end_date,
        )
        .order_by(desc(GarminData.record_date))
        .first()
    )
    if row is None or row.vo2max_running is None:
        return None
    return float(row.vo2max_running)


def fetch_fitness_age(db: Session, user_id: int, end_date: date) -> Optional[float]:
    """Garmin 体能年龄(岁)— 越低越好。90 天窗口取最近有值的一天。"""
    start = end_date - timedelta(days=90)
    row = (
        db.query(GarminData)
        .filter(
            GarminData.user_id == user_id,
            GarminData.vo2max_fitness_age.isnot(None),
            GarminData.record_date >= start,
            GarminData.record_date <= end_date,
        )
        .order_by(desc(GarminData.record_date))
        .first()
    )
    if row is None or row.vo2max_fitness_age is None:
        return None
    return float(row.vo2max_fitness_age)


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
    return _fetch_lab_item(db, user_id, end_date, ["fasting%glucose", "空腹血糖"])


def _fetch_lab_item(
    db: Session, user_id: int, end_date: date, name_patterns: list,
    days_window: int = 30,
) -> Optional[float]:
    """通用化验项取数. days_window 默认 30 天 (微营养窗口宽)."""
    try:
        from app.models.medical_exam import MedicalExamItem, MedicalExamRecord
    except ImportError:
        return None
    start = end_date - timedelta(days=days_window)
    for pat in name_patterns:
        item = (
            db.query(MedicalExamItem)
            .join(MedicalExamRecord, MedicalExamRecord.id == MedicalExamItem.exam_record_id)
            .filter(
                MedicalExamRecord.user_id == user_id,
                MedicalExamRecord.exam_date >= start,
                MedicalExamRecord.exam_date <= end_date,
                MedicalExamItem.item_name.ilike(f"%{pat}%"),
            )
            .order_by(desc(MedicalExamRecord.exam_date))
            .first()
        )
        if item is not None and item.value is not None:
            try:
                return float(item.value)
            except (ValueError, TypeError):
                continue
    return None


# ── 饮食 / 饮水 / 补剂依从 (2026-05-12 P1.2 加, 闭环 weekly_advisor 这类卡) ──


def fetch_hydration_ml(db: Session, user_id: int, end_date: date) -> Optional[float]:
    """当日饮水总量 (ml). 用 end_date 当天数据, 不取均值 (饮水按日目标判断)."""
    try:
        from app.models.daily_health import WaterIntake
    except ImportError:
        return None
    rows = (
        db.query(WaterIntake)
        .filter(
            WaterIntake.user_id == user_id,
            WaterIntake.record_date == end_date,
        )
        .all()
    )
    if not rows:
        return None
    return float(sum(r.amount_ml or 0 for r in rows))


def fetch_calories_intake(db: Session, user_id: int, end_date: date) -> Optional[float]:
    """当日总摄入卡路里 (kcal). 取 end_date 当天 DietRecord 求和."""
    try:
        from app.models.daily_health import DietRecord
    except ImportError:
        return None
    rows = (
        db.query(DietRecord)
        .filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date == end_date,
        )
        .all()
    )
    if not rows:
        return None
    total = sum((r.calories or 0) for r in rows)
    return float(total) if total > 0 else None


def fetch_supplement_adherence_pct(
    db: Session, user_id: int, end_date: date,
) -> Optional[float]:
    """近 7 天补剂依从率 (%). 取 SupplementIntake 实际服用记录数 / (active_supplements×7).

    无法精确知道 active_supplements 数量, 用 medications 表里 category='保健品' 的
    active 行数估算; 兜底 8 (常见用户配置).
    """
    try:
        from app.models.daily_health import SupplementIntake
        from app.models.medication import Medication
    except ImportError:
        return None

    start = end_date - timedelta(days=6)
    intake_count = (
        db.query(SupplementIntake)
        .filter(
            SupplementIntake.user_id == user_id,
            SupplementIntake.record_date >= start,
            SupplementIntake.record_date <= end_date,
        )
        .count()
    )
    if intake_count == 0:
        return 0.0

    active_supps = (
        db.query(Medication)
        .filter(
            Medication.user_id == user_id,
            Medication.is_active.is_(True) if hasattr(Medication, "is_active") else True,
        )
        .count()
    ) or 8
    expected = active_supps * 7
    pct = min(100.0, (intake_count / expected) * 100)
    return round(pct, 1)


# ── 微营养化验项 (P2 SupplementAdvisor 12 周试验主用) ──


def fetch_hcy(db, user_id, end_date):
    """同型半胱氨酸 (μmol/L) — MTHFR 试验主指标."""
    return _fetch_lab_item(db, user_id, end_date, ["homocysteine", "同型半胱氨酸", "Hcy"])


def fetch_vitamin_d(db, user_id, end_date):
    return _fetch_lab_item(db, user_id, end_date, ["vitamin d", "25-OH", "维生素D", "维D"])


def fetch_b12(db, user_id, end_date):
    return _fetch_lab_item(db, user_id, end_date, ["B12", "vitamin B12", "维生素B12", "钴胺"])


def fetch_ferritin(db, user_id, end_date):
    return _fetch_lab_item(db, user_id, end_date, ["ferritin", "铁蛋白"])


def fetch_ldl(db, user_id, end_date):
    return _fetch_lab_item(db, user_id, end_date, ["LDL", "低密度脂蛋白"])


def fetch_hba1c(db, user_id, end_date):
    return _fetch_lab_item(db, user_id, end_date, ["HbA1c", "糖化血红蛋白"])


def fetch_phenotypic_age(db: Session, user_id: int, end_date: date) -> Optional[float]:
    """生物年龄 (PhenoAge, 岁) — 抗衰 N-of-1 的 outcome 指标。

    取用户最新一次"完整"血检 + 实足年龄重算 PhenoAge。12 周复检后即拿到
    干预后的身体年龄,与 baseline 比较得 improved/worsened(越低越好)。
    9 项血检任一缺失 → None(不猜算);无新复检 → 与基线相同(unchanged,诚实)。
    单位映射复用 phenoage.phenoage_from_labs(单一来源,杜绝单位手抄)。
    """
    try:
        from app.twin import _collectors
        from app.services.phenoage import phenoage_from_labs
    except ImportError:
        return None
    labs = _collectors.fetch_latest_labs(db, user_id)
    if not labs:
        return None
    age = _collectors.fetch_user_age(db, user_id)
    result = phenoage_from_labs(labs, age)
    return result.phenotypic_age if result else None


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
    "spo2": fetch_spo2_avg,  # alias
    "spo2_odi": fetch_spo2_avg,
    "fasting_glucose": fetch_fasting_glucose,
    "blood_glucose": fetch_fasting_glucose,
    # 2026-05-12 P1.2 — 饮食/饮水/补剂依从 闭环
    "hydration_ml": fetch_hydration_ml,
    "calories_intake": fetch_calories_intake,
    "supplement_adherence_pct": fetch_supplement_adherence_pct,
    # 微营养化验 (SupplementAdvisor 12 周试验)
    "hcy": fetch_hcy,
    "homocysteine": fetch_hcy,
    "vitamin_d": fetch_vitamin_d,
    "vd": fetch_vitamin_d,
    "b12": fetch_b12,
    "ferritin": fetch_ferritin,
    "ldl": fetch_ldl,
    "hba1c": fetch_hba1c,
    # 抗衰 N-of-1 — 生物年龄 (PhenoAge)
    "phenotypic_age": fetch_phenotypic_age,
    "biological_age": fetch_phenotypic_age,  # alias
    # 抗衰第二信号 — 心肺适能
    "vo2max": fetch_vo2max,
    "fitness_age": fetch_fitness_age,
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
    "spo2": True,
    "spo2_odi": False,  # ODI 是低氧指数, 反向
    "rhr": False,
    "resting_hr": False,
    "weight": False,
    "systolic_bp": False,
    "diastolic_bp": False,
    "bp": False,
    "fasting_glucose": False,
    "blood_glucose": False,
    # P1.2 新加
    "hydration_ml": True,             # 喝够水 = 好
    "calories_intake": True,          # 默认假设朝目标摄入 (减脂场景在 grade 时按用户目标重写)
    "supplement_adherence_pct": True,
    # 微营养
    "hcy": False,                     # 同型半胱氨酸越低越好
    "homocysteine": False,
    "vitamin_d": True,
    "vd": True,
    "b12": True,
    "ferritin": True,                 # 在正常范围内越高越好 (女性贫血避免)
    "ldl": False,
    "hba1c": False,
    # 生物年龄越低越好
    "phenotypic_age": False,
    "biological_age": False,
    # VO2max 越高越好;体能年龄越低越好
    "vo2max": True,
    "fitness_age": False,
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
