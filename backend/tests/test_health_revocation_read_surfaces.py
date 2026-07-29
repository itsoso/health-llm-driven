"""Current health release policy must govern every persisted read surface."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.shared_conversation import SharedConversation
from app.services import history_compaction
from app.services import starter_pregen
from app.services import starter_pregen_producer
from app.services.agent_conversation_service import AgentConversationService
from app.services.health_evidence import delivery
from app.services.health_evidence.verifier import health_manifest_sha256


_HEALTH_QUERY = "我腰疼，应该怎么处理？"
_RAW_SENTINEL = "RAW_REVOKED_HEALTH_ANSWER_DO_NOT_RELEASE"


def _verified_health_meta(released_text: str) -> dict:
    from app.services.health_evidence.authority import LOW_BACK_CLAIM_POLICY

    claim_id = "claim:c_low_back_self_management_activity_boundary"
    manifest = {
        "version": "health-evidence.v1",
        "intent": {
            "version": "health-intent.v1",
            "intent_id": "health_advice.symptom.low_back_pain",
            "intent": "health_advice",
            "domain": "low_back_pain",
            "risk_level": "medium",
            "requires_authority": True,
        },
        "risk_level": "medium",
        "sufficiency": "sufficient",
        "verifier_verdict": "pass",
        "evidence_refs": [claim_id],
        "authority_evidence_refs": [claim_id],
        "authority_artifacts": [
            {
                "doc_id": claim_id,
                "sha256": LOW_BACK_CLAIM_POLICY[claim_id].artifact_sha256,
            }
        ],
    }
    return {
        "health_evidence_manifest": manifest,
        "health_evidence_verification": {
            "verdict": "pass",
            "reasons": [],
            "evidence_refs_used": [claim_id],
            "released_text_sha256": hashlib.sha256(
                released_text.encode("utf-8")
            ).hexdigest(),
            "manifest_sha256": health_manifest_sha256(manifest),
        },
    }


@dataclass
class _ObjectMessage:
    role: str
    content: str
    meta: dict | None = None


class _FakePregenRedis:
    def __init__(self):
        self.store: dict[str, object] = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, _ttl, value):
        self.store[key] = value

    def sadd(self, key, *members):
        current = self.store.setdefault(key, set())
        current.update(members)

    def expire(self, _key, _ttl):
        return True

    def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1


def test_projection_helper_accepts_mapping_and_object_and_fails_closed_unbound(
    monkeypatch,
):
    monkeypatch.setattr(
        delivery,
        "is_current_health_evidence_artifact",
        lambda *_args, **_kwargs: True,
    )
    meta = _verified_health_meta(_RAW_SENTINEL)

    paired = delivery.project_persisted_health_messages(
        [
            {"role": "user", "content": _HEALTH_QUERY},
            _ObjectMessage("assistant", _RAW_SENTINEL, meta),
        ]
    )
    assert paired[1].content == _RAW_SENTINEL
    assert paired[1].sanitized is False

    standalone = delivery.project_persisted_health_messages(
        [_ObjectMessage("assistant", _RAW_SENTINEL, meta)]
    )
    assert standalone[0].sanitized is True
    assert _RAW_SENTINEL not in standalone[0].content


def test_projection_and_compaction_policy_revoke_when_claim_is_reheld(
    monkeypatch,
):
    from app.services import clinical_claim_release

    meta = _verified_health_meta(_RAW_SENTINEL)
    current_policy = delivery.health_release_policy_fingerprint()
    current = delivery.project_persisted_health_messages(
        [
            {"role": "user", "content": _HEALTH_QUERY},
            {
                "role": "assistant",
                "content": _RAW_SENTINEL,
                "meta": meta,
            },
        ]
    )
    assert current[-1].sanitized is False

    monkeypatch.setattr(
        clinical_claim_release,
        "HEALTH_EVIDENCE_RUNTIME_RELEASED_CLAIM_IDS",
        frozenset(),
    )
    reheld_policy = delivery.health_release_policy_fingerprint()
    reheld = delivery.project_persisted_health_messages(
        [
            {"role": "user", "content": _HEALTH_QUERY},
            {
                "role": "assistant",
                "content": _RAW_SENTINEL,
                "meta": meta,
            },
        ]
    )

    assert reheld_policy != current_policy
    assert reheld[-1].sanitized is True
    assert _RAW_SENTINEL not in reheld[-1].content


def test_paired_projection_rejects_tampered_released_body(monkeypatch):
    monkeypatch.setattr(
        delivery,
        "is_current_health_evidence_artifact",
        lambda *_args, **_kwargs: True,
    )
    projected = delivery.project_persisted_health_messages(
        [
            {"role": "user", "content": _HEALTH_QUERY},
            {
                "role": "assistant",
                "content": _RAW_SENTINEL,
                "meta": _verified_health_meta(
                    "different originally released body"
                ),
            },
        ]
    )

    assert projected[-1].sanitized is True
    assert _RAW_SENTINEL not in projected[-1].content


def test_pregen_rejects_health_query_before_cache_lookup_when_runtime_flag_off(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    cache_read = {"called": False}

    def _unexpected_read(*_args, **_kwargs):
        cache_read["called"] = True
        return None

    monkeypatch.setattr(settings, "starter_pregen_enabled", True)
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", False)
    monkeypatch.setattr(starter_pregen, "read_pregen", _unexpected_read)

    result = starter_pregen.try_serve(
        db,
        user.id,
        _HEALTH_QUERY,
        conversation_id=None,
        client_turn_id=None,
    )

    assert result is None
    assert cache_read["called"] is False
    assert (
        db.query(AgentMessage)
        .filter(AgentMessage.content == _HEALTH_QUERY)
        .count()
        == 0
    )


def test_pregen_v2_namespaces_invalidate_legacy_health_entries():
    assert starter_pregen._ENTRY_PREFIX.endswith(":v2")
    assert starter_pregen._INFLIGHT_PREFIX.endswith(":v2")
    assert starter_pregen._INDEX_PREFIX.endswith(":v2")


def test_pregen_writer_rejects_health_query_and_health_metadata(monkeypatch):
    fake = _FakePregenRedis()
    monkeypatch.setattr(starter_pregen, "_redis", lambda: fake)

    starter_pregen.write_pregen(
        41,
        _HEALTH_QUERY,
        {"answer_text": _RAW_SENTINEL},
        ttl_seconds=900,
    )
    starter_pregen.write_pregen(
        41,
        "总结今天",
        {
            "answer_text": _RAW_SENTINEL,
            **_verified_health_meta(_RAW_SENTINEL),
        },
        ttl_seconds=900,
    )

    assert fake.store == {}


def test_pregen_producer_never_enqueues_health_query_when_runtime_flag_off(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    scheduled: list[tuple] = []

    class _BackgroundTasks:
        def add_task(self, *args):
            scheduled.append(args)

    monkeypatch.setattr(settings, "starter_pregen_enabled", True)
    monkeypatch.setattr(settings, "starter_pregen_max_chips", 2)
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", False)
    monkeypatch.setattr(
        starter_pregen_producer,
        "data_signals_hash",
        lambda *_args: "signals",
    )
    monkeypatch.setattr(
        starter_pregen_producer,
        "resolve_effective_model_id",
        lambda *_args: "model",
    )
    monkeypatch.setattr(
        starter_pregen_producer,
        "_should_generate",
        lambda *_args: True,
    )

    starter_pregen_producer.enqueue_pregen(
        _BackgroundTasks(),
        db,
        user.id,
        [_HEALTH_QUERY],
        "token",
    )

    assert scheduled == []


async def test_pregen_producer_rejects_health_manifest_from_done_data(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    meta = _verified_health_meta(_RAW_SENTINEL)

    async def _fake_run_stream(self, **_kwargs):
        yield {"event": "token", "data": {"content": _RAW_SENTINEL}}
        yield {
            "event": "done",
            "data": {
                "completion_status": "complete",
                **meta,
            },
        }

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        _fake_run_stream,
    )

    produced = await starter_pregen_producer._produce_answer(
        db,
        user.id,
        "总结今天",
        "model",
        None,
    )

    assert produced is None


def test_pregen_try_serve_rejects_health_metadata_entry_before_persistence(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    text = "总结今天"
    fake = _FakePregenRedis()
    payload = {
        "starter_text": text,
        "signals_hash": "signals",
        "model_id": "model",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "answer_text": _RAW_SENTINEL,
        **_verified_health_meta(_RAW_SENTINEL),
    }
    fake.store[starter_pregen._entry_key(user.id, text)] = json.dumps(payload)
    monkeypatch.setattr(settings, "starter_pregen_enabled", True)
    monkeypatch.setattr(starter_pregen, "_redis", lambda: fake)
    monkeypatch.setattr(
        starter_pregen,
        "data_signals_hash",
        lambda *_args: "signals",
    )
    monkeypatch.setattr(
        starter_pregen,
        "resolve_effective_model_id",
        lambda *_args: "model",
    )

    result = starter_pregen.try_serve(
        db,
        user.id,
        text,
        conversation_id=None,
        client_turn_id=None,
    )

    assert result is None
    assert (
        db.query(AgentMessage)
        .filter(AgentMessage.content == _RAW_SENTINEL)
        .count()
        == 0
    )


def test_pregen_duplicate_replay_projects_historical_assistant(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    turn_id = f"revoked-pregen-replay-{user.id}"
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(
        user.id,
        None,
        title="duplicate replay",
    )
    service.save_user_message_once(
        conversation.id,
        user.id,
        "总结今天",
        client_turn_id=turn_id,
    )
    service.save_message(
        conversation.id,
        "assistant",
        _RAW_SENTINEL,
        meta={
            **_verified_health_meta(_RAW_SENTINEL),
            "client_turn_finalized": True,
        },
        client_turn_id=turn_id,
        client_turn_user_id=user.id,
    )
    monkeypatch.setattr(
        delivery,
        "is_current_health_evidence_artifact",
        lambda *_args, **_kwargs: False,
    )

    replay = starter_pregen._persist_and_build_events(
        db,
        user.id,
        "总结今天",
        "new pregen answer",
        conversation_id=conversation.id,
        client_turn_id=turn_id,
        sources_used=[],
        generated_at=None,
    )

    assert replay is not None
    events = replay[0]
    token = next(event for event in events if event["event"] == "token")
    done = next(event for event in events if event["event"] == "done")
    assert _RAW_SENTINEL not in token["data"]["content"]
    assert "health_evidence_manifest" not in done["data"]
    assert "health_evidence_verification" not in done["data"]


def test_build_messages_revalidates_revoked_health_when_runtime_flag_off(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    conversation = AgentConversation(
        user_id=user.id,
        title="revoked history",
        session_key=f"revoked-build-messages-{user.id}",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    db.add_all(
        [
            AgentMessage(
                conversation_id=conversation.id,
                role="user",
                content=_HEALTH_QUERY,
            ),
            AgentMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=_RAW_SENTINEL,
                meta=_verified_health_meta(_RAW_SENTINEL),
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", False)
    monkeypatch.setattr(
        delivery,
        "is_current_health_evidence_artifact",
        lambda *_args, **_kwargs: False,
    )

    messages = AgentConversationService(db).build_messages(
        conversation.id,
        limit=15,
    )

    assert _RAW_SENTINEL not in [message["content"] for message in messages]
    assert messages[-1]["role"] == "assistant"
    assert "重新发送" in messages[-1]["content"]


def test_build_messages_never_prepends_cached_summary_after_row_revocation(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    conversation = AgentConversation(
        user_id=user.id,
        title="revoked cached summary",
        session_key=f"revoked-cached-summary-{user.id}",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    health_user = AgentMessage(
        conversation_id=conversation.id,
        role="user",
        content=_HEALTH_QUERY,
    )
    health_assistant = AgentMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=_RAW_SENTINEL,
        meta=_verified_health_meta(_RAW_SENTINEL),
    )
    db.add_all(
        [
            health_user,
            health_assistant,
            AgentMessage(
                conversation_id=conversation.id,
                role="user",
                content="最近窗口问题",
            ),
            AgentMessage(
                conversation_id=conversation.id,
                role="assistant",
                content="普通最近回答",
            ),
        ]
    )
    db.commit()
    db.refresh(health_assistant)
    monkeypatch.setattr(settings, "llm_history_compaction", True)
    monkeypatch.setattr(
        delivery,
        "is_current_health_evidence_artifact",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        history_compaction,
        "_cache_get",
        lambda _cid: {
            "folded_thru_id": health_assistant.id,
            "summary": f"旧摘要仍含 {_RAW_SENTINEL}",
        },
    )

    messages = AgentConversationService(db).build_messages(
        conversation.id,
        limit=2,
    )

    assert _RAW_SENTINEL not in json.dumps(
        messages,
        ensure_ascii=False,
    )


def test_history_compaction_cache_namespace_tracks_release_policy(monkeypatch):
    monkeypatch.setattr(
        delivery,
        "health_release_policy_fingerprint",
        lambda: "policy-a",
        raising=False,
    )
    first = history_compaction._fold_key(73)
    monkeypatch.setattr(
        delivery,
        "health_release_policy_fingerprint",
        lambda: "policy-b",
        raising=False,
    )
    second = history_compaction._fold_key(73)

    assert first != second
    assert "policy-a" in first
    assert "policy-b" in second


def test_history_compaction_never_writes_summary_under_changed_policy(
    monkeypatch,
):
    from app.utils.redis_cache import RedisCache

    writes: list[tuple] = []
    monkeypatch.setattr(
        delivery,
        "health_release_policy_fingerprint",
        lambda: "current-policy",
    )
    monkeypatch.setattr(
        RedisCache,
        "set",
        lambda *args, **kwargs: writes.append((args, kwargs)),
    )

    history_compaction._cache_set(
        73,
        {
            "summary": _RAW_SENTINEL,
            "health_release_policy": "revoked-old-policy",
        },
    )

    assert writes == []


async def test_history_compaction_projects_revoked_turn_before_llm_and_receipts(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    revoked_receipt = f"已记录 {_RAW_SENTINEL}"
    conversation = AgentConversation(
        user_id=user.id,
        title="compaction revocation",
        session_key=f"revoked-compaction-{user.id}",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    db.add_all(
        [
            AgentMessage(
                conversation_id=conversation.id,
                role="user",
                content=_HEALTH_QUERY,
            ),
            AgentMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=revoked_receipt,
                meta=_verified_health_meta(revoked_receipt),
            ),
            AgentMessage(
                conversation_id=conversation.id,
                role="user",
                content="后续一",
            ),
            AgentMessage(
                conversation_id=conversation.id,
                role="assistant",
                content="普通回答",
            ),
        ]
    )
    db.commit()
    captured: dict[str, object] = {}
    import app.database as app_database

    monkeypatch.setattr(
        app_database,
        "SessionLocal",
        sessionmaker(bind=db.get_bind()),
    )
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", False)
    monkeypatch.setattr(
        delivery,
        "is_current_health_evidence_artifact",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(history_compaction, "_cache_get", lambda _cid: None)

    def _capture_cache(_cid, payload):
        captured["payload"] = payload

    async def _capture_summary(_prior, turns):
        captured["turns"] = turns
        return "safe summary"

    monkeypatch.setattr(history_compaction, "_cache_set", _capture_cache)
    monkeypatch.setattr(history_compaction, "_summarize", _capture_summary)

    await history_compaction._refresh_fold(conversation.id, keep_recent=2)

    turns = captured["turns"]
    assert _RAW_SENTINEL not in json.dumps(turns, ensure_ascii=False)
    payload = captured["payload"]
    assert _RAW_SENTINEL not in json.dumps(payload, ensure_ascii=False)


def test_desktop_trace_projects_every_assistant_and_canonical_latest_meta(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    conversation = AgentConversation(
        user_id=user.id,
        title="desktop revocation",
        session_key=f"revoked-desktop-{user.id}",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    db.add_all(
        [
            AgentMessage(
                conversation_id=conversation.id,
                role="user",
                content=_HEALTH_QUERY,
            ),
            AgentMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=f"{_RAW_SENTINEL}-first",
                meta=_verified_health_meta(f"{_RAW_SENTINEL}-first"),
            ),
            AgentMessage(
                conversation_id=conversation.id,
                role="user",
                content=_HEALTH_QUERY,
            ),
            AgentMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=_RAW_SENTINEL,
                meta={
                    **_verified_health_meta(_RAW_SENTINEL),
                    "sources_used": ["private stale source"],
                    "shadow_passthrough": {
                        "orchestrator_text": _RAW_SENTINEL,
                    },
                    "untrusted_nested_meta": {
                        "answer_copy": _RAW_SENTINEL,
                    },
                    "cards": [
                        {
                            "type": "health_evidence",
                            "data": {"raw": _RAW_SENTINEL},
                        }
                    ],
                },
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", False)
    monkeypatch.setattr(
        delivery,
        "is_current_health_evidence_artifact",
        lambda *_args, **_kwargs: False,
    )

    response = client.get(
        f"/api/v1/desktop/traces/{conversation.id}",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert _RAW_SENTINEL not in json.dumps(body, ensure_ascii=False)
    assert body["sources_used"] == []
    assert body["evidence_cards"] == []
    assert "health_evidence_manifest" not in body["raw_meta"]
    assert "health_evidence_verification" not in body["raw_meta"]


def test_agent_share_revalidates_after_revocation_and_hides_internal_meta(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    conversation = AgentConversation(
        user_id=user.id,
        title="share revocation",
        session_key=f"revoked-share-{user.id}",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    db.add_all(
        [
            AgentMessage(
                conversation_id=conversation.id,
                role="user",
                content=_HEALTH_QUERY,
            ),
            AgentMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=_RAW_SENTINEL,
                meta={
                    **_verified_health_meta(_RAW_SENTINEL),
                    "private_personal_context": "must never enter share",
                },
            ),
        ]
    )
    db.commit()
    current = {"value": True}
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", False)
    monkeypatch.setattr(
        delivery,
        "is_current_health_evidence_artifact",
        lambda *_args, **_kwargs: current["value"],
    )

    created = client.post(
        "/api/v1/shared/create",
        headers=headers,
        json={
            "conversation_id": conversation.id,
            "source_type": "agent",
        },
    )

    assert created.status_code == 200
    shared = (
        db.query(SharedConversation)
        .filter(
            SharedConversation.user_id == user.id,
            SharedConversation.source_type == "agent",
        )
        .one()
    )
    assistant_snapshot = shared.messages_snapshot[-1]
    assert set(assistant_snapshot["health_meta"]) == {
        "health_evidence_manifest",
        "health_evidence_verification",
    }
    assert "private_personal_context" not in json.dumps(
        assistant_snapshot,
        ensure_ascii=False,
    )

    before = client.get(
        f"/api/v1/shared/{created.json()['share_token']}?count_view=false"
    )
    assert before.status_code == 200
    assert before.json()["messages"][-1]["content"] == _RAW_SENTINEL
    assert "health_evidence_manifest" not in before.text
    assert "health_evidence_verification" not in before.text

    current["value"] = False
    after = client.get(
        f"/api/v1/shared/{created.json()['share_token']}?count_view=false"
    )
    assert after.status_code == 200
    assert _RAW_SENTINEL not in after.text
    assert "health_evidence_manifest" not in after.text
    assert "health_evidence_verification" not in after.text


def test_agent_share_tamper_and_unbound_snapshot_fail_closed(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    monkeypatch.setattr(
        delivery,
        "is_current_health_evidence_artifact",
        lambda *_args, **_kwargs: True,
    )
    meta = _verified_health_meta("original released answer")
    shared = SharedConversation(
        user_id=user.id,
        share_token=f"standalone-health-{user.id}",
        source_type="agent",
        source_conversation_id=999_001,
        title="standalone transplant",
        messages_snapshot=[
            {
                "role": "assistant",
                "content": _RAW_SENTINEL,
                "created_at": None,
                "health_meta": meta,
            }
        ],
        is_active=True,
    )
    db.add(shared)
    db.commit()

    response = client.get(
        f"/api/v1/shared/{shared.share_token}?count_view=false"
    )

    assert response.status_code == 200
    assert _RAW_SENTINEL not in response.text
    assert "health_evidence_manifest" not in response.text
    assert "health_evidence_verification" not in response.text


def test_plain_text_share_health_looking_content_is_byte_identical(
    client,
    auth_user_and_headers,
    monkeypatch,
):
    _user, headers = auth_user_and_headers
    monkeypatch.setattr(
        delivery,
        "is_current_health_evidence_artifact",
        lambda *_args, **_kwargs: False,
    )
    authored = f"我自己写的腰痛记录：{_RAW_SENTINEL}"
    created = client.post(
        "/api/v1/shared/create-text",
        headers=headers,
        json={"title": "本人文本", "message": authored},
    )

    response = client.get(
        f"/api/v1/shared/{created.json()['share_token']}?count_view=false"
    )

    assert response.status_code == 200
    assert response.json()["messages"][0]["content"] == authored
