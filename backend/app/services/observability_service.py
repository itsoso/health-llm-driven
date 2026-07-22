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
# G. Memory Injection (T1.1) — _inject_memory 4 stage 命中率
#    诊断"AI 真的记得我吗" — Memory KG / case timeline 注入是否在主链路生效
# ---------------------------------------------------------------

def memory_injection_stats(db: Session, since: datetime, user_id: Optional[int]) -> dict:
    """聚合最近 N 天 _inject_memory 的 stage 级命中率.

    每次 orchestrator 调用都写一行 agent_type='memory_injection' audit, 含
    result_detail.stages = {conversation/case_timeline/directives/hybrid: {ok, chars, count, error}}
    这里按 stage 聚合 ok 率 + 平均 chars/count + 错误数.
    """
    from app.models.agent_audit_log import AgentAuditLog

    q = db.query(AgentAuditLog).filter(
        AgentAuditLog.created_at >= since,
        AgentAuditLog.agent_type == "memory_injection",
    )
    if user_id:
        q = q.filter(AgentAuditLog.user_id == user_id)

    rows = q.all()
    total = len(rows)

    if total == 0:
        return {
            "total_invocations": 0,
            "by_stage": {},
            "avg_chars_added": 0,
        }

    # 4 stage 名固定
    stages = ["conversation", "case_timeline", "directives", "hybrid"]
    by_stage: dict[str, dict] = {
        s: {"ok": 0, "fail": 0, "error": 0, "avg_chars": 0, "avg_count": 0}
        for s in stages
    }

    chars_sum = 0
    char_buckets: dict[str, int] = {s: 0 for s in stages}
    count_buckets: dict[str, int] = {s: 0 for s in stages}
    ok_buckets: dict[str, int] = {s: 0 for s in stages}

    for r in rows:
        detail = r.result_detail or {}
        if isinstance(detail, str):
            try:
                import json
                detail = json.loads(detail)
            except Exception:
                detail = {}
        chars_sum += int(detail.get("total_chars_added") or 0)
        for s in stages:
            sd = (detail.get("stages") or {}).get(s) or {}
            ok = bool(sd.get("ok"))
            err = sd.get("error")
            if ok:
                by_stage[s]["ok"] += 1
                ok_buckets[s] += 1
                char_buckets[s] += int(sd.get("chars") or 0)
                count_buckets[s] += int(sd.get("count") or 0)
            else:
                by_stage[s]["fail"] += 1
                if err:
                    by_stage[s]["error"] += 1

    for s in stages:
        ok_n = ok_buckets[s] or 1
        by_stage[s]["avg_chars"] = round(char_buckets[s] / ok_n, 1) if ok_buckets[s] else 0
        by_stage[s]["avg_count"] = round(count_buckets[s] / ok_n, 2) if ok_buckets[s] else 0
        by_stage[s]["ok_rate"] = round(by_stage[s]["ok"] / total, 2)

    return {
        "total_invocations": total,
        "by_stage": by_stage,
        "avg_chars_added": round(chars_sum / total, 1) if total else 0,
    }


# ---------------------------------------------------------------
# H. AIGC Media provider health
# ---------------------------------------------------------------

def aigc_media_stats(db: Session, since: datetime, user_id: Optional[int]) -> dict:
    """Return de-identified media-job health for operators."""
    from app.models.aigc_media_job import AIGCMediaJob
    from app.services.aigc_media_job_service import AIGC_SAFE_RETRY_ERROR_CODES

    q = db.query(AIGCMediaJob).filter(AIGCMediaJob.created_at >= since)
    if user_id:
        q = q.filter(AIGCMediaJob.user_id == user_id)

    total = q.count()
    if total == 0:
        return {
            "total_jobs": 0,
            "by_status": {},
            "by_error_code": {},
            "auth_failures": 0,
            "submission_unknown": 0,
            "safe_retryable": 0,
            "success_rate_pct": None,
            "last_job_at": None,
            "last_failure_at": None,
            "status": "no_data",
        }

    by_status = {
        str(status or "unknown"): int(count)
        for status, count in q.with_entities(
            AIGCMediaJob.status,
            func.count(AIGCMediaJob.id),
        ).group_by(AIGCMediaJob.status).all()
    }
    by_error_code = {
        str(code): int(count)
        for code, count in q.with_entities(
            AIGCMediaJob.provider_error_code,
            func.count(AIGCMediaJob.id),
        ).filter(AIGCMediaJob.provider_error_code.isnot(None)).group_by(
            AIGCMediaJob.provider_error_code
        ).all()
    }
    auth_failures = int(by_error_code.get("provider_auth_failed", 0))
    submission_unknown = int(by_status.get("submission_unknown", 0))
    safe_retryable = q.filter(
        AIGCMediaJob.status == "failed",
        AIGCMediaJob.provider_task_id.is_(None),
        AIGCMediaJob.provider_error_code.in_(AIGC_SAFE_RETRY_ERROR_CODES),
    ).count()
    resolved = int(by_status.get("succeeded", 0)) + int(by_status.get("failed", 0))
    success_rate = (
        round(100.0 * int(by_status.get("succeeded", 0)) / resolved, 1)
        if resolved else None
    )
    last_job = q.with_entities(func.max(AIGCMediaJob.created_at)).scalar()
    last_failure = q.filter(
        AIGCMediaJob.status.in_(("failed", "submission_unknown"))
    ).with_entities(func.max(AIGCMediaJob.completed_at)).scalar()
    if last_failure is None:
        last_failure = q.filter(
            AIGCMediaJob.status.in_(("failed", "submission_unknown"))
        ).with_entities(func.max(AIGCMediaJob.updated_at)).scalar()

    if auth_failures:
        status = "critical"
    elif submission_unknown or int(by_status.get("failed", 0)):
        status = "warning"
    else:
        status = "ok"
    return {
        "total_jobs": int(total),
        "by_status": by_status,
        "by_error_code": by_error_code,
        "auth_failures": auth_failures,
        "submission_unknown": submission_unknown,
        "safe_retryable": int(safe_retryable),
        "success_rate_pct": success_rate,
        "last_job_at": last_job.isoformat() if last_job else None,
        "last_failure_at": last_failure.isoformat() if last_failure else None,
        "status": status,
    }


# ---------------------------------------------------------------
# H. Client Events (Task 9) — Mobile 埋点聚合
#    reasoning_sheet_opened / journal_timeline_entered / specialist_scorecard_entered
# ---------------------------------------------------------------

def _percentile(values: list, pct: float) -> Optional[float]:
    """Linear-interpolated percentile. Returns None for an empty list."""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    if lo == hi:
        return float(s[lo])
    return float(s[lo]) + (float(s[hi]) - float(s[lo])) * (k - lo)


APP_UPDATE_HEALTH_MIN_LAUNCHES = 20
APP_UPDATE_HEALTH_EMERGENCY_RATE_PCT = 5.0
APP_UPDATE_HEALTH_TERMINAL_FAILURE_RATE_PCT = 10.0


def app_update_release_health(
    *,
    launches: int,
    emergency_launches: int,
    terminal_attempts: int,
    terminal_failures: int,
) -> dict:
    """判定发布后的客户端更新健康度.

    这是一个只读、可解释的运维信号，不执行暂停、回滚或 Remote Config 写入。
    启动样本作为最低分母；更新终态没有数据时保留 ``None``，避免伪造成功率。
    """
    safe_launches = max(0, int(launches))
    safe_emergency = min(safe_launches, max(0, int(emergency_launches)))
    safe_terminal_attempts = max(0, int(terminal_attempts))
    safe_terminal_failures = min(
        safe_terminal_attempts,
        max(0, int(terminal_failures)),
    )
    emergency_rate = (
        round(100.0 * safe_emergency / safe_launches, 1)
        if safe_launches else None
    )
    terminal_failure_rate = (
        round(100.0 * safe_terminal_failures / safe_terminal_attempts, 1)
        if safe_terminal_attempts else None
    )
    sample_sufficient = safe_launches >= APP_UPDATE_HEALTH_MIN_LAUNCHES

    reasons: list[str] = []
    if not sample_sufficient:
        reasons.append(
            f"发布启动样本不足 {APP_UPDATE_HEALTH_MIN_LAUNCHES}，继续观察"
        )
    else:
        if (
            emergency_rate is not None
            and emergency_rate >= APP_UPDATE_HEALTH_EMERGENCY_RATE_PCT
        ):
            reasons.append(
                f"紧急启动率 {emergency_rate:.1f}% 达到暂停阈值 "
                f"{APP_UPDATE_HEALTH_EMERGENCY_RATE_PCT:.1f}%"
            )
        if (
            terminal_failure_rate is not None
            and terminal_failure_rate >= APP_UPDATE_HEALTH_TERMINAL_FAILURE_RATE_PCT
        ):
            reasons.append(
                f"更新失败率 {terminal_failure_rate:.1f}% 达到暂停阈值 "
                f"{APP_UPDATE_HEALTH_TERMINAL_FAILURE_RATE_PCT:.1f}%"
            )
        if not reasons:
            reasons.append("发布启动与更新终态均在阈值内")

    has_pause_reason = any("达到暂停阈值" in reason for reason in reasons)
    if not sample_sufficient:
        status = "observe"
    elif has_pause_reason:
        status = "pause_rollout"
    else:
        status = "healthy"

    return {
        "status": status,
        "sample_sufficient": sample_sufficient,
        "thresholds": {
            "min_launches": APP_UPDATE_HEALTH_MIN_LAUNCHES,
            "emergency_rate_pct": APP_UPDATE_HEALTH_EMERGENCY_RATE_PCT,
            "terminal_failure_rate_pct": APP_UPDATE_HEALTH_TERMINAL_FAILURE_RATE_PCT,
        },
        "launches": safe_launches,
        "emergency_launches": safe_emergency,
        "emergency_rate_pct": emergency_rate,
        "terminal_attempts": safe_terminal_attempts,
        "terminal_failures": safe_terminal_failures,
        "terminal_failure_rate_pct": terminal_failure_rate,
        "reasons": reasons,
    }


def client_events_stats(db: Session, since: datetime, user_id: Optional[int]) -> dict:
    """Aggregate UI telemetry.

    Beyond raw per-event counts this surfaces the two signals the events were
    instrumented for:
      - starter_ctr: per-generator CTR (clicks / impressions) — tells which
        new-chat chip generators are useful vs dead, so priority bands can be
        tuned from data instead of guesswork.
      - home_cold_start_ms: p50/p95 of launch→first-screen-ready duration.
    """
    from app.models.client_event import ClientEvent

    q = db.query(ClientEvent).filter(ClientEvent.created_at >= since)
    if user_id:
        q = q.filter(ClientEvent.user_id == user_id)
    rows = q.with_entities(ClientEvent.event_name, ClientEvent.meta).all()

    by_event: Dict[str, int] = {}
    impressions: Dict[str, int] = {}  # starter generator key → 曝光次数
    clicks: Dict[str, int] = {}       # starter generator key → 点击次数
    cold_start_ms: list = []
    cold_start_incomplete = 0
    diet_event_map = {
        "diet_photo_recognition_terminal": "recognition",
        "diet_photo_confirmation_terminal": "confirmation",
        "diet_share_terminal": "share",
    }
    diet_durations: Dict[str, list] = {key: [] for key in diet_event_map.values()}
    diet_attempts: Dict[str, int] = {key: 0 for key in diet_event_map.values()}
    diet_failures: Dict[str, int] = {key: 0 for key in diet_event_map.values()}
    diet_cancelled: Dict[str, int] = {key: 0 for key in diet_event_map.values()}
    diet_corrections = 0
    diet_prepare_ms: list[float] = []
    diet_payload_kb: list[float] = []
    diet_share_targets = ("generic", "wechat", "xiaohongshu")
    diet_share_by_target: Dict[str, dict] = {
        target: {"attempts": 0, "completed": 0, "with_photo": 0, "failures": 0}
        for target in diet_share_targets
    }
    app_update_by_phase: Dict[str, int] = {}
    app_update_by_launch_source: Dict[str, int] = {}
    app_update_checks = 0
    app_update_outcome_terminals = 0
    app_update_ready = 0
    app_update_failures = 0

    for name, meta in rows:
        by_event[name] = by_event.get(name, 0) + 1
        meta = meta if isinstance(meta, dict) else {}
        if name == "starter_chips_shown":
            for key in meta.get("keys") or []:
                if isinstance(key, str):
                    impressions[key] = impressions.get(key, 0) + 1
        elif name == "starter_chip_clicked":
            key = meta.get("key")
            if isinstance(key, str):
                clicks[key] = clicks.get(key, 0) + 1
        elif name == "home_cold_start_perf":
            ms = meta.get("emitted_at_ms")
            if isinstance(ms, (int, float)):
                cold_start_ms.append(float(ms))
            if meta.get("incomplete"):
                cold_start_incomplete += 1
        elif name in diet_event_map:
            stage = diet_event_map[name]
            diet_attempts[stage] += 1
            phase = meta.get("phase")
            duration = meta.get("duration_ms")
            if (
                phase == "completed"
                and isinstance(duration, (int, float))
                and not isinstance(duration, bool)
            ):
                diet_durations[stage].append(float(duration))
            if phase == "failed":
                diet_failures[stage] += 1
            elif phase == "cancelled":
                diet_cancelled[stage] += 1
            if name == "diet_share_terminal":
                share_target = meta.get("share_target")
                if share_target in diet_share_by_target:
                    target_stats = diet_share_by_target[share_target]
                    target_stats["attempts"] += 1
                    if phase == "completed":
                        target_stats["completed"] += 1
                        if meta.get("has_photo") is True:
                            target_stats["with_photo"] += 1
                    elif phase == "failed":
                        target_stats["failures"] += 1
            if (
                name == "diet_photo_confirmation_terminal"
                and phase == "completed"
                and meta.get("corrected") is True
            ):
                diet_corrections += 1
            if name == "diet_photo_recognition_terminal" and phase == "completed":
                prepare_ms = meta.get("client_prepare_ms")
                payload_bytes = meta.get("payload_bytes")
                if isinstance(prepare_ms, (int, float)) and not isinstance(prepare_ms, bool):
                    diet_prepare_ms.append(float(prepare_ms))
                if isinstance(payload_bytes, (int, float)) and not isinstance(payload_bytes, bool):
                    diet_payload_kb.append(float(payload_bytes) / 1024.0)
        elif name in {"app_update_phase", "app_update_terminal"}:
            phase = meta.get("phase")
            if isinstance(phase, str):
                app_update_by_phase[phase] = app_update_by_phase.get(phase, 0) + 1
            if name == "app_update_terminal":
                app_update_checks += 1
                if phase == "ready":
                    app_update_ready += 1
                    app_update_outcome_terminals += 1
                elif phase == "failed":
                    app_update_failures += 1
                    app_update_outcome_terminals += 1
        elif name == "app_update_launch":
            launch_source = meta.get("launch_source")
            if isinstance(launch_source, str):
                app_update_by_launch_source[launch_source] = (
                    app_update_by_launch_source.get(launch_source, 0) + 1
                )

    starter_ctr: Dict[str, dict] = {}
    for key in sorted(set(impressions) | set(clicks)):
        imp = impressions.get(key, 0)
        clk = clicks.get(key, 0)
        starter_ctr[key] = {
            "impressions": imp,
            "clicks": clk,
            "ctr_pct": round(100.0 * clk / imp, 1) if imp else None,
        }

    p50 = _percentile(cold_start_ms, 50)
    p95 = _percentile(cold_start_ms, 95)
    diet_capture_ms = {}
    for stage, values in diet_durations.items():
        stage_p50 = _percentile(values, 50)
        stage_p95 = _percentile(values, 95)
        diet_capture_ms[stage] = {
            "n": len(values),
            "attempts": diet_attempts[stage],
            "p50": round(stage_p50) if stage_p50 is not None else None,
            "p95": round(stage_p95) if stage_p95 is not None else None,
            "failures": diet_failures[stage],
            "cancelled": diet_cancelled[stage],
        }
    prepare_p50 = _percentile(diet_prepare_ms, 50)
    prepare_p95 = _percentile(diet_prepare_ms, 95)
    payload_p50 = _percentile(diet_payload_kb, 50)
    payload_p95 = _percentile(diet_payload_kb, 95)
    diet_capture_ms["recognition"].update({
        "client_prepare_p50": round(prepare_p50) if prepare_p50 is not None else None,
        "client_prepare_p95": round(prepare_p95) if prepare_p95 is not None else None,
        "payload_kb_p50": round(payload_p50) if payload_p50 is not None else None,
        "payload_kb_p95": round(payload_p95) if payload_p95 is not None else None,
    })
    completed_confirmations = diet_capture_ms["confirmation"]["n"]
    diet_capture_ms["confirmation"].update({
        "corrected": diet_corrections,
        "correction_rate_pct": (
            round(100.0 * diet_corrections / completed_confirmations, 1)
            if completed_confirmations else None
        ),
    })
    diet_capture_ms["share"]["by_target"] = diet_share_by_target
    app_update_launches = sum(app_update_by_launch_source.values())
    return {
        "total": sum(by_event.values()),
        "by_event": by_event,
        "app_update": {
            "launches": app_update_launches,
            "checks": app_update_checks,
            "ready": app_update_ready,
            "failures": app_update_failures,
            "failure_rate_pct": (
                round(100.0 * app_update_failures / app_update_outcome_terminals, 1)
                if app_update_outcome_terminals else None
            ),
            "by_phase": app_update_by_phase,
            "by_launch_source": app_update_by_launch_source,
            "release_health": app_update_release_health(
                launches=app_update_launches,
                emergency_launches=app_update_by_launch_source.get("emergency", 0),
                terminal_attempts=app_update_outcome_terminals,
                terminal_failures=app_update_failures,
            ),
        },
        "starter_ctr": starter_ctr,
        "home_cold_start_ms": {
            "n": len(cold_start_ms),
            "p50": round(p50) if p50 is not None else None,
            "p95": round(p95) if p95 is not None else None,
            "incomplete": cold_start_incomplete,
        },
        "diet_capture_ms": diet_capture_ms,
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
    aigc = report.get("aigc_media") or {}
    if int(aigc.get("auth_failures") or 0) > 0:
        out.append(
            f"🔴 AIGC 媒体授权失败 {int(aigc['auth_failures'])} 次："
            "检查北京区域按量 API Key、Workspace 和模型权限"
        )
    elif int(aigc.get("submission_unknown") or 0) > 0:
        out.append(
            f"🟡 AIGC 媒体有 {int(aigc['submission_unknown'])} 个提交待核验任务："
            "先对账供应商任务，不要重复提交"
        )
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
            out.append("🟡 Journal 只有 briefing_task 产 SOAP, orchestrator 对话没触发")

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
    release_health = (ce or {}).get("app_update", {}).get("release_health", {})
    if release_health.get("status") == "pause_rollout":
        reasons = "；".join(release_health.get("reasons") or ["发布健康门命中暂停阈值"])
        out.insert(0, f"🔴 发布健康门建议暂停放量：{reasons}")

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
        "memory_injection": memory_injection_stats(db, since, user_id),
        "client_events": client_events_stats(db, since, user_id),
        "aigc_media": aigc_media_stats(db, since, user_id),
    }
    if include_journalctl:
        report["tool_validator"] = tool_validator_stats_remote(days)
    return report
