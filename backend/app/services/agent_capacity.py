"""Cross-worker admission control for paid Agent execution."""
from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models.agent_capacity import AgentCapacityLease


_CAPACITY_ADVISORY_LOCK = 1_724_663_252
_LOCAL_CAPACITY_LOCK = threading.RLock()


class AgentCapacityExceeded(RuntimeError):
    def __init__(self, scope: str):
        super().__init__("agent_capacity_exceeded")
        self.scope = scope


class AgentCapacityController:
    """Reserve and release content-free Agent concurrency leases.

    PostgreSQL admission is serialized with a transaction advisory lock, so
    every Web worker observes the same global and per-user limits. The lease
    expires after the request hard cap, which recovers capacity after a worker
    crash without operator cleanup.
    """

    def __init__(self, db: Session):
        self.db = db

    def acquire(self, *, user_id: int, origin: str) -> AgentCapacityLease:
        global_limit = int(settings.agent_max_active_runs_global)
        user_limit = int(settings.agent_max_active_runs_per_user)
        lease_seconds = int(settings.agent_capacity_lease_seconds)
        if global_limit < 1 or user_limit < 1:
            raise RuntimeError("invalid_agent_capacity_limit")
        if lease_seconds < 300 or lease_seconds > 3600:
            raise RuntimeError("invalid_agent_capacity_lease_seconds")

        now = datetime.now(UTC)
        with _LOCAL_CAPACITY_LOCK:
            try:
                self._acquire_database_lock()
                active = (
                    AgentCapacityLease.released_at.is_(None),
                    AgentCapacityLease.expires_at > now,
                )
                global_active = int(
                    self.db.query(func.count(AgentCapacityLease.lease_id))
                    .filter(*active)
                    .scalar()
                    or 0
                )
                if global_active >= global_limit:
                    raise AgentCapacityExceeded("global")

                user_active = int(
                    self.db.query(func.count(AgentCapacityLease.lease_id))
                    .filter(AgentCapacityLease.user_id == int(user_id), *active)
                    .scalar()
                    or 0
                )
                if user_active >= user_limit:
                    raise AgentCapacityExceeded("user")

                lease = AgentCapacityLease(
                    lease_id=f"cap_{uuid.uuid4().hex}",
                    user_id=int(user_id),
                    origin=str(origin or "agent")[:32],
                    expires_at=now + timedelta(seconds=lease_seconds),
                )
                self.db.add(lease)
                self.db.commit()
                self.db.refresh(lease)
                return lease
            except Exception:
                self.db.rollback()
                raise

    def release(self, lease_id: str, *, user_id: int) -> bool:
        released_at = datetime.now(UTC)
        affected = (
            self.db.query(AgentCapacityLease)
            .filter(
                AgentCapacityLease.lease_id == str(lease_id),
                AgentCapacityLease.user_id == int(user_id),
                AgentCapacityLease.released_at.is_(None),
            )
            .update(
                {"released_at": released_at},
                synchronize_session=False,
            )
        )
        self.db.commit()
        return bool(affected)

    def _acquire_database_lock(self) -> None:
        if self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": _CAPACITY_ADVISORY_LOCK},
            )
