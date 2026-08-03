"""Smoke tests for observability_service — 保证 dashboard schema 不破."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.observability_service import (
    action_card_stats,
    actionable_suggestions,
    aigc_media_stats,
    clinical_journal_stats,
    collect_dashboard,
    doctor_report_stats,
    memory_injection_stats,
    memory_kg_stats,
    open_loop_stats,
    safety_audit_stats,
)


def _now():
    return datetime.now(timezone.utc)


def _since(days=7):
    return _now() - timedelta(days=days)


# ----------------------------------------------------------------
# 空库: 每个 stats 函数都该返回完整 schema (keys 齐全, 不抛异常)
# ----------------------------------------------------------------

def test_open_loop_stats_empty_db(db):
    r = open_loop_stats(db, _since(), user_id=None)
    assert r == {
        "total_sent": 0, "by_kind": {}, "by_action": {},
        "delivery_fail": 0, "avg_score": None, "last_sent": None,
    }


def test_clinical_journal_stats_empty_db(db):
    r = clinical_journal_stats(db, _since(), user_id=None)
    assert r["total_entries"] == 0
    assert r["by_creator"] == {}
    assert r["by_theme"] == {}
    assert r["active_case_threads"] == 0
    assert r["complete_soap_pct"] is None
    assert r["last_entry"] is None


def test_memory_kg_stats_empty_db(db):
    r = memory_kg_stats(db, _since(), user_id=None)
    for k in ("facts_total", "facts_new", "entities_total",
              "entities_new", "relations_total", "relations_new"):
        assert r[k] == 0, k
    assert r["facts_by_tier"] == {}
    assert r["entities_by_type"] == {}
    assert r["relations_top_predicates"] == {}


def test_doctor_report_stats_empty_db(db):
    r = doctor_report_stats(db, _since(), user_id=None)
    assert r == {"total_attempts": 0, "unique_users": 0, "last_attempt": None}


def test_action_card_stats_empty_db(db):
    r = action_card_stats(db, _since(), user_id=None)
    assert r == {
        "created_in_window": 0, "graded_in_window": 0,
        "avg_accuracy": None, "by_specialist": {},
    }


def test_safety_audit_stats_empty_db(db):
    r = safety_audit_stats(db, _since(), user_id=None)
    assert r == {"evaluations": 0, "total_alerts_raised": 0}


def test_memory_injection_stats_empty_db(db):
    r = memory_injection_stats(db, _since(), user_id=None)
    assert r == {"total_invocations": 0, "by_stage": {}, "avg_chars_added": 0}


def test_aigc_media_stats_empty_db(db):
    r = aigc_media_stats(db, _since(), user_id=None)
    assert r == {
        "total_jobs": 0,
        "by_status": {},
        "by_model": {},
        "by_kind": {},
        "by_error_code": {},
        "auth_failures": 0,
        "submission_unknown": 0,
        "safe_retryable": 0,
        "success_rate_pct": None,
        "latency_seconds": {"count": 0, "p50": None, "p95": None},
        "output_bytes": {"count": 0, "total": 0, "average": None},
        "requested_video_seconds": 0,
        "by_duration_seconds": {},
        "stuck_active_jobs": 0,
        "engagement": {
            "played": 0,
            "share_attempts": 0,
            "share_completed": 0,
            "share_failed": 0,
            "share_by_target": {},
        },
        "last_job_at": None,
        "last_failure_at": None,
        "status": "no_data",
    }


def test_collect_dashboard_schema(db):
    """collect_dashboard 返回的 top-level keys 固化 — admin 前端的 TS 类型靠它."""
    report = collect_dashboard(db, days=7, user_id=None, include_journalctl=False)
    assert set(report.keys()) == {
        "open_loop", "clinical_journal", "memory_kg",
        "doctor_report", "action_card", "safety_guardian",
        "memory_injection", "client_events", "aigc_media",
        "registration_invitation",
    }


def test_aigc_media_stats_aggregate_failures_without_exposing_job_content(db):
    from app.models.aigc_media_job import AIGCMediaJob

    now = _now()
    db.add_all([
        AIGCMediaJob(
            id="aigc-auth-failed",
            user_id=1,
            kind="text_to_video",
            status="failed",
            progress=0,
            model="wan2.7-t2v",
            idempotency_key="auth-failed",
            request_fingerprint="a" * 64,
            provider_error_code="provider_auth_failed",
            error_message="must never be returned by aggregate",
            created_at=now - timedelta(minutes=10),
            completed_at=now - timedelta(minutes=9),
        ),
        AIGCMediaJob(
            id="aigc-success",
            user_id=1,
            kind="text_to_image",
            status="succeeded",
            progress=100,
            model="wan2.7-image",
            idempotency_key="success",
            request_fingerprint="b" * 64,
            result_metadata={
                "byte_size": 4_000_000,
                "request": {
                    "duration_seconds": 10,
                    "ratio": "9:16",
                    "resolution": "720P",
                },
            },
            created_at=now - timedelta(minutes=5),
            started_at=now - timedelta(minutes=5),
            completed_at=now - timedelta(minutes=4),
        ),
        AIGCMediaJob(
            id="aigc-other-user",
            user_id=2,
            kind="text_to_video",
            status="submission_unknown",
            progress=0,
            model="wan2.7-t2v",
            idempotency_key="other-user",
            request_fingerprint="c" * 64,
            provider_error_code="provider_submission_unknown",
            created_at=now - timedelta(minutes=3),
        ),
    ])
    db.commit()

    all_users = aigc_media_stats(db, _since(), user_id=None)
    owner = aigc_media_stats(db, _since(), user_id=1)

    assert all_users["total_jobs"] == 3
    assert all_users["auth_failures"] == 1
    assert all_users["submission_unknown"] == 1
    assert all_users["safe_retryable"] == 1
    assert all_users["by_model"] == {
        "wan2.7-image": 1,
        "wan2.7-t2v": 2,
    }
    assert all_users["by_kind"] == {
        "text_to_image": 1,
        "text_to_video": 2,
    }
    assert all_users["latency_seconds"] == {
        "count": 1,
        "p50": 60.0,
        "p95": 60.0,
    }
    assert all_users["output_bytes"] == {
        "count": 1,
        "total": 4_000_000,
        "average": 4_000_000,
    }
    assert all_users["requested_video_seconds"] == 0
    assert all_users["by_duration_seconds"] == {}
    assert all_users["success_rate_pct"] == 50.0
    assert all_users["status"] == "critical"
    assert all_users["stuck_active_jobs"] == 0
    assert all_users["engagement"]["played"] == 0
    assert owner["total_jobs"] == 2
    assert owner["submission_unknown"] == 0
    assert owner["by_status"] == {"failed": 1, "succeeded": 1}
    assert "aigc-auth-failed" not in str(all_users)
    assert "must never be returned" not in str(all_users)


def test_aigc_media_stats_aggregates_stuck_jobs_and_content_free_engagement(db):
    from app.models.aigc_media_job import AIGCMediaJob
    from app.models.client_event import ClientEvent

    now = _now()
    db.add_all([
        AIGCMediaJob(
            id="aigc-stuck-running",
            user_id=1,
            kind="text_to_video",
            status="running",
            progress=50,
            model="happyhorse-1.1-t2v",
            provider_task_id="task-stuck-running",
            idempotency_key="stuck-running",
            request_fingerprint="s" * 64,
            created_at=now - timedelta(minutes=40),
        ),
        ClientEvent(
            user_id=1,
            event_name="aigc_media_played",
            meta={"media_kind": "video"},
            created_at=now - timedelta(minutes=5),
        ),
        ClientEvent(
            user_id=1,
            event_name="aigc_media_shared",
            meta={
                "phase": "completed",
                "media_kind": "video",
                "share_target": "wechat",
            },
            created_at=now - timedelta(minutes=4),
        ),
        ClientEvent(
            user_id=1,
            event_name="aigc_media_shared",
            meta={
                "phase": "failed",
                "media_kind": "video",
                "share_target": "xiaohongshu",
                "error_code": "share_failed",
            },
            created_at=now - timedelta(minutes=3),
        ),
    ])
    db.commit()

    stats = aigc_media_stats(db, _since(), user_id=1)

    assert stats["stuck_active_jobs"] == 1
    assert stats["status"] == "warning"
    assert stats["engagement"] == {
        "played": 1,
        "share_attempts": 2,
        "share_completed": 1,
        "share_failed": 1,
        "share_by_target": {
            "wechat": {"attempts": 1, "completed": 1, "failed": 0},
            "xiaohongshu": {"attempts": 1, "completed": 0, "failed": 1},
        },
    }


def test_actionable_suggestions_reports_stuck_aigc_jobs(db):
    report = collect_dashboard(db, days=7, user_id=None, include_journalctl=False)
    report["aigc_media"] = {
        **report["aigc_media"],
        "stuck_active_jobs": 2,
        "status": "warning",
    }

    lines = actionable_suggestions(report)

    assert lines[0] == "🟡 AIGC 媒体有 2 个任务超过 30 分钟仍未完成：检查 Celery 和供应商任务状态"


def test_actionable_suggestions_puts_aigc_auth_failure_first(db):
    report = collect_dashboard(db, days=7, user_id=None, include_journalctl=False)
    report["aigc_media"] = {
        **report["aigc_media"],
        "auth_failures": 2,
        "status": "critical",
    }

    lines = actionable_suggestions(report)

    assert lines[0] == "🔴 AIGC 媒体授权失败 2 次：检查北京区域按量 API Key、Workspace 和模型权限"


# ----------------------------------------------------------------
# Memory injection: 写入 + 聚合
# ----------------------------------------------------------------

def test_memory_injection_aggregates(db):
    """写 3 条 audit row, 聚合应返回正确的 ok_rate / avg_chars / error 计数."""
    from app.agents.audit import log_memory_injection

    # 第 1 次: conversation + hybrid 命中, case_timeline 因 no_findings 失败
    log_memory_injection(db, user_id=42, trace={
        "stages": {
            "conversation":  {"ok": True,  "chars": 120, "count": 5, "error": None},
            "case_timeline": {"ok": False, "chars": 0,   "count": 0, "error": "no_findings"},
            "directives":    {"ok": False, "chars": 0,   "count": 0, "error": None},
            "hybrid":        {"ok": True,  "chars": 200, "count": 8, "error": None},
        },
        "total_chars_added": 320,
    })
    # 第 2 次: hybrid throws
    log_memory_injection(db, user_id=42, trace={
        "stages": {
            "conversation":  {"ok": True,  "chars": 80, "count": 3, "error": None},
            "case_timeline": {"ok": True,  "chars": 150, "count": 4, "error": None},
            "directives":    {"ok": False, "chars": 0,   "count": 0, "error": None},
            "hybrid":        {"ok": False, "chars": 0,   "count": 0, "error": "redis down"},
        },
        "total_chars_added": 230,
    })
    # 第 3 次: 全空 (新用户)
    log_memory_injection(db, user_id=42, trace={
        "stages": {
            "conversation":  {"ok": False, "chars": 0, "count": 0, "error": None},
            "case_timeline": {"ok": False, "chars": 0, "count": 0, "error": "no_findings"},
            "directives":    {"ok": False, "chars": 0, "count": 0, "error": None},
            "hybrid":        {"ok": False, "chars": 0, "count": 0, "error": None},
        },
        "total_chars_added": 0,
    })

    r = memory_injection_stats(db, _since(), user_id=42)
    assert r["total_invocations"] == 3
    # 平均 chars: (320+230+0) / 3 = 183.3
    assert abs(r["avg_chars_added"] - 183.3) < 0.5

    by = r["by_stage"]
    # conversation: 2 ok / 3 = 0.67
    assert by["conversation"]["ok"] == 2
    assert by["conversation"]["fail"] == 1
    assert by["conversation"]["ok_rate"] == 0.67
    # avg chars per OK call: (120+80)/2 = 100
    assert by["conversation"]["avg_chars"] == 100.0

    # case_timeline: 1 ok / 3 = 0.33; 2 errors (no_findings)
    assert by["case_timeline"]["ok"] == 1
    assert by["case_timeline"]["error"] == 2

    # hybrid: 1 ok / 3 = 0.33; 1 真错 (redis down)
    assert by["hybrid"]["ok"] == 1
    assert by["hybrid"]["error"] == 1


def test_memory_injection_stats_user_filter(db):
    """user_id 过滤应只算指定用户."""
    from app.agents.audit import log_memory_injection

    log_memory_injection(db, user_id=1, trace={
        "stages": {"conversation": {"ok": True, "chars": 50, "count": 2, "error": None}},
        "total_chars_added": 50,
    })
    log_memory_injection(db, user_id=2, trace={
        "stages": {"conversation": {"ok": True, "chars": 200, "count": 10, "error": None}},
        "total_chars_added": 200,
    })

    r1 = memory_injection_stats(db, _since(), user_id=1)
    r2 = memory_injection_stats(db, _since(), user_id=2)
    rall = memory_injection_stats(db, _since(), user_id=None)

    assert r1["total_invocations"] == 1
    assert r2["total_invocations"] == 1
    assert rall["total_invocations"] == 2
    assert r1["avg_chars_added"] == 50
    assert r2["avg_chars_added"] == 200


def test_actionable_suggestions_shape_on_empty(db):
    """空库全是红灯, 但 suggestions 必须是非空 list[str]."""
    report = collect_dashboard(db, days=7, user_id=None, include_journalctl=False)
    lines = actionable_suggestions(report)
    assert isinstance(lines, list)
    assert len(lines) > 0
    assert all(isinstance(s, str) for s in lines)


def test_actionable_suggestions_flags_release_health_pause(db):
    report = collect_dashboard(db, days=7, user_id=None, include_journalctl=False)
    report["client_events"]["app_update"]["release_health"] = {
        "status": "pause_rollout",
        "reasons": ["紧急启动率 5.0% 达到暂停阈值 5.0%"],
    }

    lines = actionable_suggestions(report)

    assert lines[0] == "🔴 发布健康门建议暂停放量：紧急启动率 5.0% 达到暂停阈值 5.0%"


def test_actionable_suggestions_flags_chat_attachment_pipeline_failures(db):
    report = collect_dashboard(db, days=7, user_id=None, include_journalctl=False)
    report["client_events"]["chat_attachment_pipeline"] = {
        "attempts": 10,
        "accepted": 7,
        "failures": 3,
        "acceptance_rate_pct": 70.0,
        "image_count_total": 14,
        "failures_by_stage": {
            "local_prepare": 2,
            "server_accept": 1,
        },
        "duration_buckets": {"lt_1s": 2, "3_10s": 8},
        "payload_buckets": {"unknown": 2, "1_4mb": 8},
    }

    lines = actionable_suggestions(report)

    assert (
        "🔴 Agent 图片受理率 70.0% (7/10)："
        "本地草稿读取失败 2 次，检查私有文件持久化与磁盘权限；"
        "服务端未受理 1 次，检查弱网恢复与请求大小"
    ) in lines


# ----------------------------------------------------------------
# 有数据: 聚合 SQL 必须和朴素 Python 逻辑等价
# ----------------------------------------------------------------

@pytest.fixture
def seed_open_loop(db):
    from app.models.open_loop_history import OpenLoopHistory
    now = _now()
    rows = [
        OpenLoopHistory(user_id=1, kind="lab_overdue", signal_key="LDL",
                        score=80, title="t", body="b",
                        sent_at=now - timedelta(hours=1),
                        delivery_ok=1, user_action="opened"),
        OpenLoopHistory(user_id=1, kind="lab_overdue", signal_key="HbA1c",
                        score=60, title="t", body="b",
                        sent_at=now - timedelta(hours=2),
                        delivery_ok=1, user_action="dismissed"),
        OpenLoopHistory(user_id=1, kind="sync_stale", signal_key="",
                        score=40, title="t", body="b",
                        sent_at=now - timedelta(hours=3),
                        delivery_ok=0, user_action=None,
                        delivery_error="timeout"),
        OpenLoopHistory(user_id=2, kind="lab_overdue", signal_key="LDL",
                        score=50, title="t", body="b",
                        sent_at=now - timedelta(hours=4),
                        delivery_ok=1, user_action=None),
    ]
    for r in rows:
        db.add(r)
    db.commit()


def test_open_loop_stats_aggregates_correctly(db, seed_open_loop):
    r = open_loop_stats(db, _since(), user_id=None)
    assert r["total_sent"] == 4
    assert r["by_kind"] == {"lab_overdue": 3, "sync_stale": 1}
    # delivery_fail only counts delivery_ok=0
    assert r["delivery_fail"] == 1
    # (80 + 60 + 40 + 50) / 4 = 57.5
    assert r["avg_score"] == 57.5
    # null user_action → "未操作"
    assert r["by_action"].get("未操作") == 2
    assert r["by_action"].get("opened") == 1
    assert r["by_action"].get("dismissed") == 1
    assert r["last_sent"] is not None


def test_open_loop_stats_user_filter(db, seed_open_loop):
    r = open_loop_stats(db, _since(), user_id=1)
    assert r["total_sent"] == 3
    assert sum(r["by_kind"].values()) == 3


def test_action_card_stats_aggregates(db):
    from app.models.action_card import ActionCard
    now = _now()
    db.add_all([
        ActionCard(user_id=1, title="t1", content="c", creator_specialist="recovery_coach",
                   created_at=now - timedelta(days=1)),
        ActionCard(user_id=1, title="t2", content="c", creator_specialist="recovery_coach",
                   created_at=now - timedelta(days=2),
                   graded_at=now - timedelta(days=1), accuracy_score=80),
        ActionCard(user_id=2, title="t3", content="c", creator_specialist="fuel_strategist",
                   created_at=now - timedelta(hours=3),
                   graded_at=now - timedelta(hours=2), accuracy_score=60),
        ActionCard(user_id=3, title="t4", content="c", creator_specialist=None,  # unknown
                   created_at=now - timedelta(hours=1)),
    ])
    db.commit()

    r = action_card_stats(db, _since(), user_id=None)
    assert r["created_in_window"] == 4
    assert r["graded_in_window"] == 2
    assert r["avg_accuracy"] == 70.0  # (80 + 60) / 2
    assert r["by_specialist"] == {
        "recovery_coach": 2, "fuel_strategist": 1, "unknown": 1,
    }


def test_doctor_report_stats_counts_clinical_journal_entries(db):
    """Fix regression: 之前用 NotificationLog ilike('%weekly%') — 错的.
    真实数据源是 ClinicalJournalEntry.created_by='doctor_weekly_task'."""
    from app.models.clinical_journal import ClinicalJournalEntry
    now = _now()
    db.add_all([
        # 命中: doctor_weekly_task
        ClinicalJournalEntry(user_id=1, created_by="doctor_weekly_task",
                             generated_at=now - timedelta(days=1),
                             subjective="s", objective="o", assessment="a", plan="p"),
        ClinicalJournalEntry(user_id=2, created_by="doctor_weekly_task",
                             generated_at=now - timedelta(days=3),
                             subjective="s", objective="o", assessment="a", plan="p"),
        # 不命中: 其他来源
        ClinicalJournalEntry(user_id=1, created_by="briefing_task",
                             generated_at=now - timedelta(hours=1),
                             subjective="s", objective="o", assessment="a", plan="p"),
    ])
    db.commit()

    r = doctor_report_stats(db, _since(), user_id=None)
    assert r["total_attempts"] == 2
    assert r["unique_users"] == 2
    assert r["last_attempt"] is not None


# ----------------------------------------------------------------
# _inject_memory 端到端: 调一次 → 应写出 audit_log 行 → 聚合可见
# ----------------------------------------------------------------

def test_inject_memory_writes_audit_row(db):
    """orchestrator._inject_memory 跑一次, 应该在 audit_log 写一行 memory_injection."""
    from app.orchestrator.orchestrator import _inject_memory
    from app.models.agent_audit_log import AgentAuditLog

    # 不传 findings, 没有 KG 数据 — 4 stage 全 fail 是正常路径
    # Phase 0.3 (2026-05-04): _inject_memory 改成返回 (prompt, trace) 元组
    # 让上层能把 trace 传给 log_orchestrator_run, audit 看得到 memory 注入情况.
    out_prompt, trace = _inject_memory(db, user_id=999, user_prompt="hello", findings=None)

    assert isinstance(out_prompt, str)
    assert isinstance(trace, dict)
    assert "stages" in trace
    assert "total_chars_added" in trace
    # 即使全 fail, audit row 也必须写
    audits = db.query(AgentAuditLog).filter(
        AgentAuditLog.agent_type == "memory_injection",
        AgentAuditLog.user_id == 999,
    ).all()
    assert len(audits) == 1
    detail = audits[0].result_detail or {}
    if isinstance(detail, str):
        import json
        detail = json.loads(detail)
    assert "stages" in detail
    # 4 stage 都该有记录, 即使 ok=False
    assert set(detail["stages"].keys()) == {
        "conversation", "case_timeline", "directives", "hybrid"
    }
    # case_timeline 应该是 no_findings (因为 findings=None)
    assert detail["stages"]["case_timeline"]["error"] == "no_findings"
