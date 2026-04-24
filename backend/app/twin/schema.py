"""
Digital Health Twin schema — 一切 agent 共享的"用户当下健康状态"视图。

设计原则：
- 全部字段 Optional，缺数据不报错，静默降级
- 按"语义分区"组织（physiological/body/labs/meds/...），不按数据源
- 简单类型优先（float/int/str/list/dict），避免复杂嵌套
- 派生字段（如 bmi_category/acwr_zone）在 builder 里计算好，不让下游重复算
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────── Meta ──────────────────────────────────


class TwinMeta(BaseModel):
    """构建元信息 — 用于调试 + 前端展示数据新鲜度。"""

    user_id: int
    generated_at: datetime
    data_sources: List[str] = Field(default_factory=list)  # 实际有数据的来源
    build_ms: int = 0
    cache_status: str = "miss"  # hit / miss / partial


# ──────────────────────────── Physiological ────────────────────────────


class PhysiologicalState(BaseModel):
    """生理状态 —— 即时值 + 短期均值。"""

    # HRV / 心率
    hrv_latest: Optional[float] = None
    hrv_7d_avg: Optional[float] = None
    hrv_status: Optional[str] = None  # 偏低 / 中等 / 良好
    resting_hr: Optional[int] = None

    # HRV 逐夜时序（P2: RecoveryCoach 用这个算真 baseline/trend）
    # 最近 N 夜的夜间平均 HRV（从 hrv_readings 表聚合）
    # 元素: {"date": "2026-04-23", "hrv_avg": 48.2, "count": 92}
    hrv_nightly_series: List[Dict[str, Any]] = Field(default_factory=list)

    # 睡眠
    sleep_score_latest: Optional[int] = None
    sleep_duration_h_latest: Optional[float] = None
    sleep_deep_h_avg_14d: Optional[float] = None
    sleep_consistency_score: Optional[float] = None

    # 能量 / 压力
    body_battery_current: Optional[int] = None
    stress_level_current: Optional[int] = None

    # 有氧 / 活动
    steps_today: Optional[int] = None
    spo2_avg: Optional[float] = None
    spo2_min_overnight: Optional[int] = None
    spo2_odi: Optional[float] = None
    spo2_below_90_pct: Optional[float] = None
    vo2max_running: Optional[float] = None
    vo2max_cycling: Optional[float] = None

    last_updated: Optional[date] = None


# ───────────────────────── Body Composition ────────────────────────────


class BodyCompositionState(BaseModel):
    weight_kg: Optional[float] = None
    bmi: Optional[float] = None
    bmi_category: Optional[str] = None  # 体重过低 / 正常 / 超重 / 肥胖
    body_fat_pct: Optional[float] = None
    bmr_kcal: Optional[float] = None
    tdee_kcal: Optional[float] = None
    last_weighed: Optional[date] = None


# ─────────────────────────── Labs / Biomarkers ─────────────────────────


class LabsContext(BaseModel):
    total_cholesterol: Optional[float] = None
    ldl: Optional[float] = None
    hdl: Optional[float] = None
    triglycerides: Optional[float] = None
    blood_glucose: Optional[float] = None
    hba1c: Optional[float] = None

    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None
    blood_pressure_date: Optional[date] = None

    last_exam_date: Optional[date] = None
    last_exam_type: Optional[str] = None
    flagged_abnormal: List[Dict[str, Any]] = Field(default_factory=list)
    # 每项 {item_name, value, unit, reference_range, exam_date}


class CgmContext(BaseModel):
    """CGM 连续血糖监测状态。"""

    has_cgm: bool = False
    latest_mg_dl: Optional[float] = None
    latest_trend_arrow: Optional[str] = None
    latest_measured_at: Optional[datetime] = None

    # 24h 摘要
    mean_24h_mg_dl: Optional[float] = None
    std_24h_mg_dl: Optional[float] = None
    cv_24h_pct: Optional[float] = None
    tir_24h_pct: Optional[float] = None         # Time in Range 70-180
    time_below_24h_pct: Optional[float] = None  # < 70
    time_above_24h_pct: Optional[float] = None  # > 180
    gmi_estimated_a1c: Optional[float] = None   # Glucose Management Indicator
    severe_low_count_24h: int = 0
    severe_high_count_24h: int = 0
    readings_count_24h: int = 0


# ─────────────────────────── Medication / Supplement ───────────────────


class MedicationState(BaseModel):
    active_meds: List[Dict[str, Any]] = Field(default_factory=list)
    # 单项 schema 来自 MedicationService.get_today_status()
    adherence_7d_pct: Optional[float] = None
    has_any: bool = False


class SupplementState(BaseModel):
    active_supplements: List[Dict[str, Any]] = Field(default_factory=list)
    # {id, name, dosage, timing, taken}
    taken_today_count: int = 0
    total_active_count: int = 0


# ─────────────────────────── Genetic ───────────────────────────────────


class GeneticContext(BaseModel):
    has_profile: bool = False
    total_variants: int = 0
    drug_sensitivity: List[Dict[str, Any]] = Field(default_factory=list)
    risk_variants: List[Dict[str, Any]] = Field(default_factory=list)
    protective_variants: List[Dict[str, Any]] = Field(default_factory=list)
    cognition_variants: List[Dict[str, Any]] = Field(default_factory=list)
    personality_variants: List[Dict[str, Any]] = Field(default_factory=list)
    sleep_variants: List[Dict[str, Any]] = Field(default_factory=list)
    recovery_variants: List[Dict[str, Any]] = Field(default_factory=list)
    exercise_variants: List[Dict[str, Any]] = Field(default_factory=list)
    nutrition_variants: List[Dict[str, Any]] = Field(default_factory=list)


# ─────────────────────────── Environmental ─────────────────────────────


class EnvironmentalState(BaseModel):
    city: Optional[str] = None
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    weather_description: Optional[str] = None
    aqi: Optional[int] = None
    aqi_level: Optional[str] = None
    pm25: Optional[float] = None
    uv_index: Optional[float] = None
    outdoor_exercise_suitability: Optional[str] = None  # suitable / caution / avoid


# ─────────────────────────── Behavioral ────────────────────────────────


class BehavioralState(BaseModel):
    # 饮食今日
    diet_calories_today: Optional[float] = None
    diet_protein_g_today: Optional[float] = None
    diet_carbs_g_today: Optional[float] = None
    diet_fat_g_today: Optional[float] = None
    meals_logged_today: int = 0

    # 饮水
    water_ml_today: int = 0
    water_goal_ml: int = 2000
    water_progress_pct: float = 0.0

    # 训练
    workouts_this_week: int = 0
    training_load_7d: Optional[float] = None
    acute_chronic_ratio: Optional[float] = None
    acwr_zone: Optional[str] = None  # under / optimal / risky

    # 鼻炎打卡
    nasal_wash_count_today: int = 0
    sneeze_count_today: int = 0


# ─────────────────────────── Mental ────────────────────────────────────


class MentalState(BaseModel):
    mood_7d_avg: Optional[float] = None
    energy_7d_avg: Optional[float] = None
    stress_7d_avg: Optional[float] = None
    sleep_quality_7d_avg: Optional[float] = None
    recent_journal_themes: List[str] = Field(default_factory=list)


# ─────────────────────────── Chronic / Goals ───────────────────────────


class ChronicConditionState(BaseModel):
    active_conditions: List[str] = Field(default_factory=list)
    rhinitis_today: Dict[str, Any] = Field(default_factory=dict)
    # {nasal_wash_count, sneeze_count, daily_score, ...}


class GoalsContext(BaseModel):
    active_goals: List[Dict[str, Any]] = Field(default_factory=list)
    active_goals_count: int = 0


# ─────────────────────────── Freshness ─────────────────────────────────


class DataFreshness(BaseModel):
    garmin: Optional[str] = None
    weight: Optional[str] = None
    labs: Optional[str] = None
    diet: Optional[str] = None
    genetic: Optional[str] = None
    medication: Optional[str] = None


# ─────────────────────────── HealthTwin (root) ─────────────────────────


class HealthTwin(BaseModel):
    """
    Digital Health Twin —— 用户当前健康状态的结构化快照。

    用法：
        from app.twin import build_twin
        twin = build_twin(db, user_id)
        twin.physiological.hrv_latest   # → 42.0
        twin.medication.active_meds     # → [...]
    """

    meta: TwinMeta
    physiological: PhysiologicalState = Field(default_factory=PhysiologicalState)
    body_composition: BodyCompositionState = Field(default_factory=BodyCompositionState)
    labs: LabsContext = Field(default_factory=LabsContext)
    cgm: CgmContext = Field(default_factory=CgmContext)
    medication: MedicationState = Field(default_factory=MedicationState)
    supplement: SupplementState = Field(default_factory=SupplementState)
    genetic: GeneticContext = Field(default_factory=GeneticContext)
    gene_config: Optional[Any] = None  # GeneConfig dataclass, built post-init
    environment: EnvironmentalState = Field(default_factory=EnvironmentalState)
    behavioral: BehavioralState = Field(default_factory=BehavioralState)
    mental: MentalState = Field(default_factory=MentalState)
    chronic: ChronicConditionState = Field(default_factory=ChronicConditionState)
    goals: GoalsContext = Field(default_factory=GoalsContext)
    freshness: DataFreshness = Field(default_factory=DataFreshness)
