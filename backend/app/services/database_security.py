"""Database-role checks for production least-privilege enforcement."""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def scheduler_runtime_enabled(dialect: str) -> bool:
    """Background schedulers require production-equivalent DB semantics."""
    return dialect == "postgresql"


def scheduler_leader_statements(dialect: str) -> tuple[str, str]:
    """Return fail-closed scheduler election SQL for supported databases."""
    if dialect == "postgresql":
        return (
            "CREATE TABLE IF NOT EXISTS scheduler_leader ("
            "id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), "
            "worker_pid VARCHAR(50), "
            "acquired_at TIMESTAMP WITH TIME ZONE DEFAULT NOW())",
            "INSERT INTO scheduler_leader (id, worker_pid, acquired_at) "
            "VALUES (1, :pid, NOW()) "
            "ON CONFLICT (id) DO UPDATE SET worker_pid = :pid, acquired_at = NOW() "
            "WHERE scheduler_leader.acquired_at < NOW() - INTERVAL '5 minutes'",
        )
    if dialect == "sqlite":
        return (
            "CREATE TABLE IF NOT EXISTS scheduler_leader ("
            "id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), "
            "worker_pid VARCHAR(50), "
            "acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "INSERT INTO scheduler_leader (id, worker_pid, acquired_at) "
            "VALUES (1, :pid, CURRENT_TIMESTAMP) "
            "ON CONFLICT (id) DO UPDATE SET worker_pid = :pid, "
            "acquired_at = CURRENT_TIMESTAMP "
            "WHERE scheduler_leader.acquired_at < datetime('now', '-5 minutes')",
        )
    raise RuntimeError(f"unsupported_scheduler_database_dialect:{dialect}")


def unsafe_runtime_role_attributes(role: dict) -> tuple[str, ...]:
    unsafe = []
    for field in ("rolsuper", "rolbypassrls", "rolcreatedb", "rolcreaterole"):
        if bool(role.get(field)):
            unsafe.append(field)
    return tuple(unsafe)


def assert_runtime_database_role(db: Session, *, production: bool) -> None:
    """Reject privileged PostgreSQL runtime roles in production."""
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    row = db.execute(text(
        "SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
        "FROM pg_roles WHERE rolname = current_user"
    )).mappings().one()
    unsafe = unsafe_runtime_role_attributes(dict(row))
    if not unsafe:
        return
    message = (
        f"database runtime role {row['rolname']} has forbidden privileges: "
        f"{', '.join(unsafe)}"
    )
    if production:
        raise RuntimeError(message)
    logger.error("[SECURITY] %s", message)
