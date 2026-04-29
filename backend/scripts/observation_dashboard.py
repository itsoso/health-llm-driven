#!/usr/bin/env python3
"""
观察期数据看板 — 让"个人工具"的使用数据可见

对照 STRATEGY-2026.md §七 原则: 数据显示的痛点 = 这周要修的东西.
不新增 feature, 不加监控组件, 纯 SQL + 打印. Sentry 卡在选型时的短期替代.

用法:
  python scripts/observation_dashboard.py                 # 默认 7 天窗口
  python scripts/observation_dashboard.py --days 14
  python scripts/observation_dashboard.py --user 1        # 限定单用户
  python scripts/observation_dashboard.py --json          # JSON 输出
  python scripts/observation_dashboard.py --remote        # 走 SSH 跑线上

模块:
  A. Open-Loop Manager 推送有效性 (弱点 G)
  B. Clinical Journal SOAP 覆盖率 (阶段 3)
  C. Memory / KG 增长 (Sprint 5)
  D. Doctor Weekly Report 推送状态 (阶段 4)
  E. ActionCard 信用循环 (信任循环)
  F. Safety Guardian 告警命中 (阶段 1)
  G. tool_validator 命中 (弱点 B, 尾部 journalctl 探针, 仅线上)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 脚本从 backend/scripts/ 运行; 把 backend/ 加入 sys.path
HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent
sys.path.insert(0, str(BACKEND_ROOT))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------
# 连 DB 的小 helper — 借助 app.database 已封装的 session
# ------------------------------------------------------------

def _get_session():
    from app.database import SessionLocal  # type: ignore
    return SessionLocal()


# ============================================================
# 各模块查询
# ============================================================

def open_loop_stats(db, since, user_id: int | None) -> dict:
    """Open-Loop 推送有效性."""
    from app.models.open_loop_history import OpenLoopHistory
    from sqlalchemy import func

    q = db.query(OpenLoopHistory).filter(OpenLoopHistory.sent_at >= since)
    if user_id:
        q = q.filter(OpenLoopHistory.user_id == user_id)

    total = q.count()
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

    last_sent = (
        db.query(func.max(OpenLoopHistory.sent_at))
        .scalar()
    )

    return {
        "total_sent": total,
        "by_kind": by_kind,
        "by_action": by_action,
        "delivery_fail": delivery_fail,
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "last_sent": last_sent.isoformat() if last_sent else None,
    }


def clinical_journal_stats(db, since, user_id: int | None) -> dict:
    """Clinical Journal SOAP 覆盖率."""
    from app.models.clinical_journal import ClinicalJournalEntry, CaseThread
    from sqlalchemy import func

    q = db.query(ClinicalJournalEntry).filter(ClinicalJournalEntry.generated_at >= since)
    if user_id:
        q = q.filter(ClinicalJournalEntry.user_id == user_id)

    entries = q.all()

    by_creator: dict[str, int] = {}
    by_theme: dict[str, int] = {}
    # 取 case_thread 信息
    thread_ids = {e.case_thread_id for e in entries if e.case_thread_id}
    thread_map: dict[int, str] = {}
    if thread_ids:
        for t in db.query(CaseThread).filter(CaseThread.id.in_(thread_ids)).all():
            thread_map[t.id] = t.theme

    for e in entries:
        creator = e.created_by or "unknown"
        by_creator[creator] = by_creator.get(creator, 0) + 1
        theme = thread_map.get(e.case_thread_id, "无主题") if e.case_thread_id else "无主题"
        by_theme[theme] = by_theme.get(theme, 0) + 1

    # Active case threads
    tq = db.query(CaseThread).filter(CaseThread.status == "active")
    if user_id:
        tq = tq.filter(CaseThread.user_id == user_id)
    active_cases = tq.count()

    last_entry = (
        db.query(func.max(ClinicalJournalEntry.generated_at))
        .scalar()
    )

    # 简单 SOAP 完整性: 四字段都有内容的比例
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


def memory_kg_stats(db, since, user_id: int | None) -> dict:
    """Memory / KG (Sprint 5) 增长."""
    from app.models.memory_fact import MemoryFact
    from app.models.health_kg import HealthEntity, EntityRelation
    from sqlalchemy import func

    # MemoryFact 总数 + 分层 + 近 N 天新增
    fq = db.query(MemoryFact)
    if user_id:
        fq = fq.filter(MemoryFact.user_id == user_id)
    total_facts = fq.count()

    by_tier: dict[str, int] = {}
    for row in fq.with_entities(MemoryFact.tier, func.count(MemoryFact.id)).group_by(MemoryFact.tier).all():
        by_tier[row[0] or "unknown"] = row[1]

    new_facts = fq.filter(MemoryFact.created_at >= since).count()

    # HealthEntity 总数 + 按 type + 近 N 天
    eq = db.query(HealthEntity).filter(HealthEntity.is_active.is_(True))
    if user_id:
        eq = eq.filter(HealthEntity.user_id == user_id)
    total_entities = eq.count()

    by_type: dict[str, int] = {}
    for row in eq.with_entities(HealthEntity.type, func.count(HealthEntity.id)).group_by(HealthEntity.type).all():
        by_type[row[0] or "unknown"] = row[1]

    new_entities = eq.filter(HealthEntity.created_at >= since).count()

    # EntityRelation 总数 + 按 predicate Top-5
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


def doctor_report_stats(db, since, user_id: int | None) -> dict:
    """Doctor Weekly Report 推送状态 — 通过 NotificationLog 追踪."""
    from app.models.notification import NotificationLog
    from sqlalchemy import func, or_

    # 可能的 type/channel 标记 — doctor_weekly 或 advisor
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


def action_card_stats(db, since, user_id: int | None) -> dict:
    """ActionCard 信用循环."""
    from app.models.action_card import ActionCard
    from sqlalchemy import func

    q = db.query(ActionCard).filter(ActionCard.created_at >= since)
    if user_id:
        q = q.filter(ActionCard.user_id == user_id)

    created = q.count()

    # 已评分的
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

    # 按 specialist 分布
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


def safety_audit_stats(db, since, user_id: int | None) -> dict:
    """Safety Guardian 告警命中 (通过 AgentAuditLog)."""
    from app.models.agent_audit_log import AgentAuditLog
    from sqlalchemy import func

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

    # 加和 alerts_count
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


def tool_validator_stats_remote(days: int) -> dict:
    """从 journalctl 扫 tool_validator_coerced 次数 — 仅线上.

    本地默认返回 "skipped". 线上用 subprocess journalctl.
    """
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
        coerced = sum(1 for l in lines if "tool_validator_coerced" in l)
        rejected = sum(1 for l in lines if "tool_validator_reject" in l)
        return {"coerced": coerced, "rejected": rejected, "log_lines": len(lines)}
    except Exception as e:
        return {"skipped": True, "reason": str(e)[:200]}


# ============================================================
# 打印
# ============================================================

def _p(title: str):
    print(f"\n{'=' * 58}")
    print(f" {title}")
    print("=" * 58)


def _kv(k, v):
    print(f"  {k:<24} {v}")


def _section_dict(d: dict, indent: int = 2):
    for k, v in d.items():
        print(f"{' ' * indent}{k:<24} {v}")


def render_text(report: dict, days: int, user_id: int | None):
    user_hint = f"user_id={user_id}" if user_id else "全量用户"
    print(f"\n📊 观察期看板  · 过去 {days} 天  · {user_hint}  · {_utc_now().isoformat()}")

    _p("A. Open-Loop Manager 推送")
    ol = report["open_loop"]
    _kv("推送总数", ol["total_sent"])
    _kv("投递失败", ol["delivery_fail"])
    _kv("平均分数", ol["avg_score"] if ol["avg_score"] is not None else "—")
    _kv("最近一条", ol["last_sent"] or "—")
    if ol["by_kind"]:
        print("  按 kind:")
        _section_dict(ol["by_kind"], indent=4)
    if ol["by_action"]:
        print("  按用户反馈:")
        _section_dict(ol["by_action"], indent=4)

    _p("B. Clinical Journal SOAP")
    cj = report["clinical_journal"]
    _kv("SOAP 条数", cj["total_entries"])
    _kv("完整率 (四字段都有)", f"{cj['complete_soap_pct']}%" if cj["complete_soap_pct"] is not None else "—")
    _kv("活跃 case 数", cj["active_case_threads"])
    _kv("最近一条", cj["last_entry"] or "—")
    if cj["by_creator"]:
        print("  按来源:")
        _section_dict(cj["by_creator"], indent=4)
    if cj["by_theme"]:
        print("  按主题:")
        _section_dict(cj["by_theme"], indent=4)

    _p("C. Memory / KG (Sprint 5)")
    mk = report["memory_kg"]
    _kv("Fact 总数", f"{mk['facts_total']} (+{mk['facts_new']} 窗口内)")
    _kv("Entity 总数", f"{mk['entities_total']} (+{mk['entities_new']} 窗口内)")
    _kv("Relation 总数", f"{mk['relations_total']} (+{mk['relations_new']} 窗口内)")
    if mk["facts_by_tier"]:
        print("  Fact 按 tier:")
        _section_dict(mk["facts_by_tier"], indent=4)
    if mk["entities_by_type"]:
        print("  Entity 按 type:")
        _section_dict(mk["entities_by_type"], indent=4)
    if mk["relations_top_predicates"]:
        print("  Relation Top predicates:")
        _section_dict(mk["relations_top_predicates"], indent=4)

    _p("D. Doctor Weekly Report")
    dr = report["doctor_report"]
    _kv("推送尝试次数", dr["total_attempts"])
    _kv("最近尝试", dr["last_attempt"] or "—")
    if dr["by_status"]:
        print("  按状态:")
        _section_dict(dr["by_status"], indent=4)

    _p("E. ActionCard 信用循环")
    ac = report["action_card"]
    _kv("窗口新建", ac["created_in_window"])
    _kv("窗口已评分", ac["graded_in_window"])
    _kv("平均 accuracy", ac["avg_accuracy"] if ac["avg_accuracy"] is not None else "—")
    if ac["by_specialist"]:
        print("  按 specialist:")
        _section_dict(ac["by_specialist"], indent=4)

    _p("F. Safety Guardian 告警")
    sg = report["safety_guardian"]
    _kv("评估次数", sg["evaluations"])
    _kv("告警总数 (alerts_count 累计)", sg["total_alerts_raised"])

    _p("G. tool_validator (需 --remote)")
    tv = report.get("tool_validator", {"skipped": True, "reason": "local run"})
    if tv.get("skipped"):
        _kv("skipped", tv.get("reason", ""))
    else:
        _kv("coerced", tv.get("coerced"))
        _kv("rejected", tv.get("rejected"))
        _kv("journalctl 行数", tv.get("log_lines"))

    _p("💡 行动建议 (自动)")
    _actionable_suggestions(report)


def _actionable_suggestions(report: dict):
    """据数据给出"个人使用"痛点列表."""
    suggestions = []
    ol = report["open_loop"]
    if ol["total_sent"] == 0:
        suggestions.append("🔴 Open-Loop 过去窗口一条没推 — 需确认 Celery 是否在跑 / 信号阈值是否太高")
    else:
        # 投递失败 — 比 dismissal 更严重, 用户根本没收到
        if ol["delivery_fail"] > 0:
            fail_pct = round(100 * ol["delivery_fail"] / ol["total_sent"], 1)
            if fail_pct >= 50:
                suggestions.append(
                    f"🔴 Open-Loop 投递失败 {ol['delivery_fail']}/{ol['total_sent']} ({fail_pct}%) — APNs 链路断了, 查 push_service 日志/设备 token 有效性"
                )
            else:
                suggestions.append(
                    f"🟡 Open-Loop 投递失败率 {fail_pct}% — 看下具体 delivery_error"
                )
        # 零交互 — 全部未操作可能是没推成功或用户没看
        未操作 = ol["by_action"].get("未操作", 0)
        if 未操作 == ol["total_sent"] and ol["delivery_fail"] == 0:
            suggestions.append(
                f"🟡 Open-Loop {ol['total_sent']} 条全未操作 — 用户真看到了吗? 检查前端反馈回调"
            )
        dismissed = (ol["by_action"].get("dismissed", 0) +
                     ol["by_action"].get("not_interested", 0) +
                     ol["by_action"].get("snooze_7d", 0))
        if dismissed > 0 and dismissed / ol["total_sent"] > 0.5:
            suggestions.append(
                f"🟡 Open-Loop dismissal 率 {dismissed}/{ol['total_sent']} — 阈值可能过低, 下周考虑调整"
            )
        # kind 单一 — Open-Loop 本该有 3 种信号 (plan_deviation / lab_overdue / trend_anomaly)
        if len(ol["by_kind"]) == 1:
            only_kind = next(iter(ol["by_kind"].keys()))
            suggestions.append(
                f"🟡 Open-Loop 只触发了一类信号 ({only_kind}) — 其他 kind 检测器是否正常?"
            )

    cj = report["clinical_journal"]
    if cj["total_entries"] == 0:
        suggestions.append("🔴 Journal 过去窗口一条 SOAP 都没写 — briefing_task 或 orchestrator 链路可能断了")
    elif cj["complete_soap_pct"] is not None and cj["complete_soap_pct"] < 80:
        suggestions.append(
            f"🟡 Journal SOAP 完整率 {cj['complete_soap_pct']}% — extractor prompt 需强化四字段要求"
        )
    # 只有 briefing_task 没 orchestrator — 说明对话不产 SOAP
    if cj["total_entries"] > 0 and len(cj["by_creator"]) == 1:
        only_creator = next(iter(cj["by_creator"].keys()))
        if only_creator == "briefing_task":
            suggestions.append(
                f"🟡 Journal 只有 briefing_task 产 SOAP, orchestrator 对话没触发 — 对话写 SOAP 旁路可能没接上"
            )

    mk = report["memory_kg"]
    # 总量稀少
    if mk["facts_total"] < 20 and mk["entities_total"] < 20:
        suggestions.append(
            f"🔴 Sprint 5 数据量极少 (facts={mk['facts_total']}, entities={mk['entities_total']}) — "
            "memory_extractor 没在对话主链路上被调用, 或 ingest hook 没触发"
        )
    if mk["facts_new"] == 0 and mk["entities_new"] == 0 and mk["relations_new"] == 0:
        suggestions.append("🟡 Memory/KG 窗口内零新增 — ingest hook 可能没接上, 查 memory_extractor 调用点")
    if mk["facts_total"] > 0 and mk["facts_by_tier"].get("semantic", 0) == 0:
        suggestions.append("🟢 Fact 有量但没 semantic 层 — Decay+Crystallization cron 是否在跑? (每天 04:00)")

    dr = report["doctor_report"]
    if dr["total_attempts"] == 0:
        suggestions.append("🔴 Doctor Weekly 窗口内零推送 — celery_app.py beat doctor-weekly-report 可能没加载")
    else:
        # 全失败
        failed = dr["by_status"].get("failed", 0) + dr["by_status"].get("error", 0)
        if failed == dr["total_attempts"]:
            suggestions.append(
                f"🔴 Doctor Weekly {dr['total_attempts']} 次尝试全部 failed — Telegram chat_id 或 bot_token 配错了?"
            )

    ac = report["action_card"]
    if ac["created_in_window"] == 0:
        suggestions.append(
            "🔴 ActionCard 窗口内零创建 — specialist 都没产 proposed_cards? "
            "orchestrator 触发频率 / proposed_cards 写入链路检查"
        )
    elif ac["graded_in_window"] == 0:
        suggestions.append("🟡 ActionCard 只创建没评分 — outcome_grader (08:00 daily) 可能没跑")

    sg = report["safety_guardian"]
    if sg["evaluations"] == 0:
        suggestions.append("🟡 Safety Guardian 没评估记录 — 你本周没用 App 吗?")
    elif sg["evaluations"] > 0:
        avg = sg["total_alerts_raised"] / sg["evaluations"]
        if avg >= 5:
            suggestions.append(
                f"🔴 Safety Guardian 平均每次评估 {avg:.1f} 条告警 (N={sg['evaluations']}) — "
                "告警风暴, 用户会被淹没, 需要降噪 / severity 门槛上调 / dedup"
            )
        elif avg >= 3:
            suggestions.append(
                f"🟡 Safety Guardian 平均 {avg:.1f} 条/次 — 偏多, 可考虑严重度过滤"
            )

    tv = report.get("tool_validator", {})
    if not tv.get("skipped") and tv.get("log_lines", 0) > 0:
        if tv.get("coerced", 0) == 0 and tv.get("rejected", 0) == 0:
            suggestions.append(
                "🟡 tool_validator 窗口内零命中 — 要么工具参数质量极好, 要么 validator 没挂在主路径上. "
                "建议抽查 1 条 tool_call 日志确认走了 validator"
            )

    if not suggestions:
        suggestions.append("✅ 所有链路看起来在跑, 无明显异常. 可以关注『个人体感』层面的痛点.")

    for s in suggestions:
        print(f"  {s}")


# ============================================================
# main
# ============================================================

def run_remote(days: int, user_id: int | None, as_json: bool) -> int:
    """SSH 到生产机跑本脚本自己."""
    cmd_parts = [
        "cd /opt/health-app/backend && source venv/bin/activate &&",
        "python scripts/observation_dashboard.py",
        f"--days {days}",
    ]
    if user_id:
        cmd_parts.append(f"--user {user_id}")
    if as_json:
        cmd_parts.append("--json")
    cmd_parts.append("--include-journal")

    remote_cmd = " ".join(cmd_parts)
    print(f"[remote] ssh root@39.98.206.178 \"{remote_cmd}\"", file=sys.stderr)
    result = subprocess.run(
        ["ssh", "root@39.98.206.178", remote_cmd],
        text=True,
    )
    return result.returncode


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--user", type=int, default=None, help="仅统计该 user_id")
    p.add_argument("--json", action="store_true")
    p.add_argument("--remote", action="store_true", help="通过 SSH 跑线上")
    p.add_argument("--include-journal", action="store_true", help="本地也扫 journalctl (一般 --remote 时自动带)")
    args = p.parse_args()

    if args.remote:
        rc = run_remote(args.days, args.user, args.json)
        sys.exit(rc)

    since = _utc_now() - timedelta(days=args.days)
    db = _get_session()
    try:
        report = {
            "open_loop": open_loop_stats(db, since, args.user),
            "clinical_journal": clinical_journal_stats(db, since, args.user),
            "memory_kg": memory_kg_stats(db, since, args.user),
            "doctor_report": doctor_report_stats(db, since, args.user),
            "action_card": action_card_stats(db, since, args.user),
            "safety_guardian": safety_audit_stats(db, since, args.user),
        }
        if args.include_journal:
            report["tool_validator"] = tool_validator_stats_remote(args.days)
    finally:
        db.close()

    if args.json:
        print(json.dumps({
            "generated_at": _utc_now().isoformat(),
            "window_days": args.days,
            "user_id": args.user,
            "report": report,
        }, ensure_ascii=False, indent=2))
    else:
        render_text(report, args.days, args.user)


if __name__ == "__main__":
    main()
