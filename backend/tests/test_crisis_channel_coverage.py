# -*- coding: utf-8 -*-
"""危机支持在 AgentExecutor 之外各入口的服务端兜底(2026-09-30)。

AgentExecutor.run_stream 在唯一出口套了 with_crisis_support;但以下入口不经过它:
- Siri 快路径(orchestrator source=siri,非流式 + 流式):不跑 specialist,Siri prompt
  也没有 TRIAGE 红线,危机话语拿不到热线;
- Telegram 的 record / directive 分支:直接写库回执,不进 run_stream;
- /orchestrator/chat[/stream] 全流程:热线只在 MentalHealthCompanion 的结构化
  finding 里,合成文本是否带热线取决于模型。

钉住:这些入口的最终文本一律 has_crisis_support;俗语夸张不得触发。
"""
import asyncio
from unittest.mock import patch

import pytest

from app.services.crisis_lexicon import has_crisis_support

CRISIS = ("我想死", "不想活了", "活着没意思")
IDIOMS = ("累死了", "想死你了")
# Siri 意图扩展只念 synthesis 前 300 字(withIntentsExtension.js),热线必须落在其中。
SIRI_DIALOG_LIMIT = 300


@pytest.fixture
def _stream_session_local(db):
    """stream_orchestrator 的后台任务自开 SessionLocal:复用测试 db。"""

    class _DBProxy:
        def __init__(self, real):
            object.__setattr__(self, "_real", real)

        def __getattr__(self, name):
            if name == "close":
                return lambda: None
            return getattr(self._real, name)

        def __setattr__(self, name, val):
            setattr(self._real, name, val)

    with patch("app.database.SessionLocal", new=lambda: _DBProxy(db)):
        yield


def _fake_call_llm(reply: str):
    async def fake(system_prompt, user_prompt, *, lite_mode=False, **kwargs):  # noqa: ARG001
        return reply

    return fake


def _fake_stream_llm(chunks: tuple[str, ...], *, fail: bool = False):
    async def fake(system_prompt, user_prompt, *, lite_mode=False, **kwargs):  # noqa: ARG001
        for chunk in chunks:
            yield chunk
        if fail:
            raise RuntimeError("provider down")

    return fake


async def _collect_stream(orch_mod, db, user_id, req) -> list[str]:
    events = [event async for event in orch_mod.stream_orchestrator(db, user_id, req)]
    if orch_mod._BACKGROUND_STREAM_TASKS:
        await asyncio.gather(
            *list(orch_mod._BACKGROUND_STREAM_TASKS), return_exceptions=True
        )
    return events


def _client_events(events: list[str]) -> list[tuple[str, str]]:
    """按 frontend/src/utils/sseParser.ts parseFullSSE 的规则解析:只认 data: 行。"""
    parsed: list[tuple[str, str]] = []
    for frame in "".join(events).split("\n\n"):
        name, data = "message", []
        for line in frame.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
        if data and "\n".join(data):
            parsed.append((name, "\n".join(data)))
    return parsed


def _chunk_text(events: list[str]) -> str:
    return "".join(data for name, data in _client_events(events) if name == "chunk")


# ─────────────────────── Siri 快路径 ───────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("query", CRISIS)
async def test_siri_fast_path_synthesis_carries_crisis_support(monkeypatch, db, query):
    from app.orchestrator import OrchestratorRequest
    from app.orchestrator import orchestrator as orch_mod
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    monkeypatch.setattr(orch_mod, "_call_llm", _fake_call_llm("我在，慢慢说。"))

    resp = await orch_mod.run_orchestrator(
        db, user.id, OrchestratorRequest(query=query, stream=False, source="siri")
    )

    assert has_crisis_support(resp.synthesis)
    assert has_crisis_support(resp.synthesis[:SIRI_DIALOG_LIMIT])
    assert query not in resp.synthesis


@pytest.mark.asyncio
@pytest.mark.parametrize("query", IDIOMS)
async def test_siri_fast_path_idioms_get_no_crisis_block(monkeypatch, db, query):
    from app.orchestrator import OrchestratorRequest
    from app.orchestrator import orchestrator as orch_mod
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    monkeypatch.setattr(orch_mod, "_call_llm", _fake_call_llm("辛苦了，早点休息。"))

    resp = await orch_mod.run_orchestrator(
        db, user.id, OrchestratorRequest(query=query, stream=False, source="siri")
    )

    assert not has_crisis_support(resp.synthesis)


@pytest.mark.asyncio
@pytest.mark.parametrize("query", CRISIS)
async def test_siri_fast_stream_leads_with_crisis_support(
    monkeypatch, db, _stream_session_local, query
):
    """流式 TTS 边收边念:热线必须在第一个 chunk,且 LLM 中途失败也已送达。"""
    from app.orchestrator import OrchestratorRequest
    from app.orchestrator import orchestrator as orch_mod
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    monkeypatch.setattr(orch_mod, "_stream_llm", _fake_stream_llm(("我在，",), fail=True))

    events = await _collect_stream(
        orch_mod, db, user.id, OrchestratorRequest(query=query, source="siri")
    )
    chunks = [data for name, data in _client_events(events) if name == "chunk"]

    assert chunks and has_crisis_support(chunks[0])
    assert has_crisis_support(_chunk_text(events))


@pytest.mark.asyncio
async def test_siri_fast_stream_safety_override_keeps_crisis_support(
    monkeypatch, db, _stream_session_local
):
    """validator 整段替换时,客户端改念 safe_text:替换文本同样要带热线。"""
    from app.orchestrator import OrchestratorRequest
    from app.orchestrator import orchestrator as orch_mod
    from app.services.episode.validator import TextValidationResult
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    monkeypatch.setattr(orch_mod, "_stream_llm", _fake_stream_llm(("x",)))
    monkeypatch.setattr(
        orch_mod,
        "_safety_wrap",
        lambda text, *, source="": TextValidationResult(
            ok=False, action="replace", safe_text="内容已替换。"
        ),
    )

    events = await _collect_stream(
        orch_mod, db, user.id, OrchestratorRequest(query="我想死", source="siri")
    )
    overrides = [d for name, d in _client_events(events) if name == "safety_override"]

    assert overrides and has_crisis_support(overrides[0])


@pytest.mark.asyncio
async def test_siri_fast_stream_idiom_has_no_crisis_chunk(
    monkeypatch, db, _stream_session_local
):
    from app.orchestrator import OrchestratorRequest
    from app.orchestrator import orchestrator as orch_mod
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    monkeypatch.setattr(orch_mod, "_stream_llm", _fake_stream_llm(("早点休息。",)))

    events = await _collect_stream(
        orch_mod, db, user.id, OrchestratorRequest(query="累死了", source="siri")
    )

    assert not has_crisis_support(_chunk_text(events))


# ─────────────────────── /orchestrator/chat 全流程 ───────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("query", CRISIS)
async def test_full_orchestrator_synthesis_carries_crisis_support(monkeypatch, db, query):
    """模型没照 crisis_warning 念热线时,服务端兜底补上。"""
    from app.orchestrator import OrchestratorRequest
    from app.orchestrator import orchestrator as orch_mod
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    monkeypatch.setattr(orch_mod, "_call_llm", _fake_call_llm("我在，先说说发生了什么。"))

    resp = await orch_mod.run_orchestrator(
        db, user.id, OrchestratorRequest(query=query, stream=False)
    )

    assert has_crisis_support(resp.synthesis)


@pytest.mark.asyncio
async def test_full_orchestrator_idiom_synthesis_is_untouched(monkeypatch, db):
    from app.orchestrator import OrchestratorRequest
    from app.orchestrator import orchestrator as orch_mod
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    monkeypatch.setattr(orch_mod, "_call_llm", _fake_call_llm("辛苦了，早点休息。"))

    resp = await orch_mod.run_orchestrator(
        db, user.id, OrchestratorRequest(query="累死了", stream=False)
    )

    assert not has_crisis_support(resp.synthesis)


@pytest.mark.asyncio
async def test_full_orchestrator_stream_carries_crisis_support(
    monkeypatch, db, _stream_session_local
):
    from app.orchestrator import OrchestratorRequest
    from app.orchestrator import orchestrator as orch_mod
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    monkeypatch.setattr(orch_mod, "_stream_llm", _fake_stream_llm(("我在。",)))

    crisis = await _collect_stream(
        orch_mod, db, user.id, OrchestratorRequest(query="不想活了", source="chat")
    )
    idiom = await _collect_stream(
        orch_mod, db, user.id, OrchestratorRequest(query="想死你了", source="chat")
    )

    assert has_crisis_support(_chunk_text(crisis))
    assert not has_crisis_support(_chunk_text(idiom))


# ─────────────────────── Telegram inbound ───────────────────────


def _telegram_spies(monkeypatch, *, agent_reply: str = "我在。"):
    from app.services import telegram_inbound

    calls = {"agent": 0, "directive": 0, "record": 0}

    async def fake_agent(db, user_id, text, **kwargs):  # noqa: ARG001
        calls["agent"] += 1
        return agent_reply

    async def fake_directive(*args, **kwargs):  # noqa: ARG001
        calls["directive"] += 1
        return '{"status": "verified", "resource_ids": []}'

    async def fake_extract(text):  # noqa: ARG001
        calls["record"] += 1
        return {"record_type": "weight", "data": {"weight": 70}}

    async def fake_execute(db, user_id, args, **kwargs):  # noqa: ARG001
        return '{"status": "verified", "weight": 70, "record_date": "今天"}'

    monkeypatch.setattr(telegram_inbound, "agent_chat_reply", fake_agent)
    monkeypatch.setattr(telegram_inbound, "execute_user_directive", fake_directive)
    monkeypatch.setattr(telegram_inbound, "llm_extract_record", fake_extract)
    monkeypatch.setattr(telegram_inbound, "execute_health_record", fake_execute)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    (
        *CRISIS,
        "记住：我不想活了",  # directive 关键词
        "记录体重70公斤，活着没意思",  # record 意图
        "目标是控制在不想活了之前",  # directive 关键词
    ),
)
async def test_telegram_crisis_text_always_ends_with_crisis_support(db, monkeypatch, text):
    """危机原话不写成 directive / 记录回执,改走完整 Agent,且回复一定带热线。"""
    from app.services.telegram_inbound import handle_inbound_text

    calls = _telegram_spies(monkeypatch)

    reply = await handle_inbound_text(db, 1, text)

    assert has_crisis_support(reply)
    assert text not in reply
    assert calls["directive"] == 0 and calls["record"] == 0


@pytest.mark.asyncio
async def test_telegram_crisis_support_survives_agent_failure_fallback(db, monkeypatch):
    from app.services.telegram_inbound import handle_inbound_text

    _telegram_spies(monkeypatch, agent_reply="系统暂时无法完成这次查询，请稍后再试。")

    reply = await handle_inbound_text(db, 1, "我想死")

    assert has_crisis_support(reply)


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ("记录体重70公斤，累死了", "想死你了", "累死了"))
async def test_telegram_idioms_keep_normal_routing_without_crisis_block(
    db, monkeypatch, text
):
    from app.services.telegram_inbound import handle_inbound_text

    calls = _telegram_spies(monkeypatch)

    reply = await handle_inbound_text(
        db, 1, text, source_message_id="42", source_conversation_id="chat-1"
    )

    assert not has_crisis_support(reply)
    if text.startswith("记录"):
        assert calls["record"] == 1 and calls["agent"] == 0
