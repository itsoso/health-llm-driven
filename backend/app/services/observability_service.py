"""观察期看板 — agent 运营数据聚合.

CLI (scripts/observation_dashboard.py) 和 admin API (api/admin_observability.py)
共用. 单一数据源, 任何 schema 调整改一处.

7 个模块:
  open_loop / clinical_journal / memory_kg / doctor_report
  / action_card / safety_guardian / tool_validator (远程 only)
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------
# A. Open-Loop Manager 推送
# ---------------------------------------------------------------

def open_loop_stats(db: Session, since: datetime, user_id: Optional[int]) -> dict:
    from app.models.open_loop_history import OpenLoopHistory

    q = db.query(OpenLoopHistory).filter(OpenLoopHistory.sent_at >= since)
    if user_id:
        q = q.filter(OpenLoopHistory.user_id == user_id)

    rows = q.all()
    by_kind: dict[str, int] = {}
    by_action: dict[str, int] = {}
    delivery_fail = 0
    scores: list[int] = []
    for r in rows:
        by_kind[r.kind] = by_kind.get(r.kind, 0) + 1
        action = r.user_action or "未操作"
        by_action[action] = by_action.get(action, 0) + 1
        if not r.delivery_ok:
            delivery_fail += 1
        scores.append(r.score)

    last_sent = db.query(func.max(OpenLoopHistory.sent_at)).scalar()

    return {
        "total_sent": len(rows),
        "by_kind": by_kind,
        "by_action": by_action,
        "delivery_fail": delivery_fail,
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "last_sent": last_sent.isoformat() if last_sent else None,
    }


# ---------------------------------------------------------------
# B. Clinical Journal SOAP
# ---------------------------------------------------------------

def clinical_journal_stats(db: Session, since: datetime, user_id: Optional[int]) -> dict:
    from app.models.clinical_journal import CaseThread, ClinicalJournalEntry

    q = db.query(ClinicalJournalEntry).filter(ClinicalJournalEntry.generated_at >= since)
    if user_id:
        q = q.filter(ClinicalJournalEntry.user_id == user_id)

    entries = q.all()

    thread_ids = {e.case_thread_id for e in entries if e.case_thread_id}
    thread_map: dict[int, str] = {}
    if thread_ids:
        for t in db.query(CaseThread).filter(CaseThread.id.in_(thread_ids)).all():
            thread_map[t.id] = t.theme

    by_creator: dict[str, int] = {}
    by_theme: dict[str, int] = {}
    for e in entries:
        creator = e.created_by or "unknown"
        by_creator[creator] = by_creator.get(creator, 0) + 1
        theme = thread_map.get(e.case_thread_id, "无主题") if e.case_thread_id else "无主题"
        by_theme[theme] = by_theme.get(theme, 0) + 1

    tq = db.query(CaseThread).filter(CaseThread.status == "active")
    if user_id:
        tq = tq.filter(CaseThread.user_id == user_id)
    active_cases = tq.count()

    last_entry = db.query(func.max(ClinicalJournalEntry.generated_at)).scalar()

    complete = sum(
        1 for e in entries
        if (e.subjective or "").strip() and (e.objective or "").strip()
        and (e.assessment or "").strip() and (e.plan or "").strip()
    )

    return {
        "total_entries": len(entries),
        "by_creator": by_creator,
        "by_theme": by_theme,
        "active_case_threads": active_cases,
        "complete_soap_pct": round(100 * complete / len(entries), 1) if entries else None,
        "last_entry": last_entry.isoformat() if last_entry else None,
    }


# ---------------------------------------------------------------
# C. Memory / KG (Sprint 5)
# ---------------------------------------------------------------

def memory_kg_stats(db: Session, since: datetime, user_id: Optional[int]) -> dict:
    from app.models.health_kg import EntityRelation, HealthEntity
    from app.models.memory_fact import MemoryFact

    fq = db.query(MemoryFact)
    if user_id:
        fq = fq.filter(MemoryFact.user_id == user_id)
    total_facts = fq.count()

    by_tier: dict[str, int] = {}
    for row in (
        fq.with_entities(MemoryFact.tier, func.count(MemoryFact.id))
        .group_by(MemoryFact.tier)
        .all()
    ):
        by_tier[row[0] or "unknown"] = row[1]
    new_facts = fq.filter(MemoryFact.created_at >= since).count()

    eq = db.query(HealthEntity).filter(HealthEntity.is_active.is_(True))
    if user_id:
        eq = eq.filter(HealthEntity.user_id == user_id)
    total_entities = eq.count()
    by_type: dict[str, int] = {}
    for row in (
        eq.with_entities(HealthEntity.type, func.count(HealthEntity.id))
        .group_by(HealthEntity.type)
        .all()
    ):
        by_type[row[0] or "unknown"] = row[1]
    new_entities = eq.filter(HealthEntity.created_at >= since).count()

    rq = db.query(EntityRelation).filter(EntityRelation.is_active.is_(True))
    if user_id:
        rq = rq.filter(EntityRelation.user_id == user_id)
    total_relations = rq.count()
    by_pred: dict[str, int] = {}
    for row in (
        rq.with_entities(EntityRelation.predicate, func.count(EntityRelation.id))
        .group_by(EntityRelation.predicate)
        .order_by(func.count(EntityRelation.id).desc())
        .limit(8)
        .all()
    ):
        by_pred[row[0] or "unknown"] = row[1]
    new_relations = rq.filter(EntityRelation.created_at >= since).count()

    return {
        "facts_total": total_facts,
        "facts_by_tier": by_tier,
        "facts_new": new_facts,
        "entities_total": total_entities,
        "entities_by_type": by_type,
        "entities_new": new_entities,
        "relations_total": total_relations,
        "relations_top_predicates": by_pred,
        "relations_new": new_relations,
    }


# ---------------------------------------------------------------
# D. Doctor Weekly Report (NotificationLog)
# ---------------------------------------------------------------

def doctor_report_stats(db: Session, since: datetime, user_id: Optional[int]) -> dict:
    from app.models.notification import NotificationLog

    q = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.created_at >= since,
            or_(
                NotificationLog.notification_type.ilike("%doctor%"),
                NotificationLog.notification_type.ilike("%advisor%"),
                NotificationLog.notification_type.ilike("%weekly%"),
            ),
        )
    )
    if user_id:
        q = q.filter(NotificationLog.user_id == user_id)

    rows = q.all()
    by_status: dict[str, int] = {}
    for r in rows:
        s = (r.status.value if hasattr(r.status, "value") else str(r.status)) if r.status else "unknown"
        by_status[s] = by_status.get(s, 0) + 1

    last_sent = None
    if rows:
        last = max(rows, key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc))
        last_sent = last.created_at.isoformat() if last.created_at else None

    return {
        "total_attempts": len(rows),
        "by_status": by_status,
        "last_attempt": last_sent,
    }


# ---------------------------------------------------------------
# E. ActionCard 信任循环
# ---------------------------------------------------------------

def action_card_stats(db: Session, since: datetime, user_id: Optional[int]) -> dict:
    from app.models.action_card import ActionCard

    q = db.query(ActionCard).filter(ActionCard.created_at >= since)
    if user_id:
        q = q.filter(ActionCard.user_id == user_id)
    created = q.count()

    gq = db.query(ActionCard).filter(
        ActionCard.graded_at.isnot(None),
        ActionCard.graded_at >= since,
    )
    if user_id:
        gq = gq.filter(ActionCard.user_id == user_id)
    graded_rows = gq.all()
    graded = len(graded_rows)
    avg_acc = (
        round(sum(r.accuracy_score for r in graded_rows if r.accuracy_score is not None) / graded, 1)
        if graded else None
    )

    by_specialist: dict[str, int] = {}
    for r in q.all():
        s = r.creator_specialist or "unknown"
        by_specialist[s] = by_specialist.get(s, 0) + 1

    return {
        "created_in_window": created,
        "graded_in_window": graded,
        "avg_accuracy": avg_acc,
        "by_specialist": by_specialist,
    }


# ---------------------------------------------------------------
# F. Safety Guardian 告警
# ---------------------------------------------------------------

def safety_audit_stats(db: Session, since: datetime, user_id: Optional[int]) -> dict:
    from app.models.agent_audit_log import AgentAuditLog

    q = (
        db.query(AgentAuditLog)
        .filter(
            AgentAuditLog.created_at >= since,
            AgentAuditLog.agent_type == "safety_guardian",
        )
    )
    if user_id:
        q = q.filter(AgentAuditLog.user_id == user_id)
    total = q.count()

    alerts_sum = db.query(func.sum(AgentAuditLog.alerts_count)).filter(
        AgentAuditLog.created_at >= since,
        AgentAuditLog.agent_type == "safety_guardian",
    )
    if user_id:
        alerts_sum = alerts_sum.filter(AgentAuditLog.user_id == user_id)
    total_alerts = alerts_sum.scalar() or 0

    return {
        "evaluations": total,
        "total_alerts_raised": int(total_alerts),
    }


# ---------------------------------------------------------------
# G. tool_validator (journalctl, 仅线上)
# ---------------------------------------------------------------

def tool_validator_stats_remote(days: int) -> dict:
    try:
        out = subprocess.run(
            [
                "journalctl", "-u", "health-backend",
                "--since", f"{days} days ago",
                "--no-pager", "-o", "short-iso",
            ],
            capture_output=True, text=True, timeout=20,
        )
        if out.returncode != 0:
            return {"skipped": True, "reason": out.stderr[:200]}
        lines = out.stdout.splitlines()
        coerced = sum(1 for line in lines if "tool_validator_coerced" in line)
        rejected = sum(1 for line in lines if "tool_validator_reject" in line)
        return {"coerced": coerced, "rejected": rejected, "log_lines": len(lines)}
    except Exception as e:
        return {"skipped": True, "reason": str(e)[:200]}


# ---------------------------------------------------------------
# 行动建议 (CLI 共用)
# ---------------------------------------------------------------

def actionable_suggestions(report: dict) -> list[str]:
    """根据数据自动给出"个人使用"痛点列表 — 同一份逻辑给 CLI 和 API."""
    out: list[str] = []
    ol = report["open_loop"]
    if ol["total_sent"] == 0:
        out.append("🔴 Open-Loop 过去窗口一条没推 — 需确认 Celery 是否在跑 / 信号阈值是否太高")
    else:
        if ol["delivery_fail"] > 0:
            fail_pct = round(100 * ol["delivery_fail"] / ol["total_sent"], 1)
            if fail_pct >= 50:
                out.append(
                    f"🔴 Open-Loop 投递失败 {ol['delivery_fail']}/{ol['total_sent']} ({fail_pct}%) — APNs 链路断了"
                )
            else:
                out.append(f"🟡 Open-Loop 投递失败率 {fail_pct}%")
        no_action = ol["by_action"].get("未操作", 0)
        if no_action == ol["total_sent"] and ol["delivery_fail"] == 0:
            out.append(f"🟡 Open-Loop {ol['total_sent']} 条全未操作 — 用户真看到了吗?")
        dismissed = (
            ol["by_action"].get("dismissed", 0)
            + ol["by_action"].get("not_interested", 0)
            + ol["by_action"].get("snooze_7d", 0)
        )
        if dismissed > 0 and dismissed / ol["total_sent"] > 0.5:
            out.append(f"🟡 Open-Loop dismissal 率 {dismissed}/{ol['total_sent']} — 阈值可能过低")
        if len(ol["by_kind"]) == 1:
            only_kind = next(iter(ol["by_kind"].keys()))
            out.append(f"🟡 Open-Loop 只触发了一类信号 ({only_kind}) — 其他 kind 检测器是否正常?")

    cj = report["clinical_journal"]
    if cj["total_entries"] == 0:
        out.append("🔴 Journal 过去窗口一条 SOAP 都没写 — briefing_task 链路可能断了")
    elif cj["complete_soap_pct"] is not None and cj["complete_soap_pct"] < 80:
        out.append(f"🟡 Journal SOAP 完整率 {cj['complete_soap_pct']}% — extractor prompt 需强化")
    if cj["total_entries"] > 0 and len(cj["by_creator"]) == 1:
        only_creator = next(iter(cj["by_creator"].keys()))
        if only_creator == "briefing_task":
            out.append(f"🟡 Journal 只有 briefing_task 产 SOAP, orchestrator 对话没触发")

    mk = report["memory_kg"]
    if mk["facts_total"] < 20 and mk["entities_total"] < 20:
        out.append(
            f"🔴 Sprint 5 数据量极少 (facts={mk['facts_total']}, entities={mk['entities_total']}) — "
            "memory_extractor 没在主链路上被调用"
        )
    if mk["facts_new"] == 0 and mk["entities_new"] == 0 and mk["relations_new"] == 0:
        out.append("🟡 Memory/KG 窗口内零新增 — ingest hook 可能没接上")
    if mk["facts_total"] > 0 and mk["facts_by_tier"].get("semantic", 0) == 0:
        out.append("🟢 Fact 有量但没 semantic 层 — Decay+Crystallization cron 是否在跑? (04:00)")

    dr = report["doctor_report"]
    if dr["total_attempts"] == 0:
        out.append("🔴 Doctor Weekly 窗口内零推送 — celery beat doctor-weekly-report 可能没加载")
    else:
        failed = dr["by_status"].get("failed", 0) + dr["by_status"].get("error", 0)
        if failed == dr["total_attempts"]:
            out.append(f"🔴 Doctor Weekly {dr['total_attempts']} 次尝试全部 failed — Telegram 配置错了?")

    ac = report["action_card"]
    if ac["created_in_window"] == 0:
        out.append("🔴 ActionCard 窗口内零创建 — specialist 都没产 proposed_cards?")
    elif ac["graded_in_window"] == 0:
        out.append("🟡 ActionCard 只创建没评分 — outcome_grader (08:00) 可能没跑")

    sg = report["safety_guardian"]
    if sg["evaluations"] == 0:
        out.append("🟡 Safety Guardian 没评估记录 — 你本周没用 App 吗?")
    elif sg["evaluations"] > 0:
        avg = sg["total_alerts_raised"] / sg["evaluations"]
        if avg >= 5:
            out.append(
                f"🔴 Safety Guardian 平均 {avg:.1f} 条告警/次 (N={sg['evaluations']}) — 告警风暴, 需降噪"
            )
        elif avg >= 3:
            out.append(f"🟡 Safety Guardian 平均 {avg:.1f} 条/次 — 偏多")

    tv = report.get("tool_validator", {})
    if not tv.get("skipped") and tv.get("log_lines", 0) > 0:
        if tv.get("coerced", 0) == 0 and tv.get("rejected", 0) == 0:
            out.append("🟡 tool_validator 窗口内零命中 — 验证下 validator 是否挂在主路径上")

    if not out:
        out.append("✅ 所有链路看起来在跑, 无明显异常.")

    return out


# ---------------------------------------------------------------
# 一站式聚合
# ---------------------------------------------------------------

def collect_dashboard(
    db: Session,
    days: int,
    user_id: Optional[int],
    include_journalctl: bool = False,
) -> dict:
    """一次性聚合 6 (或 7) 个模块, 给 CLI 和 API 用."""
    since = utc_now() - timedelta(days=days)
    report = {
        "open_loop": open_loop_stats(db, since, user_id),
        "clinical_journal": clinical_journal_stats(db, since, user_id),
        "memory_kg": memory_kg_stats(db, since, user_id),
        "doctor_report": doctor_report_stats(db, since, user_id),
        "action_card": action_card_stats(db, since, user_id),
        "safety_guardian": safety_audit_stats(db, since, user_id),
    }
    if include_journalctl:
        report["tool_validator"] = tool_validator_stats_remote(days)
    return report
