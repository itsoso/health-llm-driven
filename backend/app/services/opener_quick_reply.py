"""Protocol handler for chat opener quick replies.

The mobile chat opener is a stateful UI surface: a reply like "做到了" only
has meaning together with the opener card that asked the question. This module
turns that context into deterministic ActionCard state before the LLM answers,
so verification does not depend on the model guessing from a short reply.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.action_card import ActionCard

logger = logging.getLogger(__name__)


def infer_self_reported_adherence(reply: str) -> Optional[int]:
    text = (reply or "").strip()
    if any(token in text for token in ["没做", "未做", "没有做", "没完成", "失败"]):
        return 0
    if any(token in text for token in ["做到", "做到了", "已做", "做了", "完成"]):
        return 70
    return None


def _load_context(extra_context: Optional[str]) -> Optional[dict[str, Any]]:
    if not extra_context:
        return None
    try:
        value = json.loads(extra_context)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _context_card_id(ctx: dict[str, Any]) -> Optional[int]:
    raw = ctx.get("action_card_id") or ctx.get("source_id")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def apply_opener_quick_reply_context(
    db: Session,
    user_id: int,
    message: str,
    extra_context: Optional[str],
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Apply conversation opener quick-reply side effects.

    Returns a short system note to inject into the Agent prompt, or ``None`` if
    the context is not a supported opener reply.
    """
    ctx = _load_context(extra_context)
    if not ctx:
        return None
    if ctx.get("entry") != "conversation_opener_quick_reply":
        return None
    if ctx.get("source") != "action_card_due":
        return None

    card_id = _context_card_id(ctx)
    if card_id is None:
        return None

    reply = str(ctx.get("user_reply") or message or "")
    confidence = infer_self_reported_adherence(reply)
    if confidence is None:
        return None

    card = (
        db.query(ActionCard)
        .filter(ActionCard.id == card_id, ActionCard.user_id == user_id)
        .first()
    )
    if not card:
        return "入口动作未执行: 没有找到这张 ActionCard，不能声称已完成验证。"

    card.adherence_kind = "self_reported"
    card.adherence_confidence = confidence

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    check_back = card.check_back_date
    if check_back is not None and check_back.tzinfo is None:
        check_back = check_back.replace(tzinfo=timezone.utc)
    graded_note = ""
    if (
        check_back is not None
        and check_back <= now
        and card.graded_at is None
        and card.metric_key
        and card.target_value
    ):
        try:
            from app.tasks.outcome_grader import grade_single_card

            result = grade_single_card(db, card, now)
            if result.get("status") == "graded":
                graded_note = (
                    f" 已立即完成验证: actual={card.actual_value}, "
                    f"score={card.accuracy_score}, notes={card.grading_notes}."
                )
            elif result.get("status") == "skipped_no_data":
                graded_note = f" 暂未完成指标验证: {result.get('note') or '缺少数据'}."
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[opener_quick_reply] immediate grading failed: {e}")
            graded_note = " 依从度已记录，但即时评分失败，等待后台评分任务补偿。"

    db.commit()
    return (
        f"入口动作已执行: ActionCard #{card.id}《{card.title}》"
        f"记录 self_reported adherence={confidence}%.{graded_note} "
        "回复用户时必须基于这张卡，不要把用户回复当成孤立文本。"
    )
