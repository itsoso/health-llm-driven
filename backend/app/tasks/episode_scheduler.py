"""Episode scheduler — Agent-Native v3 Increment 3 §3.

Celery beat 每分钟扫描:
  1. due reminders: time_window_start 刚到 / 已过 N 秒, 还 pending → 发推送, 标 push_sent_at
  2. expired actions: time_window_end 已过, 还 pending → 翻 expired, 触发 maybe_close_episode

设计 dec:
  - 不依赖单条 Celery countdown task — 用户改时间窗 / replan 难追溯,
    周期扫描更鲁棒. 1min 粒度足够 (Coach 提醒不需要秒级).
  - push_dedup_key 落库 → 即使任务重跑也只推一次.
  - 一次扫全表上限 200 条, 避免巨型用户/历史积压把 worker 卡死.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.celery_app import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)


# 提醒 lookback 窗口 — 如果 worker 因为故障晚跑几分钟, 仍然能补推.
_REMIND_LOOKBACK_MIN = 5
# 单批最多处理多少条, 防止一次扫描占用过久.
_BATCH_LIMIT = 200


@celery_app.task(bind=True, time_limit=120, max_retries=0)
def scan_episode_action_windows(self):
    """每分钟扫描: 推 due reminders + 翻 expired actions.

    Returns: {"reminded": N, "expired": M, "closed": K}
    """
    from app.models.episode import EpisodeAction, HealthEpisode
    from app.services.episode.lifecycle import maybe_close_episode

    now = datetime.now(timezone.utc)
    lookback = now - timedelta(minutes=_REMIND_LOOKBACK_MIN)

    reminded = 0
    expired = 0
    closed = 0
    closed_ep_ids: set[int] = set()

    with SessionLocal() as db:
        # ---- 1. 提醒 due actions ----
        due_q = (
            db.query(EpisodeAction)
            .join(HealthEpisode, EpisodeAction.episode_id == HealthEpisode.id)
            .filter(
                EpisodeAction.status == "pending",
                EpisodeAction.push_sent_at.is_(None),
                EpisodeAction.time_window_start.isnot(None),
                EpisodeAction.time_window_start <= now,
                EpisodeAction.time_window_start >= lookback,
                HealthEpisode.status == "open",
            )
            .order_by(EpisodeAction.time_window_start.asc())
            .limit(_BATCH_LIMIT)
        )
        due_actions = due_q.all()
        for action in due_actions:
            try:
                ok = _push_action_reminder(db, action)
                if ok:
                    action.push_sent_at = now
                    action.push_dedup_key = f"action_reminder_{action.id}"
                    reminded += 1
            except Exception as e:
                logger.warning(
                    f"[Scheduler] reminder push failed action={action.id}: {e}",
                    exc_info=True,
                )
        if due_actions:
            db.commit()

        # ---- 2. 翻 expired ----
        exp_q = (
            db.query(EpisodeAction)
            .join(HealthEpisode, EpisodeAction.episode_id == HealthEpisode.id)
            .filter(
                EpisodeAction.status == "pending",
                EpisodeAction.time_window_end.isnot(None),
                EpisodeAction.time_window_end < now,
                HealthEpisode.status == "open",
            )
            .limit(_BATCH_LIMIT)
        )
        exp_actions = exp_q.all()
        for action in exp_actions:
            action.status = "expired"
            expired += 1
            closed_ep_ids.add(action.episode_id)
        if exp_actions:
            db.flush()

        # ---- 3. 这些刚翻 expired 的 episode 可能已经全终态, 跑 close ----
        if closed_ep_ids:
            episodes = (
                db.query(HealthEpisode)
                .filter(HealthEpisode.id.in_(closed_ep_ids))
                .all()
            )
            for ep in episodes:
                if maybe_close_episode(db, ep):
                    closed += 1
            db.commit()

    if reminded or expired or closed:
        logger.info(
            f"[Scheduler] Episode action sweep: reminded={reminded} "
            f"expired={expired} closed={closed}"
        )
    return {"reminded": reminded, "expired": expired, "closed": closed}


def _push_action_reminder(db, action) -> bool:
    """对单条 due action 发提醒推送. 返回 True 表示发出 (or dedup 跳过).

    用户级渠道由 PushService 决定. 注意这里我们手动把 push_db 复用 db (已是 worker
    持有的 SessionLocal), 不重新开 session — Celery task 内事务边界由我们管.
    """
    from app.models.episode import HealthEpisode
    from app.services.notification.push_service import PushService

    episode = db.query(HealthEpisode).filter_by(id=action.episode_id).first()
    if not episode:
        return False

    title = f"⏰ {action.title[:40]}"
    body_pieces: list[str] = []
    if action.body:
        body_pieces.append(action.body[:120])
    if action.time_window_end:
        # 让用户知道还剩多久
        try:
            mins_left = int(
                (action.time_window_end - datetime.now(timezone.utc)).total_seconds() // 60
            )
            if 0 < mins_left < 240:
                body_pieces.append(f"窗口还剩 {mins_left} 分钟")
        except Exception:
            pass
    body = " · ".join(body_pieces) if body_pieces else "点击打开方案查看完成步骤"

    push_svc = PushService(db)
    try:
        result = asyncio.run(push_svc.send_notification(
            user_id=episode.user_id,
            notification_type="episode_action_reminder",
            title=title,
            content=body,
            data={
                "deep_link": f"/episode/{episode.id}",
                "kind": "episode_action_reminder",
                "episode_id": episode.id,
                "action_id": action.id,
                "rule_id": f"action_reminder_{action.id}",
            },
            severity="low",
            dedup_window_hours=24,
        ))
    except Exception as e:
        logger.warning(
            f"[Scheduler] push_service raised action={action.id}: {e}", exc_info=True,
        )
        return False
    # PushService 内部任一通道成功 / 或 dedup 命中, 我们都视为"已尝试", 标 push_sent_at
    # 防止下一分钟再扫到同条.
    return True
