"""Weekly client-telemetry digest.

The UI events we instrument (starter chip impressions/clicks, home cold-start
timing, quick-record/chat actions) are worthless if nobody reads them. This task
aggregates the last week of `client_events` and logs a structured summary —
starter CTR per generator, cold-start p50/p95, Agent first-useful p50/p95/p99,
and a "dead generator" list (shown a lot, never clicked) — so the data drives
decisions instead of piling up.

Pull-on-demand already exists at GET /admin/observability; this is the push half.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from app.celery_app import celery_app
from app.database import SessionLocal
from app.services.observability_service import client_events_stats, utc_now

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.observability_digest.client_events_weekly_digest")
def client_events_weekly_digest(days: int = 7) -> dict:
    """Compute + log the last-`days` client-telemetry digest across all users."""
    since = utc_now() - timedelta(days=days)
    with SessionLocal() as db:
        stats = client_events_stats(db, since, user_id=None)

    by_event = stats.get("by_event", {})
    ctr: dict = stats.get("starter_ctr", {})
    cold: dict = stats.get("home_cold_start_ms", {})
    agent_latency: dict = stats.get("agent_turn_milestones_ms", {})
    first_useful: dict = agent_latency.get("by_phase", {}).get("first_useful", {})

    # Dead generators: shown enough to judge (≥20 impressions) yet never clicked →
    # candidates for rewording or removal (the whole point of the CTR instrumentation).
    dead = sorted(
        k for k, v in ctr.items()
        if v.get("impressions", 0) >= 20 and (v.get("clicks") or 0) == 0
    )
    top = sorted(
        ctr.items(), key=lambda kv: (kv[1].get("ctr_pct") if kv[1].get("ctr_pct") is not None else -1),
        reverse=True,
    )[:5]

    logger.info(
        "[client-events-digest %dd] total=%s events=%s | cold_start p50=%sms p95=%sms "
        "n=%s incomplete=%s | agent_first_useful p50=%sms p95=%sms p99=%sms "
        "n=%s invalid=%s | starter dead_keys=%s top_ctr=%s",
        days,
        stats.get("total"),
        by_event,
        cold.get("p50"),
        cold.get("p95"),
        cold.get("n"),
        cold.get("incomplete"),
        first_useful.get("p50"),
        first_useful.get("p95"),
        first_useful.get("p99"),
        first_useful.get("n"),
        agent_latency.get("invalid"),
        dead or "none",
        [(k, v.get("ctr_pct")) for k, v in top],
    )
    return {"since_days": days, **stats, "dead_starter_keys": dead}
