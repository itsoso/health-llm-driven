"""健康协议层服务(P1 第一刀)。

提供 HealthProtocol 的 CRUD + 今日投影(today_status)+ 双轨完成/跳过(写同一 HealthProtocolEvent)。
饮水域作参考实现;用药/饮食后续 slice 照搬同一模式。
"""
import logging
from datetime import date, datetime, timedelta
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
        source_id=data.get("source_id"),
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


def _period_start(cadence: str, today: date) -> Optional[date]:
    """给定 cadence 的当前周期起始日(用于「本周期内是否已完成」判断)。

    daily/per_meal_slot 每天到期(无周期概念,返回 None);event_triggered 不上日历。
    """
    if cadence == "weekly":
        return today - timedelta(days=today.weekday())          # 本周一
    if cadence == "monthly":
        return today.replace(day=1)                              # 本月一号
    if cadence == "quarterly":
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        return date(today.year, q_start_month, 1)                # 本季度首月一号
    if cadence == "annual":
        return date(today.year, 1, 1)                            # 本年一号
    return None


def _completed_in_period(db: Session, protocol_id: int, user_id: int,
                         since: date, today: date) -> bool:
    """周期内(since..today)是否已有完成/自动观测事件 → 已完成本周期。"""
    return db.query(HealthProtocolEvent.id).filter(
        HealthProtocolEvent.protocol_id == protocol_id,
        HealthProtocolEvent.user_id == user_id,
        HealthProtocolEvent.status.in_(("completed", "auto_observed")),
        HealthProtocolEvent.event_date >= since,
        HealthProtocolEvent.event_date <= today,
    ).first() is not None


def _is_due_today(db: Session, p: HealthProtocol, user_id: int, today: date) -> bool:
    """按 cadence 判定今天是否到期(进议程投影)。

    - daily / per_meal_slot:每天到期(完成态由 today_status 单独反映)
    - weekly/monthly/quarterly/annual:本周期内未完成才到期(完成后掉出,下周期再现)
    - event_triggered:不上日历(由事件触发,非每日投影)→ 不到期
    - 未知 cadence:退回 daily 行为(安全,不漏)
    """
    cadence = p.cadence or "daily"
    if cadence == "event_triggered":
        return False
    since = _period_start(cadence, today)
    if since is None:
        return True  # daily / per_meal_slot / 未知
    return not _completed_in_period(db, p.id, user_id, since, today)


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
            "is_due_today": _is_due_today(db, p, user_id, today),
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
    was_completed = ev is not None and ev.status == "completed"  # 防重复写真实记录
    if ev is None:
        ev = HealthProtocolEvent(user_id=user_id, protocol_id=protocol_id, event_date=day)
        db.add(ev)
    ev.status = "completed"
    ev.track = track
    merged = dict(value or {})
    # 双轨写同一份业务记录:首次从非完成→完成时,落真实领域记录(MedicationLog 等)
    if not was_completed:
        linked = _write_domain_record(db, user_id, p, track, value, day)
        if linked is not None:
            merged["linked_model"] = p.source_model
            merged["linked_record_id"] = linked
    ev.value = merged or None
    ev.skip_reason = None
    db.commit()
    db.refresh(ev)
    logger.info(f"[Protocol] 完成: user={user_id} protocol={protocol_id} track={track} linked={ev.value}")
    return ev


def _write_domain_record(
    db: Session, user_id: int, p: HealthProtocol, track: str,
    value: Optional[Dict[str, Any]], day: date,
) -> Optional[int]:
    """完成适配器:把协议完成落到真实业务表,坐实「双轨写同一份数据」。

    按 source_model 分派;失败**向上抛**(不静默,守 Rule #1:不能写库失败还报完成)。
    未配 source_model/source_id → 协议自身事件即记录,返回 None。
    """
    if not p.source_model:
        return None
    if p.source_model == "medication_logs":
        if not p.source_id:   # 用药需链接到具体药
            return None
        from app.services.medication_service import medication_service
        taken_time = datetime.now().strftime("%H:%M")
        actual = (value or {}).get("actual_dosage")
        log = medication_service.log_medication(
            db, user_id=user_id, medication_id=p.source_id,
            taken_time=taken_time, status="taken",
            actual_dosage=actual, notes="via protocol",
        )
        return log.id
    if p.source_model == "diet_records":
        # 餐模板:协议先验 implied_quantity 为底,手工轨 value 覆盖(改份量)
        from app.models.daily_health import DietRecord
        m = {**(p.implied_quantity or {}), **(value or {})}
        items = m.get("food_items") or m.get("food_name") or p.name
        rec = DietRecord(
            user_id=user_id, record_date=day,
            meal_type=m.get("meal_type") or "加餐",
            food_name=(str(items)[:100] if items else p.name),  # NOT NULL
            food_items=items,
            calories=m.get("calories"), protein=m.get("protein"),
            carbs=m.get("carbs"), fat=m.get("fat"), fiber=m.get("fiber"),
            notes="via protocol",
        )
        db.add(rec); db.flush()
        return rec.id
    if p.source_model == "water_records":
        # 协议轨:implied_quantity 的容量为底(一键=喝完整杯);手工轨:value 覆盖实际量。
        from app.models.daily_health import WaterIntake
        v = {**(p.implied_quantity or {}), **(value or {})}
        amount = v.get("volume_ml") or v.get("water_ml") or v.get("amount_ml")
        if not amount:
            return None
        rec = WaterIntake(
            user_id=user_id, record_date=day, intake_time=datetime.now(),
            amount_ml=int(round(float(amount))),
            drink_type="水", notes="via protocol",
        )
        db.add(rec); db.flush()
        return rec.id
    return None


def create_protocol_for_medication(
    db: Session, user_id: int, medication_id: int, name: Optional[str] = None,
) -> HealthProtocol:
    """从一味已存在的药生成用药域协议:完成(协议轨一键已吃/手工轨)→ 写 MedicationLog。

    用药不能默认完成(R12:必须显式信号/设备数据)。
    """
    from app.models.medication import Medication
    med = db.query(Medication).filter(
        Medication.id == medication_id, Medication.user_id == user_id
    ).first()
    if not med:
        raise ValueError("药品不存在")
    return create_protocol(db, user_id, {
        "domain": "medication",
        "name": name or f"{med.name} 服药",
        "mechanism": "fixed_container",          # 周药盒
        "implied_quantity": {"dosage": med.dosage} if med.dosage else None,
        "cadence": "daily",
        "completion_mode": "one_tap",
        "can_default_complete": False,           # R12:用药禁止默认完成
        "source_model": "medication_logs",
        "source_id": med.id,
    })


def create_protocol_for_meal_template(
    db: Session, user_id: int, template: Dict[str, Any],
) -> HealthProtocol:
    """饮食域:预承诺餐模板(PRD §5)。完成(选模板=记一餐)→ 写 DietRecord。

    template:{name, meal_type, food_items, calories, protein, carbs, fat, fiber}
    """
    if not template.get("name"):
        raise ValueError("餐模板需 name")
    implied = {k: template[k] for k in
               ("meal_type", "food_items", "calories", "protein", "carbs", "fat", "fiber")
               if k in template}
    return create_protocol(db, user_id, {
        "domain": "diet",
        "name": template["name"],
        "mechanism": "pre_commit",               # 预承诺:热量先验已知,不逐餐算
        "implied_quantity": implied,
        "cadence": "daily",
        "completion_mode": "one_tap",
        "can_default_complete": False,           # 进食需显式确认(只有饮水默认完成)
        "source_model": "diet_records",
    })


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
        "source_id": p.source_id, "notes": p.notes,
    }
