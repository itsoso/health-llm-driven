"""Machine-verifiable account deletion scope checks."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from sqlalchemy import MetaData, Table, func, inspect, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import and_, not_

from app.database import Base
from app.models.user import User
from app.utils.redis_cache import get_redis_client
from app.utils.runtime_data import upload_dir

logger = logging.getLogger(__name__)

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SCOPED_COLUMNS = ("user_id", "owner_id", "created_by_user_id")
_PRESERVED_TABLES = {"account_deletion_requests"}
_PRIVACY_AUDIT_ACTIONS = {
    "account_deletion_requested",
    "account_deletion_status_updated",
}
_UPLOAD_ROOT = upload_dir()


def _table(db: Session, table_name: str) -> Table:
    if not _IDENTIFIER.fullmatch(table_name):
        raise RuntimeError(f"invalid database identifier in deletion audit: {table_name!r}")
    known = Base.metadata.tables.get(table_name)
    if known is not None:
        return known
    return Table(table_name, MetaData(), autoload_with=db.get_bind())


def _table_names(db: Session) -> list[str]:
    return sorted(inspect(db.get_bind()).get_table_names())


def _row_counts(db: Session, table_name: str, user_id: int) -> dict[str, Any] | None:
    if table_name in _PRESERVED_TABLES:
        return None
    table = _table(db, table_name)
    scoped = [table.c[name] for name in _SCOPED_COLUMNS if name in table.c]
    if not scoped:
        return None

    matched = or_(*[column == user_id for column in scoped])
    total = int(db.execute(select(func.count()).select_from(table).where(matched)).scalar_one() or 0)
    blocking = total
    if table_name == "agent_audit_logs" and {"agent_type", "action"}.issubset(table.c):
        retained = and_(
            table.c.agent_type == "account_privacy",
            table.c.action.in_(_PRIVACY_AUDIT_ACTIONS),
        )
        blocking = int(
            db.execute(
                select(func.count()).select_from(table).where(matched, not_(retained))
            ).scalar_one()
            or 0
        )
    return {
        "table": table_name,
        "matched_columns": [column.name for column in scoped],
        "rows": total,
        "blocking_rows": blocking,
    }


def _upload_report(user_id: int) -> dict[str, Any]:
    roots: list[str] = []
    files = 0
    if _UPLOAD_ROOT.exists():
        for category in ("chat", "diet", "medical", "other"):
            root = _UPLOAD_ROOT / category / str(user_id)
            if not root.exists():
                continue
            roots.append(str(root.relative_to(_UPLOAD_ROOT)))
            files += sum(1 for path in root.rglob("*") if path.is_file())
    return {"status": "checked", "scoped_directories": roots, "files": files}


def _cache_report(user_id: int) -> dict[str, Any]:
    try:
        client = get_redis_client()
        if client is None:
            return {"status": "unavailable", "keys": None, "pattern": f"*{user_id}*"}
        keys = list(client.scan_iter(match=f"*{user_id}*"))
        return {"status": "checked", "keys": len(keys), "pattern": f"*{user_id}*"}
    except Exception as exc:  # noqa: BLE001
        logger.error("账号删除缓存核验失败 - user_id=%s, error=%s", user_id, exc)
        return {
            "status": "error",
            "keys": None,
            "pattern": f"*{user_id}*",
            "error": type(exc).__name__,
        }


def build_deletion_verification_report(db: Session, user_id: int) -> dict[str, Any]:
    """Build a secret-free, health-content-free deletion verification report."""
    table_rows = [
        row
        for table_name in _table_names(db)
        if (row := _row_counts(db, table_name, user_id)) is not None
    ]
    user_exists = db.query(User.id).filter(User.id == user_id).first() is not None
    uploads = _upload_report(user_id)
    cache = _cache_report(user_id)
    blocking_rows = sum(int(row["blocking_rows"]) for row in table_rows)
    cache_clear = cache["status"] == "checked" and cache["keys"] == 0
    can_finalize = (
        not user_exists
        and blocking_rows == 0
        and uploads["files"] == 0
        and cache_clear
    )
    report = {
        "user_exists": user_exists,
        "tables": table_rows,
        "blocking_rows": blocking_rows,
        "uploads": uploads,
        "cache": cache,
        "can_finalize": can_finalize,
    }
    digest_payload = json.dumps(report, ensure_ascii=False, sort_keys=True, default=str).encode()
    report["scope_digest"] = hashlib.sha256(digest_payload).hexdigest()
    return report
