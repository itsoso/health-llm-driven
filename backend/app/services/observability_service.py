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
from typing import Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------
# A. Open-Loop Manager 推送
# ---------------------------------------------------------------

def open_loop_stats(db: Session, since: datetime, user_id: Optional[int]) -> dict:
    from app.models.open_loop_history import OpenLoopHistory

    filters = [OpenLoopHistory.sent_at >= since]
    if user_id:
        filters.append(OpenLoopHistory.user_id == user_id)

    base = db.query(OpenLoopHistory).filter(*filters)

    total_sent = base.with_entities(func.count(OpenLoopHistory.id)).scalar() or 0
    if total_sent == 0:
        return {
            "total_sent": 0, "by_kind": {}, "by_action": {},
            "delivery_fail": 0, "avg_score": None, "last_sent": None,
        }

    by_kind = dict(
        base.with_entities(OpenLoopHistory.kind, func.count(OpenLoopHistory.id))
        .group_by(OpenLoopHistory.kind).all()
    )

    # user_action NULL → "未操作"
    raw_actions = base.with_entities(
        OpenLoopHistory.user_action, func.count(OpenLoopHistory.id)
    ).group_by(OpenLoopHistory.user_action).all()
    by_action: dict[str, int] = {}
    for action, cnt in raw_actions:
        by_action[action or "未操作"] = by_action.get(action or "未操作", 0) + cnt

    delivery_fail = base.with_entities(func.count(OpenLoopHistory.id)).filter(
        OpenLoopHistory.delivery_ok == 0
    ).scalar() or 0

    avg_score = base.with_entities(func.avg(OpenLoopHistory.score)).scalar()
    last_sent = base.with_entities(func.max(OpenLoopHistory.sent_at)).scalar()

    return {
        "total_sent": int(total_sent),
        "by_kind": by_kind,
        "by_action": by_action,
        "delivery_fail": int(delivery_fail),
        "avg_score": round(float(avg_score), 1) if avg_score is not None else None,
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

    last_entry = q.with_entities(func.max(ClinicalJournalEntry.generated_at)).scalar()

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
# D. Doctor Weekly Report
#    真实数据源 = Clinical Journal 里 created_by='doctor_weekly_task' 的 entry.
#    generate_doctor_weekly_report 推 Telegram / Email / APNs 都不写 NotificationLog,
#    只 SOAP 永久化是可靠的观测点.
# ---------------------------------------------------------------

def doctor_report_stats(db: Session, since: datetime, user_id: Optional[int]) -> dict:
    from app.models.clinical_journal import ClinicalJournalEntry

    q = db.query(ClinicalJournalEntry).filter(
        ClinicalJournalEntry.generated_at >= since,
        ClinicalJournalEntry.created_by == "doctor_weekly_task",
    )
    if user_id:
        q = q.filter(ClinicalJournalEntry.user_id == user_id)

    total = q.count()
    unique_users = q.with_entities(ClinicalJournalEntry.user_id).distinct().count()
    last_generated = q.with_entities(func.max(ClinicalJournalEntry.generated_at)).scalar()

    return {
        "total_attempts": total,
        "unique_users": unique_users,
        "last_attempt": last_generated.isoformat() if last_generated else None,
    }


# ---------------------------------------------------------------
# E. ActionCard 信任循环
# ---------------------------------------------------------------

def action_card_stats(db: Session, since: datetime, user_id: Optional[int]) -> dict:
    from app.models.action_card import ActionCard

    filters = [ActionCard.created_at >= since]
    if user_id:
        filters.append(ActionCard.user_id == user_id)
    created_q = db.query(ActionCard).filter(*filters)

    created = created_q.with_entities(func.count(ActionCard.id)).scalar() or 0

    by_specialist = dict(
        created_q.with_entities(
            func.coalesce(ActionCard.creator_specialist, "unknown"),
            func.count(ActionCard.id),
        ).group_by(ActionCard.creator_specialist).all()
    )

    graded_filters = [ActionCard.graded_at.isnot(None), ActionCard.graded_at >= since]
    if user_id:
        graded_filters.append(ActionCard.user_id == user_id)
    graded_q = db.query(ActionCard).filter(*graded_filters)

    graded = graded_q.with_entities(func.count(ActionCard.id)).scalar() or 0
    avg_acc_raw = graded_q.with_entities(func.avg(ActionCard.accuracy_score)).scalar()

    return {
        "created_in_window": int(created),
        "graded_in_window": int(graded),
        "avg_accuracy": round(float(avg_acc_raw), 1) if avg_acc_raw is not None else None,
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
# H. Client Events (Task 9) — Mobile 埋点聚合
#    reasoning_sheet_opened / journal_timeline_entered / specialist_scorecard_entered
# ---------------------------------------------------------------

def client_events_stats(db: Session, since: datetime, user_id: Optional[int]) -> dict:
    from app.models.client_event import ClientEvent

    q = db.query(ClientEvent).filter(ClientEvent.created_at >= since)
    if user_id:
        q = q.filter(ClientEvent.user_id == user_id)

    by_event: Dict[str, int] = {}
    for row in (
        q.with_entities(ClientEvent.event_name, func.count(ClientEvent.id))
        .group_by(ClientEvent.event_name)
        .all()
    ):
        by_event[row[0]] = int(row[1])

    return {
        "total": sum(by_event.values()),
        "by_event": by_event,
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
        out.append("🔴 Doctor Weekly 窗口内零 SOAP 落盘 — celery beat doctor-weekly-report 可能没加载")

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

    # Task 9: client-event 行为率 — 判断 feature 是否真被用户看见 / 点击
    ce = report.get("client_events", {})
    by_ev = (ce or {}).get("by_event", {})

    # reasoning 抽屉: 点击次数 / Safety 告警累计 (每条告警都显示"为什么?" 按钮)
    sg_total = report.get("safety_guardian", {}).get("total_alerts_raised", 0)
    reasoning_opens = by_ev.get("reasoning_sheet_opened", 0)
    if sg_total >= 3:  # 样本 <3 不评, 噪声太大
        rate = reasoning_opens / sg_total
        if rate < 0.05:
            out.append(
                f"🔴 Reasoning 抽屉点击率 {reasoning_opens}/{sg_total} ({rate * 100:.0f}%) "
                "— 用户没觉得'为什么'值得看"
            )
        elif rate < 0.2:
            out.append(
                f"🟡 Reasoning 抽屉点击率 {reasoning_opens}/{sg_total} ({rate * 100:.0f}%) — 未达 20% 目标"
            )
        else:
            out.append(
                f"🟢 Reasoning 抽屉点击率 {rate * 100:.0f}% — 达标 (目标 >=20%)"
            )

    # journal tab 进入: 当窗口有 SOAP 数据时必须有人看
    journal_entered = by_ev.get("journal_timeline_entered", 0)
    journal_total = report.get("clinical_journal", {}).get("total_entries", 0)
    if journal_total >= 3 and journal_entered == 0:
        out.append(
            f"🔴 Journal tab 零进入 ({journal_total} 条 SOAP 可看) — tab 入口不够直观?"
        )

    # specialist 详情页进入: 有 ActionCard 却没人看 chip
    sc_entered = by_ev.get("specialist_scorecard_entered", 0)
    ac_created = report.get("action_card", {}).get("created_in_window", 0)
    if ac_created >= 5 and sc_entered == 0:
        out.append(
            f"🔴 Specialist 详情页零进入 ({ac_created} 条 ActionCard 可看) — Hero chip row 不够显眼?"
        )

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
        "client_events": client_events_stats(db, since, user_id),
    }
    if include_journalctl:
        report["tool_validator"] = tool_validator_stats_remote(days)
    return report
