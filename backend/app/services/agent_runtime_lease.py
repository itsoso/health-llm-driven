"""Shared lease maintenance for durable Agent Runtime workers."""
from __future__ import annotations

import asyncio
import logging
import time

from app.config import settings

logger = logging.getLogger(__name__)


async def agent_runtime_heartbeat(
    context,
    *,
    managed: bool,
    worker_id: str,
    owner_task: asyncio.Task,
    initial_lease_deadline: float,
) -> None:
    """Renew a Run lease independently and cancel work that lost ownership."""
    if not managed:
        return

    from app.database import SessionLocal
    from app.services.agent_runtime import (
        ACTIVE_RUN_STATUSES,
        AgentRuntimeCoordinator,
        StaleRunAttempt,
        StaleRunWorker,
    )

    heartbeat_seconds = int(
        getattr(settings, "agent_runtime_heartbeat_seconds", 20) or 20
    )
    lease_seconds = int(
        getattr(settings, "agent_runtime_lease_seconds", 90) or 90
    )
    if heartbeat_seconds < 1 or heartbeat_seconds >= lease_seconds:
        raise RuntimeError("invalid_agent_runtime_heartbeat_seconds")

    lease_deadline = initial_lease_deadline
    retry_delay = float(heartbeat_seconds)
    while not owner_task.done():
        await asyncio.sleep(retry_delay)
        heartbeat_db = None
        try:
            heartbeat_db = SessionLocal()
            runtime = AgentRuntimeCoordinator(heartbeat_db)
            try:
                renew_started = time.monotonic()
                signal = runtime.renew_lease(
                    context,
                    worker_id=worker_id,
                    lease_seconds=lease_seconds,
                )
            except (StaleRunAttempt, StaleRunWorker):
                run = runtime.get_run(context.user_id, context.run_id)
                if run.current_attempt_id != context.attempt_id:
                    owner_task.cancel()
                    return
                if run.status not in ACTIVE_RUN_STATUSES:
                    if (
                        run.status in {"cancelled", "reconciliation_required"}
                        or run.error_code
                        in {"deadline_exceeded", "worker_lease_expired"}
                    ):
                        owner_task.cancel()
                    return
                owner_task.cancel()
                return

            if signal.action != "continue":
                runtime.settle_control_stop(context, action=signal.action)
                owner_task.cancel()
                return
            lease_deadline = renew_started + lease_seconds
            retry_delay = float(heartbeat_seconds)
        except Exception as exc:  # noqa: BLE001
            remaining = lease_deadline - time.monotonic()
            logger.warning(
                "Agent Runtime heartbeat retry: run_id=%s attempt_id=%s "
                "remaining_lease=%.2fs error=%s",
                context.run_id,
                context.attempt_id,
                max(0.0, remaining),
                type(exc).__name__,
            )
            if remaining <= 1.0:
                owner_task.cancel()
                return
            retry_delay = min(
                max(1.0, heartbeat_seconds / 2),
                max(0.1, remaining - 1.0),
            )
        finally:
            if heartbeat_db is not None:
                try:
                    heartbeat_db.close()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Agent Runtime heartbeat session close failed: "
                        "run_id=%s attempt_id=%s error=%s",
                        context.run_id,
                        context.attempt_id,
                        type(exc).__name__,
                    )
                    owner_task.cancel()
                    return


def start_agent_runtime_heartbeat(
    *,
    context,
    managed: bool,
    worker_id: str,
    initial_lease_deadline: float,
) -> asyncio.Task | None:
    """Start heartbeat bound to the currently executing task."""
    if not managed:
        return None
    owner_task = asyncio.current_task()
    if owner_task is None:
        raise RuntimeError("agent_runtime_missing_owner_task")
    return asyncio.create_task(
        agent_runtime_heartbeat(
            context,
            managed=True,
            worker_id=worker_id,
            owner_task=owner_task,
            initial_lease_deadline=initial_lease_deadline,
        )
    )


async def stop_agent_runtime_heartbeat(
    heartbeat_task: asyncio.Task,
    *,
    run_id: str,
) -> None:
    """Stop the helper without allowing cleanup failure to replace Run result."""
    heartbeat_task.cancel()
    try:
        await heartbeat_task
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.error(
            "Agent Runtime heartbeat failed during cleanup: run_id=%s",
            run_id,
            exc_info=True,
        )
