"""test_orchestrator_stream_persistent —— G-W9 客户端断开 background task 继续.

同 G-W8 模式: bg task 在 client disconnect 后跑完 audit / journal /
memory extract / specialist finding 落库.
"""

import asyncio
import uuid
from unittest.mock import patch

import pytest

from app.models.user import User
from app.orchestrator import orchestrator as orch_module
from app.orchestrator.orchestrator import stream_orchestrator, _BACKGROUND_STREAM_TASKS
from app.orchestrator.schema import OrchestratorRequest


@pytest.fixture(autouse=True)
def patch_session_local(db):
    """bg task 走 `from app.database import SessionLocal`, 测试让它复用 fixture db.
    ProxyDB 复用 test db, .close() 是 no-op (fixture 自己会关).
    """
    class _DBProxy:
        def __init__(self, real):
            object.__setattr__(self, "_real", real)
        def __getattr__(self, name):
            if name == "close":
                return lambda: None
            return getattr(self._real, name)
        def __setattr__(self, name, val):
            setattr(self._real, name, val)

    def _factory():
        return _DBProxy(db)

    with patch("app.database.SessionLocal", new=_factory):
        yield


def _make_user(db, name="orch_stream"):
    u = User(
        username=f"{name}_{uuid.uuid4().hex[:8]}",
        email=f"{name}_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name=name,
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


async def _fake_stream_llm(system_prompt, user_prompt, *, lite_mode=False):
    for i in range(5):
        await asyncio.sleep(0.05)
        yield f"chunk{i}"


async def _wait_bg():
    if _BACKGROUND_STREAM_TASKS:
        await asyncio.gather(*list(_BACKGROUND_STREAM_TASKS), return_exceptions=True)


@pytest.mark.asyncio
async def test_full_stream_yields_chunks_and_done(db):
    user = _make_user(db, "full_orch_stream")
    req = OrchestratorRequest(query="我最近 HRV 下降", source="chat")

    events = []
    with patch.object(orch_module, "_stream_llm", new=_fake_stream_llm):
        async for raw in stream_orchestrator(db, user.id, req):
            events.append(raw)

    await _wait_bg()

    chunk_events = [e for e in events if e.startswith("event: chunk\n")]
    done_events = [e for e in events if e.startswith("event: done\n")]
    assert len(chunk_events) >= 5
    assert len(done_events) == 1


@pytest.mark.asyncio
async def test_client_disconnect_background_task_still_audits(db):
    """client 早断 → generator 退出 → bg task 继续完成 audit 落库."""
    from app.models.agent_audit_log import AgentAuditLog

    user = _make_user(db, "orch_disc")
    req = OrchestratorRequest(query="早断测试", source="chat")

    consumed = 0
    with patch.object(orch_module, "_stream_llm", new=_fake_stream_llm):
        async for _raw in stream_orchestrator(db, user.id, req):
            consumed += 1
            if consumed >= 1:
                break

    await _wait_bg()

    audits = db.query(AgentAuditLog).filter(
        AgentAuditLog.user_id == user.id,
        AgentAuditLog.agent_type == "orchestrator",
    ).all()
    assert len(audits) >= 1, "bg task 应完成 orchestrator.run audit"


@pytest.mark.asyncio
async def test_immediate_disconnect_still_saves_audit(db):
    from app.models.agent_audit_log import AgentAuditLog

    user = _make_user(db, "orch_immediate")
    req = OrchestratorRequest(query="立刻断", source="chat")

    with patch.object(orch_module, "_stream_llm", new=_fake_stream_llm):
        async for _raw in stream_orchestrator(db, user.id, req):
            break

    await _wait_bg()

    audits = db.query(AgentAuditLog).filter(
        AgentAuditLog.user_id == user.id,
        AgentAuditLog.agent_type == "orchestrator",
    ).all()
    assert len(audits) >= 1
