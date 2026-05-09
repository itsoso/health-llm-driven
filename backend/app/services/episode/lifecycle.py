"""Episode lifecycle state machine — Agent-Native v3 Increment 3 §1.

负责 Episode 状态翻转 + Outcome 雏形写入. Reflection 在 Increment 4 单独跑.

闭环规则 (open → closed):
  当所有 EpisodeAction.status 都是终态 (done / skipped / expired) 时,
  把 Episode.status 翻成 closed, 写 closed_at = now (UTC),
  同步建一条 EpisodeOutcome (actions_total / actions_done / completion_rate),
  Reflection 字段 (metrics_delta / summary) 留给 Increment 4 Worker 回填.

调用点:
  - app/api/episodes.py submit_feedback (用户标 done/skipped 后调用)
  - 未来: scheduler 标 expired 时调用

幂等:
  status 已不是 open 的 Episode 不再触碰; 已存在的 Outcome 保持不变.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.episode import EpisodeOutcome, HealthEpisode

logger = logging.getLogger(__name__)


_TERMINAL_ACTION_STATUSES = {"done", "skipped", "expired"}


def maybe_close_episode(db: Session, episode: HealthEpisode) -> bool:
    """所有 action 终态时关闭 Episode + 写 Outcome. 已 closed 的不动.

    返回 True 表示这次调用真的把 Episode 关掉了.

    Caller 仍负责 commit (本函数只 add + flush, 让外层包在同一事务里).
    """
    if episode.status != "open":
        return False

    actions = list(episode.actions or [])
    if not actions:
        return False

    if any(a.status not in _TERMINAL_ACTION_STATUSES for a in actions):
        return False

    now = datetime.now(timezone.utc)
    episode.status = "closed"
    episode.closed_at = now

    # 雏形 Outcome — completion 数字立即可读, Reflection 字段留给 Worker 回填.
    existing = (
        db.query(EpisodeOutcome)
        .filter(EpisodeOutcome.episode_id == episode.id)
        .first()
    )
    actions_total = len(actions)
    actions_done = sum(1 for a in actions if a.status == "done")
    actions_skipped = sum(1 for a in actions if a.status == "skipped")
    completion_rate = (actions_done / actions_total) if actions_total else 0.0

    if existing is None:
        outcome = EpisodeOutcome(
            episode_id=episode.id,
            actions_total=actions_total,
            actions_done=actions_done,
            actions_skipped=actions_skipped,
            completion_rate=completion_rate,
        )
        db.add(outcome)
    else:
        existing.actions_total = actions_total
        existing.actions_done = actions_done
        existing.actions_skipped = actions_skipped
        existing.completion_rate = completion_rate

    db.flush()
    logger.info(
        "Episode closed: id=%s user=%s done=%d/%d skipped=%d rate=%.2f",
        episode.id, episode.user_id,
        actions_done, actions_total, actions_skipped, completion_rate,
    )
    return True
