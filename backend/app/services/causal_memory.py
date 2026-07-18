# -*- coding: utf-8 -*-
"""事件观察记忆——只沉淀穿过证据地板的时序观察。

"上次你血糖高是因为聚餐" 这类记忆此前没系统化。本服务复用 personal_outcome 的
事件前后指标对比(get_event_impact),把"某事件后某指标显著变化"沉淀成 agent 可召回
的结构化记忆条,供 orchestrator memory 注入 / 对话引用。

诚实:这是**时序相关**记忆,不是因果结论。每一条都必须有事件前对照、
事件前窗口、事件后窗口的按指标有效样本和波动估计；任一条件缺失即不生成。
"""
from __future__ import annotations

import math
from typing import Any, Optional

from app.services.personal_models.intervention_priors import is_clinician_gated_metric

# 指标中文名 + 方向(True=越高越好)。与 metrics.HIGHER_IS_BETTER 同源语义。
_METRIC_META = {
    "hrv": ("HRV", True),
    "rhr": ("静息心率", False),
    "sleep_score": ("睡眠评分", True),
    "deep_sleep_min": ("深睡时长", True),
    "steps": ("步数", True),
}

# 观察条目的最低证据地板。达不到时宁可不说，也不能把噪声写成个人规律。
_MIN_PCT = 0.05
_MIN_SAMPLES = 5
_Z_95 = 1.96


def _metric_sample_count(impact: dict[str, Any], period: str, metric: str) -> Optional[int]:
    """读取按指标样本数；不接受旧的整窗行数作为替代。"""
    counts = impact.get("metric_samples")
    if not isinstance(counts, dict):
        return None
    period_counts = counts.get(period)
    if not isinstance(period_counts, dict):
        return None
    value = period_counts.get(metric)
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _noise_band(sd: Any, *, before_n: int, after_n: int, baseline_n: int) -> Optional[float]:
    """Difference-in-differences 的 95% 个体内噪声带。"""
    if isinstance(sd, bool):
        return None
    try:
        deviation = float(sd)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(deviation) or deviation < 0:
        return None
    standard_error = deviation * math.sqrt(
        1 / after_n + 4 / before_n + 1 / baseline_n
    )
    return _Z_95 * standard_error


def notes_from_impact(impact: dict[str, Any], min_pct: float = _MIN_PCT) -> list[dict[str, Any]]:
    """从完整事件观察产生非因果记忆条；证据不完整时 fail closed。"""
    title = impact.get("title") or "某次干预"
    before = impact.get("before") or {}
    after = impact.get("after") or {}
    baseline = impact.get("baseline") or {}
    noise = impact.get("noise") or {}
    notes: list[dict[str, Any]] = []
    for key, (zh, higher_better) in _METRIC_META.items():
        b, a, control = before.get(key), after.get(key), baseline.get(key)
        if b is None or a is None or control is None or b == 0:
            continue
        if is_clinician_gated_metric(key):
            continue
        before_n = _metric_sample_count(impact, "before", key)
        after_n = _metric_sample_count(impact, "after", key)
        baseline_n = _metric_sample_count(impact, "baseline", key)
        if any(count is None or count < _MIN_SAMPLES for count in (before_n, after_n, baseline_n)):
            continue
        band = _noise_band(
            noise.get(key),
            before_n=before_n,
            after_n=after_n,
            baseline_n=baseline_n,
        )
        if band is None:
            continue
        try:
            raw_delta = float(a) - float(b)
            control_delta = float(b) - float(control)
        except (TypeError, ValueError):
            continue
        net_delta = raw_delta - control_delta
        if abs(net_delta) <= band:
            continue
        pct = net_delta / abs(float(b))
        if abs(pct) < min_pct:
            continue
        toward_good = pct if higher_better else -pct
        direction = "改善" if toward_good > 0 else "走低"
        notes.append({
            "metric": key,
            "before": round(float(b), 1),
            "after": round(float(a), 1),
            "pct": round(pct, 3),
            "direction": direction,
            "evidence_tier": "observational",
            "text": (
                f"「{title}」前后观察窗内,{zh} 从 {round(float(b),1)} → {round(float(a),1)}"
                f";扣除事件前趋势后呈{direction}"
                f"({impact.get('window_days', 30)} 天窗口,相关非因果,数据不足以判断因果)"
            ),
        })
    return notes


def derive_causal_notes(db, user_id: int, max_events: int = 5, window_days: int = 30) -> dict[str, Any]:
    """扫用户近期事件,沉淀"事件×指标变化"记忆条(去标识,observational)。"""
    try:
        from app.services.personal_outcome_service import PersonalOutcomeService
    except Exception:  # noqa: BLE001
        return {"notes": [], "evidence_tier": "observational"}

    svc = PersonalOutcomeService()
    timeline = svc.get_timeline(db, user_id)
    events = (timeline or {}).get("events") if isinstance(timeline, dict) else None
    if not events:
        return {"notes": [], "evidence_tier": "observational",
                "claim_boundary": "无足够事件数据。"}

    all_notes: list[dict[str, Any]] = []
    for ev in events[:max_events]:
        eid = ev.get("id") if isinstance(ev, dict) else None
        if not eid:
            continue
        try:
            impact = svc.get_event_impact(db=db, user_id=user_id, event_id=eid, window_days=window_days)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(impact, dict) and "error" not in impact:
            all_notes.extend(notes_from_impact(impact))

    return {
        "notes": all_notes,
        "evidence_tier": "observational",
        "claim_boundary": (
            "仅展示具有按指标样本、事件前匹配对照和个体内噪声检验的时序观察;"
            "相关非因果,不替代医学结论。"
        ),
    }
