"""Agent API health delivery must never bypass the current evidence runtime."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.agent_conversation import AgentConversation, AgentMessage
from app.services.agent_runtime import AgentRuntimeCoordinator


_HEALTH_QUERY = "腰痛而且排不出尿"
_UNVERIFIED_ANSWER = "已经确诊腰椎间盘突出，先在家观察并自行吃药。"
_SAFE_EXECUTOR_ANSWER = "executor verified health answer"


def _health_continuation_context(*, valid: bool) -> str:
    return json.dumps(
        {
            "health_evidence_continuation": {
                "version": "health-evidence-continuation.v1",
                "parent_intent_id": (
                    "health_advice.symptom.low_back_pain"
                ),
                "parent_message_id": 77,
                "parent_turn_id": "parent-health-turn",
                "answers": [
                    {
                        "discriminator_id": "low_back.cauda_equina",
                        "answer": "yes" if valid else "invalid",
                    }
                ],
            }
        },
        ensure_ascii=False,
    )


def _verified_health_meta(released_text: str) -> dict:
    claim_id = "claim:c_test_released_health_answer"
    return {
        "health_evidence_manifest": {
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
        },
        "health_evidence_verification": {
            "verdict": "pass",
            "reasons": [],
            "evidence_refs_used": [claim_id],
            "released_text_sha256": hashlib.sha256(
                released_text.encode("utf-8")
            ).hexdigest(),
        },
    }


def _conversation(db, user_id: int, *, suffix: str) -> AgentConversation:
    conversation = AgentConversation(
        user_id=user_id,
        title=f"health delivery {suffix}",
        session_key=f"health-delivery-{user_id}-{suffix}",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def _message(
    db,
    conversation_id: int,
    role: str,
    content: str,
    *,
    meta: dict | None = None,
) -> AgentMessage:
    message = AgentMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        meta=meta,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def _terminal_runtime_health_turn(
    db,
    *,
    user_id: int,
    origin: str,
    suffix: str,
):
    turn_id = f"turn-health-delivery-{suffix}"
    conversation = _conversation(db, user_id, suffix=suffix)
    source = _message(
        db,
        conversation.id,
        "user",
        _HEALTH_QUERY,
        meta={"client_turn_id": turn_id},
    )
    assistant = _message(
        db,
        conversation.id,
        "assistant",
        _UNVERIFIED_ANSWER,
        meta={
            "client_turn_id": turn_id,
            "completion_status": "complete",
            "client_turn_finalized": True,
            "turn_outcome": {"category": "success"},
            "sources_used": ["legacy health source"],
            "cards": [
                {
                    "type": "system_knowledge_evidence",
                    "data": {"claims": [_UNVERIFIED_ANSWER]},
                }
            ],
        },
    )
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id=f"run-health-delivery-{suffix}",
        attempt_id=f"attempt-health-delivery-{suffix}",
        user_id=user_id,
        conversation_id=conversation.id,
        client_turn_id=turn_id,
        origin=origin,
    )
    runtime.mark_running(admission.context)
    runtime.bind_messages(
        admission.context,
        conversation_id=conversation.id,
        source_message_id=source.id,
        assistant_message_id=assistant.id,
    )
    runtime.complete(admission.context, status="succeeded")
    return conversation, turn_id


def _sse_events(response) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def _install_live_executor(monkeypatch, db):
    calls: list[dict] = []

    async def fake_run_stream(self, **kwargs):
        calls.append(dict(kwargs))
        yield {
            "event": "token",
            "data": {"content": _SAFE_EXECUTOR_ANSWER},
        }
        yield {
            "event": "done",
            "data": {
                "conversation_id": None,
                "message_id": None,
                "completion_status": "complete",
            },
        }

    monkeypatch.setattr(settings, "agent_runtime_mode", "off")
    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )
    monkeypatch.setattr(
        "app.api.agent._dispatch_life_event_extraction",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.api.agent._reserve_agent_capacity",
        lambda *_args, **_kwargs: "health-delivery-capacity",
    )
    monkeypatch.setattr(
        "app.api.agent._release_agent_capacity_safely",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.database.SessionLocal",
        sessionmaker(
            bind=db.get_bind(),
            autocommit=False,
            autoflush=False,
        ),
    )
    return calls


def test_history_hides_unverified_health_answer_when_page_starts_at_assistant(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    conversation = _conversation(db, user.id, suffix="history")
    _message(db, conversation.id, "user", _HEALTH_QUERY)
    _message(
        db,
        conversation.id,
        "assistant",
        _UNVERIFIED_ANSWER,
        meta={
            "sources_used": ["legacy health source"],
            "cards": [
                {
                    "type": "system_knowledge_evidence",
                    "data": {"claims": [_UNVERIFIED_ANSWER]},
                }
            ],
        },
    )
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)

    response = client.get(
        f"/api/v1/agent/conversations/{conversation.id}?limit=1",
        headers=headers,
    )

    assert response.status_code == 200
    delivered = response.json()["messages"][0]
    assert delivered["role"] == "assistant"
    assert _UNVERIFIED_ANSWER not in delivered["content"]
    assert "未经过当前健康安全校验" in delivered["content"]
    assert delivered["meta"]["cards"] == []
    assert delivered["meta"]["sources_used"] == []
    assert delivered["meta"]["health_evidence_replay_sanitized"] is True


def test_history_preserves_current_verified_health_answer(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    conversation = _conversation(db, user.id, suffix="verified-history")
    _message(db, conversation.id, "user", "我腰疼怎么办")
    verified_answer = "已通过当前健康证据运行时的安全回答。"
    _message(
        db,
        conversation.id,
        "assistant",
        verified_answer,
        meta=_verified_health_meta(verified_answer),
    )
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)

    response = client.get(
        f"/api/v1/agent/conversations/{conversation.id}",
        headers=headers,
    )

    assert response.status_code == 200
    delivered = response.json()["messages"][-1]
    assert delivered["content"] == verified_answer
    assert "health_evidence_replay_sanitized" not in delivered["meta"]


def test_history_rejects_current_meta_when_released_body_hash_does_not_match(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    conversation = _conversation(
        db,
        user.id,
        suffix="tampered-current-history",
    )
    _message(db, conversation.id, "user", "我腰疼怎么办")
    _message(
        db,
        conversation.id,
        "assistant",
        _UNVERIFIED_ANSWER,
        meta=_verified_health_meta("另一条经过验证的回答"),
    )
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)

    response = client.get(
        f"/api/v1/agent/conversations/{conversation.id}",
        headers=headers,
    )

    assert response.status_code == 200
    delivered = response.json()["messages"][-1]
    assert _UNVERIFIED_ANSWER not in delivered["content"]
    assert delivered["meta"]["health_evidence_replay_sanitized"] is True


def test_history_treats_health_claiming_meta_as_health_for_generic_continuation(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    conversation = _conversation(
        db,
        user.id,
        suffix="generic-continuation",
    )
    _message(db, conversation.id, "user", "我的回答已提交")
    _message(
        db,
        conversation.id,
        "assistant",
        _UNVERIFIED_ANSWER,
        meta={
            "health_evidence_manifest": {
                "version": "health-evidence.v0",
                "intent": {
                    "intent_id": (
                        "health_advice.symptom.low_back_pain"
                    ),
                    "risk_level": "emergency",
                },
                "risk_level": "emergency",
                "verifier_verdict": "pending",
            },
            "cards": [
                {
                    "type": "health_evidence",
                    "data": {"legacy": True},
                }
            ],
        },
    )
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)

    response = client.get(
        f"/api/v1/agent/conversations/{conversation.id}",
        headers=headers,
    )

    assert response.status_code == 200
    delivered = response.json()["messages"][-1]
    assert _UNVERIFIED_ANSWER not in delivered["content"]
    assert "未经过当前健康安全校验" in delivered["content"]
    assert "联系当地急救服务" in delivered["content"]
    assert "请重新发送健康问题" not in delivered["content"]
    assert delivered["meta"]["cards"] == []
    assert "health_evidence_manifest" not in delivered["meta"]


def test_health_verification_public_contract_binds_the_released_text():
    from app.services.health_evidence.verifier import (
        HealthAnswerVerification,
    )

    released_text = "经过确定性 verifier 释放的健康回答"
    payload = HealthAnswerVerification(
        verdict="pass",
        text=released_text,
        evidence_refs_used=("claim:c_test",),
    ).public_dict()

    assert payload["released_text_sha256"] == hashlib.sha256(
        released_text.encode("utf-8")
    ).hexdigest()


def test_agent_runtime_stream_replay_sanitizes_unverified_health_answer(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    conversation, turn_id = _terminal_runtime_health_turn(
        db,
        user_id=user.id,
        origin="agent_stream",
        suffix="stream-replay",
    )
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)

    async def must_not_run(self, **kwargs):
        raise AssertionError("terminal runtime replay must not execute the model")
        yield

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        must_not_run,
    )

    response = client.post(
        "/api/v1/agent/stream",
        headers=headers,
        json={
            "message": _HEALTH_QUERY,
            "conversation_id": conversation.id,
            "client_turn_id": turn_id,
        },
    )

    assert response.status_code == 200
    events = _sse_events(response)
    visible = "".join(
        str((event.get("data") or {}).get("content") or "")
        for event in events
        if event.get("event") == "token"
    )
    done = next(
        event["data"] for event in events if event.get("event") == "done"
    )
    assert _UNVERIFIED_ANSWER not in visible
    assert "未经过当前健康安全校验" in visible
    assert done["cards"] == []
    assert done["sources_used"] == []
    assert done["health_evidence_replay_sanitized"] is True


def test_agent_runtime_send_replay_sanitizes_unverified_health_answer(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    conversation, turn_id = _terminal_runtime_health_turn(
        db,
        user_id=user.id,
        origin="agent_send",
        suffix="send-replay",
    )
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)

    response = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={
            "message": _HEALTH_QUERY,
            "conversation_id": conversation.id,
            "client_turn_id": turn_id,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert _UNVERIFIED_ANSWER not in body["reply"]
    assert "未经过当前健康安全校验" in body["reply"]
    assert body["meta"]["health_evidence_replay_sanitized"] is True


def test_emergency_health_chart_intent_skips_genui_and_runs_executor(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    _user, headers = auth_user_and_headers
    calls = _install_live_executor(monkeypatch, db)
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)
    monkeypatch.setattr(settings, "starter_pregen_enabled", False)
    shortcut_calls = []

    def unsafe_genui_shortcut(*_args, **_kwargs):
        shortcut_calls.append(True)
        return (
            [
                {
                    "event": "token",
                    "data": {"content": "unsafe genui health shortcut"},
                },
                {
                    "event": "done",
                    "data": {"completion_status": "complete"},
                },
            ],
            1,
            1,
        )

    monkeypatch.setattr(
        "app.api.agent._maybe_genui_chart_events",
        unsafe_genui_shortcut,
    )

    response = client.post(
        "/api/v1/agent/stream",
        headers={**headers, "X-Reva-Client-Caps": "genui-v1"},
        json={
            "message": "绘制最近半年HRV曲线，我腰痛而且排不出尿",
            "client_turn_id": "health-genui-live-executor",
        },
    )

    assert response.status_code == 200
    assert _SAFE_EXECUTOR_ANSWER in response.text
    assert "unsafe genui health shortcut" not in response.text
    assert shortcut_calls == []
    assert len(calls) == 1


def test_structured_health_continuation_chart_skips_genui_and_runs_executor(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    _user, headers = auth_user_and_headers
    calls = _install_live_executor(monkeypatch, db)
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)
    monkeypatch.setattr(settings, "starter_pregen_enabled", False)
    shortcut_calls = []

    def unsafe_genui_shortcut(*_args, **_kwargs):
        shortcut_calls.append(True)
        return (
            [
                {
                    "event": "token",
                    "data": {"content": "unsafe continuation chart"},
                },
                {
                    "event": "done",
                    "data": {"completion_status": "complete"},
                },
            ],
            1,
            1,
        )

    monkeypatch.setattr(
        "app.api.agent._maybe_genui_chart_events",
        unsafe_genui_shortcut,
    )

    response = client.post(
        "/api/v1/agent/stream",
        headers={**headers, "X-Reva-Client-Caps": "genui-v1"},
        json={
            "message": "画最近一周HRV曲线",
            "extra_context": _health_continuation_context(valid=True),
            "client_turn_id": "health-continuation-genui-live",
        },
    )

    assert response.status_code == 200
    assert _SAFE_EXECUTOR_ANSWER in response.text
    assert "unsafe continuation chart" not in response.text
    assert shortcut_calls == []
    assert len(calls) == 1


def test_emergency_health_stream_skips_starter_pregen_and_runs_executor(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    _user, headers = auth_user_and_headers
    calls = _install_live_executor(monkeypatch, db)
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)
    monkeypatch.setattr(settings, "starter_pregen_enabled", True)
    monkeypatch.setattr(
        "app.api.agent._maybe_genui_chart_events",
        lambda *_args, **_kwargs: None,
    )
    pregen_calls = []

    def unsafe_pregen(*_args, **_kwargs):
        pregen_calls.append(True)
        return (
            [
                {
                    "event": "token",
                    "data": {"content": "unsafe pregen health answer"},
                },
                {
                    "event": "done",
                    "data": {"completion_status": "complete"},
                },
            ],
            1,
            1,
            "unsafe pregen health answer",
        )

    monkeypatch.setattr(
        "app.services.starter_pregen.try_serve",
        unsafe_pregen,
    )

    response = client.post(
        "/api/v1/agent/stream",
        headers=headers,
        json={
            "message": _HEALTH_QUERY,
            "client_turn_id": "health-pregen-stream-live-executor",
        },
    )

    assert response.status_code == 200
    assert _SAFE_EXECUTOR_ANSWER in response.text
    assert "unsafe pregen health answer" not in response.text
    assert pregen_calls == []
    assert len(calls) == 1


def test_emergency_health_send_skips_starter_pregen_and_runs_executor(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    _user, headers = auth_user_and_headers
    calls = _install_live_executor(monkeypatch, db)
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)
    monkeypatch.setattr(settings, "starter_pregen_enabled", True)
    pregen_calls = []

    def unsafe_pregen(*_args, **_kwargs):
        pregen_calls.append(True)
        return ([], 1, 1, "unsafe pregen health answer")

    monkeypatch.setattr(
        "app.services.starter_pregen.try_serve",
        unsafe_pregen,
    )

    response = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={
            "message": _HEALTH_QUERY,
            "client_turn_id": "health-pregen-send-live-executor",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == _SAFE_EXECUTOR_ANSWER
    assert "unsafe pregen health answer" not in body["reply"]
    assert pregen_calls == []
    assert len(calls) == 1


def test_malformed_health_continuation_send_skips_pregen_and_runs_executor(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    _user, headers = auth_user_and_headers
    calls = _install_live_executor(monkeypatch, db)
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)
    monkeypatch.setattr(settings, "starter_pregen_enabled", True)
    pregen_calls = []

    def unsafe_pregen(*_args, **_kwargs):
        pregen_calls.append(True)
        return ([], 1, 1, "unsafe malformed continuation answer")

    monkeypatch.setattr(
        "app.services.starter_pregen.try_serve",
        unsafe_pregen,
    )

    response = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={
            "message": "画最近一周HRV曲线",
            "extra_context": _health_continuation_context(valid=False),
            "client_turn_id": "health-continuation-pregen-live",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == _SAFE_EXECUTOR_ANSWER
    assert "unsafe malformed continuation answer" not in body["reply"]
    assert pregen_calls == []
    assert len(calls) == 1
