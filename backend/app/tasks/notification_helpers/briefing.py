"""共享的 briefing / weekly report helper. 从 notifications.py 拆出 (弱点 F).

纯函数, 无 side effect (除 DB 读), 方便独立测试.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Optional


def status_emoji(
    value: Optional[float],
    good_threshold: float,
    bad_threshold: float,
    higher_is_better: bool = True,
) -> str:
    """根据阈值返回状态 emoji (✅/⚠️/🔴/❓)."""
    if value is None:
        return "❓"
    if higher_is_better:
        return "✅" if value >= good_threshold else ("⚠️" if value >= bad_threshold else "🔴")
    else:
        return "✅" if value <= good_threshold else ("⚠️" if value <= bad_threshold else "🔴")


def build_hit_rate_block(db, user_id: int, days: int = 30) -> str:
    """生成 specialist 信用面板 markdown — 周报顶部, 让用户看到 agent 准不准.

    输出: 表格 + "本期最该信的 specialist" 提示 + 待复查数.
    空串 iff 用户无 graded ActionCard 且无 pending card.
    """
    from app.models.action_card import ActionCard
    from sqlalchemy import func, Integer

    since = datetime.now(UTC) - timedelta(days=days)

    rows = db.query(
        ActionCard.creator_specialist,
        func.count(ActionCard.id).label("total"),
        func.avg(ActionCard.accuracy_score).label("avg_score"),
        func.sum((ActionCard.accuracy_score >= 70).cast(Integer)).label("hits"),
    ).filter(
        ActionCard.user_id == user_id,
        ActionCard.graded_at.isnot(None),
        ActionCard.graded_at >= since,
        ActionCard.creator_specialist.isnot(None),
    ).group_by(ActionCard.creator_specialist).all()

    pending = db.query(func.count(ActionCard.id)).filter(
        ActionCard.user_id == user_id,
        ActionCard.check_back_date.isnot(None),
        ActionCard.graded_at.is_(None),
    ).scalar() or 0

    if not rows and pending == 0:
        return ""

    lines = [f"### 🎯 Specialist 信用 (最近 {days} 天)"]

    if rows:
        ranked = sorted(
            [(r.creator_specialist, int(r.total),
              int(r.hits or 0), float(r.avg_score or 0))
             for r in rows],
            key=lambda x: (x[2] / x[1] if x[1] else 0),
            reverse=True,
        )
        best = ranked[0]
        lines.append(f"**本期最该信的 specialist**: `{best[0]}` "
                     f"(命中 {best[2]}/{best[1]}, 平均分 {best[3]:.0f})")
        lines.append("")
        lines.append("| Specialist | 已评 | 命中 (≥70) | 平均分 |")
        lines.append("|---|---|---|---|")
        for name, total, hits, avg in ranked:
            rate = (hits / total * 100) if total else 0
            lines.append(f"| {name} | {total} | {hits} ({rate:.0f}%) | {avg:.0f} |")

    if pending > 0:
        lines.append("")
        lines.append(f"⏳ **{pending} 张卡片待复查**（到期会自动评分）")

    return "\n".join(lines)
