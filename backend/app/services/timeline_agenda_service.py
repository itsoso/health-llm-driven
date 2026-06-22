"""First-class HealthEvent 议程生命周期 + 闭环完成(Reva 首页脊柱 · Increment 1)。

**这是闭环的修复点**。在此之前:point-in-time 推送提醒用户 → 用户点「完成」→
完成写到 medication/protocol/open-loop 三条独立路径,但首页脊柱项不会熄灭
(没有一条统一的 completed 事实供脊柱读)。

修复方式:把一个被调度的全天行动**物化**成一条 first-class HealthEvent
(agenda_status=pending),完成接口翻该 HealthEvent 的生命周期 **并** 经既有
`agenda_service.complete_item` 双轨回写真实 source —— **不 fork 写路径**。

本模块只管议程生命周期那一层(物化 / 完成 / 跳过 / 过期),业务记录的落库仍由
`health_protocol_service.complete_protocol` 的 DB 原子双轨写负责。

幂等:同一 (user_id, action_kind, complete_ref, scheduled_date) 至多一条 HealthEvent
议程行;双击完成 → 第一次翻 done 并回写,后续命中终态直接返回(一次效果)。
不假装成功:回写失败向上抛,绝不静默吞。
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.health_event import HealthEvent
from app.models.health_protocol import SKIP_REASONS

logger = logging.getLogger(__name__)

# 议程行动项专用 event_type(把这些 HealthEvent 行从设备摄入事实流里区分开)。
AGENDA_EVENT_TYPE = "agenda_action"

# agenda item.type(域)→ 行动种类(action_kind)。push / 客户端据此分类。
_DOMAIN_TO_KIND: Dict[str, str] = {
    "hydration": "hydration",
    "diet": "diet",
    "medication": "medication",
    "supplement": "supplement",
    "training": "movement",
    "movement": "movement",
    "exercise": "movement",
    "measurement": "measurement",
    "activity": "movement",
    "mood": "mood",
    "checkup": "checkup",
    "sleep": "sleep",
}


def kind_for_domain(domain: Optional[str]) -> str:
    return _DOMAIN_TO_KIND.get(str(domain or ""), str(domain or "action"))


def _ref_key(complete_ref: Dict[str, Any]) -> str:
    """complete_ref → 稳定 item_key(用于同日去重)。"""
    ot = complete_ref.get("object_type")
    oid = complete_ref.get("object_id")
    return f"{ot}:{oid}"


def find_agenda_event(
    db: Session, user_id: int, complete_ref: Dict[str, Any], on_date: date,
) -> Optional[HealthEvent]:
    """查同日同 source 的议程 HealthEvent(去重 / 完成回查)。"""
    key = _ref_key(complete_ref)
    day_start = datetime.combine(on_date, datetime.min.time())
    day_end = datetime.combine(on_date, datetime.max.time())
    rows = (
        db.query(HealthEvent)
        .filter(
            HealthEvent.user_id == user_id,
            HealthEvent.event_type == AGENDA_EVENT_TYPE,
            HealthEvent.scheduled_for >= day_start,
            HealthEvent.scheduled_for <= day_end,
        )
        .all()
    )
    for ev in rows:
        ref = ev.complete_ref or {}
        if _ref_key(ref) == key:
            return ev
    return None


def materialize_agenda_event(
    db: Session,
    user_id: int,
    *,
    action_kind: str,
    title: str,
    complete_ref: Dict[str, Any],
    scheduled_for: datetime,
    source: str = "agenda",
) -> HealthEvent:
    """物化(或复用)一个被调度行动的 first-class HealthEvent(agenda_status=pending)。

    幂等:同 (user, complete_ref, scheduled_date) 至多一条。并发首建竞态由重查兜底
    (无 DB 唯一约束 —— 议程行可由多入口物化,用「查→建→撞了重查」而非约束,避免误杀)。
    """
    on_date = scheduled_for.date()
    existing = find_agenda_event(db, user_id, complete_ref, on_date)
    if existing is not None:
        return existing

    ev = HealthEvent(
        user_id=user_id,
        event_type=AGENDA_EVENT_TYPE,
        source=source,
        agenda_status="pending",
        action_kind=action_kind,
        complete_ref=complete_ref,
        scheduled_for=scheduled_for,
        event_time=scheduled_for,
        confirmed_data={"title": title} if title else None,
        association_only=False,
    )
    db.add(ev)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        again = find_agenda_event(db, user_id, complete_ref, on_date)
        if again is None:
            raise
        return again
    db.refresh(ev)
    return ev


class AgendaEventNotFound(Exception):
    """议程 HealthEvent 不存在或不属于该用户(→ 404,跨用户隔离)。"""


class AgendaCompleteError(Exception):
    """完成回写失败(真实 source 写库失败)→ 让调用方感知,不假装成功。"""


def complete_agenda_event(
    db: Session,
    user_id: int,
    event_id: int,
    *,
    status: str = "done",
    skip_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """闭环完成一个议程 HealthEvent。

    1) 用户隔离取行:不存在 / 非本人 → AgendaEventNotFound(端点转 404)。
    2) 幂等:已是终态(done/skipped)→ 直接返回当前态,不二次回写(双击一次效果)。
    3) status=done 且有 complete_ref → 经 agenda_service.complete_item 双轨回写真实 source。
       回写失败向上抛(AgendaCompleteError),HealthEvent 生命周期**不**翻 done(不假装)。
    4) 翻 agenda_status + completed_at,写统一 completed/skipped 事实。
    """
    if status not in ("done", "skipped"):
        raise ValueError(f"未知 status: {status}(应为 done|skipped)")
    if status == "skipped" and skip_reason is not None and skip_reason not in SKIP_REASONS:
        raise ValueError(f"未知 skip_reason: {skip_reason}(应为 {SKIP_REASONS})")

    ev = (
        db.query(HealthEvent)
        .filter(
            HealthEvent.id == event_id,
            HealthEvent.user_id == user_id,
            HealthEvent.event_type == AGENDA_EVENT_TYPE,
        )
        .first()
    )
    if ev is None:
        raise AgendaEventNotFound(f"议程事件不存在: id={event_id}")

    # 幂等:已终态直接返回(双击 / 重放 → 一次效果)。
    if ev.agenda_status in ("done", "skipped"):
        return _serialize(ev, idempotent=True)

    write_result: Optional[Dict[str, Any]] = None
    if status == "done" and ev.complete_ref:
        ref = ev.complete_ref
        object_type = ref.get("object_type")
        object_id = ref.get("object_id")
        track = ref.get("track") or "protocol"
        if object_type is not None and object_id is not None:
            from app.services import agenda_service
            try:
                write_result = agenda_service.complete_item(
                    db, user_id, object_type, int(object_id), track=track,
                )
            except ValueError as e:
                # 不支持经议程完成的来源 / source 不存在 → 让调用方感知(不假装完成)。
                raise AgendaCompleteError(str(e)) from e

    # 生命周期翻态(回写已成功,或本就是 skip / 无 complete_ref 的纯生命周期项)。
    ev.agenda_status = status
    ev.skip_reason = skip_reason if status == "skipped" else None
    ev.completed_at = datetime.now()
    db.commit()
    db.refresh(ev)
    logger.info(
        "[timeline-agenda] complete user=%s event=%s status=%s wrote=%s",
        user_id, event_id, status, bool(write_result),
    )
    out = _serialize(ev, idempotent=False)
    out["source_write"] = write_result
    return out


def _serialize(ev: HealthEvent, *, idempotent: bool) -> Dict[str, Any]:
    title = (ev.confirmed_data or {}).get("title") if ev.confirmed_data else None
    return {
        "event_id": ev.id,
        "agenda_status": ev.agenda_status,
        "action_kind": ev.action_kind,
        "title": title,
        "skip_reason": ev.skip_reason,
        "completed_at": ev.completed_at.isoformat() if ev.completed_at else None,
        "complete_ref": ev.complete_ref,
        "idempotent": idempotent,
    }
