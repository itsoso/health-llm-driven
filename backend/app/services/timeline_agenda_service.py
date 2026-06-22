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
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import update
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


def _action_kind_for(object_type: str) -> str:
    """complete_ref.object_type → 行动种类(action_kind)。

    与 _DOMAIN_TO_KIND / today_timeline 的 kind 标注保持一致:medication/supplement
    各自成 kind(客户端据此分类),health_protocol 等其余沿用其字面类型。
    """
    return _DOMAIN_TO_KIND.get(object_type, object_type)


def complete_by_ref(
    db: Session,
    user_id: int,
    object_type: str,
    object_id: int,
    *,
    status: str = "done",
    skip_reason: Optional[str] = None,
    track: Optional[str] = None,
    value: Optional[Dict[str, Any]] = None,
    title: Optional[str] = None,
    scheduled_for: Optional[datetime] = None,
) -> Dict[str, Any]:
    """按 {object_type, object_id} 闭环完成(push + mobile 手里就这俩键)。

    懒物化:先查当日同 source 的议程 HealthEvent,没有就现物化一条(pending),
    再委托既有 `complete_agenda_event` 做生命周期翻态 + 双轨回写真实 source。
    所有不变量(单次事务、幂等、回写失败不翻 done 且 422)都由 complete_agenda_event 守。

    title 不传则 None —— confirmed_data.title 对药即药名(L3),但已核实 HealthEvent.
    confirmed_data 不进任何 Twin/LLM/orchestrator/export 读路径,存它是受限且与既有
    health_events 一致的;不要把 confirmed_data 引入任何 LLM/Twin 读路径。

    TODO(F5b,多剂闭环前必做):complete_ref 当前仅 {object_type, object_id},不带剂量槽。
    一日两次(BID)/多剂药的两次提醒会落同一 (user, ref, date) 议程行 → 第二剂被幂等短路
    → 依从 under-count。接 BID/多剂提醒前,complete_ref 必须扩出剂量槽(如 {..., "slot": "HH:MM"}),
    并把 slot 并入 find_agenda_event 的去重键 + _slot_time。**当前不声称多剂依从已闭环。**
    """
    from app.services import agenda_service
    from app.utils.timezone import get_user_now, get_user_today

    # F1:物化前先验对 **所有** status 生效(done 与 skip 同标准)。
    # - 不支持的来源 → ValueError(端点转 400);
    # - 来源不存在 / 非本人 → LookupError(端点转 404)。
    # 绝不给外人/不存在/不支持的 ref 凭空物化幻影议程 HealthEvent(skip 此前会漏物化)。
    agenda_service.ensure_source_exists(db, user_id, object_type, object_id)

    ref = {"object_type": object_type, "object_id": object_id}
    today = get_user_today(db, user_id)
    ev = find_agenda_event(db, user_id, ref, today)
    if ev is None:
        # 懒物化的 scheduled_for 取「整点」(minute/second 归零),不取裸 now:并发懒物化
        # 在同一小时内算出同一 scheduled_for → 同一 _slot_time → 万一并发建了两条议程行,
        # 完成时也会落同一 uq_medlog 槽被 DB 唯一约束兜住(配合 complete_agenda_event 的
        # 原子 claim,把重复领域写收敛到至多一条)。
        slot_dt = scheduled_for or get_user_now(db, user_id).replace(
            minute=0, second=0, microsecond=0)
        ev = materialize_agenda_event(
            db, user_id,
            action_kind=_action_kind_for(object_type),
            title=title or "",
            complete_ref=ref,
            scheduled_for=slot_dt,
        )
    return complete_agenda_event(
        db, user_id, ev.id, status=status, skip_reason=skip_reason,
        track=track, value=value,
    )


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
    track: Optional[str] = None,
    value: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """闭环完成 / 跳过一个议程 HealthEvent。

    1) 用户隔离取行:不存在 / 非本人 → AgendaEventNotFound(端点转 404)。
    2) 幂等 / 并发(D1,对齐 complete_protocol):领域记录的落库由 **DB 原子状态转移**门控,
       不靠应用层读-检查-写。用
           UPDATE health_events SET agenda_status=:status WHERE id=:id
             AND agenda_status NOT IN (<不可被本次覆盖的终态>)
       抢转移:仅当本事务 rowcount==1(真翻成本次终态)才回写领域记录;rowcount==0
       (并发/双击/重放里别人已完成)→ 不二次回写,重读返回 idempotent=True(双击一次效果)。
       这堵住「两个并发 POST 各读到 pending → 各写一条 MedicationLog → 虚高依从污染
       DDI/PGx/SafetyGuardian」(历史教训:依从写回的幂等必须 DB 兜底)。
    3) **F2 supersede**:done 与 skipped 都经 agenda_service.complete_item 回写真实 source
       (done→taken/completed、skipped→skipped 行)。状态转移规则:
         - pending → done / skipped:允许(常规完成/跳过)。
         - skipped → done:**允许**(用户先跳后服 → 必须能记成已服;源行同槽 supersede)。
         - done → 任何:拒绝(已服不可改写,守 R4;幂等返回当前 done)。
         - x → 同 x:幂等返回。
       回写失败抛(AgendaCompleteError/LookupError),整个事务回滚(连状态转移一起撤),
       HealthEvent 生命周期**不**翻态(不假装,fail-loud)。
    4) taken_time 用议程事件的 scheduled_for(确定性槽),不用 wall-clock now —— 同一议程项
       skip→done / 重复完成必落同一 uq_medlog_med_date_time 槽,源行 supersede / DB 唯一约束
       二次兜底;跨分钟也不漏。

    track / value 可选:不传(既有 event_id 端点调用方)→ 沿用 ref 内的 track、无手工量,
    行为与改前完全一致;传入(统一 /agenda/complete 手工轨)→ 把用户实际量/剂量透传给
    complete_item(否则会静默丢失用户填的 volume_ml / actual_dosage)。
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

    # 快路幂等 / 终态门控(在抢转移前先判,省一次空 UPDATE):
    # - 当前已是本次请求的终态 → 幂等返回。
    # - 当前 done,请求 skipped → 拒绝降级(已服不可改写成漏服,守 R4),幂等返回当前 done。
    # - 当前 skipped,请求 done → 放行进抢转移(F2 supersede:先跳后服记成已服)。
    if ev.agenda_status == status:
        return _serialize(ev, idempotent=True)
    if ev.agenda_status == "done":
        # done 是不可覆盖的最终态(skip 无权降级它)。返回当前 done,不报错(幂等语义)。
        return _serialize(ev, idempotent=True)

    # 不可被本次覆盖的终态集合:done 永不可覆盖;skipped 仅在「升级为 done」时可被覆盖。
    blocked = ("done", "skipped") if status == "skipped" else ("done",)

    # 原子 claim:仅当从「可覆盖态」翻成本次终态才算抢到状态转移(并发至多一个 rowcount==1)。
    completed_at = datetime.now(timezone.utc)  # 列为 DateTime(timezone=True),写 tz-aware。
    res = db.execute(
        update(HealthEvent)
        .where(
            HealthEvent.id == ev.id,
            HealthEvent.user_id == user_id,
            HealthEvent.agenda_status.notin_(blocked),
        )
        .values(
            agenda_status=status,
            skip_reason=skip_reason if status == "skipped" else None,
            completed_at=completed_at,
        )
    )
    won_transition = res.rowcount == 1

    if not won_transition:
        # 没抢到 → 并发里别人已翻成不可覆盖态。撤本次空转,重读返回 idempotent(一次效果)。
        db.rollback()
        again = (
            db.query(HealthEvent)
            .filter(HealthEvent.id == event_id, HealthEvent.user_id == user_id)
            .first()
        )
        if again is None:  # 理论不至于
            raise AgendaEventNotFound(f"议程事件不存在: id={event_id}")
        return _serialize(again, idempotent=True)

    # F2:done 与 skipped 都回写真实 source(skip 也写源行 → today_status 翻 skipped,
    # 不再 re-nag、跨视图一致)。仅抢到转移的事务回写;失败 → 整事务回滚(状态转移一并撤)。
    write_result: Optional[Dict[str, Any]] = None
    if ev.complete_ref:
        ref = ev.complete_ref
        object_type = ref.get("object_type")
        object_id = ref.get("object_id")
        # track 优先用显式入参(统一完成端点的手工/协议轨),回退 ref 内的 track,再回退协议轨。
        effective_track = track or ref.get("track") or "protocol"
        if object_type is not None and object_id is not None:
            from app.services import agenda_service
            try:
                write_result = agenda_service.complete_item(
                    db, user_id, object_type, int(object_id),
                    track=effective_track, value=value,
                    taken_time=_slot_time(ev),
                    status=status, skip_reason=skip_reason,
                )
            except LookupError:
                # 资源不存在 / 非本人 → 回滚 + 上抛(端点转 404,跨用户隔离),不翻态。
                db.rollback()
                raise
            except ValueError as e:
                # 不支持经议程完成的来源 / source 不存在 → 回滚 + 让调用方感知(不假装完成)。
                db.rollback()
                raise AgendaCompleteError(str(e)) from e
            except IntegrityError as e:
                # 领域唯一约束撞(同槽并发/重放)→ 回滚 + 当回写失败上抛,绝不静默二写。
                db.rollback()
                raise AgendaCompleteError(f"领域记录唯一约束冲突: {e}") from e

    db.commit()
    db.refresh(ev)
    logger.info(
        "[timeline-agenda] complete user=%s event=%s status=%s wrote=%s",
        user_id, event_id, status, bool(write_result),
    )
    out = _serialize(ev, idempotent=False)
    out["source_write"] = write_result
    return out


def _slot_time(ev: HealthEvent) -> str:
    """议程事件 → 确定性 taken_time("HH:MM")。

    用 scheduled_for(议程项的代表时点)而非 wall-clock now:同一议程项两次完成落同一
    uq_medlog_med_date_time 槽,让 DB 唯一约束真兜住二次写;多剂(不同 scheduled_for)
    仍各自成槽不误伤。无 scheduled_for 时回退 event_time,再回退中国时区 now。
    """
    slot = ev.scheduled_for or ev.event_time
    if slot is not None:
        return slot.strftime("%H:%M")
    from app.utils.timezone import get_china_now
    return get_china_now().strftime("%H:%M")


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
