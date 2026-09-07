"""Machine-verifiable account deletion scope checks."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
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
_OWNER_UPLOAD_CATEGORIES = {"chat", "diet", "medical", "other", "aigc"}

# Audit only key metadata. Unknown/legacy namespaces (including hashed owners,
# conversation IDs and shared Celery payloads) cannot prove user-data absence.
# Deliberately do not infer ownership from a number elsewhere in a key.
_CACHE_OWNER_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r"(?:daily_rec|supplement_rec|rec_gen_lock):(?P<owner>[1-9][0-9]*):[0-9]{4}-[0-9]{2}-[0-9]{2}",
    r"dim_analysis:(?P<owner>[1-9][0-9]*):[0-9]{4}-[0-9]{2}-[0-9]{2}:[^:\n]+",
    r"(?:twin:v2|twin_env):(?P<owner>[1-9][0-9]*)",
    r"safety:v3:(?P<owner>[1-9][0-9]*):s[0-9]+:l[0-9]+:d[01]",
    r"(?:starter_polish:v2|starter_pregen:v2|starter_pregen:inflight:v2):(?P<owner>[1-9][0-9]*):[a-f0-9]+",
    r"starter_pregen:idx:v2:(?P<owner>[1-9][0-9]*)",
    r"agent_loop:push_count:(?P<owner>[1-9][0-9]*):[0-9]{8}",
    r"genetic_report:agent_summary:v1:u(?P<owner>[1-9][0-9]*):p[1-9][0-9]*",
    r"genetic_snp_detail:v2:user=(?P<owner>[1-9][0-9]*):rsid=[^:\n]+:gt=[^:\n]+",
    r"observability:dashboard:d=[0-9]+:u=(?P<owner>[1-9][0-9]*):j=[01]",
))
_CACHE_SCAN_MAX_PAGES = 128
_CACHE_SCAN_MAX_KEYS = 10_000
_CACHE_KEY_MAX_BYTES = 4096


def _cache_key_owner(key: bytes) -> str | None:
    """Return only a proven owner from a known producer's exact key shape."""
    try:
        text = key.decode("utf-8")
    except UnicodeDecodeError:
        return None
    for pattern in _CACHE_OWNER_PATTERNS:
        matched = pattern.fullmatch(text)
        if matched is not None:
            return matched.group("owner")
    return None


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


def _count_upload_entries(path: Path) -> int:
    """Count residual files without following links or hiding IO failures."""
    if path.is_symlink() or not path.is_dir():
        return 1
    return sum(_count_upload_entries(child) for child in path.iterdir())


def _upload_report(user_id: int) -> dict[str, Any]:
    roots: list[str] = []
    files = 0
    unresolved = 0
    if _UPLOAD_ROOT.is_symlink():
        return {"status": "checked", "scoped_directories": [], "files": 0, "unresolved_files": 1}
    if _UPLOAD_ROOT.exists():
        for category_root in _UPLOAD_ROOT.iterdir():
            category = category_root.name
            if category_root.is_symlink() or not category_root.is_dir():
                unresolved += 1
                continue
            for entry in category_root.iterdir():
                if entry.is_symlink():
                    unresolved += 1
                elif (
                    category in _OWNER_UPLOAD_CATEGORIES
                    and entry.is_dir()
                    and re.fullmatch(r"[1-9][0-9]*", entry.name)
                ):
                    if entry.name == str(user_id):
                        roots.append(str(entry.relative_to(_UPLOAD_ROOT)))
                        files += _count_upload_entries(entry)
                    # Canonical owner directories belonging to other users are
                    # not deletion targets and must never be traversed/deleted.
                elif category == "chat" and entry.name == ".lifecycle.lock" and entry.is_file():
                    continue
                else:
                    # Legacy flat uploads, orphaned avatars and unknown layouts
                    # have no surviving owner proof. Do not silently clear them
                    # or authorize deletion of another user's data.
                    unresolved += _count_upload_entries(entry)
    return {
        "status": "checked",
        "scoped_directories": sorted(roots),
        "files": files,
        "unresolved_files": unresolved,
    }


def _cache_report(user_id: int) -> dict[str, Any]:
    base = {"pattern": "*", "scope": "known_owner_slots_v1"}
    try:
        client = get_redis_client()
        if client is None:
            return {**base, "status": "unavailable", "keys": None}
        cursor = 0
        seen: set[bytes] = set()
        owned = unresolved = 0
        inspected = 0
        complete = False
        # SCAN COUNT is a hint, not a limit. Bound both pages (even empty ones)
        # and returned keys (even duplicates), never treating truncation as zero.
        for _ in range(_CACHE_SCAN_MAX_PAGES):
            cursor, keys = client.scan(cursor, match="*", count=100)
            exceeded = False
            for key in keys:
                if inspected >= _CACHE_SCAN_MAX_KEYS:
                    exceeded = True
                    break
                inspected += 1
                raw = key.encode("utf-8") if isinstance(key, str) else key
                if not isinstance(raw, bytes) or len(raw) > _CACHE_KEY_MAX_BYTES:
                    exceeded = True
                    break
                fingerprint = hashlib.sha256(raw).digest()
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                owner = _cache_key_owner(raw)
                if owner is None:
                    unresolved += 1
                elif owner == str(user_id):
                    owned += 1
            if exceeded:
                break
            if cursor == 0:
                complete = True
                break
        return {
            **base,
            "status": "checked" if complete and unresolved == 0 else "partial",
            "keys": owned,
            "unresolved_keys": unresolved,
            "scanned_keys": len(seen),
            "scan_complete": complete,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("账号删除缓存核验失败 - user_id=%s, error_type=%s", user_id, type(exc).__name__)
        return {
            **base,
            "status": "error",
            "keys": None,
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
    # A User.avatar_url reference is client-controlled (including via WeChat),
    # so it cannot exempt a shared file from residual-data verification.
    uploads = _upload_report(user_id)
    cache = _cache_report(user_id)
    blocking_rows = sum(int(row["blocking_rows"]) for row in table_rows)
    cache_clear = cache["status"] == "checked" and cache["keys"] == 0
    can_finalize = (
        not user_exists
        and blocking_rows == 0
        and uploads["files"] == 0
        and uploads["unresolved_files"] == 0
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
