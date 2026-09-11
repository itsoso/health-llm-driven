"""共享的 briefing / weekly report helper. 从 notifications.py 拆出 (弱点 F).

纯函数, 无 side effect (除 DB 读), 方便独立测试.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Optional


class BriefingNarrativeBlocked(RuntimeError):
    """Stable verdict from the existing medical-advice verifier."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def ai_generation_failure(error: BaseException) -> tuple[dict, str]:
    """Separate generated interpretation from delivered data, without raw errors."""
    from app.services.llm.recovery import diagnose_llm_error

    if isinstance(error, BriefingNarrativeBlocked):
        return ({"status": "blocked", "reason": error.reason},
                "本次提供数据汇总；个性化 AI 解读尚缺通过审核的医学依据，暂不生成执行建议。")

    diagnosis = diagnose_llm_error(error)
    metadata = {"status": diagnosis.execution_status, "reason": diagnosis.error_class}
    if diagnosis.retry_at is not None:
        metadata["retry_at"] = diagnosis.retry_at
    explanation = {
        "budget_exhausted": "AI 解读受调用额度限制，待预算周期恢复后重新核验",
        "budget_guard_unavailable": "暂时无法核验调用预算，已停止 AI 解读",
        "consent_required": "AI 服务授权尚未确认，暂不生成 AI 解读",
        "consent_unavailable": "暂时无法核验 AI 服务授权，已停止 AI 解读",
        "recipient_not_disclosed": "AI 服务提供方尚未完成授权披露，暂不生成 AI 解读",
    }.get(diagnosis.error_class, "AI 解读本次生成失败")
    return metadata, f"本次提供数据汇总；{explanation}。"


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
    from collections import defaultdict
    from app.services.outcome_safety import is_efficacy_score_eligible_card

    since = datetime.now(UTC) - timedelta(days=days)

    cards = db.query(ActionCard).filter(
        ActionCard.user_id == user_id,
        ActionCard.graded_at.isnot(None),
        ActionCard.graded_at >= since,
        ActionCard.creator_specialist.isnot(None),
        ActionCard.accuracy_score.isnot(None),
    ).all()
    grouped = defaultdict(list)
    for card in cards:
        if is_efficacy_score_eligible_card(card):
            grouped[card.creator_specialist].append(int(card.accuracy_score))

    pending_cards = db.query(ActionCard).filter(
        ActionCard.user_id == user_id,
        ActionCard.check_back_date.isnot(None),
        ActionCard.graded_at.is_(None),
    ).all()
    pending = sum(is_efficacy_score_eligible_card(card) for card in pending_cards)

    if not grouped and pending == 0:
        return ""

    lines = [f"### 🎯 Specialist 信用 (最近 {days} 天)"]

    if grouped:
        ranked = sorted(
            [
                (name, len(scores), sum(score >= 70 for score in scores), sum(scores) / len(scores))
                for name, scores in grouped.items()
            ],
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
