# -*- coding: utf-8 -*-
"""激活漏斗 —— 注册 → 第一个改善 outcome(Phase3 P1,增长仪表)。

北极星是"完成 ≥1 个闭环且改善的用户",但此前从注册到第一个 outcome 没有系统度量。
本服务把漏斗各级 distinct 用户数 + 相邻转化率算出来,服务增长/激活分析。

去标识:只出计数/比率,无 user_id。漏斗:
  registered → activated(有≥1 ActionCard)→ accepted(决策 accepted/adjusted)
  → graded(outcome 非空)→ improved(outcome=improved,北极星)
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.action_card import ActionCard
from app.models.user import User

# 视为"接受了建议"的决策语义
_ACCEPT_DECISIONS = ("accepted", "adjusted")


def _distinct_users(q) -> int:
    return q.distinct().count()


def activation_funnel(db: Session) -> dict[str, Any]:
    """注册 → 改善 漏斗(去标识)。"""
    registered = db.query(User.id).count()

    base = db.query(ActionCard.user_id)
    activated = _distinct_users(base)
    accepted = _distinct_users(
        base.filter(ActionCard.user_decision.in_(_ACCEPT_DECISIONS))
    )
    graded = _distinct_users(base.filter(ActionCard.outcome.isnot(None)))
    improved = _distinct_users(base.filter(func.lower(ActionCard.outcome) == "improved"))

    stages = [
        ("registered", registered),
        ("activated", activated),       # 拿到过 AI 建议
        ("accepted", accepted),         # 接受了建议
        ("graded", graded),             # 闭环完成、评分出来
        ("improved", improved),         # 指标真改善(北极星)
    ]

    # 相邻转化率(下一级 / 上一级)
    conversions: dict[str, Optional[float]] = {}
    for (name_a, va), (name_b, vb) in zip(stages, stages[1:]):
        conversions[f"{name_a}->{name_b}"] = round(vb / va, 3) if va else None

    return {
        "funnel": {name: cnt for name, cnt in stages},
        "conversions": conversions,
        "north_star_users": improved,                # 完成闭环且改善
        "overall_register_to_improved": (
            round(improved / registered, 4) if registered else None
        ),
        "note": "去标识 distinct 用户数;全历史口径。北极星=improved。",
    }
