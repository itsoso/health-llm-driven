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
    # 本次构建中抛异常被降级跳过的分区名 (如 "sleep_deep")。**关键信号**,与 safety
    # engine 的 `failed_rule_count` 同一口径:各 _fill_* 的 try/except 吞异常保护 Twin
    # 韧性(一个分区崩不该打死整个 Twin),但吞掉后该分区字段全 None、`data_sources` 里
    # 也不会出现对应源 —— 与「用户本来就没这项数据」在结果上**完全不可分辨**。
    # sleep_deep 正是这样静默死了 5 周(生产 698 次/24h AttributeError 没人发现)。
    # 语义: 分区名在此 list 里 = 「该分区评估失败,状态未知」,≠「无数据」。
    failed_partitions: List[str] = Field(default_factory=list)


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

    # Garmin 官方 Training Readiness (P1a 已采, 现在接入 Twin)
    # score 0-100, level: poor/low/moderate/high/prime
    training_readiness_score: Optional[int] = None
    training_readiness_level: Optional[str] = None
    training_readiness_date: Optional[date] = None  # readiness 来自哪天(可能非今天:同步延迟/昨晚没同步)→ 据此判新鲜度,避免旧分当今日
    training_readiness_factors: Optional[Dict[str, Any]] = None  # hrvWeeklyAverage/sleepScore/recoveryTime 等分解

    # 有氧 / 活动
    steps_today: Optional[int] = None
    spo2_avg: Optional[float] = None
    spo2_min_overnight: Optional[int] = None
    spo2_odi: Optional[float] = None
    spo2_below_90_pct: Optional[float] = None
    vo2max_running: Optional[float] = None
    vo2max_cycling: Optional[float] = None
    vo2max_fitness_age: Optional[int] = None  # Garmin 体能年龄(心肺) — 抗衰第二信号,可对比实足年龄

    # 夜间呼吸 (2026-05-07 接入 Garmin respiration_samples) —
    # OSAHS 筛查信号: 夜间 avg rate + 变异度 (stddev). 正常 12-20 brpm,
    # 变异大 (stddev>3) 结合 SpO2 dip 是呼吸暂停前兆.
    respiration_nightly_avg: Optional[float] = None    # 昨夜 22:00-07:00 平均
    respiration_nightly_stddev: Optional[float] = None  # 同时间窗标准差
    respiration_nightly_samples: int = 0                # 样本数 (判断数据可靠)

    # ECG (Apple Watch 独有, 房颤筛查信号非诊断) — 供 SafetyGuardian + agent 读.
    # ecg_classification: 最近一次 HealthKit 原样分类字符串.
    # afib_recent: 最近一次分类是否为 AtrialFibrillation (或 afib_event_count>=1).
    # afib_event_count: 最近一次上送窗口内的房颤分类次数.
    ecg_classification: Optional[str] = None
    ecg_recorded_at: Optional[datetime] = None
    afib_recent: bool = False
    afib_event_count: int = 0

    last_updated: Optional[date] = None

    # P4 多源合并: 每字段的 winning data_source. 用于 LLM source-aware prompting
    # (e.g. "HRV 来自 oura,可信度高于 Watch 数据"). 仅当多源数据存在时填充.
    field_sources: Dict[str, str] = Field(default_factory=dict)

    # Phase 0 个人基线: per-metric 滚动基线 + 当前值偏离 (z-score) + 趋势。
    # "你现在 vs 你自己的历史" (≠ #149 跨源差异)。由 personal_baseline service 算,
    # builder 填充。冷启动不足的指标不产出 (别拿 3 天当基线误导)。
    # 单项 schema 见 PersonalBaselineMetric。
    personal_baselines: List["PersonalBaselineMetric"] = Field(default_factory=list)

    # R3 多源置信度回灌: 跨设备(Garmin/Apple Watch/RingConn 等)同指标一致性,构 Twin 时算一次写进来,
    # 让决策灯/specialist/agenda 统一消费(而非各自重算)。仅多源(≥2)用户填充。
    # device_agreement_index: 0–1,越高越一致(None=单源,置信度退回只看 source)。
    device_agreement_index: Optional[float] = None
    device_sources: List[str] = Field(default_factory=list)
    divergent_metrics: List["CrossSourceDivergence"] = Field(default_factory=list)


class CrossSourceDivergence(BaseModel):
    """单指标跨源偏离(超阈值)—— 由 cross_source_validator.flag_outliers 投影。

    用于 agenda 生成 data_quality 提示(R3:冲突降置信不平均,暂以高优先级源为准),
    以及 prompt blob 让 agent source-aware。不做诊断,只标「这个数可疑、暂以谁为准」。
    """
    metric: str
    label: str
    trusted_source: str          # 暂以谁为准
    outlier_source: str          # 偏离最大的源
    deviation_pct: float         # outlier 相对各源均值偏离 %
    hint: str                    # 人话描述


class PersonalBaselineMetric(BaseModel):
    """单指标个人滚动基线 + 偏离 (Phase 0, 纯统计)。

    见 app/services/personal_baseline.py。``low_side_only`` 指标 (如 SpO2)
    只在低侧标 deviation。
    """

    key: str                                 # hrv / resting_heart_rate / spo2_avg / ...
    label: str                               # 中文标签
    unit: str = ""
    baseline_mean: float
    baseline_std: float
    n_days: int                              # 基线有效天数
    latest: Optional[float] = None
    latest_date: Optional[str] = None        # ISO date
    z: Optional[float] = None                # (latest - mean) / std
    trend: Optional[str] = None              # rising / falling / stable
    is_deviation: bool = False               # |z| >= 阈值 (low_side 仅低侧)
    low_confidence: bool = False             # 有效天数偏少, agent 应保守措辞
    message: Optional[str] = None            # 人话描述 (仅 deviation 时)


# ───────────────────────── Body Composition ────────────────────────────


class BodyCompositionState(BaseModel):
    weight_kg: Optional[float] = None
    waist_cm: Optional[float] = None
    waist_to_height_ratio: Optional[float] = None
    central_obesity_flag: Optional[bool] = None
    bmi: Optional[float] = None
    bmi_category: Optional[str] = None  # 体重过低 / 正常 / 超重 / 肥胖
    body_fat_pct: Optional[float] = None
    bmr_kcal: Optional[float] = None
    tdee_kcal: Optional[float] = None
    last_weighed: Optional[date] = None
    last_waist_measured: Optional[date] = None


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

    # 肝肾功能 (cross-review 用 — 高蛋白 vs 肾, 药物代谢 vs 肝)
    alt: Optional[float] = None             # ALT (谷丙转氨酶)
    ast: Optional[float] = None
    ggt: Optional[float] = None
    creatinine: Optional[float] = None      # μmol/L
    egfr: Optional[float] = None            # eGFR mL/min/1.73m²
    uric_acid: Optional[float] = None

    # PhenoAge 输入项 (Levine 2018) — 单位严格对齐 app/services/phenoage.py:
    #   albumin g/L · crp mg/dL · lymphocyte/rdw % · mcv fL · alp U/L · wbc 10⁹/L
    # 中国体检报告默认单位通常已对齐,例外: CRP 常报 mg/L (需 ÷10), albumin 偶报 g/dL。
    # 当前 collector 直存原始数值,不做单位转换 — 错单位 → phenoage 失真 (跟踪在 design-longevity-mvp §3.2)。
    albumin: Optional[float] = None         # 白蛋白 g/L
    crp: Optional[float] = None             # CRP mg/dL (hs-CRP)
    lymphocyte_pct: Optional[float] = None  # 淋巴细胞百分比 %
    mcv: Optional[float] = None             # 红细胞平均体积 fL
    rdw: Optional[float] = None             # 红细胞分布宽度 %
    alp: Optional[float] = None             # 碱性磷酸酶 U/L
    wbc: Optional[float] = None             # 白细胞 10⁹/L

    # 血常规 CBC (blood_routine 深度评估 + red_cell_elevation 安全规则的消费源)。
    hemoglobin: Optional[float] = None      # HGB 血红蛋白 g/L
    hematocrit: Optional[float] = None      # HCT 红细胞压积 %
    rbc: Optional[float] = None             # RBC 红细胞计数 10¹²/L
    platelet: Optional[float] = None        # PLT 血小板计数 10⁹/L
    mch: Optional[float] = None             # MCH 平均血红蛋白量 pg
    mchc: Optional[float] = None            # MCHC 平均血红蛋白浓度 g/L
    neutrophil_pct: Optional[float] = None  # NEUT% 中性粒细胞百分比 %

    # PhenoAge 派生 (twin/builder 在所有 9 项 + age 齐时调用 compute_phenoage 填充)。
    # 缺任一输入 → 全部留 None,不猜算。证据等级独立于 EpigeneticState (后者 experimental,
    # PhenoAge 是 validated)。展示侧必须同时呈现 claim_boundary 文案。
    phenotypic_age: Optional[float] = None
    phenotypic_age_delta_years: Optional[float] = None  # = phenotypic_age - 实足年龄
    phenotypic_age_inputs_complete: Optional[bool] = None
    phenoage_evidence_tier: Optional[str] = None        # "validated"
    phenoage_claim_boundary: Optional[str] = None

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
    # "在服"分段(加法字段,2026-07-03):is_active 语义是"在库未归档",不是
    # "正在服用"—— 二者混淆曾让 LLM 把 24 种库存说成"你目前有 24 种补剂"
    # (红参适用性分析 case)。在服 = 近 taking_window_days 天有 taken 打卡。
    # 安全规则(DSI)仍用全量 active_supplements(加层不减层,不收窄安全输入)。
    taking_recent_count: int = 0
    taking_recent_names: List[str] = Field(default_factory=list)
    taking_window_days: int = 14


# ─────────────────────────── Genetic ───────────────────────────────────


class GeneticContext(BaseModel):
    has_profile: bool = False
    total_variants: int = 0
    # 异步解析: PDF 上传后 1-3 分钟内 has_profile=True 但 total_variants 可能为 0
    # specialist 看到该字段时应回 "解析中, 稍后补充" 而不是 "用户没有基因数据"
    pending_profile_count: int = 0
    # Phase 1 (基因解读): 每个 variant dict 由 builder._classify_genetic_variants
    # 注入两维静态分级 (genetic_registry.classify_variant, 不靠 LLM):
    #   "actionability"  ∈ {act, risk_stratify, de_emphasize}
    #   "evidence_grade" ∈ {cpic_a, pharmgkb_1a, clinvar_path_confirm,
    #                        clinvar_likely, gwas_association, proxy_uncertain}
    # 这是给 dict 加键 (沿用 #205/#199 的加字段方式), 不改分区结构/数量。
    drug_sensitivity: List[Dict[str, Any]] = Field(default_factory=list)
    risk_variants: List[Dict[str, Any]] = Field(default_factory=list)
    protective_variants: List[Dict[str, Any]] = Field(default_factory=list)
    cognition_variants: List[Dict[str, Any]] = Field(default_factory=list)
    personality_variants: List[Dict[str, Any]] = Field(default_factory=list)
    sleep_variants: List[Dict[str, Any]] = Field(default_factory=list)
    recovery_variants: List[Dict[str, Any]] = Field(default_factory=list)
    exercise_variants: List[Dict[str, Any]] = Field(default_factory=list)
    nutrition_variants: List[Dict[str, Any]] = Field(default_factory=list)


class EpigeneticState(BaseModel):
    """Experimental methylation-clock feedback for long-horizon trajectory use."""

    has_methylation_report: bool = False
    status: str = "missing"
    evidence_tier: str = "experimental"
    confidence: str = "low"
    claim_boundary: str = (
        "甲基化时钟只作为长期代理指标和研究性反馈, "
        "不能证明个体短期干预成效或真实衰老速度改变。"
    )
    latest_test_date: Optional[str] = None
    vendor: Optional[str] = None
    clock_type: Optional[str] = None
    biological_age: Optional[float] = None
    biological_age_delta_years: Optional[float] = None
    pace_of_aging: Optional[float] = None
    raw_summary: Dict[str, Any] = Field(default_factory=dict)


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
    diet_sodium_mg_today: Optional[float] = None
    high_sodium_foods_today: List[str] = Field(default_factory=list)
    meals_logged_today: int = 0

    # 饮水
    water_ml_today: int = 0
    water_goal_ml: int = 2000
    water_progress_pct: float = 0.0

    # 训练 (聚合)
    workouts_this_week: int = 0
    training_load_7d: Optional[float] = None
    acute_chronic_ratio: Optional[float] = None
    acwr_zone: Optional[str] = None  # under / optimal / risky

    # Garmin 官方 Training Status (P1a 已采, 现在接入 Twin)
    # productive / maintaining / detraining / overreaching / peaking / recovery / unproductive
    training_status: Optional[str] = None
    training_status_feedback: Optional[str] = None
    acute_load: Optional[float] = None  # Garmin 急性负荷 (7d)
    load_ratio: Optional[float] = None  # Garmin 官方 ACWR (跟我们自算对照)

    # 训练 (细粒度, 近 7 天 — 每条 = 一次 WorkoutRecord 摘要)
    # 用于 movement_coach / fuel_strategist 基于真实训练细节判断
    recent_workouts: List["WorkoutSummary"] = Field(default_factory=list)

    # 鼻炎打卡
    nasal_wash_count_today: int = 0
    sneeze_count_today: int = 0


class ProblemRedLine(BaseModel):
    """用户已登记 HealthProblem 的个性化红线(命中症状即升级)。

    由 builder 从未 resolved(active + monitoring)的 HealthProblem.red_lines 投影到 Twin,供 safety
    规则 problem_red_lines.py 把当前症状文本与每条 condition 做关键词匹配。
    这让安全网随用户的具体病情(如胃溃疡黑便/呕血)个性化,而非只有通用急症规则。
    """
    problem_name: str
    condition: str          # 触发短语,如 "黑便/呕血"
    action: str             # 命中动作,如 "立即就医/急诊"
    risk_level: str = "P1"  # 来源 problem 的 P0/P1/P2


class AcuteHealthState(BaseModel):
    """急性病/近期症状状态，用于安全兜底运动、睡眠和用药建议。"""

    has_active_illness: bool = False
    illness_names: List[str] = Field(default_factory=list)
    illness_severity_max: Optional[int] = None
    recent_symptoms: List[str] = Field(default_factory=list)
    # 近 72h **全部**症状描述(未按呼吸道过滤),供 symptoms.py 症状级红线做关键词匹配。
    # recent_symptoms 只含呼吸道/感冒(给训练兜底);这条是完整集合(给急症识别)。
    symptom_texts_all: List[str] = Field(default_factory=list)
    suspected_cold: bool = False
    fever_reported: bool = False
    should_rest_from_training: bool = False
    training_guardrail: Optional[str] = None
    # 用户已登记健康问题的个性化红线(builder 从 active HealthProblem 投影)
    problem_red_lines: List["ProblemRedLine"] = Field(default_factory=list)
    # 待校验的 AI 生成指导/总结文本(R4):仅由 guidance 校验路径(如餐食监控 finish)
    # 临时塞入,供 safety rules guidance_red_lines.py 扫描量化处方/命令式越界。
    # builder 永远不填充它 —— 默认空 = 全部存量 safety 评估路径行为零变化。
    pending_guidance_texts: List[str] = Field(default_factory=list)


class WorkoutSummary(BaseModel):
    """单次 WorkoutRecord 的 LLM-friendly 摘要 (近 7 天填充).

    剔除原 WorkoutRecord 的 GPS / AI analysis 等大字段, 保留训练科学关键指标.
    """
    workout_date: Optional[str] = None     # ISO date
    workout_type: Optional[str] = None     # running / swimming / cycling / hiit / strength / ...
    duration_min: Optional[float] = None
    distance_km: Optional[float] = None
    calories: Optional[int] = None

    # 心率 & 区间
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    hr_zone_dominant: Optional[int] = None  # 1-5, 哪个 zone 停留最长
    hr_zone_minutes: Optional[Dict[str, float]] = None  # {"z1": 5.2, "z2": 12.8, ...}

    # 训练效果
    training_effect_aerobic: Optional[float] = None   # 0-5
    training_effect_anaerobic: Optional[float] = None  # 0-5
    training_load: Optional[int] = None

    # 主观
    perceived_exertion: Optional[int] = None  # 1-10
    feeling: Optional[str] = None              # great / good / normal / tired / exhausted

    # 跑/走/骑
    avg_cadence: Optional[int] = None
    avg_power_watts: Optional[int] = None
    elevation_gain_m: Optional[float] = None


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
    waist: Optional[str] = None
    blood_pressure: Optional[str] = None
    sleep: Optional[str] = None
    labs: Optional[str] = None
    diet: Optional[str] = None
    genetic: Optional[str] = None
    epigenetic: Optional[str] = None
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
    epigenetic: EpigeneticState = Field(default_factory=EpigeneticState)
    gene_config: Optional[Any] = None  # GeneConfig dataclass, built post-init
    environment: EnvironmentalState = Field(default_factory=EnvironmentalState)
    behavioral: BehavioralState = Field(default_factory=BehavioralState)
    acute: AcuteHealthState = Field(default_factory=AcuteHealthState)
    mental: MentalState = Field(default_factory=MentalState)
    chronic: ChronicConditionState = Field(default_factory=ChronicConditionState)
    goals: GoalsContext = Field(default_factory=GoalsContext)
    freshness: DataFreshness = Field(default_factory=DataFreshness)
