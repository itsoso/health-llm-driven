import pytest


@pytest.mark.parametrize(
    "job_success,job_status,expected",
    [
        (True, "completed", "已返回成功"),
        (False, "failed", "任务失败"),
        (False, "unknown", "没有核实"),
    ],
)
def test_merged_reply_separates_job_from_historical_account_status(
    db, job_success, job_status, expected
):
    from app.services.agent_executor import AgentExecutor
    from tests.test_agent_read_plan_binding import snapshot
    from app.services.agent_kernel.daily_read_plan import resolve_daily_read_plan

    ex = AgentExecutor(db)
    ex._current_user_id = 41
    ex._current_turn_user_message = "昨天晚上我睡得怎么样？佳明的数据同步完了吗？"
    ex._agent_kernel_snapshot = snapshot(ex._current_turn_user_message)
    ex._turn_daily_read_plan = resolve_daily_read_plan(
        ex._agent_kernel_snapshot.envelope.text, ex._agent_kernel_reference_now()
    )
    ex._turn_daily_read_results = {
        "sleep": {"status": "verified", "evidence_kind": "read_result"}
    }
    ex._turn_daily_read_payloads = {
        "sleep": {
            "dimension": "sleep",
            "records": [
                {
                    "record_date": "2026-07-17",
                    "total_sleep_duration": 420,
                    "sleep_score": 80,
                }
            ],
            "sync_check": {
                "lookup_status": "available",
                "bound": True,
                "sync_enabled": True,
                "credentials_valid": True,
                "requires_mfa": False,
                "error_count": 0,
                "last_sync_at": "2026-07-16T08:00:00+08:00",
            },
        }
    }
    ex._turn_sync_status_result = {
        "version": "garmin-sync-status.v1",
        "status": job_status,
        "job_success_verified": job_success,
        "submission_status": "unverified",
    }
    text = ex._trusted_read_summary()
    assert "7小时" in text
    assert "80" in text
    assert expected in text
    assert "2026-07-16" in text
    if job_status in {"completed", "failed"}:
        assert "仍无法确认" not in text


def test_verified_job_observation_can_answer_status_when_account_lookup_fails():
    from app.services.agent_daily_read_execution import sync_status_goal

    result = sync_status_goal(
        {
            "sync_check": {"lookup_status": "failed"},
            "sync_job": {
                "version": "garmin-sync-status.v1",
                "job_id": "873a4765-48b5-49d5-a989-fcc234ba3e88",
                "status": "completed",
                "job_success_verified": True,
            },
        }
    )
    assert result["status"] == "verified"


def test_account_success_never_verifies_job_execution():
    from app.services.agent_daily_read_execution import sync_status_goal

    result = sync_status_goal(
        {"sync_check": {"lookup_status": "available", "bound": False}}
    )
    assert result["kind"] == "query"
    assert result["evidence_kind"] == "read_result"


def test_four_domain_disclosure_does_not_claim_only_diet_and_sleep():
    from app.services.agent_composed_read_completion import read_scope_notices
    from app.services.agent_kernel.read_task_scope import OwnedReadScope

    scope = OwnedReadScope(
        queries=(),
        limitations=("default_recent_7_days", "mood_not_queried", "work_not_queried"),
    )
    text = "\n".join(read_scope_notices(scope))
    assert "默认查询最近7天" in text
    assert "情绪背景未查询" in text
    assert "工作背景未查询" in text
    assert "仅覆盖饮食" not in text
