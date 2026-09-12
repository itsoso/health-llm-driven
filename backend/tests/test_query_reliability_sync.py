"""Pi sync enqueue honesty, read-only boundaries and exact-turn replay."""

import json
import pytest
from app.services.agent_executor import AgentExecutor
from app.models.user import GarminCredential
from tests.test_query_reliability_outcomes import _run_scripted


@pytest.fixture(autouse=True)
def isolate(isolated_agent_protocol_transport):
    pass


@pytest.mark.asyncio
async def test_queued_sync_exact_turn_replay_does_not_enqueue_again(
    db, auth_user_and_headers, monkeypatch
):
    import app.tasks.garmin_sync as task

    user, _ = auth_user_and_headers
    db.add(
        GarminCredential(
            user_id=user.id,
            garmin_email="synthetic@example.test",
            encrypted_password="synthetic",
            sync_enabled=True,
            credentials_valid=True,
            requires_mfa=False,
        )
    )
    db.commit()
    enqueued = []
    monkeypatch.setattr(
        task.sync_user_garmin_data, "delay", lambda *a, **k: enqueued.append((a, k))
    )
    executor, done, persisted, public, dispatched = await _run_scripted(
        db,
        user,
        monkeypatch,
        query="帮我同步佳明数据",
        first_tool="health_record",
        first_args={"record_type": "garmin_sync", "data": {}},
        dispatch=lambda request: {},
        reply="同步完成，所有数据已更新。",
        turn_id="review-sync-replay",
        actual_sync=True,
    )
    assert len(enqueued) == 1
    assert "尚未确认" in persisted.content
    assert "所有数据已更新" not in public

    async def no_new_provider(*a, **k):
        raise AssertionError("Finalized sync replay must not call provider")
        yield

    monkeypatch.setattr(executor, "_call_llm_stream", no_new_provider)
    events = [
        e
        async for e in executor.run_stream(
            user.id,
            "帮我同步佳明数据",
            conversation_id=done["conversation_id"],
            client_turn_id="review-sync-replay",
        )
    ]
    replay = events[-1]["data"]
    assert replay["message_id"] == done["message_id"]
    assert len(enqueued) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "read_only,cred_state",
    [
        (True, "valid"),
        (False, "disabled"),
        (False, "invalid"),
        (False, "mfa"),
        (False, "missing"),
    ],
)
async def test_sync_readonly_or_invalid_credential_never_enqueues(
    db, auth_user_and_headers, monkeypatch, read_only, cred_state
):
    import app.tasks.garmin_sync as task

    user, _ = auth_user_and_headers
    if cred_state != "missing":
        db.add(
            GarminCredential(
                user_id=user.id,
                garmin_email="synthetic@example.test",
                encrypted_password="synthetic",
                sync_enabled=cred_state != "disabled",
                credentials_valid=cred_state != "invalid",
                requires_mfa=cred_state == "mfa",
            )
        )
        db.commit()
    executor = AgentExecutor(db)
    enqueued = []
    rounds = []
    monkeypatch.setattr(
        task.sync_user_garmin_data, "delay", lambda *a, **k: enqueued.append((a, k))
    )

    async def provider(messages, tools):
        rounds.append(True)
        if len(rounds) == 1:
            yield {
                "type": "tool_calls",
                "tool_calls": [
                    {
                        "id": "sync",
                        "type": "function",
                        "function": {
                            "name": "health_record",
                            "arguments": json.dumps(
                                {"record_type": "garmin_sync", "data": {}}
                            ),
                        },
                    }
                ],
            }
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "同步完成，所有数据已更新。"}
            yield {"type": "finish", "finish_reason": "stop"}

    async def dispatch(request, token):
        assert request.tool_name == "health_record"
        return await executor._trigger_garmin_sync()

    monkeypatch.setattr(
        executor, "_build_system_prompt", lambda *a, **k: "Only authorized tools."
    )
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)
    events = [
        e
        async for e in executor.run_stream(
            user.id,
            "帮我同步佳明数据",
            client_turn_id=f"review-sync-{cred_state}-{read_only}",
            read_only_tools=read_only,
        )
    ]
    public = "".join(
        e.get("data", {}).get("content", "")
        for e in events
        if e.get("event") == "token"
    )
    assert not enqueued
    assert not executor._turn_sync_queued
    assert "所有数据已更新" not in public
