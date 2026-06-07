# -*- coding: utf-8 -*-
"""因果记忆(RFC 方向二)—— 从"事件 × 指标变化"沉淀可召回的记忆条。

"上次你血糖高是因为聚餐" 这类记忆此前没系统化。本服务复用 personal_outcome 的
事件前后指标对比(get_event_impact),把"某事件后某指标显著变化"沉淀成 agent 可召回
的结构化记忆条,供 orchestrator memory 注入 / 对话引用。

诚实:这是**时序相关**记忆(事件先于变化),**非证明因果**;窗口均值对比、带样本,
evidence_tier=observational,文案明标"相关非因果",不说"因为"。
"""
from __future__ import annotations

from typing import Any, Optional

# 指标中文名 + 方向(True=越高越好)。与 metrics.HIGHER_IS_BETTER 同源语义。
_METRIC_META = {
    "hrv": ("HRV", True),
    "rhr": ("静息心率", False),
    "sleep_score": ("睡眠评分", True),
    "deep_sleep_min": ("深睡时长", True),
    "steps": ("步数", True),
}

# 显著变化阈值(相对 %)
_MIN_PCT = 0.05


def notes_from_impact(impact: dict[str, Any], min_pct: float = _MIN_PCT) -> list[dict[str, Any]]:
    """从单个事件的 before/after 指标对比,产出显著变化的记忆条(纯函数,可测)。

    direction=改善/恶化 由指标方向决定;|pct|<阈值 → 跳过;缺值/零基线 → 跳过。
    """
    title = impact.get("title") or "某次干预"
    before = impact.get("before") or {}
    after = impact.get("after") or {}
    notes: list[dict[str, Any]] = []
    for key, (zh, higher_better) in _METRIC_META.items():
        b, a = before.get(key), after.get(key)
        if b is None or a is None or b == 0:
            continue
        pct = (a - b) / abs(b)
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
            "text": (
                f"「{title}」之后,{zh} 从 {round(float(b),1)} → {round(float(a),1)}"
                f"({direction};{impact.get('window_days', 30)} 天窗口,相关非因果)"
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
        "claim_boundary": "事件先于指标变化的时序相关,非证明因果;窗口均值对比,不替代医学结论。",
    }
