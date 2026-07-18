# -*- coding: utf-8 -*-
"""因果记忆(RFC 方向二)—— 从"事件 × 指标变化"沉淀可召回的记忆条。

"上次你血糖高是因为聚餐" 这类记忆此前没系统化。本服务复用 personal_outcome 的
事件前后指标对比(get_event_impact),把"某事件后某指标变化"沉淀成 agent 可召回
的结构化记忆条,供 orchestrator memory 注入 / 对话引用。

诚实地板(2026-06-27 加固):原实现只要 |相对变化| ≥ 5% 就出"改善/走低"条 —— 没有
显著性门、没有匹配对照窗口、没有回归均值收缩。在嘈杂的自记录序列上这等于把噪声和
均值回归当成"X 改善了 Y",直接侵蚀因果账本护城河赖以成立的信任。现在每条记忆必须穿过:

  1. 样本地板:before/after 每侧天数 ≥ ``_MIN_SAMPLES``(1 天 vs 1 天的纯噪声不出条)。
  2. 匹配对照:用事件前等长对照窗口做 difference-in-differences,扣掉事件前既有趋势。
  3. 回归均值:对照后效应再朝零保守折减 ``_RTM_SHRINK``。
  4. 噪声带:折减后效应须超过个体内变异 —— 日间 SD 的两均值差标准误 ×1.96(95%);
     无 SD 时退回人群参考变化值 RCV%(见 ``intervention_significance``)。
  5. 实用显著:相对变化须 ≥ ``min_pct``。
  6. 处方/激素门控:与两个 N-of-1 估计器(treatment_effect / effect_estimator)共用
     ``intervention_priors.is_clinician_gated_metric`` 这一**单一事实源** —— 这类指标
     永不在此下"改善/走低"方向(only-downgrade-never-upgrade,基因无关)。

这是**时序相关**记忆(事件先于变化),**非证明因果**;evidence_tier=observational,
文案严格 observational("相关非因果"/"数据不足以判断因果"),不出现"因为/有效"。
"""
from __future__ import annotations

import math
from typing import Any, Optional

from app.services.intervention_significance import rcv_pct
from app.services.personal_models.intervention_priors import is_clinician_gated_metric

# 指标中文名 + 方向(True=越高越好)。与 metrics.HIGHER_IS_BETTER 同源语义。
_METRIC_META = {
    "hrv": ("HRV", True),
    "rhr": ("静息心率", False),
    "sleep_score": ("睡眠评分", True),
    "deep_sleep_min": ("深睡时长", True),
    "steps": ("步数", True),
}

# ── 诚实地板常量 ──────────────────────────────────────────────────────────────
_MIN_PCT = 0.05       # 实用显著性最低相对变化(避免大样本下统计显著但无实际意义的微变)
_MIN_SAMPLES = 5      # 每个窗口最少天数(杀掉 1天vs1天 / 稀疏窗口的伪归因)
_Z = 1.96             # 95% 双向
_RTM_SHRINK = 0.8     # 回归均值保守折减:噪声自记录序列的观测变化里一部分是均值回归,
                      # 即便扣掉线性趋势仍先朝零收缩再下判断(humility factor,非标定系数)


def _noise_band(
    sd: Optional[float], nb: Optional[int], na: Optional[int],
    before_mean: float, metric_code: str,
) -> float:
    """信号必须超过的个体内噪声带宽(绝对值)。

    有日间 SD → 两均值差的标准误 × Z(95%,随天数 √n 收紧);
    无 SD → 退回人群参考变化值 RCV%(对 wearable 指标退到保守通用值,宁可少出条)。
    """
    if sd is not None and sd > 0 and nb and na:
        return _Z * sd * math.sqrt(1.0 / nb + 1.0 / na)
    rcv, _known = rcv_pct(metric_code)
    return (rcv / 100.0) * abs(before_mean)


def notes_from_impact(impact: dict[str, Any], min_pct: float = _MIN_PCT) -> list[dict[str, Any]]:
    """从单个事件的 before/after 指标对比,产出**穿过诚实地板**的记忆条(纯函数,可测)。

    impact 约定(get_event_impact 产出;字段缺失则该地板退化为更保守=更少出条):
      before / after : {metric: 窗口均值, "samples": 窗口天数}
      noise          : {metric: 个体内日间 SD}(可选;缺则用 RCV% 兜底)
      baseline       : {metric: 事件前等长对照窗口均值}(可选;缺则不做趋势扣除)

    任一地板不过 → 跳过(fail-closed)。direction 由**对照+折减后的净效应**符号决定,
    before/after 仍展示原始均值;两者方向相左时文案显式标注"已扣事件前趋势"。
    """
    title = impact.get("title") or "某次干预"
    before = impact.get("before") or {}
    after = impact.get("after") or {}
    noise = impact.get("noise") or {}
    baseline = impact.get("baseline") or {}
    nb = before.get("samples")
    na = after.get("samples")
    notes: list[dict[str, Any]] = []
    for key, (zh, higher_better) in _METRIC_META.items():
        b, a = before.get(key), after.get(key)
        if b is None or a is None or b == 0:
            continue
        # ① 处方/激素指标:嘈杂 wearable 管线绝不在此声称方向(only-downgrade-never-upgrade)
        if is_clinician_gated_metric(key):
            continue
        # ② 样本地板:每侧天数不足 → 不足以从噪声里分出信号(杀 1天vs1天 / 稀疏窗口)
        if nb is None or na is None or nb < _MIN_SAMPLES or na < _MIN_SAMPLES:
            continue
        raw_delta = a - b
        # ③ 匹配对照窗口 → difference-in-differences,扣掉事件前既有趋势
        c = baseline.get(key)
        control_delta = (b - c) if c is not None else 0.0
        # ④ 回归均值保守折减
        effect = (raw_delta - control_delta) * _RTM_SHRINK
        # ⑤ 噪声带:净效应须超过个体内变异
        band = _noise_band(noise.get(key), nb, na, float(b), key)
        if abs(effect) < band:
            continue
        pct = effect / abs(b)
        # ⑥ 实用显著:相对变化太小不出条(即便统计显著)
        if abs(pct) < min_pct:
            continue
        toward_good = pct if higher_better else -pct
        direction = "改善" if toward_good > 0 else "走低"
        # 原始 before→after 与净效应方向是否相左(强烈的事件前趋势会反号)
        trend_note = "" if (a - b) * effect >= 0 else "(原始趋势相反,系扣除事件前既有趋势后) "
        notes.append({
            "metric": key,
            "before": round(float(b), 1),
            "after": round(float(a), 1),
            "pct": round(pct, 3),  # 对照+折减后的净效应相对变化(非原始 (a-b)/b)
            "direction": direction,
            "evidence_tier": "observational",
            "text": (
                f"「{title}」之后,{zh} 从 {round(float(b),1)} → {round(float(a),1)}"
                f";{trend_note}本次观察支持「{direction}」"
                f"({impact.get('window_days', 30)} 天窗口,已扣事件前趋势与日间噪声,"
                f"相关非因果,数据不足以判断因果)"
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
            "事件先于指标变化的时序相关,非证明因果;已扣事件前对照趋势与日间噪声,"
            "未达个体内变异/样本门槛的变化不沉淀;不替代医学结论。"
        ),
    }
