"""健康协议层服务(P1 第一刀)。

提供 HealthProtocol 的 CRUD + 今日投影(today_status)+ 双轨完成/跳过(写同一 HealthProtocolEvent)。
饮水域作参考实现;用药/饮食后续 slice 照搬同一模式。
"""
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.health_protocol import (
    HealthProtocol, HealthProtocolEvent,
    PROTOCOL_DOMAINS, PROTOCOL_MECHANISMS, SKIP_REASONS,
)
from app.utils.timezone import get_user_today

logger = logging.getLogger(__name__)


# 医疗级 source_model → 必须配的 domain(结构性不变量,防御纵深)。
# 议程完成把 medication_logs/supplement_records 当医疗级写(写 MedicationLog / SupplementRecord),
# 而 Rokid 语音「确认/跳过」门用 domain 白名单(hydration/sleep/mood/activity/respiratory)代理「非医疗写」。
# 若允许 {domain:"hydration", source_model:"medication_logs"} 的错配协议,它会以非医疗 type 过语音门,
# 完成时却落真实 MedicationLog —— 绕过 R4 白名单。在创建处钉死配对,把门的安全从「调用点纪律」升成结构性约束。
_MEDICAL_SOURCE_MODEL_DOMAINS = {
    "medication_logs": "medication",
    "supplement_records": "supplement",
    "diet_records": "diet",
}


def create_protocol(db: Session, user_id: int, data: Dict[str, Any]) -> HealthProtocol:
    domain = data.get("domain")
    if domain not in PROTOCOL_DOMAINS:
        raise ValueError(f"未知 domain: {domain}")
    mech = data.get("mechanism")
    if mech is not None and mech not in PROTOCOL_MECHANISMS:
        raise ValueError(f"未知 mechanism: {mech}")
    source_model = data.get("source_model")
    required_domain = _MEDICAL_SOURCE_MODEL_DOMAINS.get(source_model)
    if required_domain is not None and domain != required_domain:
        raise ValueError(
            f"source_model={source_model!r} 必须配 domain={required_domain!r}(实得 {domain!r}):"
            f"医疗级写不得借非医疗 domain 绕过语音/R4 白名单"
        )
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
        source_model=source_model,
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
    - event_triggered:默认不上日历;若带 implied_quantity.trigger_date,则只在触发当天到期
    - 未知 cadence:退回 daily 行为(安全,不漏)
    """
    cadence = p.cadence or "daily"
    if cadence == "event_triggered":
        implied = p.implied_quantity or {}
        return implied.get("trigger_date") == today.isoformat()
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


def _snoozed_until(ev: HealthProtocolEvent) -> Optional[datetime]:
    value = ev.value or {}
    raw = value.get("snoozed_until")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


def _effective_today_status(ev: Optional[HealthProtocolEvent]) -> str:
    if ev is None:
        return "pending"
    if ev.status == "snoozed":
        until = _snoozed_until(ev)
        if until is not None and until > datetime.now(UTC):
            return "snoozed"
        return "pending"
    return ev.status


def today_status(
    db: Session, user_id: int, day: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """今日各活跃协议的待办 + 完成态(双轨任一轨完成都算)。"""
    today = day or get_user_today(db, user_id)
    out: List[Dict[str, Any]] = []
    for p in list_protocols(db, user_id, active_only=True):
        ev = _today_event(db, p.id, user_id, today)
        effective_status = _effective_today_status(ev)
        snoozed_until = _snoozed_until(ev) if ev and effective_status == "snoozed" else None
        out.append({
            "protocol_id": p.id,
            "domain": p.domain,
            "name": p.name,
            "mechanism": p.mechanism,
            # 完成时落哪张业务表(water_records / medication_logs / supplement_records / ...);
            # None = 完成只写协议事件(非医疗级)。下游议程据此判「含糊语音可否安全自动写」,
            # 比 domain 更权威(domain↔source_model 可漂移)。见 agenda_service._is_voice_actionable。
            "source_model": p.source_model,
            "implied_quantity": p.implied_quantity,
            "time_window": p.time_window,
            "cadence": p.cadence,
            "is_due_today": _is_due_today(db, p, user_id, today),
            "can_default_complete": p.can_default_complete,
            "manual_track_allowed": p.manual_track_allowed,
            "today_status": effective_status,
            "today_track": ev.track if ev else None,
            "skip_reason": ev.skip_reason if ev else None,
            "snoozed_until": snoozed_until.isoformat() if snoozed_until else None,
        })
    return out


def _claim_today_event(
    db: Session, protocol_id: int, user_id: int, day: date,
) -> HealthProtocolEvent:
    """拿到今日事件行(并发安全)。

    首次创建竞态由唯一约束 uq_hpe_protocol_date 兜底:两个并发请求都尝试 INSERT,
    一个成功、另一个撞 IntegrityError → rollback + 重读已存在行(D1)。
    """
    ev = _today_event(db, protocol_id, user_id, day)
    if ev is not None:
        return ev
    ev = HealthProtocolEvent(
        user_id=user_id, protocol_id=protocol_id, event_date=day,
        status="pending", track="protocol",
    )
    db.add(ev)
    try:
        db.flush()
    except IntegrityError:
        # 另一个并发请求已建了今日行 → 回滚本次 INSERT,重读那一行
        db.rollback()
        existing = _today_event(db, protocol_id, user_id, day)
        if existing is None:  # 理论不至于(约束撞了说明存在),保底 fail loud
            raise
        return existing
    return ev


def complete_protocol(
    db: Session, protocol_id: int, user_id: int,
    track: str = "protocol", value: Optional[Dict[str, Any]] = None,
    day: Optional[date] = None,
) -> Optional[HealthProtocolEvent]:
    """完成今日协议(track=protocol 协议轨一键/自动;track=manual 手工轨带量)。

    每协议每天一条终态事件:已有终态则更新(改轨/改量/从 skip 翻成 completed),不重复插。

    幂等 / 并发(D1):领域记录(MedicationLog 等)的落库由 **DB 原子状态转移**门控,
    不再靠应用层读-检查-写。用
        UPDATE ... SET status='completed' WHERE id=:id AND status != 'completed'
    抢转移:仅当本事务的 rowcount==1(真把 pending/skipped 翻成 completed)才写领域
    记录 + 审计;rowcount==0(别人已完成 / 已是 completed)→ 跳过领域写。生产 PG 下
    两个并发 POST 至多一个 rowcount==1,故同一剂依从至多落一条。
    """
    p = get_protocol(db, protocol_id, user_id)
    if not p:
        return None
    if track not in ("protocol", "manual"):
        raise ValueError(f"未知 track: {track}")
    if track == "manual" and not p.manual_track_allowed:
        raise ValueError("该协议未开放手工轨")
    day = day or get_user_today(db, user_id)
    ev = _claim_today_event(db, protocol_id, user_id, day)

    # 原子 claim:仅当从「非完成」翻成「完成」才算本事务抢到状态转移。
    res = db.execute(
        update(HealthProtocolEvent)
        .where(
            HealthProtocolEvent.id == ev.id,
            HealthProtocolEvent.status != "completed",
        )
        .values(status="completed", track=track, skip_reason=None)
    )
    won_transition = res.rowcount == 1

    if won_transition:
        merged = dict(value or {})
        # 双轨写同一份业务记录:仅抢到转移的事务落真实领域记录(MedicationLog 等)
        linked = _write_domain_record(db, user_id, p, track, value, day)
        if linked is not None:
            merged["linked_model"] = p.source_model
            merged["linked_record_id"] = linked
        db.execute(
            update(HealthProtocolEvent)
            .where(HealthProtocolEvent.id == ev.id)
            .values(value=merged or None)
        )
        db.commit()
        if linked is not None:
            # 依从是临床推断的事实 → 旁路审计取证(D1 灌水的追溯手段)。
            # 完成已 commit,审计是侧路,任何异常都不得回流主流程(在此兜一层)。
            try:
                from app.agents import audit
                audit.log_watch_complete(
                    db, user_id,
                    protocol_id=protocol_id,
                    source_model=p.source_model,
                    linked_record_id=linked,
                    taken_time=datetime.now().strftime("%H:%M"),
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[Protocol] watch_complete 审计失败(跳过): {e}")
    else:
        # 别人已完成(或已是 completed):状态保持,不重复写领域记录,提交无害 no-op。
        db.commit()

    db.refresh(ev)
    logger.info(f"[Protocol] 完成: user={user_id} protocol={protocol_id} track={track} "
                f"won={won_transition} value={ev.value}")
    return ev


def auto_observe_protocol(
    db: Session, protocol_id: int, user_id: int,
    value: Optional[Dict[str, Any]] = None,
    day: Optional[date] = None,
    commit: bool = True,
) -> Optional[HealthProtocolEvent]:
    """被动设备/可穿戴自动观测到协议完成。

    与用户一键完成不同,这里保留 status=auto_observed,让后续统计能区分
    "用户显式确认" 与 "设备自动观测"。只在 pending/空事件上写入;用户已跳过时
    不用低摩擦自动化覆盖手动决定,避免误识别造成假完成。
    """
    p = get_protocol(db, protocol_id, user_id)
    if not p or p.status != "active":
        return None
    day = day or get_user_today(db, user_id)
    ev = _claim_today_event(db, protocol_id, user_id, day)

    if ev.status in ("completed", "auto_observed"):
        if commit:
            db.commit()
            db.refresh(ev)
        return ev
    if ev.status == "skipped":
        if commit:
            db.commit()
            db.refresh(ev)
        return None

    ev.status = "auto_observed"
    ev.track = "protocol"
    ev.skip_reason = None
    ev.value = value or None
    db.flush()
    if commit:
        db.commit()
        db.refresh(ev)

    logger.info(f"[Protocol] 自动观测: user={user_id} protocol={protocol_id} value={ev.value}")
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
        # commit=False:把用药记录的提交并入 complete_protocol 的一次性 commit,
        # 避免中途提交半成品 event 破坏原子性(S2);四分支(用药/餐/补剂/饮水)对齐用 flush。
        log = medication_service.log_medication(
            db, user_id=user_id, medication_id=p.source_id,
            taken_time=taken_time, status="taken",
            actual_dosage=actual, notes="via protocol", commit=False,
            taken_date=day,
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
        db.add(rec)
        db.flush()
        return rec.id
    if p.source_model == "supplement_records":
        # 补剂依从:一键已吃 → 落 SupplementRecord(taken=True, taken_time≈now)。
        # source_id 链接到 SupplementDefinition.id(= SupplementRecord.supplement_id)。
        if not p.source_id:   # 补剂需链接到具体补剂定义
            return None
        from app.models.supplement import SupplementRecord
        # 单补剂单日一条(uq_supprec_supp_date)。用户可能已在补剂页 / NFC 勾过同日打卡 →
        # 翻成 taken 而非再 INSERT 撞唯一约束(否则协议完成被无辜 500)。读-改-写在协议事件
        # 门控的同一事务内, 跨请求并发由 DB 唯一约束兜底。
        rec = db.query(SupplementRecord).filter(
            SupplementRecord.user_id == user_id,
            SupplementRecord.supplement_id == p.source_id,
            SupplementRecord.record_date == day,
        ).first()
        if rec is not None:
            rec.taken = True
            rec.taken_time = datetime.now().time()
            if not rec.notes:
                rec.notes = "via protocol"
            db.flush()
            return rec.id
        rec = SupplementRecord(
            user_id=user_id, supplement_id=p.source_id, record_date=day,
            taken=True, taken_time=datetime.now().time(), notes="via protocol",
        )
        db.add(rec)
        db.flush()
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
        db.add(rec)
        db.flush()
        return rec.id
    if p.source_model == "exercise_records":
        # 餐后散步 / 微运动协议:完成必须落真实 ExerciseRecord,避免"假完成"。
        from app.models.daily_health import ExerciseRecord
        v = {**(p.implied_quantity or {}), **(value or {})}
        duration = v.get("duration_min") or v.get("duration")
        rec = ExerciseRecord(
            user_id=user_id,
            record_date=day,
            exercise_type=v.get("exercise_type") or "walk",
            duration=int(round(float(duration))) if duration is not None else None,
            intensity=v.get("intensity") or "easy",
            notes=v.get("notes") or "via protocol: 餐后散步",
        )
        db.add(rec)
        db.flush()
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


POSTMEAL_WALK_MEAL_TYPES = {"lunch", "dinner"}


def postmeal_window(meal_type: str, meal_time: Any = None) -> str:
    """餐后散步协议的腕上时间窗。meal_type 使用 /diet/records 的英文枚举。"""
    meal = str(getattr(meal_type, "value", meal_type) or "").lower()
    if meal == "lunch":
        # 有明确较早午餐时间时可贴近 noon;默认下午更稳,避免午休前过早打扰。
        try:
            if meal_time is not None and int(getattr(meal_time, "hour", 99)) <= 12:
                return "noon"
        except Exception:  # noqa: BLE001
            pass
        return "afternoon"
    if meal == "dinner":
        return "evening"
    if meal == "breakfast":
        return "morning"
    return "anytime"


def create_postmeal_walk_protocol(
    db: Session,
    user_id: int,
    *,
    record_date: date,
    meal_type: str,
    meal_time: Any = None,
    diet_record_id: Optional[int] = None,
) -> Optional[HealthProtocol]:
    """午/晚餐后创建一次性 walk 协议。

    幂等:同一用户同一日期同一餐次最多一条;早餐/加餐不触发。
    """
    meal = str(getattr(meal_type, "value", meal_type) or "").lower()
    if meal not in POSTMEAL_WALK_MEAL_TYPES:
        return None

    trigger_date = record_date.isoformat()
    existing = db.query(HealthProtocol).filter(
        HealthProtocol.user_id == user_id,
        HealthProtocol.status == "active",
        HealthProtocol.domain == "exercise",
        HealthProtocol.cadence == "event_triggered",
        HealthProtocol.source_model == "exercise_records",
    ).all()
    for p in existing:
        implied = p.implied_quantity or {}
        if (
            implied.get("trigger_date") == trigger_date
            and implied.get("trigger_meal_type") == meal
            and implied.get("exercise_type") == "walk"
        ):
            return None

    return create_protocol(db, user_id, {
        "domain": "exercise",
        "name": "餐后轻松步行 20 分钟",
        "mechanism": "pre_commit",
        "implied_quantity": {
            "exercise_type": "walk",
            "duration_min": 20,
            "intensity": "easy",
            "trigger_date": trigger_date,
            "trigger_meal_type": meal,
            "source_diet_record_id": diet_record_id,
        },
        "cadence": "event_triggered",
        "time_window": postmeal_window(meal, meal_time),
        "completion_mode": "one_tap",
        "can_default_complete": False,
        "manual_track_allowed": True,
        "source_model": "exercise_records",
        "source_id": diet_record_id,
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
    day = day or get_user_today(db, user_id)
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


def snooze_protocol(
    db: Session, protocol_id: int, user_id: int,
    minutes: int = 30, day: Optional[date] = None,
) -> Optional[HealthProtocolEvent]:
    """稍后今日协议,让 Watch/top_action 暂时不再投影该项。"""
    p = get_protocol(db, protocol_id, user_id)
    if not p:
        return None
    if minutes < 5 or minutes > 240:
        raise ValueError("snooze 分钟数需在 5-240 之间")
    day = day or get_user_today(db, user_id)
    ev = _claim_today_event(db, protocol_id, user_id, day)
    if ev.status in ("completed", "auto_observed", "skipped"):
        raise ValueError("已处理的协议不能稍后")
    expected_value = None
    if ev.status == "snoozed":
        current_until = _snoozed_until(ev)
        if current_until is not None and current_until > datetime.now(UTC):
            return ev
        expected_value = ev.value
    elif ev.status != "pending":
        raise ValueError("当前协议状态不能稍后")

    until = datetime.now(UTC) + timedelta(minutes=minutes)
    transition = [
        HealthProtocolEvent.id == ev.id,
        HealthProtocolEvent.user_id == user_id,
        HealthProtocolEvent.status == ev.status,
    ]
    if ev.status == "snoozed":
        transition.append(HealthProtocolEvent.value == expected_value)
    result = db.execute(
        update(HealthProtocolEvent)
        .where(*transition)
        .values(
            status="snoozed",
            track="protocol",
            skip_reason=None,
            value={"minutes": minutes, "snoozed_until": until.isoformat()},
        )
    )
    if result.rowcount != 1:
        db.rollback()
        current = _today_event(db, protocol_id, user_id, day)
        if current is None:
            return None
        if current.status == "snoozed":
            current_until = _snoozed_until(current)
            if current_until is not None and current_until > datetime.now(UTC):
                return current
            raise ValueError("稍后状态已变化，请重试")
        if current.status in ("completed", "auto_observed", "skipped"):
            raise ValueError("已处理的协议不能稍后")
        raise ValueError("当前协议状态不能稍后")
    db.commit()
    db.refresh(ev)
    logger.info(
        f"[Protocol] 稍后: user={user_id} protocol={protocol_id} minutes={minutes}"
    )
    return ev


def resume_protocol(
    db: Session, protocol_id: int, user_id: int, day: Optional[date] = None,
) -> Optional[tuple[HealthProtocolEvent, bool]]:
    """恢复今日被稍后的协议；重复恢复幂等，终态不得重新打开。"""
    p = get_protocol(db, protocol_id, user_id)
    if not p:
        return None
    day = day or get_user_today(db, user_id)
    ev = _today_event(db, protocol_id, user_id, day)
    if ev is None:
        return None
    if ev.status in ("completed", "auto_observed", "skipped"):
        raise ValueError("已处理的协议不能恢复为待办")
    if ev.status == "pending":
        return ev, True
    if ev.status != "snoozed":
        raise ValueError("只有稍后中的协议可以恢复")

    result = db.execute(
        update(HealthProtocolEvent)
        .where(
            HealthProtocolEvent.id == ev.id,
            HealthProtocolEvent.user_id == user_id,
            HealthProtocolEvent.status == "snoozed",
        )
        .values(status="pending", track="protocol", skip_reason=None, value=None)
    )
    if result.rowcount != 1:
        db.rollback()
        current = _today_event(db, protocol_id, user_id, day)
        if current is None:
            return None
        if current.status == "pending":
            return current, True
        if current.status in ("completed", "auto_observed", "skipped"):
            raise ValueError("已处理的协议不能恢复为待办")
        raise ValueError("只有稍后中的协议可以恢复")
    db.commit()
    db.refresh(ev)
    logger.info(f"[Protocol] 恢复稍后: user={user_id} protocol={protocol_id}")
    return ev, False


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


# ── P6 学习闭环:用户显式应用一条人体工学调参(SUGGEST → APPLY,不劫持)──────
# 只允许应用这些「人体工学」字段;**绝不**改量/剂量(R4)或医疗升级节奏(R13)。
_APPLIABLE_FIELDS = ("time_window", "cadence", "surface", "cooldown")
# 用药/补剂域:绝不让 apply 触碰任何量/剂量键(即便客户端伪造 field 名)。
_APPLY_FORBIDDEN_FIELDS = frozenset(
    {"implied_quantity", "dosage", "actual_dosage", "drug", "dose"}
)
_TIME_WINDOWS = ("morning", "noon", "afternoon", "evening", "bedtime", "anytime")
_CADENCES = ("daily", "weekly", "monthly", "quarterly", "annual", "per_meal_slot")


def apply_adjustment(
    db: Session, protocol_id: int, user_id: int, field: str, to_value: Any,
) -> Optional[HealthProtocol]:
    """用户显式应用一条学习闭环建议(default 是 suggest-only,这里是 opt-in 的写)。

    R4 硬门:
      - field 必须 ∈ _APPLIABLE_FIELDS,且绝不在量/剂量键集合内。
      - **任何** field 落在 _APPLY_FORBIDDEN_FIELDS → ValueError(端点转 400)。
      - surface / cooldown 是「提醒人体工学」语义,不改协议本体的医疗字段:落到
        notes 备注(供提醒侧读),绝不动 implied_quantity / source_* / cadence 的量义。
    R13:绝不在此改 HealthProblem.follow_up / red_lines(那是医疗升级,不归本函数)。
    返回 None = 协议不存在(端点转 404)。
    """
    if field in _APPLY_FORBIDDEN_FIELDS:
        raise ValueError(f"R4 拒绝:不允许通过学习闭环修改量/剂量字段 {field!r}")
    if field not in _APPLIABLE_FIELDS:
        raise ValueError(f"未知/不可应用字段: {field!r}(应为 {_APPLIABLE_FIELDS})")

    p = get_protocol(db, protocol_id, user_id)
    if not p:
        return None

    if field == "time_window":
        tw = str(to_value)
        if tw not in _TIME_WINDOWS:
            raise ValueError(f"未知 time_window: {tw}")
        p.time_window = tw
    elif field == "cadence":
        # R4/R13:用药/补剂域不接受经学习闭环改节奏(多剂塌剂歧义 F5b + 量义敏感)。
        if p.domain in ("medication", "supplement"):
            raise ValueError("用药/补剂域不允许经学习闭环调整节奏(F5b/R13)")
        cad = str(to_value)
        if cad not in _CADENCES:
            raise ValueError(f"未知 cadence: {cad}")
        p.cadence = cad
    elif field in ("surface", "cooldown"):
        # 提醒人体工学:不改协议本体医疗字段,只在 notes 留一条机器可读的提醒偏好。
        prefs = (p.notes or "")
        tag = f"[learn:{field}={to_value}]"
        if tag not in prefs:
            p.notes = (prefs + (" " if prefs else "") + tag)[:1000]

    db.commit()
    db.refresh(p)
    logger.info(f"[Protocol] 应用学习调参: user={user_id} protocol={protocol_id} "
                f"field={field} to={to_value}")
    return p


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
