"""Starter chip answer pre-generation (rank7) tests.

Safety review points (roadmap):
  1. Hash-mismatch fail-closed — a data change between pregen and tap → live turn,
     the stored answer is discarded/ignored (never served on changed data).
  2. Pregen answers go through the SAME turn pipeline — enforced by the read-only
     tool guard at the executor's single dispatch choke (no write ever executes).
  3. Flag off → byte-identical behavior (serve returns None, enqueue no-ops).
  4. Token budget — dedupe: a single attempt per (user, starter) while in-flight.
"""
import asyncio
import fnmatch
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models.user import User
from app.services import starter_pregen
from app.services import starter_pregen_producer as spp


# ── Fake Redis (deterministic, no live Redis dependency) ─────────────────


class _FakeRedis:
    def __init__(self):
        self.store: dict = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value
        return True

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    def delete(self, *keys):
        n = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                n += 1
        return n

    def scan_iter(self, match=None):
        for k in list(self.store.keys()):
            if match is None or fnmatch.fnmatch(k, match):
                yield k

    def sadd(self, key, *members):
        s = self.store.setdefault(key, set())
        before = len(s)
        s.update(members)
        return len(s) - before

    def smembers(self, key):
        return set(self.store.get(key, set()))

    def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    def expire(self, key, ttl):
        return True


@pytest.fixture
def fake_redis(monkeypatch):
    fr = _FakeRedis()
    monkeypatch.setattr(starter_pregen, "_redis", lambda: fr)
    return fr


@pytest.fixture
def pregen_on(monkeypatch):
    monkeypatch.setattr(settings, "starter_pregen_enabled", True)
    monkeypatch.setattr(settings, "starter_pregen_ttl_seconds", 900)
    monkeypatch.setattr(settings, "starter_pregen_max_chips", 2)


def _make_user(db, suffix: str = "1") -> User:
    user = User(
        username=f"pregen_{suffix}",
        email=f"pregen_{suffix}@example.com",
        hashed_password="x",
        name=f"Pregen {suffix}",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _now_iso(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat()


def _store_fresh(db, user_id, text, *, sig="H1", model="m1", answer="预生成答案", age=0):
    """Write a pregen entry directly (bypassing production)."""
    starter_pregen.write_pregen(
        user_id,
        text,
        {
            "starter_text": text,
            "signals_hash": sig,
            "model_id": model,
            "generated_at": _now_iso(-age),
            "answer_text": answer,
            "sources_used": ["设备数据"],
            "mode": "agent",
        },
        ttl_seconds=900,
    )


# ── Safety #3: flag off → byte-identical (no serve, no enqueue) ──────────


def test_flag_off_try_serve_returns_none(db, fake_redis):
    user = _make_user(db)
    _store_fresh(db, user.id, "分析我最近的代谢健康")
    # Flag defaults to False — even a stored entry must not serve.
    assert settings.starter_pregen_enabled is False
    out = starter_pregen.try_serve(
        db, user.id, "分析我最近的代谢健康", conversation_id=None, client_turn_id=None
    )
    assert out is None


def test_flag_off_enqueue_noop(db, fake_redis):
    user = _make_user(db)
    calls = []

    class _BG:
        def add_task(self, *a, **k):
            calls.append(a)

    spp.enqueue_pregen(_BG(), db, user.id, ["分析我最近的代谢健康"], "tok")
    assert calls == []


# ── Safety #1: hash-mismatch / model / expiry fail-closed ───────────────


def test_serve_hit_when_fresh(db, fake_redis, pregen_on, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(starter_pregen, "data_signals_hash", lambda d, u: "H1")
    monkeypatch.setattr(starter_pregen, "resolve_effective_model_id", lambda d, u: "m1")
    _store_fresh(db, user.id, "分析我最近的代谢健康", sig="H1", model="m1", answer="你的代谢分析…")

    out = starter_pregen.try_serve(
        db, user.id, "分析我最近的代谢健康", conversation_id=None, client_turn_id=None
    )
    assert out is not None
    events, conv_id, msg_id, reply = out
    assert reply == "你的代谢分析…"
    # Persisted as a normal assistant message tagged pregen_served (honest receipts).
    from app.models.agent_conversation import AgentMessage

    msg = db.query(AgentMessage).filter(AgentMessage.id == msg_id).first()
    assert msg is not None
    assert msg.role == "assistant"
    assert msg.content == "你的代谢分析…"
    assert (msg.meta or {}).get("pregen_served") is True
    assert starter_pregen.get_metrics().get("hit") == 1


def test_hash_mismatch_fails_closed(db, fake_redis, pregen_on, monkeypatch):
    """Data changed between pregen and tap → live turn, stored answer discarded."""
    user = _make_user(db)
    _store_fresh(db, user.id, "分析我最近的代谢健康", sig="H1", model="m1")
    # Underlying data now hashes DIFFERENTLY (a write happened).
    monkeypatch.setattr(starter_pregen, "data_signals_hash", lambda d, u: "H2_CHANGED")
    monkeypatch.setattr(starter_pregen, "resolve_effective_model_id", lambda d, u: "m1")

    out = starter_pregen.try_serve(
        db, user.id, "分析我最近的代谢健康", conversation_id=None, client_turn_id=None
    )
    assert out is None
    assert starter_pregen.get_metrics().get("stale_miss") == 1
    assert starter_pregen.get_metrics().get("hit", 0) == 0


def test_model_switch_fails_closed(db, fake_redis, pregen_on, monkeypatch):
    user = _make_user(db)
    _store_fresh(db, user.id, "分析我最近的代谢健康", sig="H1", model="m1")
    monkeypatch.setattr(starter_pregen, "data_signals_hash", lambda d, u: "H1")
    monkeypatch.setattr(starter_pregen, "resolve_effective_model_id", lambda d, u: "m2_switched")

    out = starter_pregen.try_serve(
        db, user.id, "分析我最近的代谢健康", conversation_id=None, client_turn_id=None
    )
    assert out is None
    assert starter_pregen.get_metrics().get("stale_miss") == 1


def test_expired_entry_fails_closed(db, fake_redis, pregen_on, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(starter_pregen, "data_signals_hash", lambda d, u: "H1")
    monkeypatch.setattr(starter_pregen, "resolve_effective_model_id", lambda d, u: "m1")
    # generated_at is older than the 900s TTL.
    _store_fresh(db, user.id, "分析我最近的代谢健康", sig="H1", model="m1", age=1000)

    out = starter_pregen.try_serve(
        db, user.id, "分析我最近的代谢健康", conversation_id=None, client_turn_id=None
    )
    assert out is None
    assert starter_pregen.get_metrics().get("stale_miss") == 1


def test_non_starter_message_misses_cheaply(db, fake_redis, pregen_on, monkeypatch):
    user = _make_user(db)
    _store_fresh(db, user.id, "分析我最近的代谢健康", sig="H1", model="m1")
    # A message that was never pregen'd → miss on the (user, text) key, and the
    # expensive freshness hash is never even computed.
    called = {"hashed": False}

    def _hash(d, u):
        called["hashed"] = True
        return "H1"

    monkeypatch.setattr(starter_pregen, "data_signals_hash", _hash)
    out = starter_pregen.try_serve(
        db, user.id, "今天天气怎么样", conversation_id=None, client_turn_id=None
    )
    assert out is None
    assert called["hashed"] is False


# ── Safety #1 (write belt) + invalidate ─────────────────────────────────


def test_invalidate_drops_all_user_entries(db, fake_redis, pregen_on):
    user = _make_user(db)
    _store_fresh(db, user.id, "分析我最近的代谢健康")
    _store_fresh(db, user.id, "今天怎么安排训练和恢复")
    assert starter_pregen.read_pregen(user.id, "分析我最近的代谢健康") is not None

    n = starter_pregen.invalidate_pregen(user.id)
    assert n == 2
    assert starter_pregen.read_pregen(user.id, "分析我最近的代谢健康") is None
    assert starter_pregen.read_pregen(user.id, "今天怎么安排训练和恢复") is None


def test_invalidate_noop_when_flag_off(db, fake_redis):
    """C3: with the feature OFF, invalidate touches Redis zero times (no scan)."""
    user = _make_user(db)
    _store_fresh(db, user.id, "分析我最近的代谢健康")
    # Flag defaults False → early return, entry left intact (harmless: try_serve is
    # also gated off, so nothing stale can serve).
    assert starter_pregen.invalidate_pregen(user.id) == 0
    assert starter_pregen.read_pregen(user.id, "分析我最近的代谢健康") is not None


# ── Safety #4: dedupe / single-attempt ──────────────────────────────────


def test_should_generate_dedup(db, fake_redis):
    user = _make_user(db)
    text = "分析我最近的代谢健康"
    # No entry, nothing in flight → generate (claims in-flight).
    assert starter_pregen._should_generate(user.id, text, "H1", "m1") is True
    # In-flight now → second call declines (no retry storm).
    assert starter_pregen._should_generate(user.id, text, "H1", "m1") is False
    # Release + store a FRESH entry → already covered, decline.
    starter_pregen._release_inflight(user.id, text)
    _store_fresh(db, user.id, text, sig="H1", model="m1")
    assert starter_pregen._should_generate(user.id, text, "H1", "m1") is False
    # A STALE stored entry (data moved) does NOT block regenerating the fresh one.
    assert starter_pregen._should_generate(user.id, text, "H2", "m1") is True


def test_enqueue_caps_at_max_chips(db, fake_redis, pregen_on, monkeypatch):
    user = _make_user(db)
    # enqueue lives in the producer module, which imports these names — patch there.
    monkeypatch.setattr(spp, "data_signals_hash", lambda d, u: "H1")
    monkeypatch.setattr(spp, "resolve_effective_model_id", lambda d, u: "m1")
    scheduled = []

    class _BG:
        def add_task(self, fn, *a):
            scheduled.append(a[1])  # starter_text is arg index 1

    spp.enqueue_pregen(
        _BG(), db, user.id,
        ["chip A", "chip B", "chip C", "chip D"],  # 4 served, cap = 2
        "tok",
    )
    assert scheduled == ["chip A", "chip B"]


def test_enqueue_skips_when_no_fingerprint(db, fake_redis, pregen_on, monkeypatch):
    user = _make_user(db)
    # Empty signals_hash = fail-closed → no pregen scheduled.
    monkeypatch.setattr(spp, "data_signals_hash", lambda d, u: "")
    scheduled = []

    class _BG:
        def add_task(self, *a):
            scheduled.append(a)

    spp.enqueue_pregen(_BG(), db, user.id, ["chip A"], "tok")
    assert scheduled == []


# ── Safety #2: read-only executor guard (single dispatch choke) ─────────


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_read_only_turn_blocks_write_tools(db, monkeypatch):
    from app.services import agent_executor as ae
    from app.services.llm import tool_validator

    # Pass-through validation so we reach the read-only guard deterministically.
    monkeypatch.setattr(
        tool_validator, "validate_tool_call",
        lambda tool_name, args, **kw: {"error": None, "data": args},
    )
    ex = ae.AgentExecutor(db)
    ex._current_user_id = 1
    ex._read_only_turn = True
    ex._read_only_turn_write_attempted = False

    executed = {"health_record": False}

    async def _boom(*a, **k):
        executed["health_record"] = True
        return "SHOULD_NOT_RUN"

    monkeypatch.setattr(ex, "_exec_health_record", _boom)

    for tool in ("health_record", "health_manage", "intervention_cycle",
                 "upload_medical_exam_text", "manage_plan"):
        ex._read_only_turn_write_attempted = False
        out = _run(ex._execute_tool(tool, {"record_type": "water", "data": {"amount_ml": 500}}, None))
        assert out.startswith("Error:"), f"{tool} not blocked: {out}"
        assert ex._read_only_turn_write_attempted is True, f"{tool} did not flag write attempt"
    # The write _exec_* was never reached — no side effect.
    assert executed["health_record"] is False


def test_read_only_turn_allows_read_tools(db, monkeypatch):
    from app.services import agent_executor as ae
    from app.services.llm import tool_validator

    monkeypatch.setattr(
        tool_validator, "validate_tool_call",
        lambda tool_name, args, **kw: {"error": None, "data": args},
    )
    ex = ae.AgentExecutor(db)
    ex._current_user_id = 1
    ex._read_only_turn = True
    ex._read_only_turn_write_attempted = False

    async def _ok(args):
        return "OK-READ"

    monkeypatch.setattr(ex, "_exec_knowledge_search", _ok)
    out = _run(ex._execute_tool("knowledge_search", {"query": "x"}, None))
    assert out == "OK-READ"
    assert ex._read_only_turn_write_attempted is False


def test_read_only_turn_cannot_precommit_medication_confirmation_plan(db):
    from app.models.write_intent import WriteIntent
    from app.services import agent_executor as ae
    from app.services.agent_conversation_service import AgentConversationService

    user = _make_user(db, "medication_plan")
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="只读预生成")
    source, _ = svc.save_user_message_once(
        conv.id,
        user.id,
        "记录服用阿奇霉素两粒",
        client_turn_id=None,
    )
    ex = ae.AgentExecutor(db)
    ex._current_user_id = user.id
    ex._current_turn_conversation_id = conv.id
    ex._current_turn_source_message_id = source.id
    ex._read_only_turn = True
    ex._read_only_turn_write_attempted = False

    ex._prepare_medication_tool_plan([{
        "function": {
            "name": "health_record",
            "arguments": {
                "record_type": "medication",
                "data": {
                    "medication_name": "阿奇霉素",
                    "actual_dosage": "2粒",
                },
            },
        },
    }])

    assert ex._read_only_turn_write_attempted is True
    assert "只读" in (ex._turn_medication_tool_preflight_error or "")
    assert db.query(WriteIntent).filter(WriteIntent.user_id == user.id).count() == 0


def test_live_turn_unaffected_by_guard(db, monkeypatch):
    """read_only_turn False (default live turn) → guard never fires."""
    from app.services import agent_executor as ae
    from app.services.llm import tool_validator

    monkeypatch.setattr(
        tool_validator, "validate_tool_call",
        lambda tool_name, args, **kw: {"error": None, "data": args},
    )
    ex = ae.AgentExecutor(db)
    ex._current_user_id = 1
    ex._current_turn_user_message = "记录喝水500ml"
    # _read_only_turn defaults False from __init__.
    assert ex._read_only_turn is False

    reached = {"health_record": False}

    async def _rec(base, headers, args):
        reached["health_record"] = True
        return "记录成功"

    monkeypatch.setattr(ex, "_exec_health_record", _rec)
    out = _run(ex._execute_tool("health_record", {"record_type": "water", "data": {"amount_ml": 500}}, None))
    assert reached["health_record"] is True
    assert out == "记录成功"
    assert ex._read_only_turn_write_attempted is False


# ── Freshness key is wired to REAL data (data_signals_hash flips on write) ─


def test_data_signals_hash_flips_on_real_write(db):
    from datetime import date

    from app.models.daily_health import WaterIntake

    user = _make_user(db, "realdata")
    h1 = starter_pregen.data_signals_hash(db, user.id)
    assert h1  # non-empty digest

    db.add(WaterIntake(user_id=user.id, amount_ml=500, record_date=date.today()))
    db.commit()

    h2 = starter_pregen.data_signals_hash(db, user.id)
    assert h2
    assert h1 != h2, "signals_hash must flip when underlying starter data changes"


# ── C1 write belt: passive writers drop pregen (negative-space adversarial) ──
#
# These are exactly the gaps signals_hash can't see: a CGM reading and a device
# (Garmin) data sync change data a deep answer uses but leave the starter cards
# unchanged. Post-C1 those writers call invalidate_twin → invalidate_pregen. conftest
# no-ops the real invalidate_twin, so we install a spy that calls through to the real
# invalidate_pregen and assert BOTH that the writer reaches the choke and that the
# stored answer is dropped.


def _wire_belt_spy(monkeypatch) -> list:
    import app.twin.cache as tc

    calls: list = []

    def _spy(uid):
        calls.append(uid)
        starter_pregen.invalidate_pregen(uid)

    monkeypatch.setattr(tc, "invalidate_twin", _spy)
    return calls


def test_cgm_write_drops_pregen_via_belt(
    client, db, auth_user_and_headers, fake_redis, pregen_on, monkeypatch
):
    user, headers = auth_user_and_headers
    _store_fresh(db, user.id, "分析我最近的代谢健康")
    assert starter_pregen.read_pregen(user.id, "分析我最近的代谢健康") is not None
    calls = _wire_belt_spy(monkeypatch)

    resp = client.post(
        "/api/v1/cgm/readings", json={"glucose_mg_dl": 110}, headers=headers
    )
    assert resp.status_code in (200, 201), resp.text
    assert user.id in calls, "CGM write did not reach invalidate_twin (C1 gap)"
    assert starter_pregen.read_pregen(user.id, "分析我最近的代谢健康") is None


def test_device_sync_write_drops_pregen_via_belt(
    client, db, auth_user_and_headers, fake_redis, pregen_on, monkeypatch
):
    from datetime import date

    user, headers = auth_user_and_headers
    _store_fresh(db, user.id, "分析我最近的代谢健康")
    calls = _wire_belt_spy(monkeypatch)

    resp = client.post(
        "/api/v1/daily-health/garmin",
        json={"user_id": user.id, "record_date": str(date.today()), "hrv": 55.0},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    assert user.id in calls, "device-data write did not reach invalidate_twin (C1 gap)"
    assert starter_pregen.read_pregen(user.id, "分析我最近的代谢健康") is None


def test_quick_record_weight_drops_pregen_via_belt(
    client, db, auth_user_and_headers, fake_redis, pregen_on, monkeypatch
):
    """quick-record writes WeightRecord/BloodPressureRecord — only the ≤60s cached
    twin caught these pre-fast-follow. A weight text must reach the belt choke."""
    user, headers = auth_user_and_headers
    _store_fresh(db, user.id, "分析我最近的代谢健康")
    calls = _wire_belt_spy(monkeypatch)

    resp = client.post(
        "/api/v1/quick-record", json={"text": "体重71.5"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["type"] == "weight"
    assert user.id in calls, "quick-record weight write did not reach invalidate_twin"
    assert starter_pregen.read_pregen(user.id, "分析我最近的代谢健康") is None


def test_withings_sync_write_drops_pregen_via_belt(
    client, db, auth_user_and_headers, fake_redis, pregen_on, monkeypatch
):
    """Withings passive weight/BP sync — the one passive-device class C1 missed.

    The endpoint needs OAuth-token'd credentials + live Withings HTTP, so we stub the
    adapter (a fake client) and drive the real /sync endpoint. The belt is guarded on
    events_created > 0, so a non-empty parse must reach invalidate_twin.
    """
    from app.api import withings as withings_api
    from app.models.device_credential import DeviceCredential

    user, headers = auth_user_and_headers
    cred = DeviceCredential(
        user_id=user.id, device_type="withings", auth_type="oauth2", is_valid=True
    )
    cred.set_oauth_tokens(access_token="at-test", refresh_token="rt-test")
    db.add(cred)
    db.commit()

    class _FakeWithingsAdapter:
        def __init__(self, **kwargs):
            # Match the credential token so the endpoint's token-refresh branch skips.
            self.access_token = kwargs.get("access_token")
            self._refresh_token = kwargs.get("refresh_token")

        async def get_measures_by_timestamp(self, start, end):
            return {"measuregrps": []}  # opaque; parse (below) yields the records

        @staticmethod
        def parse_webhook_measures(measures):
            return [{"weight": 71.5}, {"systolic": 120, "diastolic": 80}]

    monkeypatch.setattr(withings_api, "WithingsHealthAdapter", _FakeWithingsAdapter)

    _store_fresh(db, user.id, "分析我最近的代谢健康")
    calls = _wire_belt_spy(monkeypatch)

    resp = client.post("/api/v1/devices/withings/sync?days=7", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["events_created"] == 2
    assert user.id in calls, "withings sync write did not reach invalidate_twin"
    assert starter_pregen.read_pregen(user.id, "分析我最近的代谢健康") is None


# ── Producer: same pipeline, read-only, aborts on write, cleans scratch ──


def _scratch_count(db, user_id) -> int:
    from app.models.agent_conversation import AgentConversation
    from app.services.agent_conversation_service import PREGEN_SCRATCH_SESSION_PREFIX

    return (
        db.query(AgentConversation)
        .filter(
            AgentConversation.user_id == user_id,
            AgentConversation.session_key.like(f"{PREGEN_SCRATCH_SESSION_PREFIX}%"),
        )
        .count()
    )


def _fake_run_stream(events, *, write_attempted=False):
    async def _gen(self, **kwargs):
        # Prove the producer requested a read-only turn.
        assert kwargs.get("read_only_tools") is True
        if write_attempted:
            self._read_only_turn_write_attempted = True
        for ev in events:
            yield ev
    return _gen


def test_produce_answer_clean(db, monkeypatch):
    from app.services import agent_executor as ae

    user = _make_user(db, "prod_clean")
    events = [
        {"event": "token", "data": {"content": "你的代谢分析结论…"}},
        {"event": "done", "data": {
            "completion_status": "complete", "message_id": 7,
            "sources_used": ["设备数据"], "tools_used": ["health_query"],
        }},
    ]
    monkeypatch.setattr(ae.AgentExecutor, "run_stream", _fake_run_stream(events))

    out = _run(spp._produce_answer(db, user.id, "分析我最近的代谢健康", "m1", "tok"))
    assert out is not None
    assert out["answer_text"] == "你的代谢分析结论…"
    assert out["mode"] == "agent"
    # Scratch conversation cleaned up (no phantom in the user's history).
    assert _scratch_count(db, user.id) == 0


def test_produce_answer_aborts_on_write_attempt(db, monkeypatch):
    from app.services import agent_executor as ae

    user = _make_user(db, "prod_write")
    events = [
        {"event": "token", "data": {"content": "部分答案"}},
        {"event": "done", "data": {"completion_status": "complete", "message_id": 8, "tools_used": []}},
    ]
    monkeypatch.setattr(
        ae.AgentExecutor, "run_stream", _fake_run_stream(events, write_attempted=True)
    )

    out = _run(spp._produce_answer(db, user.id, "分析我最近的代谢健康", "m1", "tok"))
    assert out is None  # write attempted → discard, never serve
    assert _scratch_count(db, user.id) == 0


def test_produce_answer_discards_write_tool_in_tools_used(db, monkeypatch):
    from app.services import agent_executor as ae

    user = _make_user(db, "prod_tool")
    events = [
        {"event": "token", "data": {"content": "答案"}},
        {"event": "done", "data": {"completion_status": "complete", "message_id": 9,
                                    "tools_used": ["health_query", "health_record"]}},
    ]
    monkeypatch.setattr(ae.AgentExecutor, "run_stream", _fake_run_stream(events))

    out = _run(spp._produce_answer(db, user.id, "分析我最近的代谢健康", "m1", "tok"))
    assert out is None
    assert _scratch_count(db, user.id) == 0


def test_produce_answer_incomplete_turn_discarded(db, monkeypatch):
    from app.services import agent_executor as ae

    user = _make_user(db, "prod_incomplete")
    events = [
        {"event": "token", "data": {"content": "半截"}},
        {"event": "done", "data": {"completion_status": "interrupted", "message_id": 10, "tools_used": []}},
    ]
    monkeypatch.setattr(ae.AgentExecutor, "run_stream", _fake_run_stream(events))

    out = _run(spp._produce_answer(db, user.id, "分析我最近的代谢健康", "m1", "tok"))
    assert out is None
    assert _scratch_count(db, user.id) == 0


# ── Scratch conversation never leaks into user-facing lists ─────────────


def test_pregen_scratch_conversation_excluded_from_lists(db):
    from app.models.agent_conversation import AgentConversation
    from app.services.agent_conversation_service import (
        PREGEN_SCRATCH_SESSION_PREFIX,
        AgentConversationService,
    )

    user = _make_user(db, "scratch")
    normal = AgentConversation(user_id=user.id, title="真对话", session_key="agent-x")
    scratch = AgentConversation(
        user_id=user.id, title="pregen",
        session_key=f"{PREGEN_SCRATCH_SESSION_PREFIX}{user.id}-abc",
    )
    db.add_all([normal, scratch])
    db.commit()

    svc = AgentConversationService(db)
    convs = svc.get_conversations(user.id, limit=50)
    ids = {c.id for c in convs}
    assert normal.id in ids
    assert scratch.id not in ids
    assert svc.count_conversations(user.id) == 1


# ── End-to-end through the /stream endpoint ──────────────────────────────


def test_stream_endpoint_serves_pregen_and_skips_executor(
    client, db, auth_user_and_headers, fake_redis, pregen_on, monkeypatch
):
    """A fresh pregen hit replays via SSE without ever invoking the live executor."""
    user, headers = auth_user_and_headers
    monkeypatch.setattr(starter_pregen, "data_signals_hash", lambda d, u: "H1")
    monkeypatch.setattr(starter_pregen, "resolve_effective_model_id", lambda d, u: "m1")
    _store_fresh(db, user.id, "分析我最近的代谢健康", sig="H1", model="m1", answer="预生成的代谢分析")

    async def _boom(*a, **k):  # run_stream MUST NOT run on a pregen hit
        raise AssertionError("run_stream must not run on a pregen hit")
        yield  # pragma: no cover — make it an async generator

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream", _boom
    )

    resp = client.post(
        "/api/v1/agent/stream",
        json={"message": "分析我最近的代谢健康"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.text
    assert "预生成的代谢分析" in body
    assert "pregen_served" in body  # honest done.meta flag

    # And a stale entry (data changed) at the endpoint falls through to the live
    # executor → the boom fires → 200 with an error event, NOT a served answer.
    monkeypatch.setattr(starter_pregen, "data_signals_hash", lambda d, u: "H2_CHANGED")
    resp2 = client.post(
        "/api/v1/agent/stream",
        json={"message": "分析我最近的代谢健康", "client_turn_id": "ct-stale-1"},
        headers=headers,
    )
    assert resp2.status_code == 200
    assert "预生成的代谢分析" not in resp2.text
