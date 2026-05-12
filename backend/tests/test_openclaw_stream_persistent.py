"""test_openclaw_stream_persistent —— G-W8 客户端断开 background task 继续."""

import asyncio
import uuid
from unittest.mock import patch

import pytest

from app.models.openclaw import OpenClawMessage
from app.models.user import User
from app.services.openclaw_service import OpenClawService, _BACKGROUND_STREAM_TASKS


@pytest.fixture(autouse=True)
def patch_session_local(db):
    """G-W8: bg task 用 SessionLocal() 创新 db, 测试时让它复用测试 fixture db.

    code 路径: bg_task 内 `from app.database import SessionLocal as _SessionLocal`
    + `bg_db = _SessionLocal()`. 我们把 SessionLocal 替成返回 ProxyDB 的 callable,
    proxy 复用测试 db, .close() 是 no-op.
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


def _make_user(db, name="stream_user"):
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


async def _fake_gateway_stream(self, messages, session_key):
    """模拟 LLM 慢响应 — 5 个 token, 每个 50ms."""
    for i in range(5):
        await asyncio.sleep(0.05)
        yield f"token{i}"


async def _wait_bg():
    """等所有 background task 完成 (落库)."""
    if _BACKGROUND_STREAM_TASKS:
        await asyncio.gather(*list(_BACKGROUND_STREAM_TASKS), return_exceptions=True)


@pytest.mark.asyncio
async def test_full_stream_completes_and_saves(db):
    user = _make_user(db, "full_stream")
    svc = OpenClawService(db)

    chunks = []
    with patch.object(OpenClawService, "_call_gateway_stream", new=_fake_gateway_stream):
        async for event in svc.send_message_stream(user_id=user.id, message="hello"):
            chunks.append(event)

    await _wait_bg()

    token_events = [e for e in chunks if e["event"] == "token"]
    done_events = [e for e in chunks if e["event"] == "done"]
    assert len(token_events) >= 5
    assert len(done_events) == 1

    msgs = db.query(OpenClawMessage).filter(OpenClawMessage.role == "assistant").all()
    assert len(msgs) == 1
    assert msgs[0].content == "token0token1token2token3token4"


@pytest.mark.asyncio
async def test_client_disconnect_background_task_still_saves(db):
    """客户端早断 → generator 关 → bg task 继续完成 save_message."""
    user = _make_user(db, "disconnect_user")
    svc = OpenClawService(db)

    consumed = 0
    with patch.object(OpenClawService, "_call_gateway_stream", new=_fake_gateway_stream):
        async for event in svc.send_message_stream(user_id=user.id, message="early disc"):
            consumed += 1
            if consumed >= 2:
                break  # 模拟客户端断开

    await _wait_bg()

    msgs = db.query(OpenClawMessage).filter(OpenClawMessage.role == "assistant").all()
    assert len(msgs) == 1, "background task 应在客户端断开后仍完成 save_message"
    assert msgs[0].content == "token0token1token2token3token4"


@pytest.mark.asyncio
async def test_user_message_saved_even_if_immediate_disconnect(db):
    """客户端立刻断开 → user msg 已落, ai msg 由 bg 完成."""
    user = _make_user(db, "immediate_disc")
    svc = OpenClawService(db)

    with patch.object(OpenClawService, "_call_gateway_stream", new=_fake_gateway_stream):
        async for event in svc.send_message_stream(user_id=user.id, message="quick gone"):
            break

    await _wait_bg()

    user_msgs = db.query(OpenClawMessage).filter(OpenClawMessage.role == "user").all()
    ai_msgs = db.query(OpenClawMessage).filter(OpenClawMessage.role == "assistant").all()
    assert len(user_msgs) == 1
    assert user_msgs[0].content == "quick gone"
    assert len(ai_msgs) == 1
    assert ai_msgs[0].content == "token0token1token2token3token4"


@pytest.mark.asyncio
async def test_llm_error_falls_back_to_apology(db):
    user = _make_user(db, "llm_error")
    svc = OpenClawService(db)

    async def _failing(self, messages, session_key):
        yield "p"
        raise RuntimeError("upstream timeout")

    chunks = []
    with patch.object(OpenClawService, "_call_gateway_stream", new=_failing):
        async for event in svc.send_message_stream(user_id=user.id, message="trigger error"):
            chunks.append(event)

    await _wait_bg()

    msgs = db.query(OpenClawMessage).filter(OpenClawMessage.role == "assistant").all()
    assert len(msgs) == 1
    assert "抱歉" in msgs[0].content or "无法响应" in msgs[0].content
