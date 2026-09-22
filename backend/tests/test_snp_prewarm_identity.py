"""SNP details must use the owner's live consent and bounded prewarm attempts."""
import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from app.services import ai_consent, genetic_report
from app.services.llm.providers.openai_provider import OpenAIProvider
from app.utils.redis_cache import RedisCache
from tests.test_background_ai_identity import assert_job_context, stale_context
from tests.test_genetic_report import _make_user, _make_profile, _make_variant


@pytest.fixture
def cache(monkeypatch):
    values, writes = {}, []
    monkeypatch.setattr(RedisCache, "get", lambda key: values.get(key))
    def put(key, value, ttl):
        values[key] = value
        writes.append((key, ttl))
        return True
    monkeypatch.setattr(RedisCache, "set", put)
    monkeypatch.setattr("app.twin.build_twin", lambda *a: SimpleNamespace(
        labs=SimpleNamespace(flagged_abnormal=[]),
        supplement=SimpleNamespace(active_supplements=[]),
        chronic=SimpleNamespace(active_conditions=[])))
    return values, writes


def seed(db):
    user = _make_user(db)[0]
    profile = _make_profile(db, user.id)
    _make_variant(db, profile, "MTHFR", "C677T", genotype="CT")
    return user, profile


@pytest.mark.parametrize("running_loop", [False, True])
@pytest.mark.parametrize("permission", ["accepted", "missing", "revoked", "inactive", "unapproved", "stale", "cookie", "unknown_host"])
def test_real_snp_provider_guard(db, monkeypatch, cache, running_loop, permission):
    user, _ = seed(db)
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    if permission != "missing":
        ai_consent.update_ai_consent(db, user.id, True, ai_consent.POLICY_VERSION)
    if permission == "revoked":
        ai_consent.update_ai_consent(db, user.id, False, ai_consent.POLICY_VERSION)
    if permission == "inactive":
        user.is_active = False
    if permission == "unapproved":
        user.is_approved = False
    db.commit()
    if permission == "stale":
        monkeypatch.setattr(ai_consent, "POLICY_VERSION", "next-policy")
    host = "unknown.example" if permission == "unknown_host" else "dashscope.aliyuncs.com"
    provider = OpenAIProvider(api_key="test-only", base_url=f"https://{host}/compatible-mode/v1")
    sent = []
    def create(**kwargs):
        assert_job_context(user.id, "genetic.snp_detail")
        sent.append(user.id)
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content='{"headline":"synthetic"}', tool_calls=None))])
    monkeypatch.setattr(provider, "_get_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr("app.services.llm.get_llm_provider", lambda: provider)
    def invoke():
        return genetic_report.get_snp_detail(db, user.id, "rs1801133")
    async def invoke_in_loop():
        return invoke()
    token = ai_consent._cookie_subject_missing.set(permission == "cookie")
    try:
        with stale_context() as bindings:
            result = asyncio.run(invoke_in_loop()) if running_loop else invoke()
            assert sent == ([user.id] if permission == "accepted" else [])
            assert bool(result["actions"]) == (permission == "accepted")
            assert len(cache[1]) == (1 if permission == "accepted" else 0)
            for var, value in bindings:
                assert var.get() == value
    finally:
        ai_consent._cookie_subject_missing.reset(token)


@pytest.mark.parametrize("foreign_variant", [False, True])
def test_no_owned_hit_never_builds_prompt_or_provider(db, monkeypatch, cache, foreign_variant):
    owner, profile = seed(db)
    other = _make_user(db)[0]
    if foreign_variant:
        # Imported row with mismatched owner must not be trusted via profile alone.
        from app.models.genetic_data import GeneticVariant
        db.query(GeneticVariant).filter_by(profile_id=profile.id).update({"user_id": other.id})
        db.commit()
        target = owner.id
    else:
        target = other.id
    def forbidden(*args):
        pytest.fail("unowned SNP reached model preparation")
    monkeypatch.setattr(genetic_report, "_build_snp_detail_prompt", forbidden)
    result = genetic_report.get_snp_detail(db, target, "rs1801133")
    assert result["user"]["hit"] is False
    assert result["actions"] is None
    assert cache[1] == []


def test_cache_is_owner_scoped_and_has_24h_ttl(db, monkeypatch, cache):
    first, _ = seed(db)
    second, _ = seed(db)
    calls = []
    async def chat(**kwargs):
        from app.services.llm.usage_tracker import get_caller_user_id
        calls.append(get_caller_user_id())
        return '{"headline":"synthetic"}'
    monkeypatch.setattr("app.services.llm.get_llm_provider", lambda: SimpleNamespace(chat=chat))
    for uid in (first.id, first.id, second.id):
        assert genetic_report.get_snp_detail(db, uid, "rs1801133")["actions"]
    assert calls == [first.id, second.id]
    assert len(cache[0]) == 2
    assert all(ttl == 86400 for _, ttl in cache[1])


def test_sequential_users_and_revocation_recheck_real_provider(db, monkeypatch, cache):
    first, _ = seed(db)
    second, _ = seed(db)
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    ai_consent.update_ai_consent(db, first.id, True, ai_consent.POLICY_VERSION)
    provider = OpenAIProvider(api_key="test-only", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    sent = []
    def create(**kwargs):
        from app.services.llm.usage_tracker import get_caller_user_id
        sent.append(get_caller_user_id())
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content='{"headline":"synthetic"}', tool_calls=None))])
    monkeypatch.setattr(provider, "_get_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr("app.services.llm.get_llm_provider", lambda: provider)
    with stale_context():
        assert genetic_report.get_snp_detail(db, first.id, "rs1801133")["actions"]
        assert genetic_report.get_snp_detail(db, second.id, "rs1801133")["actions"] is None
        ai_consent.update_ai_consent(db, first.id, False, ai_consent.POLICY_VERSION)
        cache[0].clear()  # Expiry/eviction must require current consent, not cached identity.
        assert genetic_report.get_snp_detail(db, first.id, "rs1801133")["actions"] is None
    assert sent == [first.id]


@pytest.mark.parametrize("raw", ["[]", "{}", "null", "not json"])
def test_invalid_model_actions_are_not_cached(db, monkeypatch, cache, raw):
    user, _ = seed(db)
    async def chat(**kwargs):
        return raw
    monkeypatch.setattr("app.services.llm.get_llm_provider", lambda: SimpleNamespace(chat=chat))
    assert genetic_report.get_snp_detail(db, user.id, "rs1801133")["actions"] is None
    assert not cache[1]


def test_failure_is_not_cached_and_does_not_log_payload(db, monkeypatch, cache, caplog):
    user, _ = seed(db)
    async def chat(**kwargs):
        raise RuntimeError("synthetic-private-genotype-payload")
    monkeypatch.setattr("app.services.llm.get_llm_provider", lambda: SimpleNamespace(chat=chat))
    assert genetic_report.get_snp_detail(db, user.id, "rs1801133")["actions"] is None
    assert not cache[1]
    assert "RuntimeError" in caplog.text
    assert "synthetic-private-genotype-payload" not in caplog.text


@pytest.mark.parametrize("outcome", ["empty", "exception", "success"])
def test_prewarm_counts_only_actions_and_limits_all_attempts(db, monkeypatch, outcome, caplog):
    from app.tasks import snp_prewarm
    user, profile = seed(db)
    _make_variant(db, profile, "ALDH2", "酒精代谢")
    _make_variant(db, profile, "VDR", "维生素D受体")
    monkeypatch.setattr(snp_prewarm, "SessionLocal", lambda: db)
    monkeypatch.setattr(snp_prewarm, "PREWARM_TOP_N", 2)
    calls = []
    def detail(db, uid, rsid, *, require_cached=False):
        assert require_cached is True
        calls.append((uid, rsid))
        if outcome == "exception":
            raise RuntimeError("synthetic-private-prewarm-payload")
        return {"actions": {"headline": "synthetic"} if outcome == "success" else None}
    monkeypatch.setattr(genetic_report, "get_snp_detail", detail)
    result = snp_prewarm._impl(force_user_ids=[user.id])
    assert len(calls) == 2
    assert result["attempted"] == 2
    assert result["failed"] == (0 if outcome == "success" else 2)
    assert result["snps"] == (2 if outcome == "success" else 0)
    assert "synthetic-private-prewarm-payload" not in caplog.text


def test_prewarm_rejects_variant_with_foreign_owner(db, monkeypatch):
    from app.models.genetic_data import GeneticVariant
    from app.tasks import snp_prewarm
    owner, profile = seed(db)
    other = _make_user(db)[0]
    db.query(GeneticVariant).filter_by(profile_id=profile.id).update({"user_id": other.id})
    db.commit()
    monkeypatch.setattr(snp_prewarm, "SessionLocal", lambda: db)
    def forbidden(*args):
        pytest.fail("foreign variant entered prewarm")
    monkeypatch.setattr(genetic_report, "get_snp_detail", forbidden)
    result = snp_prewarm._impl(force_user_ids=[owner.id])
    assert result["attempted"] == 0
    assert result["snps"] == 0


@pytest.mark.parametrize("write_result", ["false", "exception", "success"])
def test_prewarm_counts_only_confirmed_cache_writes(db, monkeypatch, cache, write_result):
    from app.tasks import snp_prewarm
    user, _ = seed(db)
    monkeypatch.setattr(snp_prewarm, "SessionLocal", lambda: db)
    async def chat(**kwargs):
        return '{"headline":"synthetic"}'
    monkeypatch.setattr("app.services.llm.get_llm_provider", lambda: SimpleNamespace(chat=chat))
    def write(*args, **kwargs):
        if write_result == "exception":
            raise RuntimeError("synthetic cache unavailable")
        return write_result == "success"
    monkeypatch.setattr(RedisCache, "set", write)
    result = snp_prewarm._impl(force_user_ids=[user.id])
    assert result == {"users": 1, "snps": int(write_result == "success"),
                      "attempted": 1, "failed": int(write_result != "success"), "failed_users": 0}


@pytest.mark.parametrize("write_result", [False, "exception"])
def test_normal_detail_preserves_actions_when_cache_write_fails(db, monkeypatch, cache, write_result):
    user, _ = seed(db)
    async def chat(**kwargs):
        return '{"headline":"synthetic"}'
    monkeypatch.setattr("app.services.llm.get_llm_provider", lambda: SimpleNamespace(chat=chat))
    def write(*args, **kwargs):
        if write_result == "exception":
            raise RuntimeError("synthetic cache unavailable")
        return write_result
    monkeypatch.setattr(RedisCache, "set", write)
    assert genetic_report.get_snp_detail(db, user.id, "rs1801133")["actions"] == {"headline": "synthetic"}


@pytest.mark.parametrize("cached_actions", [{"headline": "synthetic"}, {}, [], ["invalid"], "invalid"])
def test_prewarm_requires_valid_cached_actions(db, monkeypatch, cache, cached_actions):
    from app.tasks import snp_prewarm
    user, _ = seed(db)
    cache[0][genetic_report._snp_cache_key(user.id, "rs1801133", "CT")] = {"actions": cached_actions}
    monkeypatch.setattr(snp_prewarm, "SessionLocal", lambda: db)
    calls = []
    async def chat(**kwargs):
        calls.append(True)
        raise RuntimeError("synthetic model unavailable")
    monkeypatch.setattr("app.services.llm.get_llm_provider", lambda: SimpleNamespace(chat=chat))
    result = snp_prewarm._impl(force_user_ids=[user.id])
    valid = isinstance(cached_actions, dict) and bool(cached_actions)
    assert calls == ([] if valid else [True])
    assert result["snps"] == int(valid)
    assert result["failed"] == int(not valid)


def test_prewarm_scan_failure_has_separate_user_count(db, monkeypatch, caplog):
    from app.tasks import snp_prewarm
    monkeypatch.setattr(snp_prewarm, "SessionLocal", lambda: db)
    def fail(*args):
        raise RuntimeError("synthetic-private-scan-payload")
    monkeypatch.setattr(genetic_report, "_resolve_active_profile", fail)
    result = snp_prewarm._impl(force_user_ids=[123])
    assert result == {"users": 1, "snps": 0, "attempted": 0, "failed": 0, "failed_users": 1}
    assert "synthetic-private-scan-payload" not in caplog.text


def test_prewarm_zero_users_has_complete_counters(db, monkeypatch):
    from app.tasks import snp_prewarm
    monkeypatch.setattr(snp_prewarm, "SessionLocal", lambda: db)
    monkeypatch.setattr(snp_prewarm, "_active_user_ids", lambda *args: [])
    assert snp_prewarm._impl() == {"users": 0, "snps": 0, "attempted": 0, "failed": 0, "failed_users": 0}
