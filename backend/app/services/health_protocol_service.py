"""健康协议层服务(P1 第一刀)。

提供 HealthProtocol 的 CRUD + 今日投影(today_status)+ 双轨完成/跳过(写同一 HealthProtocolEvent)。
饮水域作参考实现;用药/饮食后续 slice 照搬同一模式。
"""
import logging
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.health_protocol import (
    HealthProtocol, HealthProtocolEvent,
    PROTOCOL_DOMAINS, PROTOCOL_MECHANISMS, SKIP_REASONS,
)

logger = logging.getLogger(__name__)


def create_protocol(db: Session, user_id: int, data: Dict[str, Any]) -> HealthProtocol:
    domain = data.get("domain")
    if domain not in PROTOCOL_DOMAINS:
        raise ValueError(f"未知 domain: {domain}")
    mech = data.get("mechanism")
    if mech is not None and mech not in PROTOCOL_MECHANISMS:
        raise ValueError(f"未知 mechanism: {mech}")
    p = HealthProtocol(
        user_id=user_id,
        domain=domain,
        name=data["name"],
        mechanism=mech,
        implied_quantity=data.get("implied_quantity"),
        cadence=data.get("cadence", "daily"),
        time_window=data.get("time_window", "anytime"),
        completion_mode=data.get("completion_mode", "one_tap"),
        can_default_complete=bool(data.get("can_default_complete", False)),
        manual_track_allowed=bool(data.get("manual_track_allowed", True)),
        program_id=data.get("program_id"),
        source_model=data.get("source_model"),
        notes=data.get("notes"),
        status="active",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    logger.info(f"[Protocol] 创建: user={user_id} domain={domain} name={p.name}")
    return p


def list_protocols(db: Session, user_id: int, active_only: bool = True) -> List[HealthProtocol]:
    q = db.query(HealthProtocol).filter(HealthProtocol.user_id == user_id)
    if active_only:
        q = q.filter(HealthProtocol.status == "active")
    return q.order_by(HealthProtocol.created_at.desc()).all()


def get_protocol(db: Session, protocol_id: int, user_id: int) -> Optional[HealthProtocol]:
    return db.query(HealthProtocol).filter(
        HealthProtocol.id == protocol_id, HealthProtocol.user_id == user_id
    ).first()


def archive_protocol(db: Session, protocol_id: int, user_id: int) -> bool:
    p = get_protocol(db, protocol_id, user_id)
    if not p:
        return False
    p.status = "archived"
    db.commit()
    return True


def _is_due_today(p: HealthProtocol) -> bool:
    """本 slice:daily 每天到期;非 daily cadence 的到期投影留后续 slice。"""
    return (p.cadence or "daily") == "daily"


def _today_event(db: Session, protocol_id: int, user_id: int, day: date) -> Optional[HealthProtocolEvent]:
    return db.query(HealthProtocolEvent).filter(
        HealthProtocolEvent.protocol_id == protocol_id,
        HealthProtocolEvent.user_id == user_id,
        HealthProtocolEvent.event_date == day,
    ).order_by(HealthProtocolEvent.created_at.desc()).first()


def today_status(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """今日各活跃协议的待办 + 完成态(双轨任一轨完成都算)。"""
    today = date.today()
    out: List[Dict[str, Any]] = []
    for p in list_protocols(db, user_id, active_only=True):
        ev = _today_event(db, p.id, user_id, today)
        out.append({
            "protocol_id": p.id,
            "domain": p.domain,
            "name": p.name,
            "mechanism": p.mechanism,
            "implied_quantity": p.implied_quantity,
            "time_window": p.time_window,
            "cadence": p.cadence,
            "is_due_today": _is_due_today(p),
            "can_default_complete": p.can_default_complete,
            "manual_track_allowed": p.manual_track_allowed,
            "today_status": ev.status if ev else "pending",
            "today_track": ev.track if ev else None,
            "skip_reason": ev.skip_reason if ev else None,
        })
    return out


def complete_protocol(
    db: Session, protocol_id: int, user_id: int,
    track: str = "protocol", value: Optional[Dict[str, Any]] = None,
    day: Optional[date] = None,
) -> Optional[HealthProtocolEvent]:
    """完成今日协议(track=protocol 协议轨一键/自动;track=manual 手工轨带量)。

    每协议每天一条终态事件:已有终态则更新(改轨/改量/从 skip 翻成 completed),不重复插。
    """
    p = get_protocol(db, protocol_id, user_id)
    if not p:
        return None
    if track not in ("protocol", "manual"):
        raise ValueError(f"未知 track: {track}")
    if track == "manual" and not p.manual_track_allowed:
        raise ValueError("该协议未开放手工轨")
    day = day or date.today()
    ev = _today_event(db, protocol_id, user_id, day)
    if ev is None:
        ev = HealthProtocolEvent(user_id=user_id, protocol_id=protocol_id, event_date=day)
        db.add(ev)
    ev.status = "completed"
    ev.track = track
    ev.value = value
    ev.skip_reason = None
    db.commit()
    db.refresh(ev)
    logger.info(f"[Protocol] 完成: user={user_id} protocol={protocol_id} track={track}")
    return ev


def skip_protocol(
    db: Session, protocol_id: int, user_id: int,
    reason: Optional[str] = None, day: Optional[date] = None,
) -> Optional[HealthProtocolEvent]:
    """跳过今日协议,捕获失败原因(R14,驱动后续协议自纠偏)。"""
    p = get_protocol(db, protocol_id, user_id)
    if not p:
        return None
    if reason is not None and reason not in SKIP_REASONS:
        raise ValueError(f"未知 skip_reason: {reason}(应为 {SKIP_REASONS})")
    day = day or date.today()
    ev = _today_event(db, protocol_id, user_id, day)
    if ev is None:
        ev = HealthProtocolEvent(user_id=user_id, protocol_id=protocol_id, event_date=day)
        db.add(ev)
    ev.status = "skipped"
    ev.skip_reason = reason
    db.commit()
    db.refresh(ev)
    logger.info(f"[Protocol] 跳过: user={user_id} protocol={protocol_id} reason={reason}")
    return ev


# ── 参考实现:饮水 2000ml 温水杯协议(其余域照搬)──────────────
def create_water_cup_protocol(db: Session, user_id: int) -> HealthProtocol:
    """PRD §5 饮水协议:固定容器 + 可默认完成。"""
    return create_protocol(db, user_id, {
        "domain": "hydration",
        "name": "2000ml 温水杯",
        "mechanism": "fixed_container",
        "implied_quantity": {"water_ml": 2000, "temp_c": 50},
        "cadence": "daily",
        "time_window": "anytime",
        "completion_mode": "one_tap",
        "can_default_complete": True,   # 饮水可默认完成只标未达(R12 边界)
        "source_model": "water_records",
    })


def serialize_protocol(p: HealthProtocol) -> Dict[str, Any]:
    return {
        "id": p.id, "domain": p.domain, "name": p.name, "mechanism": p.mechanism,
        "implied_quantity": p.implied_quantity, "cadence": p.cadence,
        "time_window": p.time_window, "completion_mode": p.completion_mode,
        "can_default_complete": p.can_default_complete,
        "manual_track_allowed": p.manual_track_allowed,
        "status": p.status, "program_id": p.program_id, "source_model": p.source_model,
        "notes": p.notes,
    }
