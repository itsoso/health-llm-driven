"""Write 层 v0 服务 —— 写意图账本(propose → 一键确认才执行)。

见 docs/design/health-os/architecture-lens.md。v0 只做一个 syscall:
**复查到点 → 提议建提醒**(良性写,不改药/不开方)。全 manual_confirm,不自治。

不变量:
- user_id 一律由调用方(端点)从 token 传入,查询全按 user_id 过滤(IDOR 安全)。
- propose 幂等:同 (user, kind, target) 已有 pending → 不重复提。
- confirm 原子门:仅 (id,user,status=pending) → executed,同事务内执行;执行失败整体
  回滚(状态退回 pending,绝不假装成功)。双击下第二次 update 命中 0 行 → 幂等返回不重执行。
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.smart_reminder import SmartReminder
from app.models.write_intent import WriteIntent


def _view(wi: WriteIntent) -> Dict[str, Any]:
    return {
        "id": wi.id,
        "kind": wi.kind,
        "title": wi.title,
        "description": wi.description,
        "status": wi.status,
        "source": wi.source,
        "trust_tier": wi.trust_tier,
        "target_type": wi.target_type,
        "target_id": wi.target_id,
        "payload": wi.payload,
        "executed_ref": wi.executed_ref,
        "created_at": wi.created_at.isoformat() if wi.created_at else None,
    }


def list_pending(db: Session, user_id: int) -> List[Dict[str, Any]]:
    rows = (
        db.query(WriteIntent)
        .filter(WriteIntent.user_id == user_id, WriteIntent.status == "pending")
        .order_by(WriteIntent.created_at.desc())
        .all()
    )
    return [_view(r) for r in rows]


def _has_decided_target(
    db: Session,
    user_id: int,
    kind: str,
    target_type: Optional[str],
    target_id,
    *,
    payload_key: Optional[str] = None,
    payload_value: Any = None,
) -> bool:
    """同一个生成源已被用户确认/忽略过 → 不再重新生成待确认项。

    复查类目标会随到期日推进,所以支持用 payload_key 比对同一到期批次;以后 source 的
    next_due / planned_end_date 变化后,仍可重新进入提醒窗口。
    """
    rows = (
        db.query(WriteIntent)
        .filter(
            WriteIntent.user_id == user_id,
            WriteIntent.kind == kind,
            WriteIntent.target_type == target_type,
            WriteIntent.target_id == target_id,
            WriteIntent.status != "pending",
        )
        .order_by(WriteIntent.created_at.desc())
        .all()
    )
    if not rows:
        return False
    if payload_key is None:
        return True
    expected = None if payload_value is None else str(payload_value)
    for row in rows:
        payload = row.payload or {}
        actual = payload.get(payload_key)
        if (None if actual is None else str(actual)) == expected:
            return True
    return False


def propose(
    db: Session,
    user_id: int,
    *,
    kind: str,
    title: str,
    description: Optional[str],
    source: str,
    target_type: Optional[str],
    target_id: Optional[int],
    payload: Optional[Dict[str, Any]] = None,
    commit: bool = True,
) -> Optional[WriteIntent]:
    """提一个待确认写意图。同 (user,kind,target) 已有 pending → 返回 None(不重复)。"""
    existing = (
        db.query(WriteIntent)
        .filter(
            WriteIntent.user_id == user_id,
            WriteIntent.kind == kind,
            WriteIntent.status == "pending",
            WriteIntent.target_type == target_type,
            WriteIntent.target_id == target_id,
        )
        .first()
    )
    if existing is not None:
        return None
    wi = WriteIntent(
        user_id=user_id,
        kind=kind,
        title=title,
        description=description,
        source=source,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
        status="pending",
        trust_tier="manual_confirm",
    )
    db.add(wi)
    if commit:
        db.commit()
        db.refresh(wi)
    else:
        db.flush()
    return wi


def confirm(
    db: Session, user_id: int, intent_id: int, *, trust_tier: Optional[str] = None
) -> Dict[str, Any]:
    """一键确认 → 执行。原子门防双执行;执行失败整体回滚(状态退回 pending,fail loud)。

    trust_tier(可选):自治路径(write_autonomy)传 'auto',让信任档**只在赢得原子认领的
    那一条**(affected==1)上随 status 一起翻成 auto —— 绝不在认领前用旁路 ORM mutation 改
    trust_tier(否则并发下若另一路先以 manual 执行了同条,本路的 flush 会把它误标成 auto)。
    默认 None=不改 trust_tier,人确认路径(端点)行为零变化。
    """
    wi = (
        db.query(WriteIntent)
        .filter(WriteIntent.id == intent_id, WriteIntent.user_id == user_id)
        .first()
    )
    if wi is None:
        raise LookupError("write_intent not found")  # 端点 → 404(含 IDOR)
    if wi.status != "pending":
        return {"id": wi.id, "status": wi.status, "executed_ref": wi.executed_ref, "idempotent": True}

    claim_values: Dict[str, Any] = {"status": "executed", "decided_at": datetime.now(timezone.utc)}
    if trust_tier is not None:
        claim_values["trust_tier"] = trust_tier  # 只随赢得认领的那条原子翻档
    affected = (
        db.query(WriteIntent)
        .filter(
            WriteIntent.id == intent_id,
            WriteIntent.user_id == user_id,
            WriteIntent.status == "pending",
        )
        .update(claim_values, synchronize_session=False)
    )
    if affected != 1:
        # 并发双击:别人先 claim 了 → 不重复执行
        db.rollback()
        db.refresh(wi)
        return {"id": wi.id, "status": wi.status, "executed_ref": wi.executed_ref, "idempotent": True}

    # 赢得认领后,把内存对象 trust_tier 同步成已写入 DB 的值(claim 用 synchronize_session=False
    # 不会回填内存)——_execute 据 wi.trust_tier 分流(如自治产物用 low 优先级)。只在 affected==1
    # 后同步 → 不破坏"只随赢得认领的那条翻档"的防误标语义。
    if trust_tier is not None:
        wi.trust_tier = trust_tier

    try:
        ref = _execute(db, wi)
    except Exception:
        db.rollback()  # 撤销 status=executed,回到 pending,不假装成功
        raise
    db.query(WriteIntent).filter(WriteIntent.id == intent_id).update(
        {"executed_ref": ref}, synchronize_session=False
    )
    db.commit()
    db.refresh(wi)
    # P5 外部动作(food_order 财务相邻 → audit_required;doctor_booking/alarm_set/
    # environment_actuation 也记)。
    # 旁路审计:失败不抛、不回滚已确认的写意图(取证写不能反噬主流程)。
    if wi.kind in ("food_order", "doctor_booking", "alarm_set", "environment_actuation"):
        from app.agents import audit

        if wi.kind == "food_order":
            outcome = "drafted_acknowledged"
        elif wi.kind == "environment_actuation":
            outcome = "actuation_acknowledged"
        else:
            outcome = "reminder_created"
        audit.log_external_action_intent(
            db, wi.user_id, intent_id=wi.id, kind=wi.kind, outcome=outcome,
            target_type=wi.target_type, target_id=wi.target_id,
        )
    return {"id": wi.id, "status": "executed", "executed_ref": ref, "idempotent": False}


def dismiss(db: Session, user_id: int, intent_id: int) -> Dict[str, Any]:
    wi = (
        db.query(WriteIntent)
        .filter(WriteIntent.id == intent_id, WriteIntent.user_id == user_id)
        .first()
    )
    if wi is None:
        raise LookupError("write_intent not found")
    if wi.status == "pending":
        wi.status = "dismissed"
        wi.decided_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(wi)
    return {"id": wi.id, "status": wi.status}


# ─────────────────────────── 执行(syscall 分发)───────────────────────────


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _remind_at_for(next_due: Optional[str], overdue: Optional[bool]) -> datetime:
    """复查提醒时间:逾期 → 明天 9 点;否则到期日 9 点(已过则明天)。"""
    today = datetime.now(timezone.utc).date()
    target = None
    if not overdue and next_due:
        d = _parse_dt(next_due)
        target = d.date() if d else None
    if target is None or target < today:
        target = today + timedelta(days=1)
    return datetime(target.year, target.month, target.day, 9, 0, tzinfo=timezone.utc)


def _execute(db: Session, wi: WriteIntent) -> str:
    """按 kind 分发执行。未知 kind → fail loud(不静默)。返回执行产物引用。"""
    if wi.kind == "checkup_reminder":
        p = wi.payload or {}
        rem = SmartReminder(
            user_id=wi.user_id,
            title=wi.title,
            message=p.get("what_to_check") or wi.description,
            remind_at=_parse_dt(p.get("remind_at")) or _remind_at_for(p.get("next_due"), False),
            priority="normal",
            status="pending",
            source="health_assistant",
            extra_data={
                "write_intent_id": wi.id,
                "target_type": wi.target_type,
                "target_id": wi.target_id,
                "kind": wi.kind,
            },
        )
        db.add(rem)
        db.flush()
        return f"smart_reminder:{rem.id}"
    if wi.kind == "measurement_prompt":
        # 良性写:确认 → 建一条「今天测量并记录」的提醒(不改药/不开方/不诊断)。
        p = wi.payload or {}
        rem = SmartReminder(
            user_id=wi.user_id,
            title=wi.title,
            message=wi.description or "记得测量并记录",
            remind_at=_parse_dt(p.get("remind_at")) or (datetime.now(timezone.utc) + timedelta(hours=1)),
            # 自治创建(trust_tier=auto)→ low 优先级:静音 + 尊重勿扰时段(用户未主动确认,
            # 不该在睡眠窗推带声通知);人确认的仍 normal。
            priority="low" if wi.trust_tier == "auto" else "normal",
            status="pending",
            source="health_assistant",
            extra_data={
                "write_intent_id": wi.id,
                "target_type": wi.target_type,
                "kind": wi.kind,
                "metric": p.get("metric"),
            },
        )
        db.add(rem)
        db.flush()
        return f"smart_reminder:{rem.id}"
    if wi.kind == "recheck_due":
        # 良性写:确认 → 建一条「该复查了,记录复查」的提醒(不改药/不开方/不诊断)。
        p = wi.payload or {}
        rem = SmartReminder(
            user_id=wi.user_id,
            title=wi.title,
            message=wi.description or "该复查了,记录一次复查",
            remind_at=_parse_dt(p.get("remind_at")) or _remind_at_for(p.get("planned_end_date"), p.get("overdue", False)),
            priority="normal",
            status="pending",
            source="health_assistant",
            extra_data={
                "write_intent_id": wi.id,
                "target_type": wi.target_type,
                "target_id": wi.target_id,
                "kind": wi.kind,
            },
        )
        db.add(rem)
        db.flush()
        return f"smart_reminder:{rem.id}"
    if wi.kind == "hearing_health_task":
        # 良性写:确认 → 建一条听力测试/噪音回顾提醒。不诊断,不替代专业听力评估。
        p = wi.payload or {}
        rem = SmartReminder(
            user_id=wi.user_id,
            title=wi.title,
            message=wi.description or "建立或更新听力健康基线",
            remind_at=_parse_dt(p.get("remind_at")) or (datetime.now(timezone.utc) + timedelta(days=7)),
            priority=p.get("priority") or "normal",
            status="pending",
            source="health_assistant",
            extra_data={
                "write_intent_id": wi.id,
                "target_type": wi.target_type,
                "target_id": wi.target_id,
                "kind": wi.kind,
                "task_type": p.get("task_type"),
            },
        )
        db.add(rem)
        db.flush()
        return f"smart_reminder:{rem.id}"
    if wi.kind == "adherence_nudge":
        # 写依从事实:确认即用户断言「我服了」。同事务内只 flush(外层 confirm 统一 commit);
        # 幂等防虚高依从(虚高依从会经 twin.medication.adherence 误证给 DDI/PGx/SafetyGuardian)。
        from datetime import date as _date
        from sqlalchemy.exc import IntegrityError
        p = wi.payload or {}
        item_type = p.get("item_type")
        today = _date.today()  # 与服药/补剂子系统口径一致(服务器 Asia/Shanghai)
        if item_type == "medication":
            from app.models.medication import MedicationLog

            def _find_med():
                return (
                    db.query(MedicationLog)
                    .filter(
                        MedicationLog.user_id == wi.user_id,
                        MedicationLog.medication_id == wi.target_id,
                        MedicationLog.taken_date == today,
                        MedicationLog.taken_time.is_(None),
                    )
                    .order_by(MedicationLog.id.desc())
                    .first()
                )

            existing = _find_med()
            if existing is not None:  # 今天已按日标记 → 幂等,不重复写
                return f"medication_log:{existing.id}"
            log = MedicationLog(
                user_id=wi.user_id, medication_id=wi.target_id,
                taken_date=today, taken_time=None, status="taken",
                notes="write_intent:adherence_nudge",
            )
            try:
                with db.begin_nested():  # SAVEPOINT:并发撞 uq_medlog 只回滚这条 INSERT,不毁外层事务
                    db.add(log)
                    db.flush()
                return f"medication_log:{log.id}"
            except IntegrityError:  # TOCTOU:另一路已落同槽 → 收敛到既有行,不虚高依从
                dup = _find_med()
                if dup is None:  # 撞约束却查不到 → 反常,fail loud
                    raise
                return f"medication_log:{dup.id}"
        if item_type == "supplement":
            from app.models.supplement import SupplementRecord

            def _find_supp():
                return (
                    db.query(SupplementRecord)
                    .filter(
                        SupplementRecord.user_id == wi.user_id,
                        SupplementRecord.supplement_id == wi.target_id,
                        SupplementRecord.record_date == today,
                    )
                    .first()
                )

            existing = _find_supp()
            if existing is not None:  # 幂等:已有当日行 → 置 taken,不新增
                existing.taken = True
                db.flush()
                return f"supplement_record:{existing.id}"
            rec = SupplementRecord(
                user_id=wi.user_id, supplement_id=wi.target_id,
                record_date=today, taken=True,
            )
            try:
                with db.begin_nested():  # SAVEPOINT:并发撞 uq_supprec 只回滚这条 INSERT
                    db.add(rec)
                    db.flush()
                return f"supplement_record:{rec.id}"
            except IntegrityError:
                dup = _find_supp()
                if dup is None:
                    raise
                dup.taken = True
                db.flush()
                return f"supplement_record:{dup.id}"
        raise ValueError(f"unknown adherence_nudge item_type: {item_type}")
    if wi.kind == "reorder_nudge":
        # P3(D1):复购提醒。确认 = **仅确认知悉(acknowledge)**,绝不下单/购买/支付。
        # 本期不调任何电商 skill、不建 ReorderIntent —— 那是 PRD §3.D2(P5)的财务面,
        # 要过 governance 一等对象 Gate + 财务安全评审。这里 confirm 只把意图标记为已处理。
        # D2 落地时,会把这里的 acknowledge 换成「调快手电商 Agent action 下单」(仍逐笔强确认)。
        return "acknowledged"
    if wi.kind == "alarm_set":
        # P5 external-action:闹钟设置。确认 → 建一条 SmartReminder(后端只**记录**提醒,
        # 实际闹钟由设备/客户端到点触发)。良性写,零 R4 面(无饮食/训练/诊断措辞)。
        # 不假装成功:executed_ref 带上 reminder id,客户端据此把意图与设备闹钟关联;
        # 客户端设备侧闹钟设置失败应自行回报(本端只承诺"已记录提醒",不冒充"已上闹钟")。
        p = wi.payload or {}
        rem = SmartReminder(
            user_id=wi.user_id,
            title=wi.title,
            message=wi.description or (p.get("label") or "闹钟提醒"),
            remind_at=_parse_dt(p.get("alarm_time")) or (datetime.now(timezone.utc) + timedelta(hours=8)),
            priority="normal",
            status="pending",
            source="health_assistant",
            extra_data={
                "write_intent_id": wi.id,
                "kind": wi.kind,
                "alarm_time": p.get("alarm_time"),
                "label": p.get("label"),
            },
        )
        db.add(rem)
        db.flush()
        return f"smart_reminder:{rem.id}"
    if wi.kind == "doctor_booking":
        # P5 external-action:医生预约。确认 → 建一条「去 <科室> 预约 <项目> 复查」提醒。
        # **不做真挂号**(out of scope,需外部挂号 skill + 账号绑定 + 安全评审);只产出物流
        # 提醒(纯逻辑、非诊断,R4 安全)。预约本身仍由用户线下/院方 App 完成。
        p = wi.payload or {}
        dept = p.get("department") or "对应科室"
        item = p.get("item_name") or "复查项目"
        rem = SmartReminder(
            user_id=wi.user_id,
            title=wi.title,
            message=wi.description or f"去{dept}预约{item}复查",
            remind_at=_parse_dt(p.get("remind_at")) or _remind_at_for(p.get("next_due_date"), False),
            priority="normal",
            status="pending",
            source="health_assistant",
            extra_data={
                "write_intent_id": wi.id,
                "target_type": wi.target_type,
                "target_id": wi.target_id,
                "kind": wi.kind,
                "department": p.get("department"),
                "hospital": p.get("hospital"),
                "item_name": p.get("item_name"),
            },
        )
        db.add(rem)
        db.flush()
        return f"smart_reminder:{rem.id}"
    if wi.kind == "food_order":
        # P5 external-action:外卖下单 —— **DRAFT ONLY,确认即惰性(acknowledge)**。
        # 财务硬边界:此分支**绝不**下单、绝不付款、绝不触碰任何支付字段、绝不调外卖网关。
        # 仓库里唯一能"下单"的入口是 food_order_skill_gateway.place_order,它恒抛
        # NotImplementedError —— 本分支根本不调它(财务路径在代码上可证为惰性 inert)。
        # 真实下单待本系统 Agent action 就绪 + 财务安全评审后,才会逐笔强确认接入。
        return "acknowledged"
    if wi.kind == "environment_actuation":
        # P5 external-action:环境/家居设备下行 —— **ACK + event only**。
        # 财务/硬件边界:确认后只写 BedroomAutomationEvent(source=reva),作为「用户确认过
        # 这个受白名单保护的动作」的审计事实;不调用 Home Assistant,不调 webhook,不发任意
        # service_data。真正 HA 下发需单独接入凭证、设备状态回执和失败补偿。
        from app.models.bedroom_environment import BedroomAutomationEvent

        p = _normalize_environment_actuation_payload(wi.payload or {})
        event = BedroomAutomationEvent(
            user_id=wi.user_id,
            room_id=p["room_id"],
            event_type="environment_actuation_confirmed",
            reason=p.get("reason") or wi.description,
            command_entity_id=p["command_entity_id"],
            command_mode=p["command_mode"],
            source="reva",
            manual_override=False,
        )
        db.add(event)
        db.flush()
        return f"bedroom_automation_event:{event.id}"
    raise ValueError(f"unknown write_intent kind: {wi.kind}")


# ─────────────────────────── 生成器(第一个提议源)───────────────────────────


def generate_followup_recall(db: Session, user_id: int, within_days: int = 14) -> int:
    """复查到点召回:扫 HealthProblem follow_up 到期/逾期 → 提议「复查提醒」写意图(幂等)。

    返回本次新建的提议数。复用 health_problem_service.due_followups(议程同源)。
    """
    from app.services import health_problem_service as prob_svc

    created = 0
    for f in prob_svc.due_followups(db, user_id, within_days=within_days):
        name = f.get("name")
        remind_at = _remind_at_for(f.get("next_due"), f.get("overdue"))
        if _has_decided_target(
            db,
            user_id,
            "checkup_reminder",
            "health_problem",
            f.get("problem_id"),
            payload_key="next_due",
            payload_value=f.get("next_due"),
        ):
            continue
        wi = propose(
            db,
            user_id,
            kind="checkup_reminder",
            title=f"复查提醒:{name}",
            description=f.get("what_to_check") or f"{name} 该复查了",
            source="followup_recall",
            target_type="health_problem",
            target_id=f.get("problem_id"),
            payload={
                "remind_at": remind_at.isoformat(),
                "what_to_check": f.get("what_to_check"),
                "next_due": f.get("next_due"),
            },
            commit=False,
        )
        if wi is not None:
            created += 1
    db.commit()
    return created


def generate_measurement_prompts(db: Session, user_id: int) -> int:
    """测量缺口提议:有进行中干预周期 + 今天还没测 BP/体重 → 提议「现在测一下」(良性提醒)。

    只在有 active cycle 时提(闭环上下文,喂快反馈指标),不打扰无周期用户。同一 metric 今天
    已提过(任何状态)→ 不再提,防同日反复 nag。返回新建提议数。
    """
    from app.services.intervention_cycle_service import get_active_cycle
    from app.models.blood_pressure import BloodPressureRecord
    from app.models.weight import WeightRecord
    from app.utils.timezone import get_china_today

    if get_active_cycle(db, user_id) is None:
        return 0

    # 用北京日历日:BP/体重 record_date 按北京时写入(全仓 record_date==today 都用 get_china_today)。
    today = get_china_today()
    _beijing = timezone(timedelta(hours=8))
    specs = [
        ("bp", "血压", BloodPressureRecord),
        ("weight", "体重", WeightRecord),
    ]
    created = 0
    for metric, label, model in specs:
        target_type = f"measurement_{metric}"
        # 今天已有该测量记录 → 不必提
        has_today = (
            db.query(model.id)
            .filter(model.user_id == user_id, model.record_date == today)
            .first()
            is not None
        )
        if has_today:
            continue
        # 今天已提过(任何状态)→ 不重复 nag(按存储时间的日历日比对,tz 安全)
        last = (
            db.query(WriteIntent)
            .filter(
                WriteIntent.user_id == user_id,
                WriteIntent.kind == "measurement_prompt",
                WriteIntent.target_type == target_type,
            )
            .order_by(WriteIntent.created_at.desc())
            .first()
        )
        if last is not None and last.created_at is not None:
            ca = last.created_at
            if ca.tzinfo is None:  # SQLite 存的是 naive UTC;PG 为 tz-aware
                ca = ca.replace(tzinfo=timezone.utc)
            if ca.astimezone(_beijing).date() == today:  # 同北京日历日已提过 → 不重复 nag
                continue
        wi = propose(
            db,
            user_id,
            kind="measurement_prompt",
            title=f"今天还没测{label}",
            description=f"现在测一下{label},几十秒——给进行中的干预周期补上今天的数据。",
            source="measurement_gap",
            target_type=target_type,
            target_id=None,
            payload={"metric": metric},
            commit=False,
        )
        if wi is not None:
            created += 1
    db.commit()
    return created


def generate_recheck_due(db: Session, user_id: int, within_days: int = 7) -> int:
    """复测窗口到点:active 周期临近/逾期 planned_end_date 且尚未复查 → 提议「该复查了·记录复查」。

    只催**首次**复查(latest_snapshot_id 为空时);用户复查过一次即停,不长期 nag。
    同周期当天已提过(任何状态)→ 不重复。日历日用北京时。返回新建提议数。
    """
    from app.services.intervention_cycle_service import get_active_cycle
    from app.utils.timezone import get_china_today

    cycle = get_active_cycle(db, user_id)
    if cycle is None or cycle.planned_end_date is None:
        return 0
    if cycle.latest_snapshot_id is not None:
        return 0  # 已复查过 → 不再催首次复查

    today = get_china_today()
    days_left = (cycle.planned_end_date - today).days
    if days_left > within_days:
        return 0  # 还没到复测窗口
    if _has_decided_target(
        db,
        user_id,
        "recheck_due",
        "intervention_cycle",
        cycle.id,
        payload_key="planned_end_date",
        payload_value=cycle.planned_end_date.isoformat(),
    ):
        return 0

    _beijing = timezone(timedelta(hours=8))
    last = (
        db.query(WriteIntent)
        .filter(
            WriteIntent.user_id == user_id,
            WriteIntent.kind == "recheck_due",
            WriteIntent.target_type == "intervention_cycle",
            WriteIntent.target_id == cycle.id,
        )
        .order_by(WriteIntent.created_at.desc())
        .first()
    )
    if last is not None and last.created_at is not None:
        ca = last.created_at
        if ca.tzinfo is None:
            ca = ca.replace(tzinfo=timezone.utc)
        if ca.astimezone(_beijing).date() == today:  # 同北京日历日已提过 → 不重复
            return 0

    overdue = days_left < 0
    title = "复查已逾期" if overdue else "该复查了"
    description = (
        f"干预周期已过复查日 {abs(days_left)} 天——记录一次复查,看看对你有没有效。"
        if overdue
        else "干预周期到复测窗口了——记录一次复查,看看对你有没有效。"
    )
    wi = propose(
        db,
        user_id,
        kind="recheck_due",
        title=title,
        description=description,
        source="recheck_window",
        target_type="intervention_cycle",
        target_id=cycle.id,
        payload={
            "planned_end_date": cycle.planned_end_date.isoformat(),
            "overdue": overdue,
            "days_left": days_left,
            "cycle_id": cycle.id,
        },
        commit=False,
    )
    db.commit()
    return 1 if wi is not None else 0


def _proposed_same_day_local(db: Session, user_id: int, kind: str, target_type: str, target_id) -> bool:
    """该 (kind,target) 今天(本地日历日)是否已提过(任何状态)→ 防同日重复 nag。

    created_at 存 UTC,本地化到机器时区后与 date.today() 同基准比对(服务器 Asia/Shanghai)。
    """
    from datetime import date as _date

    last = (
        db.query(WriteIntent)
        .filter(
            WriteIntent.user_id == user_id,
            WriteIntent.kind == kind,
            WriteIntent.target_type == target_type,
            WriteIntent.target_id == target_id,
        )
        .order_by(WriteIntent.created_at.desc())
        .first()
    )
    if last is None or last.created_at is None:
        return False
    ca = last.created_at
    if ca.tzinfo is None:  # SQLite 存 naive UTC;PG 为 tz-aware
        ca = ca.replace(tzinfo=timezone.utc)
    return ca.astimezone().date() == _date.today()


def generate_adherence_nudge(db: Session, user_id: int) -> int:
    """服药/补剂依从缺口:今天该服但没记录 → 提议「已服了?标记已服」(确认即写依从事实)。

    不依赖干预周期(依从是日常)。药用 get_today_status(taken_count==0=今天完全没记录);补剂
    用活跃定义 ∧ 今天无 taken 记录。每个 item 一条,同 item 当天已提过(任何状态)→ 不重复。
    返回新建提议数。
    """
    from datetime import date as _date
    from app.services.medication_service import medication_service
    from app.models.supplement import SupplementDefinition, SupplementRecord

    today = _date.today()
    created = 0
    _DESC = "如果已经服用了,点确认记一笔(标记已服);没服就忽略。"

    # ── 药:今天完全没记录(taken_count==0)的活跃药 ──
    for st in medication_service.get_today_status(db, user_id):
        if st.get("taken_count", 0) > 0:
            continue
        med_id = st.get("medication_id")
        if _proposed_same_day_local(db, user_id, "adherence_nudge", "medication", med_id):
            continue
        wi = propose(
            db, user_id, kind="adherence_nudge",
            title=f"今天还没记录:{st.get('name')}",
            description=_DESC, source="adherence_gap",
            target_type="medication", target_id=med_id,
            payload={"item_type": "medication", "name": st.get("name")},
            commit=False,
        )
        if wi is not None:
            created += 1

    # ── 补剂:今天没有 taken 记录的活跃补剂 ──
    active_supps = (
        db.query(SupplementDefinition)
        .filter(SupplementDefinition.user_id == user_id, SupplementDefinition.is_active)
        .all()
    )
    for supp in active_supps:
        rec = (
            db.query(SupplementRecord)
            .filter(
                SupplementRecord.user_id == user_id,
                SupplementRecord.supplement_id == supp.id,
                SupplementRecord.record_date == today,
            )
            .first()
        )
        if rec is not None and rec.taken:
            continue
        if _proposed_same_day_local(db, user_id, "adherence_nudge", "supplement", supp.id):
            continue
        wi = propose(
            db, user_id, kind="adherence_nudge",
            title=f"今天还没记录:{supp.name}",
            description=_DESC, source="adherence_gap",
            target_type="supplement", target_id=supp.id,
            payload={"item_type": "supplement", "name": supp.name},
            commit=False,
        )
        if wi is not None:
            created += 1

    db.commit()
    return created


# ─────────────────── P5 external-action intents(food_order/doctor_booking/alarm_set)───────────────────

# 外部动作 kind 白名单(propose_external_action 服务端门控,未知 kind → ValueError,端点 422)。
_EXTERNAL_ACTION_KINDS = frozenset({
    "alarm_set",
    "food_order",
    "doctor_booking",
    "environment_actuation",
})

# L4 硬门:支付凭据类 key 绝不进 WriteIntent.payload(后端永不存支付凭据)。
# 这是代码级护栏(非仅约定):任一 payload key 命中 → 落库前 ValueError(端点 422,fail-loud)。
# 子串匹配,覆盖大小写/常见变体(card_no / card_number / payment_token / paymentMethod /
# payment_method / cvv / cvc / account_number / routing / iban / 支付密码 …)。任意层级命中即拒。
# 注:不收 bare "pan"(误伤 plan/japan/expand/company);card_number 已被 "card" 覆盖。
_PAYMENT_KEY_SUBSTRINGS = (
    "payment", "card", "cvv", "cvc", "bank", "alipay", "wechat_pay", "wechatpay",
    "account_number", "accountnumber", "routing", "iban",
    "credential", "password", "passwd", "secret", "支付", "银行卡", "密码",
)


def _reject_payment_keys(value: Any) -> None:
    """L4:**递归**扫整份 payload(dict + list/tuple,任意深度),命中支付凭据类子串的 key
    → ValueError(端点 422)。整份 payload 会落库,故支付凭据嵌在任意层级都必须在落库前拒绝
    (历史:只扫顶层 key 时 {"checkout":{"payment_token": "tok_…"}} 会把 L4 支付材料持久化进
    write_intents.payload —— §11 支付凭据 L4,本 feature 绝不存)。绝不静默丢弃。

    按设计是 **key 级** 门控:本 feature 契约是后端根本不经手支付材料(payload 是系统起草的
    food_order/booking 物流摘要,非自由凭据录入面)。把凭据藏进 value(如 note 字段塞 token 串)
    属契约外误用,不在本门射程内——value 级启发式扫描会有损/误伤,不是这里的合同。"""
    if isinstance(value, dict):
        for k, v in value.items():
            kl = str(k).lower()
            if any(s in kl for s in _PAYMENT_KEY_SUBSTRINGS):
                raise ValueError(f"payment-credential key not allowed in payload: {k}")
            _reject_payment_keys(v)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_payment_keys(item)


_ENVIRONMENT_ACTUATION_ALLOWED_KEYS = frozenset({
    "room_id",
    "reason",
    "command_entity_id",
    "entity_id",
    "command_mode",
    "mode",
    "source_snapshot_id",
    "user_visible_summary",
    "execution_policy",
})

_ENVIRONMENT_ACTUATION_ALLOWLIST = {
    # P5 scaffold:只允许低风险睡眠环境动作,且只是 confirm 后写 ACK/event。
    # 不接受 Home Assistant service/service_data,避免把本意图变成任意设备执行器。
    "fan.bedroom_fresh_air": {
        "room_id": "bedroom",
        "modes": frozenset({"boost", "low", "off"}),
    },
    "humidifier.bedroom": {
        "room_id": "bedroom",
        "modes": frozenset({"on", "off", "sleep"}),
    },
    "climate.bedroom_ac": {
        "room_id": "bedroom",
        "modes": frozenset({"sleep_cool", "sleep_heat", "off"}),
    },
    "light.bedroom": {
        "room_id": "bedroom",
        "modes": frozenset({"dim", "off"}),
    },
}


def _normalize_environment_actuation_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """环境设备意图 payload 归一化 + 服务端白名单。

    这是执行边界,不是 UI 校验:只接受 {entity, mode, room, reason...} 这类描述性字段,
    不接受 HA service/service_data/webhook/token 等任意下发材料。确认后也只 ACK/event。
    """
    unknown_keys = set(payload.keys()) - _ENVIRONMENT_ACTUATION_ALLOWED_KEYS
    if unknown_keys:
        key = sorted(unknown_keys)[0]
        raise ValueError(f"unsupported environment-actuation payload key: {key}")

    entity_id = payload.get("command_entity_id") or payload.get("entity_id")
    command_mode = payload.get("command_mode") or payload.get("mode")
    if not entity_id:
        raise ValueError("environment-actuation command_entity_id required")
    if not command_mode:
        raise ValueError("environment-actuation command_mode required")

    entity_id = str(entity_id).strip()
    command_mode = str(command_mode).strip()
    spec = _ENVIRONMENT_ACTUATION_ALLOWLIST.get(entity_id)
    if spec is None:
        raise ValueError(f"environment-actuation entity not allowlisted: {entity_id}")
    if command_mode not in spec["modes"]:
        raise ValueError(
            f"environment-actuation mode not allowlisted: {entity_id}/{command_mode}"
        )

    room_id = str(payload.get("room_id") or spec["room_id"]).strip()
    if room_id != spec["room_id"]:
        raise ValueError(f"environment-actuation room mismatch: {entity_id}/{room_id}")

    normalized = {
        "room_id": room_id,
        "command_entity_id": entity_id,
        "command_mode": command_mode,
        "execution_policy": "manual_confirm_ack_only",
    }
    for key in ("reason", "source_snapshot_id", "user_visible_summary"):
        if payload.get(key) is not None:
            normalized[key] = payload[key]
    return normalized


def propose_external_action(
    db: Session,
    user_id: int,
    *,
    kind: str,
    title: str,
    description: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    commit: bool = True,
) -> Optional[WriteIntent]:
    """提一个外部动作写意图(propose→confirm 生命周期,全 manual_confirm,不自治)。

    服务端 kind 白名单:kind ∉ _EXTERNAL_ACTION_KINDS → ValueError(端点转 422)。
    food_order 的 user-visible 摘要先过 R4 守门(guidance_validator):若 LLM 生成的摘要
    里混进量化/命令式饮食处方(「必须吃X克蛋白」),在**落库前**被 strip/soften,违规记
    payload['guidance_violations'] 审计(fail-loud,绝不静默改写)。
    propose 本身保持幂等(同 user+kind+target 已有 pending → None)、trust_tier=manual_confirm。
    """
    if kind not in _EXTERNAL_ACTION_KINDS:
        raise ValueError(f"unknown external-action kind: {kind}")

    safe_payload = dict(payload or {})
    _reject_payment_keys(safe_payload)  # L4:支付凭据类 key → ValueError(端点 422),fail-loud
    if kind == "food_order":
        # R4 防御纵深:外卖摘要里的营养"估算"是描述性的(标注估算来源),绝不能是量化饮食处方。
        # 把 user_visible_summary 过 guidance_validator,命中即 strip/soften + 记违规(fail-loud)。
        from app.services.guidance_validator import sanitize_guidance

        raw = safe_payload.get("user_visible_summary")
        if raw:
            res = sanitize_guidance(raw)
            safe_payload["user_visible_summary"] = res.text
            if res.flagged:
                safe_payload["guidance_violations"] = res.violations
    elif kind == "environment_actuation":
        safe_payload = _normalize_environment_actuation_payload(safe_payload)

    return propose(
        db,
        user_id,
        kind=kind,
        title=title,
        description=description,
        source="external_action",
        target_type=target_type,
        target_id=target_id,
        payload=safe_payload,
        commit=commit,
    )


def generate_doctor_booking_drafts(db: Session, user_id: int, within_days: int = 30) -> int:
    """复查到期召回(医生预约草稿):扫该用户 due 的 ReviewSchedule → 提议「doctor_booking」写意图。

    过滤:status ∈ {pending, overdue} ∧ is_active ∧ user_id == 调用方(IDOR)∧ next_due_date
    在 [today-逾期, today+within_days] 窗内。同 (kind,target) 当天已提过 → 不重复(防刷屏)。
    摘要是纯物流(「复查到期,可预约 X 科」),非诊断。NO 真挂号 —— 确认只建提醒(见 _execute)。
    返回新建提议数。
    """
    from datetime import date as _date

    from app.models.family_health import ReviewSchedule

    today = _date.today()
    horizon = today + timedelta(days=within_days)
    rows = (
        db.query(ReviewSchedule)
        .filter(
            ReviewSchedule.user_id == user_id,           # IDOR:只扫调用方自己的复查计划
            ReviewSchedule.is_active.is_(True),
            ReviewSchedule.status.in_(("pending", "overdue")),
            ReviewSchedule.next_due_date <= horizon,     # 已逾期(<today)也含,催预约
        )
        .all()
    )

    created = 0
    for rs in rows:
        next_due_value = rs.next_due_date.isoformat() if rs.next_due_date else None
        if _has_decided_target(
            db,
            user_id,
            "doctor_booking",
            "review_schedule",
            rs.id,
            payload_key="next_due_date",
            payload_value=next_due_value,
        ):
            continue
        if _proposed_same_day_local(db, user_id, "doctor_booking", "review_schedule", rs.id):
            continue
        dept = rs.department or "对应科室"
        item = rs.item_name or "复查项目"
        overdue = rs.next_due_date < today
        title = f"复查到期:{item}" if not overdue else f"复查已逾期:{item}"
        # 纯物流描述(R4 安全):只说"到期可预约 X 科",绝不下诊断("你得了 X")。
        desc = f"{item} 复查到期,可预约{dept}" + (f"({rs.hospital})" if rs.hospital else "") + "。"
        wi = propose_external_action(
            db,
            user_id,
            kind="doctor_booking",
            title=title,
            description=desc,
            target_type="review_schedule",
            target_id=rs.id,
            payload={
                "department": rs.department,
                "hospital": rs.hospital,
                "item_name": rs.item_name,
                "next_due_date": next_due_value,
            },
            commit=False,
        )
        if wi is not None:
            created += 1

    db.commit()
    return created


def generate_reorder_nudges(db: Session, user_id: int) -> int:
    """P3(D1)复购提醒:补剂剩余天数 ≤ 阈值(low)→ 提议「该补货了」write_intent(幂等)。

    数据来源 reorder_detection.low_items_for_user(库存 + 依从估的剩余天数)。
    每个 low 补剂一条;同补剂当天已提过(任何状态)→ 不重复(防每日扫描刷屏)。
    title 带剩余天数,description 带品牌/规格(便于复购),纯物流提醒、非医疗建议。

    边界:这里只**提议提醒**,不下单/不购买/不调电商 skill —— 确认执行也只 acknowledge
    (见 _execute 的 reorder_nudge 分支)。返回新建提议数。
    """
    from app.services import reorder_detection

    created = 0
    for it in reorder_detection.low_items_for_user(db, user_id):
        supp_id = it["supplement_id"]
        if _proposed_same_day_local(db, user_id, "reorder_nudge", "supplement", supp_id):
            continue
        days = it.get("days_remaining")
        days_txt = f"约 {round(days)} 天" if isinstance(days, (int, float)) else "快用完了"
        brand_spec = " ".join(x for x in (it.get("brand"), it.get("spec")) if x).strip()
        desc = f"{it['name']} 库存{days_txt},可以补货了。" + (
            f"上次:{brand_spec}。" if brand_spec else ""
        ) + "确认即标记已知悉(不会自动下单)。"
        wi = propose(
            db, user_id, kind="reorder_nudge",
            title=f"{it['name']} 还剩{days_txt},该补货了",
            description=desc, source="reorder_detection",
            target_type="supplement", target_id=supp_id,
            payload={
                "name": it["name"],
                "brand": it.get("brand") or "",
                "spec": it.get("spec") or "",
                "days_remaining": days,
                "units_remaining": it.get("units_remaining"),
            },
            commit=False,
        )
        if wi is not None:
            created += 1

    db.commit()
    return created
