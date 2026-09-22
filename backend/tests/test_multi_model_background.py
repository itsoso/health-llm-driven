"""Owner-scoped analysis must not turn rejected/failed output into success."""
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.daily_health import GarminData, WorkoutRecord, WorkoutAnalysisResult
from app.services import ai_consent
from app.services.multi_model_analyze import MultiModelAnalyzeClient
from app.services.post_run_analyze import PostRunAnalyzeService
from tests.test_background_ai_identity import stale_context, assert_job_context
from tests.test_life_events import _mk_user
from app.utils.timezone import get_china_today


@pytest.mark.asyncio
@pytest.mark.parametrize("permission", ["accepted", "missing", "revoked", "stale", "inactive", "cookie", "unknown_host"])
async def test_multi_model_owner_fresh_consent_and_restoration(db, monkeypatch, permission):
    user = _mk_user(db)
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    allowed = permission == "accepted"
    if permission != "missing":
        ai_consent.update_ai_consent(db, user.id, permission != "revoked", ai_consent.POLICY_VERSION)
    if permission == "stale":
        monkeypatch.setattr(ai_consent, "POLICY_VERSION", "next-policy")
    if permission == "inactive":
        user.is_active = False
        db.commit()
    sent, checked = [], []
    async def analyze(prompt):
        assert_job_context(user.id, "multi_model_analyze")
        checked.append(True)
        host = "unknown.example" if permission == "unknown_host" else "dashscope.aliyuncs.com"
        ai_consent.require_ai_consent(destination=f"https://{host}/api/v1")
        sent.append(prompt)
        return {"status": "completed", "aggregation": "synthetic summary", "model_results": []}
    monkeypatch.setattr("app.services.llm.get_llm_provider", lambda: SimpleNamespace(multi_model_analyze=analyze))
    token = ai_consent._cookie_subject_missing.set(permission == "cookie")
    try:
        with stale_context() as bindings:
            result = await MultiModelAnalyzeClient().analyze("synthetic input", user_id=user.id)
            assert result["status"] == ("completed" if allowed else "error")
            for var, value in bindings:
                assert var.get() == value
    finally:
        ai_consent._cookie_subject_missing.reset(token)
    assert checked == [True]
    assert len(sent) == int(allowed)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [None, {}, {"status": "error", "aggregation": "synthetic-private"},
    {"status": "partial", "aggregation": "synthetic-private"},
    {"status": "completed", "aggregation": " "},
    {"status": "completed", "aggregation": {"private": "payload"}}])
async def test_multi_model_rejects_nonpublishable_output(monkeypatch, bad):
    provider = SimpleNamespace(multi_model_analyze=AsyncMock(return_value=bad))
    monkeypatch.setattr("app.services.llm.get_llm_provider", lambda: provider)
    result = await MultiModelAnalyzeClient().analyze("synthetic", user_id=7)
    assert result["status"] == "error"
    assert result["model_results"] == []
    assert "synthetic-private" not in str(result)


@pytest.mark.asyncio
async def test_default_provider_error_does_not_log_or_return_payload(caplog):
    from app.services.llm.base import LLMProvider
    class BrokenProvider(LLMProvider):
        async def chat(self, *args, **kwargs):
            raise RuntimeError("synthetic-private-upstream")
        async def chat_with_vision(self, *args, **kwargs):
            return "unused"
    result = await BrokenProvider().multi_model_analyze("synthetic")
    assert result["status"] == "error"
    assert "synthetic-private-upstream" not in str(result) + caplog.text


def workout(db, uid):
    row = WorkoutRecord(user_id=uid, workout_date=get_china_today(), workout_type="running",
                        start_time=datetime.now(timezone.utc), duration_seconds=1200)
    db.add(row)
    db.commit()
    return row


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["full", "brief"])
async def test_post_run_failed_analysis_never_reports_success(db, monkeypatch, fmt):
    user = _mk_user(db)
    row = workout(db, user.id)
    svc = PostRunAnalyzeService(db)
    monkeypatch.setattr(svc, "_sync_garmin", AsyncMock(return_value={"status": "no_new_data"}))
    async def failed(prompt, *, user_id=None):
        return {"status": "error", "aggregation": "synthetic-private", "model_results": []}
    monkeypatch.setattr(svc.analyzer, "analyze", failed)
    result = await svc.analyze(user.id, format=fmt)
    assert result["success"] is False
    assert "synthetic-private" not in str(result)
    assert db.query(WorkoutAnalysisResult).filter_by(workout_id=row.id).count() == 0


@pytest.mark.asyncio
async def test_post_run_passes_owner_and_requires_saved_result(db, monkeypatch):
    user = _mk_user(db)
    workout(db, user.id)
    svc = PostRunAnalyzeService(db)
    monkeypatch.setattr(svc, "_sync_garmin", AsyncMock(return_value={"status": "no_new_data"}))
    seen = []
    async def completed(prompt, *, user_id=None):
        seen.append(user_id)
        return {"status": "completed", "aggregation": "synthetic summary", "model_results": []}
    monkeypatch.setattr(svc.analyzer, "analyze", completed)
    monkeypatch.setattr(svc, "_save_analysis_result", lambda *a: False)
    result = await svc.analyze(user.id)
    assert result["success"] is False
    assert seen == [user.id]


@contextmanager
def session_scope(db):
    yield db


@pytest.mark.parametrize("completed", [False, True])
def test_daily_insight_only_pushes_complete_analysis_with_owner(db, monkeypatch, completed):
    from app.tasks import notifications as task
    user = _mk_user(db)
    today = get_china_today()
    db.add(GarminData(user_id=user.id, record_date=today, steps=6000))
    workout(db, user.id)  # actual workout branch, not just a no-workout fixture
    seen, pushed = [], []
    async def analyze(self, prompt, *, user_id=None):
        seen.append(user_id)
        return {"status": "completed" if completed else "error", "aggregation": "synthetic summary"}
    async def send(self, **kwargs):
        pushed.append(kwargs)
        return {"success": True}
    monkeypatch.setattr(task, "SessionLocal", lambda: session_scope(db))
    monkeypatch.setattr(MultiModelAnalyzeClient, "analyze", analyze)
    monkeypatch.setattr(task.PushService, "send_notification", send)
    result = task._generate_daily_insight_for_user(user.id, today)
    assert seen == [user.id]
    assert len(pushed) == int(completed)
    assert result["status"] == ("completed" if completed else "error")


def test_daily_rollup_does_not_count_skips_or_failures(db, monkeypatch):
    from app.tasks import notifications as task
    users = [_mk_user(db) for _ in range(3)]
    for user in users:
        db.add(GarminData(user_id=user.id, record_date=get_china_today(), steps=6000))
    db.commit()
    outcomes = {users[0].id: "completed", users[1].id: "error", users[2].id: "skipped"}
    monkeypatch.setattr(task, "SessionLocal", lambda: session_scope(db))
    monkeypatch.setattr(task, "_generate_daily_insight_for_user", lambda uid, day: {"status": outcomes[uid]})
    result = task.generate_daily_insights_for_all.run()
    assert result["analyzed_count"] == 1
    assert result["failed_count"] == 1
    assert result["skipped_count"] == 1


@pytest.mark.parametrize("completed", [False, True])
def test_auto_workout_does_not_publish_failed_analysis(db, monkeypatch, completed):
    from app.tasks import garmin_sync as task
    from app.services.notification.push_service import PushService
    user = _mk_user(db)
    row = workout(db, user.id)
    # Historical failed rows must not prevent the current requested analysis.
    db.add(WorkoutAnalysisResult(user_id=user.id, workout_id=row.id, source="multi_model",
                                status="error", aggregation="synthetic old failure"))
    db.commit()
    seen, pushed, episodes = [], [], []
    async def analyze(self, prompt, *, user_id=None):
        seen.append(user_id)
        return {"status": "completed" if completed else "error", "aggregation": "synthetic summary", "model_results": []}
    async def send(self, **kwargs):
        pushed.append(kwargs)
        return {"success": True}
    monkeypatch.setattr(task, "SessionLocal", lambda: session_scope(db))
    monkeypatch.setattr(MultiModelAnalyzeClient, "analyze", analyze)
    monkeypatch.setattr(PushService, "send_notification", send)
    monkeypatch.setattr(task, "_maybe_create_run_episode", lambda *a: episodes.append(True))
    result = task.auto_analyze_workout.run(user.id, row.id)
    assert seen == [user.id]
    assert result["status"] == ("success" if completed else "error")
    assert len(pushed) == len(episodes) == int(completed)


@pytest.mark.parametrize("aggregation,sensitive", [("今天步数达标，注意休息。", False),
    ("建议继续服用二甲双胍并控制主食。", True)])
def test_auto_workout_push_privacy_and_delivery_status(db, monkeypatch, aggregation, sensitive):
    from app.tasks import garmin_sync as task
    from app.services.notification.push_service import PushService
    user = _mk_user(db)
    row = workout(db, user.id)
    async def analyze(self, prompt, *, user_id):
        return {"status": "completed", "aggregation": aggregation, "model_results": []}
    pushed = []
    async def send(self, **kwargs):
        pushed.append(kwargs)
        return {"success": False, "reason": "synthetic delivery failure"}
    monkeypatch.setattr(task, "SessionLocal", lambda: session_scope(db))
    monkeypatch.setattr(MultiModelAnalyzeClient, "analyze", analyze)
    monkeypatch.setattr(PushService, "send_notification", send)
    monkeypatch.setattr(task, "_maybe_create_run_episode", lambda *a: None)
    result = task.auto_analyze_workout.run(user.id, row.id)
    assert result["status"] == "success"  # Analysis persisted, delivery is separate.
    assert result["notification_status"] == "failed"
    assert len(pushed) == 1
    if sensitive:
        assert "二甲双胍" not in pushed[0]["content"]
        assert pushed[0]["content"] == "你的运动分析已生成，点击查看详情。"
    else:
        assert pushed[0]["content"] == aggregation


def test_post_run_save_failure_rolls_back_and_redacts_error(db, monkeypatch, caplog):
    user = _mk_user(db)
    row = workout(db, user.id)
    def broken_commit():
        raise RuntimeError("synthetic-private-db-payload")
    monkeypatch.setattr(db, "commit", broken_commit)
    assert PostRunAnalyzeService(db)._save_analysis_result(user.id, row.id, "synthetic", {
        "status": "completed", "aggregation": "synthetic", "model_results": []}) is False
    assert db.query(WorkoutAnalysisResult).count() == 0
    assert "synthetic-private-db-payload" not in caplog.text


def test_auto_workout_foreign_owner_never_reaches_analysis(db, monkeypatch):
    from app.tasks import garmin_sync as task
    first, second = _mk_user(db), _mk_user(db)
    row = workout(db, first.id)
    async def forbidden(*args, **kwargs):
        pytest.fail("foreign workout reached model")
    monkeypatch.setattr(task, "SessionLocal", lambda: session_scope(db))
    monkeypatch.setattr(MultiModelAnalyzeClient, "analyze", forbidden)
    assert task.auto_analyze_workout.run(second.id, row.id) == {"status": "skipped", "reason": "not_found"}


@pytest.mark.parametrize("endpoint", ["post-run-analyze", "post-run-analyze-siri"])
@pytest.mark.parametrize("completed", [False, True])
def test_authenticated_post_run_api_keeps_success_and_failure_contract(db, client, monkeypatch, endpoint, completed):
    from tests.conftest import create_authenticated_user
    from app.services.llm.usage_tracker import get_caller_user_id
    user, token = create_authenticated_user(db)
    row = workout(db, user.id)
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    ai_consent.update_ai_consent(db, user.id, True, ai_consent.POLICY_VERSION)
    monkeypatch.setattr(PostRunAnalyzeService, "_sync_garmin", AsyncMock(return_value={"status": "no_new_data"}))
    owners = []
    async def analyze(prompt):
        ai_consent.require_ai_consent(destination="https://dashscope.aliyuncs.com/api/v1")
        owners.append(get_caller_user_id())
        return {"status": "completed" if completed else "error",
                "aggregation": "synthetic summary" if completed else "synthetic-private-error", "model_results": []}
    monkeypatch.setattr("app.services.llm.get_llm_provider", lambda: SimpleNamespace(multi_model_analyze=analyze))
    response = client.post(f"/api/v1/workout/{endpoint}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["success"] is completed
    assert owners == [user.id]
    assert "synthetic-private-error" not in response.text
    assert db.query(WorkoutAnalysisResult).filter_by(workout_id=row.id).count() == int(completed)
