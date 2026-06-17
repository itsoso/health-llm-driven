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


def confirm(db: Session, user_id: int, intent_id: int) -> Dict[str, Any]:
    """一键确认 → 执行。原子门防双执行;执行失败整体回滚(状态退回 pending,fail loud)。"""
    wi = (
        db.query(WriteIntent)
        .filter(WriteIntent.id == intent_id, WriteIntent.user_id == user_id)
        .first()
    )
    if wi is None:
        raise LookupError("write_intent not found")  # 端点 → 404(含 IDOR)
    if wi.status != "pending":
        return {"id": wi.id, "status": wi.status, "executed_ref": wi.executed_ref, "idempotent": True}

    affected = (
        db.query(WriteIntent)
        .filter(
            WriteIntent.id == intent_id,
            WriteIntent.user_id == user_id,
            WriteIntent.status == "pending",
        )
        .update(
            {"status": "executed", "decided_at": datetime.now(timezone.utc)},
            synchronize_session=False,
        )
    )
    if affected != 1:
        # 并发双击:别人先 claim 了 → 不重复执行
        db.rollback()
        db.refresh(wi)
        return {"id": wi.id, "status": wi.status, "executed_ref": wi.executed_ref, "idempotent": True}

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
