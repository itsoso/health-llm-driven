"""verify_action_card_outcomes —— P5-1 N-of-1 自动验证 Celery 任务.

每天 02:00 跑: 扫所有 user_decision='accepted' 且 check_back_date <= now 且
graded_at IS NULL 的卡 → 拉 metric_key 当前值 → 与 baseline_value 比对 →
写 actual_value + outcome + effect_size + accuracy_score + graded_at.

设计:
- 一次最多处理 200 张卡 (避免单次任务超时)
- 没 metric_key / 没 baseline 的卡 → outcome='inconclusive', graded_at = now
  (避免反复扫不评)
- 失败旁路: 单卡评估异常不影响其它卡

WSCLA 闭环最后一公里 — 这之前用户接受了建议永远等不到 outcome,
WSCLA 永远 = 0.
"""

import logging
from datetime import date, datetime, timedelta, timezone

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.action_card import ActionCard
from app.tasks.metrics import fetch_metric, grade_outcome
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)

BATCH_LIMIT = 200


@celery_app.task
def verify_action_card_outcomes():
    """每天 02:00 跑. 见 module docstring."""
    return _verify_impl()


def _verify_impl(dry_run: bool = False):
    """实际逻辑. dry_run 用于单测/手动 trigger 不写库."""
    now = get_china_now()
    today = now.date()

    graded = 0
    inconclusive = 0
    improved = 0
    unchanged = 0
    worsened = 0
    failed = 0
    seen = 0

    with SessionLocal() as db:
        cards = (
            db.query(ActionCard)
            .filter(
                ActionCard.user_decision == "accepted",
                ActionCard.check_back_date.isnot(None),
                ActionCard.check_back_date <= now,
                ActionCard.graded_at.is_(None),
            )
            .order_by(ActionCard.check_back_date.asc())
            .limit(BATCH_LIMIT)
            .all()
        )
        seen = len(cards)

        for card in cards:
            try:
                outcome, effect, actual = _verify_one(db, card, today)
                if not dry_run:
                    card.outcome = outcome
                    card.effect_size = effect
                    if actual is not None:
                        card.actual_value = str(actual)
                    card.graded_at = now
                    # accuracy_score: improved=80 / unchanged=50 / worsened=20 / inconclusive=0
                    card.accuracy_score = _score_from_outcome(outcome)
                    db.commit()
                graded += 1
                if outcome == "improved":
                    improved += 1
                elif outcome == "unchanged":
                    unchanged += 1
                elif outcome == "worsened":
                    worsened += 1
                else:
                    inconclusive += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                logger.warning(f"[verify_outcomes] card={card.id} 失败: {e}")
                if not dry_run:
                    try:
                        db.rollback()
                    except Exception:
                        pass

    if seen:
        logger.info(
            f"[verify_outcomes] seen={seen} graded={graded} "
            f"improved={improved} unchanged={unchanged} worsened={worsened} "
            f"inconclusive={inconclusive} failed={failed}"
        )
    return {
        "seen": seen,
        "graded": graded,
        "improved": improved,
        "unchanged": unchanged,
        "worsened": worsened,
        "inconclusive": inconclusive,
        "failed": failed,
    }


def _verify_one(db, card: ActionCard, end_date: date):
    """评估单卡. 返回 (outcome, effect_size, actual_value)."""
    if not card.metric_key or not card.baseline_value:
        return ("inconclusive", None, None)

    actual = fetch_metric(db, card.user_id, card.metric_key, end_date)
    if actual is None:
        return ("inconclusive", None, None)

    outcome, effect = grade_outcome(card.metric_key, card.baseline_value, actual)
    return (outcome, effect, actual)


def _score_from_outcome(outcome: str) -> int:
    return {
        "improved": 80,
        "unchanged": 50,
        "worsened": 20,
        "inconclusive": 0,
    }.get(outcome, 0)
