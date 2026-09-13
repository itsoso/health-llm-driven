from datetime import datetime, timedelta
import json
from uuid import uuid4
from unittest.mock import Mock

import pytest


@pytest.mark.asyncio
async def test_failed_new_sync_never_reuses_prior_success_in_turn_or_followup(
    db, auth_user_and_headers, monkeypatch
):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_garmin_sync_status import (
        VerifiedGarminSyncJob,
        latest_owned_garmin_sync_job,
    )
    from app.services.agent_kernel.read_task_scope import resolve_sync_status_query

    user, _ = auth_user_and_headers
    conv = AgentConversation(user_id=user.id)
    db.add(conv)
    db.flush()
    old = VerifiedGarminSyncJob(
        user.id, str(uuid4()), datetime.now().astimezone() - timedelta(hours=1)
    )
    db.add(
        AgentMessage(
            conversation_id=conv.id,
            role="assistant",
            content="old synthetic receipt",
            meta={"garmin_sync_job": old.as_metadata()},
        )
    )
    db.commit()
    backend = Mock(
        return_value={
            "task_id": old.job_id,
            "status": "SUCCESS",
            "result": {
                "status": "success",
                "success_count": 1,
                "error_count": 0,
                "activities_count": 0,
            },
        }
    )
    monkeypatch.setattr(
        "app.services.agent_garmin_sync_status._read_task_meta", backend
    )
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    ex._current_turn_user_message = "同步佳明"
    ex._current_turn_conversation_id = conv.id
    ex._start_agent_kernel_turn(
        channel="chat", user_id=user.id, message=ex._current_turn_user_message
    )
    reply = await ex._trigger_garmin_sync()
    assert "没有绑定" in reply
    result = json.loads(
        await ex._exec_health_query(
            "", {}, resolve_sync_status_query(ex._ensure_agent_kernel_turn())
        )
    )
    assert result["job_success_verified"] is False
    assert "已返回成功" not in ex._trusted_sync_summary()
    assert ex._sync_goal_outcomes()[0]["status"] == "failed"
    metadata = ex._garmin_sync_metadata()
    assert metadata == {"garmin_sync_job": None}
    db.add(
        AgentMessage(
            conversation_id=conv.id,
            role="assistant",
            content=reply,
            meta={**metadata, "read_task": ex._read_task_metadata()},
        )
    )
    db.commit()
    assert latest_owned_garmin_sync_job(db, user.id, conv.id) is None
    follow = AgentExecutor(db)
    follow._current_user_id = user.id
    follow._current_turn_user_message = "好了吗"
    follow._current_turn_conversation_id = conv.id
    follow._start_agent_kernel_turn(channel="chat", user_id=user.id, message="好了吗")
    follow._bind_read_task_reference(user.id, conv.id)
    result = json.loads(
        await follow._exec_health_query(
            "", {}, resolve_sync_status_query(follow._ensure_agent_kernel_turn())
        )
    )
    assert result["job_success_verified"] is False
    backend.assert_not_called()


@pytest.mark.asyncio
async def test_real_pi_failed_sync_persists_boundary_and_followup_cannot_claim_old_success(
    db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch
):
    from tests.test_agent_coherence_pi_trajectories import script_executor, run
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.services.agent_garmin_sync_status import VerifiedGarminSyncJob
    from app.twin.schema import HealthTwin, TwinMeta

    user, _ = auth_user_and_headers
    monkeypatch.setattr(
        "app.twin.builder.build_twin",
        lambda _db, uid, **kw: HealthTwin(
            meta=TwinMeta(user_id=uid, generated_at=datetime.now().astimezone())
        ),
    )
    conv = AgentConversation(user_id=user.id)
    db.add(conv)
    db.flush()
    old = VerifiedGarminSyncJob(
        user.id, str(uuid4()), datetime.now().astimezone() - timedelta(hours=1)
    )
    db.add(
        AgentMessage(
            conversation_id=conv.id,
            role="assistant",
            content="old synthetic receipt",
            meta={"garmin_sync_job": old.as_metadata()},
        )
    )
    db.commit()
    observed = Mock(
        return_value={
            "task_id": old.job_id,
            "status": "SUCCESS",
            "result": {
                "status": "success",
                "success_count": 1,
                "error_count": 0,
                "activities_count": 0,
            },
        }
    )
    monkeypatch.setattr(
        "app.services.agent_garmin_sync_status._read_task_meta", observed
    )
    first = script_executor(
        db,
        monkeypatch,
        [("health_record", {"record_type": "garmin", "data": {}}), "同步已经完成。"],
    )
    done, saved = await run(db, first, user, "同步佳明", conversation_id=conv.id)
    assert done["turn_outcome"]["status"] != "complete"
    assert saved.meta["garmin_sync_job"] is None
    follow = script_executor(
        db,
        monkeypatch,
        [("health_query", {"dimension": "garmin"}), "还没有核实本次同步完成。"],
    )
    _, saved = await run(db, follow, user, "好了吗", conversation_id=conv.id)
    assert (
        follow.results
        and json.loads(follow.results[0][1])["job_success_verified"] is False
    )
    observed.assert_not_called()
