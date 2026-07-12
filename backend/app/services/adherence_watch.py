# -*- coding: utf-8 -*-
"""依从性智能 —— 检测 N-of-1 在飞协议的掉队风险(Next Horizon Tier 2)。

outcome 最大杠杆是用户**有没有执行到底**。已接受但迟迟没评分的卡 = 掉队风险。
本模块纯判定:给一组用户已接受、未评分的 N-of-1 卡,挑出"快到期还没动"和"已逾期没复检"
的,任务层(tasks/adherence_watch.py)走全局打扰预算温和再激活。直接抬北极星(完成率)。

纯逻辑(无 DB/Celery/通知),可全测。诚实:这是基于"周期进度 + 未评分"的代理信号,
非逐日依从打卡;不报警化、给可执行下一步。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional

# 视为"已接受、在执行"的决策语义
_ACCEPTED = ("accepted", "adjusted")
# 过了周期这个比例还没评分 → 算"中途掉队风险"
_MIDWAY_RISK_FRAC = 0.6


@dataclass(frozen=True)
class AtRiskCard:
    card_id: Any
    title: str
    metric: Optional[str]
    kind: str            # midway_risk / overdue
    days_left: int       # midway: 距到期天数;overdue: 已逾期天数(负向语义用 kind 区分)
    progress_pct: int


def _elapsed_days(created_at: Any, now: datetime) -> Optional[int]:
    if not isinstance(created_at, datetime):
        return None
    try:
        return (now - created_at).days
    except TypeError:
        # tz-aware 与 naive 混用 → 退化为按 date 比
        return (now.date() - created_at.date()).days


def at_risk_cards(cards: List[Any], now: datetime) -> List[AtRiskCard]:
    """从用户的卡里挑掉队风险(已接受、未评分、未归档、有验证窗口)。"""
    out: List[AtRiskCard] = []
    for c in cards:
        outcome = getattr(c, "outcome", None)
        status = (getattr(c, "status", "") or "").lower()
        decision = (getattr(c, "user_decision", "") or "").lower()
        window = getattr(c, "verification_days", None)
        created = getattr(c, "created_at", None)
        if outcome is not None or status == "archived" or decision not in _ACCEPTED:
            continue
        if not window or window <= 0:
            continue
        elapsed = _elapsed_days(created, now)
        if elapsed is None or elapsed < 0:
            continue
        progress = elapsed / window
        title = getattr(c, "title", "") or "你的计划"
        metric = getattr(c, "metric_key", None)
        if elapsed > window:
            out.append(AtRiskCard(
                card_id=getattr(c, "id", None), title=title, metric=metric,
                kind="overdue", days_left=elapsed - window,
                progress_pct=min(int(progress * 100), 999),
            ))
        elif progress >= _MIDWAY_RISK_FRAC:
            out.append(AtRiskCard(
                card_id=getattr(c, "id", None), title=title, metric=metric,
                kind="midway_risk", days_left=window - elapsed,
                progress_pct=int(progress * 100),
            ))
    return out


def nudge_text(card: AtRiskCard) -> tuple[str, str]:
    """(title, message)。温和、给可执行下一步,不报警化。

    §5 推送隐私:ActionCard 标题可能带补剂/药名/化验项,不进锁屏可见文本;
    标题走 push data.card_title,App 解锁后应用内渲染。
    """
    if card.kind == "overdue":
        return (
            "你的计划周期到了 ⏰",
            f"有一个健康计划周期已满(逾期 {card.days_left} 天)。去复检/记一次数据,"
            "让 AI 帮你看看这轮有没有效果。",
        )
    return (
        "坚持一下,快到验证点了 💪",
        f"有一个健康计划已进行 {card.progress_pct}%,还有 {card.days_left} 天到验证点。"
        "保持节奏,到点就能看到结果。",
    )
