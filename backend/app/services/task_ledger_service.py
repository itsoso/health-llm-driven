"""统一任务账本(Harness 自由度升级 Slice 4)— 一张账本管所有后台活。

只读聚合五个来源,统一 shape ``{kind, title, status, when, source}``:

1. write_intents — pending 全量 + 最近 48h 已裁决(小巴刚替你办完/你刚驳回的)
2. desktop_jobs — active(queued/running)
3. agenda — 未来 48h 的排期项(复用 agenda_service.range_view,不自写 SQL)
4. heartbeat — 最近 emitted 的情境心跳提示(Slice 2 遥测源未落库,见 TODO)
5. recipes — 已存的程序性配方(Slice 3 ProcedureRecipe 未落库,恒空源)

v1 只读:不提供取消/重试(留 v2)。单源查询抛错 fail-loud 计入返回体
``failed_sources``(不整包 500、不静默吞),其余源照常返回。
"""
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 已裁决 write_intent 的「最近」窗口(小时)与各源单次上限(账本是概览,不是分页列表)。
RECENT_DECIDED_HOURS = 48
AGENDA_WINDOW_DAYS = 2
PER_SOURCE_CAP = 20

LedgerItem = Dict[str, Any]


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _as_utc(dt: datetime) -> datetime:
    """naive(SQLite 测试库)按 UTC 处理;aware 原样转 UTC。窗口过滤在 Python 做,
    避免 SQLite 对 tz-aware 绑定参数做字符串比较的坑。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _write_intent_items(db: Session, user_id: int) -> List[LedgerItem]:
    """写意图:pending 全量(待确认)+ 最近 48h 已裁决(executed/dismissed/failed)。"""
    from app.models.write_intent import WriteIntent
    from app.services import write_intent_service

    items: List[LedgerItem] = []
    for wi in write_intent_service.list_pending(db, user_id)[:PER_SOURCE_CAP]:
        items.append({
            "kind": wi["kind"],
            "title": wi["title"],
            "status": wi["status"],          # pending
            "when": wi["created_at"],
            "source": "write_intent",
        })

    decided = (
        db.query(WriteIntent)
        .filter(WriteIntent.user_id == user_id, WriteIntent.status != "pending")
        .order_by(WriteIntent.decided_at.desc())
        .limit(PER_SOURCE_CAP)
        .all()
    )
    cutoff = datetime.now(UTC) - timedelta(hours=RECENT_DECIDED_HOURS)
    for wi in decided:
        if wi.decided_at is None or _as_utc(wi.decided_at) < cutoff:
            continue
        items.append({
            "kind": wi.kind,
            "title": wi.title,
            "status": wi.status,             # executed / dismissed / failed
            "when": _iso(wi.decided_at),
            "source": "write_intent",
        })
    return items


def _desktop_job_items(db: Session, user_id: int) -> List[LedgerItem]:
    """桌面长任务:active(queued/running)。与 api/desktop._active_desktop_jobs 同判据。"""
    from app.models.desktop_job import DesktopJob

    jobs = (
        db.query(DesktopJob)
        .filter(
            DesktopJob.user_id == user_id,
            DesktopJob.status.in_(["queued", "running"]),
        )
        .order_by(DesktopJob.created_at.desc())
        .limit(PER_SOURCE_CAP)
        .all()
    )
    return [{
        "kind": job.job_type,
        "title": job.source_name or job.job_type,
        "status": job.status,                # queued / running
        "when": _iso(job.created_at),
        "source": "desktop_job",
    } for job in jobs]


def _agenda_items(db: Session, user_id: int) -> List[LedgerItem]:
    """议程:未来 48h 有到期日的排期项。复用 agenda_service.range_view(不自写 SQL)。"""
    from app.services import agenda_service

    view = agenda_service.range_view(db, user_id, days=AGENDA_WINDOW_DAYS)
    items: List[LedgerItem] = []
    for entry in (view.get("scheduled") or [])[:PER_SOURCE_CAP]:
        items.append({
            "kind": entry.get("type") or "agenda",
            "title": entry.get("title") or "",
            "status": "overdue" if entry.get("overdue") else "scheduled",
            "when": entry.get("date"),
            "source": "agenda",
        })
    return items


def _heartbeat_items(db: Session, user_id: int) -> List[LedgerItem]:
    """情境心跳最近 emitted。

    TODO(Slice 2): heartbeat_considered/emitted/suppressed_by_budget 遥测尚未落库
    (contextual-heartbeat beat 未上线)。落库后从遥测表读最近 emitted 提示填充本源;
    在那之前诚实返回空,不伪造。
    """
    return []


def _recipe_items(db: Session, user_id: int) -> List[LedgerItem]:
    """程序性配方(Slice 3 ProcedureRecipe)未落库 → 恒空源。模型落库后改为查已存配方。"""
    return []


_SOURCES: List[Tuple[str, Callable[[Session, int], List[LedgerItem]]]] = [
    ("write_intents", _write_intent_items),
    ("desktop_jobs", _desktop_job_items),
    ("agenda", _agenda_items),
    ("heartbeat", _heartbeat_items),
    ("recipes", _recipe_items),
]


def _sort_key(item: LedgerItem) -> Tuple[int, str, str, str]:
    when = item.get("when")
    # 有 when 的按时间升序;无 when 的沉底,再按 (kind, title) 稳定排。
    return (0 if when else 1, str(when or ""), str(item.get("kind") or ""), str(item.get("title") or ""))


def build_ledger(user_id: int, db: Session) -> Dict[str, Any]:
    """统一任务账本:五源只读聚合 → 按 when 排序,(kind, title, when) 去重。

    单源失败 fail-loud:记 log + 计入 ``failed_sources``,不拖垮整个账本。
    """
    items: List[LedgerItem] = []
    failed_sources: List[Dict[str, str]] = []
    for source_name, fetch in _SOURCES:
        try:
            items.extend(fetch(db, user_id))
        except Exception as exc:  # noqa: BLE001 — 单源隔离,失败必须可观测
            logger.exception("[TaskLedger] 源 %s 查询失败 user=%s", source_name, user_id)
            failed_sources.append({"source": source_name, "error": str(exc)})

    seen: set = set()
    deduped: List[LedgerItem] = []
    for item in items:
        key = (item.get("kind"), item.get("title"), item.get("when"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    deduped.sort(key=_sort_key)
    return {"items": deduped, "failed_sources": failed_sources}
