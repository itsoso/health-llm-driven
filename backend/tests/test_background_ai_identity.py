"""Background calls bind their owner without borrowing prior consent or quota identity."""
import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from app.services import ai_consent
from app.services.llm import usage_tracker as usage
from tests.test_life_events import _mk_user, _mk_user_message, _MSG_CREATED_UTC
from tests.test_insight_generator import TestLLMPatternMining as PatternFixtures


@contextmanager
def stale_context():
    bindings = [(usage._caller_ctx, "previous-job"), (usage._user_id_ctx, 99999),
                (usage._user_is_admin_ctx, True), (usage._run_id_ctx, "previous-run"),
                (usage._usage_capture_ctx, []), (usage._api_usage_ctx, {"old": True}),
                (usage._recovery_depth_ctx, 1)]
    tokens = [(var, var.set(value)) for var, value in bindings]
    try:
        with ai_consent.ai_user_scope(99999):
            yield bindings
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def assert_job_context(user_id, caller):
    assert usage.get_caller_user_id() == user_id
    assert ai_consent._user_ctx.get() == user_id
    assert usage._caller_ctx.get() == caller
    assert usage._user_is_admin_ctx.get() is None
    assert usage._run_id_ctx.get() is None
    assert usage._usage_capture_ctx.get() is None
    assert usage._api_usage_ctx.get() is None
    assert usage._recovery_depth_ctx.get() == 0


@pytest.mark.parametrize("failure", [False, True])
def test_background_scope_restores_all_context_on_success_or_error(failure):
    with stale_context() as bindings:
        try:
            with usage.background_ai_scope("job", user_id=7):
                assert_job_context(7, "job")
                with usage.background_ai_scope("nested", user_id=8):
                    assert_job_context(8, "nested")
                assert_job_context(7, "job")
                if failure:
                    raise RuntimeError("synthetic failure")
        except RuntimeError:
            assert failure
        for var, value in bindings:
            assert var.get() == value
        assert ai_consent._user_ctx.get() == 99999


@pytest.mark.parametrize("user_id", [None, True, False, 0, -1, "7"])
def test_background_scope_rejects_invalid_identity(user_id):
    with pytest.raises(ValueError):
        with usage.background_ai_scope("job", user_id=user_id):
            pytest.fail("invalid owner entered background scope")


@pytest.mark.parametrize("entry", ["life", "insight", "insight_running_loop"])
@pytest.mark.parametrize("permission", ["accepted", "missing", "revoked", "stale", "inactive", "unapproved", "unknown_host", "cookie_subject_missing"])
def test_real_background_entry_checks_its_owner_consent(db, monkeypatch, entry, permission):
    if entry == "life":
        user = _mk_user(db)
        msg = _mk_user_message(db, user.id, "synthetic trip", _MSG_CREATED_UTC)
    else:
        user = PatternFixtures()._seed_data(db)
    uid = user.id
    user.is_approved = permission != "unapproved"
    db.commit()
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    if permission != "missing":
        ai_consent.update_ai_consent(db, uid, True, ai_consent.POLICY_VERSION)
    if permission == "revoked":
        ai_consent.update_ai_consent(db, uid, False, ai_consent.POLICY_VERSION)
    if permission == "stale":
        monkeypatch.setattr(ai_consent, "POLICY_VERSION", "next-policy")
    if permission == "inactive":
        user.is_active = False
        db.commit()
    checked, sent = [], []

    async def chat(**kwargs):
        caller = "life_event.extractor" if entry == "life" else "insight.llm_pattern_mining"
        assert_job_context(uid, caller)
        checked.append(uid)
        host = "unknown.example" if permission == "unknown_host" else "dashscope.aliyuncs.com"
        ai_consent.require_ai_consent(destination=f"https://{host}/api/v1")
        sent.append(uid)
        return '{"events": [], "found_pattern": false}'

    provider = SimpleNamespace(chat=chat)
    monkeypatch.setattr("app.services.llm.factory.create_provider_for_model_id", lambda *a: provider)
    monkeypatch.setattr("app.services.llm.factory.get_llm_provider", lambda: provider)
    monkeypatch.setattr("app.services.llm.get_llm_provider", lambda: provider)

    def invoke():
        if entry == "life":
            from app.services.life_event_extractor import extract_life_events_from_message
            return extract_life_events_from_message(db, uid, msg.id)
        from app.services.insight_generator import _gen_llm_pattern_mining
        return _gen_llm_pattern_mining(db, uid)

    async def invoke_with_loop():
        return invoke()

    cookie_token = ai_consent._cookie_subject_missing.set(permission == "cookie_subject_missing")
    try:
        with stale_context() as bindings:
            if entry == "life" and permission != "accepted":
                with pytest.raises(HTTPException):
                    invoke()
            elif entry == "insight_running_loop":
                asyncio.run(invoke_with_loop())
            else:
                invoke()
            assert checked == [uid], "guard must be reached with the correct context"
            assert sent == ([uid] if permission == "accepted" else [])
            for var, value in bindings:
                assert var.get() == value
    finally:
        ai_consent._cookie_subject_missing.reset(cookie_token)


def test_life_event_foreign_message_never_reaches_provider(db, monkeypatch):
    from app.services.life_event_extractor import extract_life_events_from_message
    user, other = _mk_user(db), _mk_user(db)
    msg = _mk_user_message(db, other.id, "synthetic trip", _MSG_CREATED_UTC)
    def forbidden(*args):
        pytest.fail("foreign message reached provider construction")
    monkeypatch.setattr("app.services.llm.factory.get_llm_provider", forbidden)
    monkeypatch.setattr("app.services.llm.factory.create_provider_for_model_id", forbidden)
    assert extract_life_events_from_message(db, user.id, msg.id)["created"] == 0


@pytest.mark.asyncio
async def test_concurrent_background_jobs_keep_distinct_owners():
    ready, release = asyncio.Event(), asyncio.Event()

    async def first():
        with usage.background_ai_scope("first", user_id=7):
            ready.set()
            await release.wait()
            assert_job_context(7, "first")

    async def second():
        await ready.wait()
        with usage.background_ai_scope("second", user_id=8):
            assert_job_context(8, "second")
            release.set()

    with stale_context() as bindings:
        await asyncio.gather(first(), second())
        for var, value in bindings:
            assert var.get() == value


def test_background_scope_does_not_erase_cookie_session_guard(db, monkeypatch):
    user = _mk_user(db)
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    ai_consent.update_ai_consent(db, user.id, True, ai_consent.POLICY_VERSION)
    token = ai_consent._cookie_subject_missing.set(True)
    try:
        with usage.background_ai_scope("job", user_id=user.id), pytest.raises(HTTPException) as denied:
            ai_consent.require_ai_consent(destination="https://dashscope.aliyuncs.com/api/v1")
        assert denied.value.status_code == 409
    finally:
        ai_consent._cookie_subject_missing.reset(token)


@pytest.mark.parametrize("entry", ["life", "insight"])
def test_provider_failure_is_visible_without_logging_payload(db, monkeypatch, caplog, entry):
    marker = "synthetic-private-upstream-payload"
    async def chat(**kwargs):
        raise RuntimeError(marker)
    provider = SimpleNamespace(chat=chat)
    monkeypatch.setattr("app.services.llm.factory.create_provider_for_model_id", lambda *a: provider)
    monkeypatch.setattr("app.services.llm.factory.get_llm_provider", lambda: provider)
    monkeypatch.setattr("app.services.llm.get_llm_provider", lambda: provider)
    with stale_context() as bindings:
        if entry == "life":
            from app.services.life_event_extractor import extract_life_events_from_message
            user = _mk_user(db)
            msg = _mk_user_message(db, user.id, "synthetic trip", _MSG_CREATED_UTC)
            with pytest.raises(RuntimeError, match=marker):
                extract_life_events_from_message(db, user.id, msg.id)
        else:
            from app.services.insight_generator import _gen_llm_pattern_mining
            user = PatternFixtures()._seed_data(db)
            assert _gen_llm_pattern_mining(db, user.id) is None
        for var, value in bindings:
            assert var.get() == value
    assert "RuntimeError" in caplog.text
    assert marker not in caplog.text
