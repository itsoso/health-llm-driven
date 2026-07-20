"""
CGM 相关的 Safety Guardian 规则。

覆盖：
- 严重低血糖 (< 54)
- 严重高血糖 (> 250)
- TIR 过低（糖尿病管理目标 TIR > 70%）
- 变异系数过高 (CV > 36%)
- GLP-1 + CGM 低血糖风险升级
- 趋势急剧下降（double_down 且 < 80）
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.agents.safety_guardian.engine import register
from app.agents.safety_guardian.schema import Alert, Severity
from app.twin.schema import HealthTwin

# 急性血糖告警("立即就医/补糖")只在最近一次读数足够新鲜时触发。CGM 每 5–15min 一读,
# 读数 >60min 说明传感器离线或是补录的旧值,不代表"当前"状态。
_ACUTE_FRESH_MAX_MIN = 60


def _stale_for_acute(c) -> bool:
    """能证明读数陈旧(latest_measured_at 已知且 >60min)→ True,抑制急性告警。

    年龄未知(None)→ False(不抑制,保真阳性:宁可对未知年龄的极值告警,
    也不漏掉可能真实的急症)。修复:补录历史极值/传感器停同步的旧 spike 误触"立即就医"。
    """
    m = getattr(c, "latest_measured_at", None)
    if m is None:
        return False
    if m.tzinfo is None:
        m = m.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - m) > timedelta(minutes=_ACUTE_FRESH_MAX_MIN)


@register
def cgm_severe_hypoglycemia(twin: HealthTwin) -> Optional[Alert]:
    """最近一次读数 < 54 mg/dL (3.0 mmol/L) —— 严重低血糖。"""
    c = twin.cgm
    if not c.has_cgm or c.latest_mg_dl is None:
        return None
    if c.latest_mg_dl >= 54:
        return None
    if _stale_for_acute(c):
        return None

    return Alert(
        rule_id="cgm.severe_hypoglycemia",
        category="cgm",
        severity=Severity.CRITICAL,
        title="严重低血糖",
        message=(
            f"最近一次 CGM 读数 {c.latest_mg_dl:.0f} mg/dL ({c.latest_mg_dl/18:.1f} mmol/L)，"
            "低于严重低血糖阈值 54 mg/dL。此水平会导致认知损伤、意识丧失、抽搐。"
        ),
        action="立即摄入 15g 快速碳水（葡萄糖片 / 果汁 / 糖水），15 分钟后复测；仍低于 70 再次补给；若出现意识改变立即求助并拨打急救。",
        data_citation={"latest_mg_dl": c.latest_mg_dl, "trend": c.latest_trend_arrow},
        requires_medical_attention=True,
    )


@register
def cgm_severe_hyperglycemia(twin: HealthTwin) -> Optional[Alert]:
    """最近一次读数 > 250 mg/dL —— 严重高血糖。"""
    c = twin.cgm
    if not c.has_cgm or c.latest_mg_dl is None:
        return None
    if c.latest_mg_dl <= 250:
        return None
    if _stale_for_acute(c):
        return None

    severity = Severity.CRITICAL if c.latest_mg_dl > 300 else Severity.HIGH
    return Alert(
        rule_id="cgm.severe_hyperglycemia",
        category="cgm",
        severity=severity,
        title="严重高血糖",
        message=(
            f"最近一次 CGM 读数 {c.latest_mg_dl:.0f} mg/dL "
            f"({c.latest_mg_dl/18:.1f} mmol/L)。持续高血糖会增加糖尿病并发症"
            "（酮症酸中毒、肾损伤、神经病变）风险。"
        ),
        action=(
            "多饮水、避免再摄入高 GI 食物；如有胰岛素方案按医生指导补打；"
            "如伴有恶心呕吐、呼吸困难、腹痛、果香味呼吸（酮症征兆）立即就医。"
        ),
        data_citation={"latest_mg_dl": c.latest_mg_dl, "trend": c.latest_trend_arrow},
        requires_medical_attention=severity == Severity.CRITICAL,
    )


@register
def cgm_rapid_fall(twin: HealthTwin) -> Optional[Alert]:
    """CGM 趋势急速下降 + 当前值偏低 —— 即将低血糖。"""
    c = twin.cgm
    if not c.has_cgm or c.latest_mg_dl is None or not c.latest_trend_arrow:
        return None
    if _stale_for_acute(c):
        return None

    is_rapid_fall = c.latest_trend_arrow in ("double_down", "falling_rapidly", "↓↓")
    if not is_rapid_fall:
        return None

    if c.latest_mg_dl > 100:
        return None

    return Alert(
        rule_id="cgm.rapid_fall_approaching_low",
        category="cgm",
        severity=Severity.HIGH,
        title="血糖急速下降",
        message=(
            f"当前 {c.latest_mg_dl:.0f} mg/dL 且趋势箭头显示急速下降。"
            "按当前速率，预计 10-20 分钟内可能进入低血糖范围。"
        ),
        action="立即摄入 10-15g 快速碳水；若接下来要运动请推迟；15 分钟后复测。",
        data_citation={"latest_mg_dl": c.latest_mg_dl, "trend": c.latest_trend_arrow},
    )


@register
def cgm_tir_poor(twin: HealthTwin) -> Optional[Alert]:
    """Time In Range < 50% —— 血糖管理不佳。"""
    c = twin.cgm
    if not c.has_cgm or c.tir_24h_pct is None:
        return None
    if c.readings_count_24h < 48:  # 24h 至少 48 个读数（≈每半小时一次）才有代表性
        return None
    if c.tir_24h_pct >= 50:
        return None

    severity = Severity.HIGH if c.tir_24h_pct < 30 else Severity.MEDIUM

    return Alert(
        rule_id="cgm.tir_poor",
        category="cgm",
        severity=severity,
        title=f"TIR {c.tir_24h_pct:.0f}% — 血糖管理未达标",
        message=(
            f"过去 24 小时 Time In Range (70-180 mg/dL) 仅 {c.tir_24h_pct:.0f}%，"
            f"低于糖尿病管理目标 70%。高于 180 占 {c.time_above_24h_pct or 0:.0f}%，"
            f"低于 70 占 {c.time_below_24h_pct or 0:.0f}%。"
        ),
        action=(
            "检查最近饮食和运动记录，定位高/低血糖触发点；"
            "如在使用降糖药，联系处方医生调整剂量或方案。"
        ),
        data_citation={
            "tir_24h_pct": c.tir_24h_pct,
            "time_above_pct": c.time_above_24h_pct,
            "time_below_pct": c.time_below_24h_pct,
            "readings_count": c.readings_count_24h,
        },
    )


@register
def cgm_high_variability(twin: HealthTwin) -> Optional[Alert]:
    """变异系数 > 36% —— 血糖波动大。"""
    c = twin.cgm
    if not c.has_cgm or c.cv_24h_pct is None:
        return None
    if c.readings_count_24h < 48:
        return None
    if c.cv_24h_pct <= 36:
        return None

    return Alert(
        rule_id="cgm.high_variability",
        category="cgm",
        severity=Severity.MEDIUM,
        title=f"血糖变异系数 {c.cv_24h_pct:.0f}%",
        message=(
            "24 小时血糖变异系数 (CV) > 36%，说明血糖波动幅度大。"
            "高波动与心血管事件和微血管并发症风险升高相关，目标是 CV ≤ 36%。"
        ),
        action="识别波动触发因素：精制碳水餐、压力、睡眠不足、错过药物。考虑定时定量进餐和低 GI 饮食。",
        data_citation={"cv_24h_pct": c.cv_24h_pct, "mean_mg_dl": c.mean_24h_mg_dl},
    )


@register
def cgm_glp1_hypoglycemia_risk(twin: HealthTwin) -> Optional[Alert]:
    """GLP-1 + CGM 低血糖频发 —— 升级为高风险。"""
    c = twin.cgm
    if not c.has_cgm or c.time_below_24h_pct is None:
        return None
    if c.time_below_24h_pct < 4:  # 国际目标：< 4% 时间 below 70
        return None
    if c.readings_count_24h < 48:
        return None

    # 检查是否在用 GLP-1
    from app.agents.safety_guardian.rules.ddi import _has_drug_class, _med_names

    meds = _med_names(twin)
    glp1 = _has_drug_class(meds, "glp1")
    if not glp1:
        return None

    return Alert(
        rule_id="cgm.glp1_hypoglycemia_frequent",
        category="cgm",
        severity=Severity.HIGH,
        title="GLP-1 用药期间低血糖频发",
        message=(
            f"过去 24 小时有 {c.time_below_24h_pct:.0f}% 时间血糖 < 70 mg/dL，"
            f"超过国际目标 4%。你正在使用 GLP-1（{', '.join(set(glp1))}），"
            "合并其他降糖药或过度节食时低血糖风险更高。"
        ),
        action=(
            "与处方医生确认是否需要调整其他降糖药剂量；"
            "每餐保证 15-20g 复合碳水；运动前监测血糖；随身备快速碳水。"
        ),
        data_citation={
            "time_below_pct": c.time_below_24h_pct,
            "glp1_meds": glp1,
        },
        requires_medical_attention=True,
    )
