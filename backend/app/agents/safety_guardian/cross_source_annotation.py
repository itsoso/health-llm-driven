"""跨源可疑读数 → 安全告警附加复测提示(R3 多源置信度的「安全层」消费)。

`twin.physiological.divergent_metrics` 已由 builder 回灌(CrossSourceValidator 检测
Garmin/Apple Watch/RingConn 同指标差异过大);agenda 已消费成 data_quality 提示,但
**安全告警此前完全无视它** —— 一条依据可疑读数的 vitals 急症告警不带任何「这数可能是
设备误差,先复测」的上下文。本模块补这一段。

**安全不变量(under-alarm 防线,blocking review 重点)**:
- **只加不减**:只在 `Alert.message` 尾部追加一句 caveat + 在 `data_citation` 记一条溯源;
  **绝不改 severity / 不删告警 / 不改条数 / 不改顺序**。可疑值可能仍是真值,降级=under-alarm
  (见 `spo2_min_needs_sustained_corroboration` / `safety_dedup_additive_not_subtractive`)。
- **保守映射(精确 rule_id 白名单,fail-closed)**:只认「告警的真实输入指标 == 跨源比对指标」
  的 4 条规则(见 `_RULE_TO_METRIC`)。**新增规则默认不标**,需显式登记 —— 避免给一条其实没
  跨源依据的告警贴「可疑」误导标。关键反例(双评审实锤):`spo2_osa_screening`/
  `spo2_min_nocturnal_severe`/`spo2_sustained_low_overnight` 这 3 条吃的是 ODI / 夜间最低 /
  below90%,**不是** 跨源比对的 `spo2_avg`,绝不能因 `spo2_avg` 设备分歧给这些被佐证的真 OSA
  CRITICAL 贴「复测」标(=误导性 under-alarm)。BP 单源、sleep(偏的是 sleep_score≠时长)、
  stress(不跨源比对)同理排除。
- **幂等**:重复调用不重复追加(认 CAVEAT_MARKER)。
- **失败安全**:任何异常 → 原样返回 alerts(不反噬已产出的告警)。
"""
from __future__ import annotations

import logging
from typing import List

from app.agents.safety_guardian.schema import Alert
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)

# 标记串:用于幂等判断 + 测试断言(出现在 caveat 文案最前面)。
CAVEAT_MARKER = "⚠️ 跨设备校验"

# 精确 rule_id → 该规则真实输入指标对应的跨源比对 key(device_comparison_service._COMPARE_METRICS)。
# **白名单、fail-closed**:只登记「告警输入指标 == 跨源比对指标」的规则;前缀匹配会误伤
# (spo2_osa_screening/min_nocturnal/sustained 吃 ODI/min/below90,非 spo2_avg —— 故不在表内)。
# 注:rhr 规则读 twin.physiological.resting_hr,与跨源 key `resting_heart_rate` 同一物理量。
_RULE_TO_METRIC = {
    "vitals.rhr_tachycardia": "resting_heart_rate",
    "vitals.rhr_bradycardia": "resting_heart_rate",
    "vitals.spo2_severe_hypoxia": "spo2_avg",
    "vitals.spo2_mild_hypoxia": "spo2_avg",
}


def _metric_for_rule(rule_id: str) -> str | None:
    """登记在白名单里的规则 → 其跨源指标;其余(含未来新规则)→ None(不标)。"""
    return _RULE_TO_METRIC.get(rule_id)


def annotate_cross_source_suspect(alerts: List[Alert], twin: HealthTwin) -> List[Alert]:
    """对依据跨源可疑指标的 vitals 告警,**原地**在 message 追加复测提示。返回同一 list。

    只加不减:severity / 条数 / 顺序 / rule_id 一律不动。
    """
    try:
        divs = getattr(getattr(twin, "physiological", None), "divergent_metrics", None) or []
        if not alerts or not divs:
            return alerts
        by_metric = {d.metric: d for d in divs}

        for a in alerts:
            metric = _metric_for_rule(a.rule_id)
            if metric is None:
                continue
            div = by_metric.get(metric)
            if div is None:
                continue
            if CAVEAT_MARKER in a.message:  # 幂等
                continue
            caveat = (
                f"{CAVEAT_MARKER}:{div.hint} "
                f"本提醒所依据的「{div.label}」可能受设备读数差异影响,"
                f"建议复测确认后再判断(本提醒未因此降级,仍按原级别提示)。"
            )
            a.message = f"{a.message}\n\n{caveat}"
            a.data_citation = {
                **(a.data_citation or {}),
                "cross_source_suspect": {
                    "metric": metric,
                    "label": div.label,
                    "outlier_source": div.outlier_source,
                    "trusted_source": div.trusted_source,
                    "deviation_pct": div.deviation_pct,
                },
            }
        return alerts
    except Exception as e:  # noqa: BLE001 — 标注失败绝不能吞掉/破坏已产出的告警
        logger.warning("[safety.cross_source_annotation] 标注失败,原样返回告警: %s", e)
        return alerts
