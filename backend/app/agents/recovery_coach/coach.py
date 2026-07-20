"""
Recovery Coach —— 恢复评分与行动建议。

Readiness score 算法（参考 WHOOP / Garmin Body Battery / HRV4Training 的加权组合）:
  0-100 分，60 以上可进行正常训练，85 以上可做高强度。

  组件权重：
    HRV 偏离   35%  （今日 HRV vs 7 日均值的相对差）
    睡眠质量   25%  （Garmin sleep score / 100 × 权重）
    睡眠时长   15%  （相对 7h 的比例，上限 1.15）
    Body Battery 15% （/100 × 权重）
    压力水平    10%  （反向：(100 - stress) / 100 × 权重）

  ACWR 惩罚：
    acwr > 1.5 扣 15；> 1.3 扣 8；< 0.5 不扣（恢复态）

缺数据时：该组件权重重新分摊到有数据的组件上，避免低估。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.orchestrator.schema import Intent, ProposedCard, SpecialistFinding
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


# ─────────────────────── 核心算法 ────────────────────────


@dataclass
class ReadinessBreakdown:
    score: int
    components: Dict[str, float]      # 每个组件的归一化得分 (0..1)
    weights_used: Dict[str, float]    # 实际使用的权重
    penalty: float                    # ACWR 惩罚
    missing_components: List[str]     # 缺数据的组件
    zone: str                         # rest / light / moderate / hard
    source: str = "computed"          # "garmin" (官方 readiness) / "computed" (自算)


_DEFAULT_WEIGHTS = {
    "hrv": 0.35,
    "sleep_quality": 0.25,
    "sleep_duration": 0.15,
    "body_battery": 0.15,
    "stress": 0.10,
}


def _safe(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _clip(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _hrv_component_from_series(nightly: List[Dict[str, Any]]) -> Optional[float]:
    """基于夜间 HRV 时序计算恢复得分（0..1）。

    规则：用最近一夜 HRV 与前 7 夜中位数的 z-score 做归一化。
    - z ≥ +1 (高于基线 1σ)      → 1.0
    - z = 0 (中位)               → 0.85
    - z = -1 (低于基线 1σ)       → 0.5
    - z ≤ -2 (远低于基线)        → 0.2

    至少需要 4 夜数据才可靠。
    """
    if not nightly or len(nightly) < 4:
        return None
    # 按日期升序，取最后一条做"今夜"，前面做 baseline
    sorted_ns = sorted(nightly, key=lambda x: x.get("date", ""))
    tonight = sorted_ns[-1].get("hrv_avg")
    if tonight is None:
        return None
    baseline_rows = sorted_ns[-8:-1] if len(sorted_ns) >= 5 else sorted_ns[:-1]
    baseline_vals = [r.get("hrv_avg") for r in baseline_rows if r.get("hrv_avg") is not None]
    if len(baseline_vals) < 3:
        return None

    # 中位数 + MAD (绝对偏差中位数) 代替 stdev（对离群值更鲁棒）
    baseline_vals_sorted = sorted(baseline_vals)
    median = baseline_vals_sorted[len(baseline_vals_sorted) // 2]
    mad = max(
        1e-3,
        sorted([abs(v - median) for v in baseline_vals])[len(baseline_vals) // 2],
    )
    z = (tonight - median) / (mad * 1.4826)  # 1.4826 = MAD → σ 校正因子

    if z >= 1:
        return 1.0
    if z <= -2:
        return 0.2
    # 线性插值：z=-2 → 0.2, z=0 → 0.85, z=+1 → 1.0
    if z >= 0:
        return 0.85 + (z / 1.0) * 0.15
    return 0.85 + (z / 2.0) * 0.65


def compute_readiness(twin: HealthTwin) -> ReadinessBreakdown:
    """对 Twin 计算 readiness 分数与分解。

    优先级:
    1. Garmin 官方 training_readiness_score (综合了 HRV/sleep/recovery_time/load, 比自算全面)
    2. 自算 5 维组合 (HRV/sleep_quality/sleep_duration/body_battery/stress)
    自算分解依然做, 用于分数解释 + 行动建议.
    """
    p = twin.physiological
    b = twin.behavioral

    components: Dict[str, Optional[float]] = {}

    # HRV — 优先用真时序（P2），fallback 到 hrv_latest/hrv_7d_avg
    # lazy import 避免循环引用 (config → orchestrator → ... → coach)
    try:
        from app.config import settings as _settings
        use_timeseries = getattr(_settings, "recovery_hrv_use_timeseries", True)
    except ImportError:
        use_timeseries = True
    nightly_series = getattr(p, "hrv_nightly_series", None) or []
    ts_score = _hrv_component_from_series(nightly_series) if use_timeseries else None

    if ts_score is not None:
        components["hrv"] = ts_score
    else:
        # 回退到旧逻辑：日均比值
        hrv_latest = _safe(p.hrv_latest)
        hrv_baseline = _safe(p.hrv_7d_avg)
        if hrv_latest is not None and hrv_baseline and hrv_baseline > 0:
            ratio = hrv_latest / hrv_baseline
            components["hrv"] = _clip(0.85 + (ratio - 1.0) * 1.5)
        elif hrv_latest is not None:
            components["hrv"] = _clip((hrv_latest - 20) / 60)
        else:
            components["hrv"] = None

    # 睡眠质量
    sleep_score = _safe(p.sleep_score_latest)
    components["sleep_quality"] = sleep_score / 100.0 if sleep_score is not None else None

    # 睡眠时长（7h = 1.0，5h = 0.4，9h = 1.1）
    sleep_h = _safe(p.sleep_duration_h_latest)
    if sleep_h is not None:
        components["sleep_duration"] = _clip((sleep_h - 4.0) / 3.5, 0.0, 1.15)
    else:
        components["sleep_duration"] = None

    # Body battery
    bb = _safe(p.body_battery_current)
    components["body_battery"] = bb / 100.0 if bb is not None else None

    # 压力（反向）
    stress = _safe(p.stress_level_current)
    components["stress"] = (100.0 - stress) / 100.0 if stress is not None else None

    # 权重再分配：缺数据的组件把权重分给剩下的
    used_weights: Dict[str, float] = {}
    missing: List[str] = []
    available_total = 0.0
    for name, weight in _DEFAULT_WEIGHTS.items():
        if components.get(name) is None:
            missing.append(name)
        else:
            available_total += weight

    if available_total <= 0:
        # 自算组件全缺, 但如果 Garmin 有 readiness 分数, 直接用它 — 不要 early return 成 unknown
        garmin_score_fallback = _safe(getattr(p, "training_readiness_score", None))
        if garmin_score_fallback is not None and 0 <= garmin_score_fallback <= 100:
            return ReadinessBreakdown(
                score=int(round(garmin_score_fallback)),
                components={},
                weights_used={},
                penalty=0.0,
                missing_components=list(_DEFAULT_WEIGHTS.keys()),
                zone=_readiness_zone(float(garmin_score_fallback), []),
                source="garmin",
            )
        return ReadinessBreakdown(
            score=0,
            components={},
            weights_used={},
            penalty=0.0,
            missing_components=list(_DEFAULT_WEIGHTS.keys()),
            zone="unknown",
        )

    score_raw = 0.0
    for name, weight in _DEFAULT_WEIGHTS.items():
        val = components.get(name)
        if val is None:
            continue
        used_weights[name] = weight / available_total
        score_raw += val * used_weights[name]

    # 0..1 → 0..100
    score = score_raw * 100.0

    # ACWR 惩罚
    acwr = _safe(b.acute_chronic_ratio)
    penalty = 0.0
    if acwr is not None:
        if acwr > 1.5:
            penalty = 15.0
        elif acwr > 1.3:
            penalty = 8.0
    score_final = _clip(score - penalty, 0.0, 100.0)

    # Garmin 官方 readiness 覆写 — 如果有就直接用它替代自算,保留分解作为解释.
    # Garmin 的 readiness 内部综合了 HRV / sleep 历史 / recovery_time / acute_load / HRV baseline
    # 比我们自算 5 维更全面,且用户已经在手表 UI 看到同一个数字,一致性重要.
    garmin_score = _safe(getattr(p, "training_readiness_score", None))
    if garmin_score is not None and 0 <= garmin_score <= 100:
        score_final = float(garmin_score)
        # 注意: zone 不传 missing — Garmin 分数自成一体 (它已经综合考虑 HRV/sleep/load),
        # 不能因为"我们自算路径的 HRV 组件没采到"就把 Garmin 的 zone 打成 unknown.
        # 传空 list 让 _readiness_zone 按 score 正常分档.
        zone = _readiness_zone(score_final, [])
        return ReadinessBreakdown(
            score=int(round(score_final)),
            components={k: round(v, 3) for k, v in components.items() if v is not None},
            weights_used={k: round(v, 3) for k, v in used_weights.items()},
            penalty=penalty,
            missing_components=missing,
            zone=zone,
            source="garmin",
        )

    zone = _readiness_zone(score_final, missing)

    return ReadinessBreakdown(
        score=int(round(score_final)),
        components={k: round(v, 3) for k, v in components.items() if v is not None},
        weights_used={k: round(v, 3) for k, v in used_weights.items()},
        penalty=penalty,
        missing_components=missing,
        zone=zone,
        source="computed",
    )


def _readiness_zone(score: float, missing: List[str]) -> str:
    # 数据严重缺失时保守
    if len(missing) >= 4:
        return "unknown"
    if score >= 85:
        return "hard"        # 可高强度
    if score >= 70:
        return "moderate"    # 可中等强度
    if score >= 55:
        return "light"       # 建议低强度/Z2
    return "rest"            # 建议完全恢复


# ─────────────────────── 建议生成 ────────────────────────


def _build_actions(breakdown: ReadinessBreakdown, twin: HealthTwin) -> List[str]:
    actions: List[str] = []
    zone = breakdown.zone

    # 1. 今日训练建议
    if zone == "hard":
        actions.append("今天身体状态很好，可以进行高强度训练（阈值跑/间歇/力量大重量）。")
    elif zone == "moderate":
        actions.append("今天适合中等强度有氧（Z2 慢跑 30-50 分钟）或中重量力量训练。")
    elif zone == "light":
        actions.append("今天建议低强度活动（Z1 快走、瑜伽、流动训练），避免大重量和高心率间歇。")
    elif zone == "rest":
        actions.append("今天身体恢复不足，建议完全休息或仅做 15-20 分钟拉伸/散步。")
    else:
        actions.append("数据不足以评估恢复状态，建议先同步 Garmin 数据再判断。")

    # 2. 针对性修复建议
    comp = breakdown.components
    if comp.get("sleep_duration") is not None and comp["sleep_duration"] < 0.7:
        sleep_h = twin.physiological.sleep_duration_h_latest
        actions.append(
            f"昨晚睡眠仅 {sleep_h:.1f}h，今晚至少 7.5h；提前 30 分钟关屏幕、保持卧室 18-20°C。"
            if sleep_h
            else "昨晚睡眠不足，今晚优先保证 7.5h 以上。"
        )

    if comp.get("sleep_quality") is not None and comp["sleep_quality"] < 0.6:
        actions.append("睡眠质量偏低，今天避免下午后饮用咖啡因，晚餐提前至睡前 3h 以前。")

    if comp.get("hrv") is not None and comp["hrv"] < 0.5:
        actions.append("HRV 明显低于基线，说明自主神经偏交感亢进。建议做 5 分钟 4-7-8 呼吸或正念。")

    if comp.get("stress") is not None and comp["stress"] < 0.4:
        actions.append("压力值偏高，安排一次主动恢复：15 分钟散步或冷水洗脸。")

    if breakdown.penalty >= 10:
        actions.append(
            f"急慢性负荷比偏高（ACWR 扣分 {int(breakdown.penalty)}），"
            "未来 3-5 天显著降低强度，避免伤病风险。"
        )

    # ── 暗信号点亮(纯叙事, 不进 readiness 评分; 全程 None-safe; 仍受下面 4 条上限约束) ──
    # 作息规律性: Garmin sleep consistency 0-100, <50 视为不规律. 仅当睡眠时长「已知且确实不短」时给——
    # 阈值取 component>=0.85(≈7h):低于此既可能命中上面的短睡建议(别叠加矛盾信息),也不该
    # 声称时长 OK(系统自己的短睡建议把目标设在 7.5h,故 7h 以下只说规律性会自相矛盾;时长未知同理跳过).
    consistency = _safe(twin.physiological.sleep_consistency_score)
    sleep_dur_comp = comp.get("sleep_duration")
    duration_known_ok = sleep_dur_comp is not None and sleep_dur_comp >= 0.85
    if consistency is not None and consistency < 50 and duration_known_ok:
        actions.append(
            f"睡眠时长尚可但作息不规律（一致性 {consistency:.0f}/100）：固定起床时间比补觉更能稳住"
            "自主神经；试着这两天同一时间起床,周末也别赖床太久。"
        )

    # readiness「为什么是这个数」: 用 Garmin 自己的判读(权威/与手表一致), 退而用语义明确的 sleepScore.
    driver = _readiness_driver_note(twin)
    if driver:
        actions.append(driver)

    return actions[:4]  # 限制 4 条，避免信息过载


def _readiness_driver_note(twin: HealthTwin) -> Optional[str]:
    """从 Garmin training_readiness_factors 取一条权威「为什么 readiness 是这个数」。

    优先用 Garmin 自己的 feedback 文案(权威、与手表显示一致、无单位歧义);退而用 sleepScore
    (语义明确的 0-100 贡献分)。**不解读 recoveryTime / hrvWeeklyAverage**——它们是原始厂商透传、
    单位不确定(分钟 vs 小时 / ms),数值化叙述会误述,故只在语义确定的字段上说话。

    全程 None-safe:非 dict / 缺键 / 字符串值 → 返回 None(省略该行),绝不抛——这里崩了会被
    specialist 的外层 except 吞成「恢复评估失败」,静默欠掉整份 recovery 教练(参见 swallow-points 教训)。
    """
    factors = getattr(twin.physiological, "training_readiness_factors", None)
    if not isinstance(factors, dict) or not factors:
        return None
    fb = factors.get("feedbackShort") or factors.get("feedbackLong")
    if isinstance(fb, str) and fb.strip():
        return f"Garmin 对今天 readiness 的判读：{fb.strip()}"
    sleep_score = _safe(factors.get("sleepScore"))
    if sleep_score is not None and sleep_score < 60:
        return (
            f"Garmin 拆解：睡眠对今天 readiness 的贡献偏低（睡眠分 {sleep_score:.0f}/100），"
            "优先补睡眠质量。"
        )
    return None


# ─────────────────────── 基因恢复修饰 ────────────────────────


def _gene_recovery_modifiers(twin: HealthTwin) -> List[Dict[str, Any]]:
    """从 Twin.genetic 派生恢复/炎症相关基因洞察。"""
    results: List[Dict[str, Any]] = []
    all_variants = (
        (twin.genetic.drug_sensitivity or [])
        + (twin.genetic.risk_variants or [])
        + (twin.genetic.protective_variants or [])
        + (twin.genetic.recovery_variants or [])
    )
    by_gene: Dict[str, Dict[str, Any]] = {}
    for v in all_variants:
        name = (v.get("gene_name") or "").upper()
        if name:
            by_gene.setdefault(name, v)

    il6 = by_gene.get("IL-6") or by_gene.get("IL6")
    if il6:
        geno = (il6.get("genotype") or "").upper()
        if "GG" in geno:
            results.append({"type": "gene_recovery", "gene": "IL-6", "profile": "高炎症反应型(GG)",
                "tip": "运动后炎症反应偏强→恢复时间建议比标准多20%→拉长恢复日间隔、增加抗炎食物(深海鱼/樱桃/姜黄)。",
                "recovery_modifier": 1.2})

    tnfa = by_gene.get("TNF-Α") or by_gene.get("TNF") or by_gene.get("TNFA")
    if tnfa and (tnfa.get("risk_level") or "").lower() in ("medium", "high"):
        results.append({"type": "gene_recovery", "gene": "TNF-α", "profile": "基础炎症偏高",
            "tip": "推荐抗炎饮食策略：ω-3(EPA+DHA≥2g/d)、姜黄素(500mg/d)、酸樱桃汁(运动后)。",
            "recovery_modifier": 1.15})

    sod2 = by_gene.get("SOD2")
    if sod2:
        geno = (sod2.get("genotype") or "").upper()
        if "VAL/VAL" in geno:
            results.append({"type": "gene_recovery", "gene": "SOD2", "profile": "抗氧化能力弱(Val/Val)",
                "tip": "线粒体超氧清除效率低→运动后氧化应激高→补充CoQ10(200mg/d)+NAC(600mg/d)+维C(500mg/d)。"})

    gpx1 = by_gene.get("GPX1")
    if gpx1 and (gpx1.get("risk_level") or "").lower() in ("medium", "high"):
        results.append({"type": "gene_recovery", "gene": "GPX1", "profile": "谷胱甘肽系统偏弱",
            "tip": "GPX1活性低→补充硒(200μg/d)+NAC(600mg/d)支持谷胱甘肽再生。"})

    gstp1 = by_gene.get("GSTP1")
    if gstp1 and (gstp1.get("risk_level") or "").lower() in ("medium", "high"):
        results.append({"type": "gene_recovery", "gene": "GSTP1", "profile": "解毒能力下降",
            "tip": "Phase II解毒酶效率低→增加十字花科蔬菜(西兰花/萝卜硫素)→减少环境毒素暴露。"})

    return results[:4]


# ─────────────────────── 可验证假设 (信任循环) ─────────────────


def _build_proposed_cards(breakdown: ReadinessBreakdown, twin: HealthTwin) -> List[ProposedCard]:
    """根据 readiness 状态产出最多 1 张可验证假设卡片.

    触发条件:
      - readiness >= 70 且 HRV 稳定 → forecast: "未来 3 天 HRV 保持稳定" (pure prediction, 不需用户做事)
      - readiness < 60 且 HRV 在 baseline 之下 → "增加睡眠 7 天验证 HRV 回升"
      - readiness < 50 且 sleep < 6h → "保证 7+ 小时睡眠 5 天"
    """
    cards: List[ProposedCard] = []
    p = twin.physiological
    score = breakdown.score
    zone = breakdown.zone

    if zone == "unknown":
        return cards  # 数据不全, 没法押任何注

    hrv_latest = getattr(p, "hrv_latest", None)
    hrv_baseline = getattr(p, "hrv_7d_avg", None)

    # 高分稳定态 (zone='hard' / 'moderate' / score>=70): 押 forecast — 纯预测, 不要求用户做事
    if score >= 70:
        if hrv_latest is not None and hrv_baseline is not None and hrv_latest >= hrv_baseline * 0.9:
            # 设 floor target = max(baseline*0.9, hrv_latest - 5)
            floor = max(int(hrv_baseline * 0.9), int(hrv_latest) - 5)
            cards.append(ProposedCard(
                title=f"AI 预测: 未来 3 天 HRV 保持 ≥ {floor}",
                content=(
                    f"## AI 预测\n\n"
                    f"**当前**: HRV {hrv_latest:.0f}ms（7 日均值 {hrv_baseline:.0f}ms）, readiness={score}\n"
                    f"**预测**: 3 天后 HRV ≥ {floor}ms\n\n"
                    f"这是一条 *纯预测* — 不需要你做任何事, AI 押注当前轨迹将延续.\n"
                    f"3 天后系统自动评分. 命中率会写到 Specialist scorecard.\n"
                ),
                metric_key="hrv",
                baseline_value=f"{hrv_latest:.0f}",
                target_value=f">{floor}",
                verification_days=3,
                card_type="forecast",
                priority=8,  # 比 plan 低 — 状态好的时候不该挤掉真问题
            ))
        return cards  # 状态好, 只有可能的 forecast, 不生成 plan

    # 主卡: HRV 回升 (最常见场景)
    if hrv_latest is not None and hrv_baseline is not None and hrv_latest < hrv_baseline:
        target = max(int(hrv_baseline), int(hrv_latest) + 5)
        cards.append(ProposedCard(
            title=f"7 天恢复实验：HRV 从 {hrv_latest:.0f} 回升到 ≥ {target}",
            content=(
                f"## 7 天恢复实验\n\n"
                f"**起点**: 当前 HRV {hrv_latest:.0f}ms（7 日均值 {hrv_baseline:.0f}ms）\n"
                f"**目标**: 7 天后 HRV ≥ {target}ms\n\n"
                f"### 行动\n"
                f"- 每晚 22:30 前上床，目标 7.5h 睡眠\n"
                f"- 训练强度降到 light（zone 1-2 有氧 30 分钟内）\n"
                f"- 睡前 1h 不看屏幕\n"
                f"- 限酒精 / 咖啡因 14:00 后停\n\n"
                f"7 天后系统会自动用 Garmin HRV 数据评分。"
            ),
            metric_key="hrv",
            baseline_value=f"{hrv_latest:.0f}",
            target_value=f">{target}",
            verification_days=7,
            card_type="plan",
            priority=15,
        ))
    elif zone == "rest":
        # 没 HRV 数据但 zone=rest, 押睡眠分
        sleep_score = getattr(p, "sleep_score_latest", None) or 60
        target = min(80, sleep_score + 15)
        cards.append(ProposedCard(
            title=f"5 天睡眠修复：sleep_score 从 {sleep_score} 提升到 ≥ {target}",
            content=(
                f"## 5 天睡眠修复实验\n\n"
                f"**起点**: 最近睡眠分 {sleep_score}/100\n"
                f"**目标**: 5 天后 sleep_score ≥ {target}\n\n"
                f"### 行动\n"
                f"- 固定 23:00 前上床\n"
                f"- 卧室温度 19-21°C\n"
                f"- 训练后到睡眠间隔 ≥ 3h\n"
                f"- 不在床上看手机\n"
            ),
            metric_key="sleep_score",
            baseline_value=str(sleep_score),
            target_value=f">{target}",
            verification_days=5,
            card_type="plan",
            priority=12,
        ))

    return cards


# ─────────────────────── Specialist 适配器 ────────────────────


class RecoveryCoachSpecialist:
    """Orchestrator 的 Recovery Coach 适配器。"""

    name = "recovery_coach"
    category = "recovery"

    TRIGGER_KEYWORDS = {
        "恢复", "累", "疲劳", "疲惫", "睡", "睡眠",
        "hrv", "休息", "精力", "状态", "readiness",
        "能不能训练", "今天能跑",
        "sleep", "recover", "fatigue", "rest", "tired",
    }

    def applies_to(self, intent: Intent, twin: HealthTwin) -> bool:
        if "recovery" in intent.categories:
            return True
        q = (intent.raw_query or "").lower()
        if any(k in q for k in self.TRIGGER_KEYWORDS):
            return True
        # 兜底：如果 Twin 里生理数据齐全，让 coach 主动参与（user 的 dashboard 场景）
        p = twin.physiological
        if p.hrv_latest is not None and p.sleep_score_latest is not None:
            return "general" in intent.categories
        return False

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        t0 = time.monotonic()
        try:
            breakdown = compute_readiness(twin)
            actions = _build_actions(breakdown, twin)

            findings: List[Dict[str, Any]] = [
                {
                    "type": "readiness_score",
                    "score": breakdown.score,
                    "zone": breakdown.zone,
                    "source": breakdown.source,  # garmin / computed — UI 可以展示 "Garmin 官方分"
                    "components": breakdown.components,
                    "weights_used": breakdown.weights_used,
                    "penalty": breakdown.penalty,
                    "missing": breakdown.missing_components,
                }
            ]
            for i, action in enumerate(actions, 1):
                findings.append({
                    "type": "action",
                    "order": i,
                    "text": action,
                })

            # 基因恢复修饰
            gene_mods = _gene_recovery_modifiers(twin)
            findings.extend(gene_mods)

            # 概括
            if breakdown.zone == "unknown":
                summary = "恢复状态未知（数据不足）"
            else:
                zone_zh = {
                    "hard": "状态极佳，可高强度训练",
                    "moderate": "状态良好，适合中等训练",
                    "light": "状态一般，建议低强度",
                    "rest": "恢复不足，建议休息",
                }[breakdown.zone]
                prefix = "Garmin Readiness" if breakdown.source == "garmin" else "Readiness"
                summary = f"{prefix} {breakdown.score}/100 — {zone_zh}"

            proposed_cards = _build_proposed_cards(breakdown, twin)

            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=summary,
                findings=findings,
                raw={
                    "score": breakdown.score,
                    "zone": breakdown.zone,
                    "components": breakdown.components,
                    "penalty": breakdown.penalty,
                },
                ms_elapsed=int((time.monotonic() - t0) * 1000),
                proposed_cards=proposed_cards,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[recovery_coach] run failed: {e}")
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=f"恢复评估失败: {e}",
                findings=[],
                raw={"error": str(e)},
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )
