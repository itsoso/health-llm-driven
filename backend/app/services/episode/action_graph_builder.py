"""ActionGraph Builder — 把 Planner 输出写入 DB (HealthEpisode + EpisodeAction)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.episode import HealthEpisode, EpisodeAction
from app.services.episode.planner import ActionGraph

logger = logging.getLogger(__name__)


def persist_action_graph(
    db: Session,
    *,
    user_id: int,
    episode_type: str,
    occurred_at: datetime,
    graph: ActionGraph,
    source_type: Optional[str] = None,
    source_id: Optional[int] = None,
    context_snapshot: Optional[Dict[str, Any]] = None,
    baseline_snapshot: Optional[Dict[str, Any]] = None,
) -> HealthEpisode:
    """创建 Episode + 批量写 EpisodeAction, 返回 persisted Episode."""
    episode = HealthEpisode(
        user_id=user_id,
        episode_type=episode_type,
        source_type=source_type,
        source_id=source_id,
        occurred_at=occurred_at,
        status="open",
        risk_level=graph.risk.level,
        risk_flags=graph.risk.flags,
        protocol_slug=graph.protocol_slug,
        protocol_version=graph.protocol_version,
        context_snapshot=context_snapshot,
        baseline_snapshot=baseline_snapshot,
        headline=graph.headline,
    )
    db.add(episode)
    db.flush()  # 拿 id

    for pa in graph.actions:
        action = EpisodeAction(
            episode_id=episode.id,
            sequence=pa.sequence,
            title=pa.title,
            body=pa.body,
            icon=pa.icon,
            action_type=pa.action_type,
            template_id=pa.template_id,
            evidence_id=pa.evidence_id,
            time_window_start=pa.time_window_start,
            time_window_end=pa.time_window_end,
            condition_expr=pa.condition_expr,
            completion_check=pa.completion_check,
            risk_condition=pa.risk_condition,
            status="pending",
        )
        db.add(action)

    db.commit()
    db.refresh(episode)
    logger.info(
        "Episode created: id=%s user=%s type=%s risk=%s protocol=%s@%s actions=%d",
        episode.id, user_id, episode_type, graph.risk.level,
        graph.protocol_slug, graph.protocol_version, len(graph.actions),
    )
    return episode
