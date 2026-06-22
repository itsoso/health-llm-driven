"""设备观察服务(P2 · 折叠进 HealthEvent 流,无新表)。

观察是**事实**(association_only=False,无诊断/处方,R4)。两类处理:

- SIGNAL(posture_bad/posture_ok/screen_focus_started/screen_focus_ended):
  纯事实。只写一条 HealthEvent —— **不**翻任何议程项、**不**发内联提醒(R15:
  提醒/预算层稍后读累积信号,这里不越权 nudge)。

- COMPLETION(eye_break_completed/pushup_set_completed/nasal_wash_completed/
  hand_sanitize_completed):写 HealthEvent + 经**既有闭环核心**熄灭对应议程项 ——
  `timeline_agenda_service.complete_by_ref(... "health_protocol" ...)`(唯一被认可的
  完成核心:懒物化 + 原子 DB claim + 不重复领域写),并复用
  `health_event_service._auto_observe_protocol` 把协议标记 auto_observed。
  二者收敛到同一条 HealthProtocolEvent(uq_hpe_protocol_date),不 fork 写路径、
  不重复领域写。无法解析协议 → 仅记录事实,不假装完成(fail soft 只对「闭环」这一步)。

观察无业务目标表(不映射 weight/BP/water 的 _write_to_target)。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.health_event import HealthEvent, EventStatus
from app.schemas.device_observation import (
    OBSERVATION_EVENT_TYPES,
    DeviceObservationIngest,
)
from app.services import timeline_agenda_service
from app.services.health_event_service import (
    HealthEventService,
    PROTOCOL_ID_KEYS,
)

logger = logging.getLogger(__name__)

# COMPLETION 动词:闭环熄灭议程项。其余白名单动词皆为 SIGNAL(纯事实)。
# 域映射在 health_event_service.EVENT_PROTOCOL_DOMAINS(单一真相,供 _single_due_passive
# 唯一匹配复用)。eye_break_completed 故意无域,只接受 payload 显式 protocol_id。
COMPLETION_TYPES = frozenset({
    "eye_break_completed",
    "pushup_set_completed",
    "nasal_wash_completed",
    "hand_sanitize_completed",
})
SIGNAL_TYPES = OBSERVATION_EVENT_TYPES - COMPLETION_TYPES

# 高置信度自动确认阈值(与 HealthEventService 一致)。
_AUTO_CONFIRM_THRESHOLD = 0.8


def _explicit_protocol_id(payload: Optional[dict]) -> Optional[int]:
    """payload 里显式 health_protocol_id / protocol_id(无效值按无配置)。"""
    if not isinstance(payload, dict):
        return None
    for key in PROTOCOL_ID_KEYS:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            logger.warning("Invalid protocol id in observation payload: %s=%r", key, value)
            return None
    return None


def _resolve_completion_protocol_id(
    db: Session, user_id: int, event: HealthEvent,
) -> Optional[int]:
    """COMPLETION 观察 → 可解析的协议 id。

    1) payload 显式 health_protocol_id(归该用户的才生效,由下游 get_protocol 兜底)。
    2) 否则复用既有 `_single_due_passive_protocol_id`(读 EVENT_PROTOCOL_DOMAINS 的
       唯一被动协议匹配,不 fork 解析逻辑)。eye_break_completed 无域 → 仅显式 id 可闭环。

    同域有多个待办被动协议时不唯一 → 返回 None(under-close,只记录事实,绝不臆断
    闭环哪一个);此类用户需在 payload 带显式 protocol_id 才能闭环具体协议。
    """
    explicit = _explicit_protocol_id(event.raw_data)
    if explicit is not None:
        return explicit
    return HealthEventService(db)._single_due_passive_protocol_id(event)  # noqa: SLF001


def _close_loop(db: Session, user_id: int, event: HealthEvent) -> None:
    """COMPLETION 观察 → 经既有闭环核心熄灭议程项。

    复用 complete_by_ref(唯一被认可的完成核心:懒物化 + 原子 claim + 双轨回写)。
    无法解析协议 / 协议非本人或不存在(LookupError)→ 仅记录观察事实,不假装完成
    (不 fork done 路径,不跨用户写)。complete_by_ref 内部 commit;随后复用
    _auto_observe_protocol 把同一协议事件标 auto_observed(收敛到同一 HealthProtocolEvent)。
    """
    protocol_id = _resolve_completion_protocol_id(db, user_id, event)
    if protocol_id is None:
        return

    try:
        timeline_agenda_service.complete_by_ref(
            db, user_id, "health_protocol", protocol_id, status="done",
        )
    except LookupError:
        # 协议不存在 / 非本人 → 不闭环、不跨用户写。观察事实已记录,fail soft 只限此步。
        db.rollback()
        logger.info(
            "observation %s: protocol %s not owned by user %s, recorded fact only",
            event.event_type, protocol_id, user_id,
        )
        return

    # 复用既有「设备自动观测协议」核心:把同一协议事件标 auto_observed(commit=False)。
    # complete_by_ref 已把该协议事件翻成 completed → 此调用命中终态早返回,不二次写。
    HealthEventService(db)._auto_observe_protocol(  # noqa: SLF001
        event, None, _AUTO_CONFIRM_THRESHOLD,
    )
    db.commit()


def record_observation(
    db: Session, user_id: int, body: DeviceObservationIngest,
) -> HealthEvent:
    """记录一条设备观察(折叠进 HealthEvent 流)。

    SIGNAL:只写 HealthEvent(不翻议程、不 nudge)。
    COMPLETION:写 HealthEvent + 经 complete_by_ref 闭环议程项(可解析协议时)。
    """
    now = datetime.now(timezone.utc)
    status = (
        EventStatus.auto_confirmed
        if body.confidence >= _AUTO_CONFIRM_THRESHOLD
        else EventStatus.pending
    )
    event = HealthEvent(
        user_id=user_id,
        event_type=body.event_type,
        source=body.provider,
        source_device_id=body.device_type or body.source_session_id,
        raw_data=body.payload,
        confidence=body.confidence,
        status=status,
        association_only=False,  # 观察是事实,R4-clean
        event_time=body.occurred_at or now,
        confirmed_at=now if status == EventStatus.auto_confirmed else None,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    if body.event_type in COMPLETION_TYPES:
        _close_loop(db, user_id, event)
        db.refresh(event)

    logger.info(
        "device observation recorded: user=%s type=%s provider=%s confidence=%.2f status=%s",
        user_id, body.event_type, body.provider, body.confidence, event.status.value,
    )
    return event


def list_observations(
    db: Session,
    user_id: int,
    on_date: Optional[date] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
) -> List[HealthEvent]:
    """列出该用户的设备观察(HealthEvent 投影,严格按 user_id 隔离)。

    复用 HealthEventService.get_events,再收口到观察白名单 + 可选日期过滤。
    """
    if event_type is not None and event_type not in OBSERVATION_EVENT_TYPES:
        return []

    service = HealthEventService(db)
    # get_events 已按 user_id 过滤;不传 event_type 时取较大上限,再在本层收口白名单。
    rows = service.get_events(
        user_id, event_type=event_type, status=None,
        limit=max(limit, 200) if event_type is None else limit,
    )
    out = [r for r in rows if r.event_type in OBSERVATION_EVENT_TYPES]
    if on_date is not None:
        out = [r for r in out if r.event_time and r.event_time.date() == on_date]
    return out[:limit]
