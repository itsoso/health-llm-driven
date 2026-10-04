"""Measure provider inputs without changing the authoritative Pi transcript."""

import copy
import json
import os
from pathlib import Path

import pytest

from app.services import agent_executor as ae
from tests.test_agent_prompt_budget_execution import CaptureProvider
from tests.test_agent_composed_synthesis_projection import run_projection
from tests.test_agent_read_repair_round_budget import (
    _isolate_twin_cache as _isolate_twin_cache,
    clock as clock,
    four_domain_user as four_domain_user,
    owned_data as owned_data,
)


def test_read_synthesis_omits_execution_manual_but_keeps_safety(
    db, auth_user_and_headers, monkeypatch
):
    from tests.test_agent_diet_synthesis_projection import _context_sentinels

    _context_sentinels(monkeypatch)
    executor = ae.AgentExecutor(db)
    user, _ = auth_user_and_headers
    monkeypatch.setattr(ae.settings, "domain_prompt_optimization", True)
    baseline = executor._build_system_prompt(user.id, 1, None, static_rules_only=True)
    compact = executor._build_system_prompt(
        user.id, 1, None, static_rules_only=True, synthesis_only=True
    )
    assert len(compact) < len(baseline) * 0.7
    assert "## 数据记录规则" not in compact
    assert "## 分析规则" not in compact
    assert "本轮只依据返回结果回答" in compact
    for rule in ae._CLINICIAN_PROVENANCE_PROMPT_BLOCK:
        assert rule in compact
    for rule in (
        "安全与边界 (R4",
        "不做诊断",
        "相关性,非因果",
        "STATIC_TRIAGE_SENTINEL",
        "数据合理性提示",
    ):
        assert rule in baseline and rule in compact
    normal = executor._build_system_prompt(user.id, 1, None)
    assert (
        executor._build_system_prompt(user.id, 1, None, synthesis_only=True) == normal
    )
    monkeypatch.setattr(ae.settings, "domain_prompt_optimization", False)
    assert (
        executor._build_system_prompt(
            user.id, 1, None, static_rules_only=True, synthesis_only=True
        )
        == baseline
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_json_tool_transport_is_compact_without_mutating_pi(
    db, monkeypatch, stream
):
    executor = ae.AgentExecutor(db)
    provider = CaptureProvider()
    monkeypatch.setattr(ae.settings, "domain_prompt_optimization", True)
    monkeypatch.setattr(ae.settings, "agent_base_url", None)
    monkeypatch.setattr(ae.settings, "agent_api_key", None)
    monkeypatch.setattr(
        executor, "_resolve_chat_provider", lambda tools: (provider, tools)
    )
    payload = '{\n  "value": 1.2300e-12, "id": 999999999999999999, "text": "keep  two spaces\\nnext", "same": 1, "same": 2\n}'
    messages = [
        {"role": "user", "content": payload},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "read1",
                    "type": "function",
                    "function": {
                        "name": "health_query",
                        "arguments": '{"dimension": "sleep"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "read1", "content": payload},
    ]
    before = copy.deepcopy(messages)
    if stream:
        _ = [e async for e in executor._call_llm_stream(messages, [])]
    else:
        await executor._call_llm(messages, [])
    sent = provider.calls[-1]["messages"]
    assert messages == before
    assert sent[0] == before[0] and sent[1] == before[1]
    assert sent[2]["tool_call_id"] == "read1"
    assert (
        sent[2]["content"]
        == '{"value":1.2300e-12,"id":999999999999999999,"text":"keep  two spaces\\nnext","same":1,"same":2}'
    )


@pytest.mark.asyncio
async def test_health_read_provider_budget_replay(
    db, four_domain_user, owned_data, monkeypatch
):
    pairs = []
    for enabled in (False, True):
        monkeypatch.setattr(ae.settings, "domain_prompt_optimization", enabled)
        _, calls, _, done, saved = await run_projection(
            db, four_domain_user, monkeypatch
        )
        assert done["completion_status"] == "complete"
        pairs.append({"enabled": enabled, "calls": calls})
    if output := os.environ.get("REVA_ARCHITECTURE_PAYLOADS"):
        Path(output).write_text(json.dumps(pairs, ensure_ascii=False, indent=2) + "\n")
    before, after = pairs[0]["calls"][-1], pairs[1]["calls"][-1]
    assert not before.get("tools") and not after.get("tools")
    assert after["messages"][1:] == before["messages"][1:]
    assert "## 数据记录规则" not in after["messages"][0]["content"]
    assert (
        len(after["messages"][0]["content"])
        < len(before["messages"][0]["content"]) * 0.7
    )


@pytest.mark.asyncio
async def test_diet_provider_budget_replay(db, auth_user_and_headers, monkeypatch):
    from tests.test_agent_diet_synthesis_projection import _run

    user, _ = auth_user_and_headers
    pairs = []
    for enabled in (False, True):
        monkeypatch.setattr(ae.settings, "domain_prompt_optimization", enabled)
        _, calls, _, done, _ = await _run(
            db, user, monkeypatch, query="今天我吃的怎么样?", client_turn_id=f"budget-{enabled}"
        )
        assert done["completion_status"] == "complete"
        pairs.append({"enabled": enabled, "calls": calls})
    if output := os.environ.get("REVA_ARCHITECTURE_DIET_PAYLOADS"):
        Path(output).write_text(json.dumps(pairs, ensure_ascii=False, indent=2) + "\n")
    before, after = pairs[0]["calls"][-1], pairs[1]["calls"][-1]
    assert not after.get("tools")
    assert before["messages"][1:] == after["messages"][1:]
    assert (
        len(after["messages"][0]["content"])
        < len(before["messages"][0]["content"]) * 0.7
    )


@pytest.mark.parametrize(
    "payload",
    [
        '{ "unclosed": 1',
        'Error: { "available": false }',
        '{ "value": NaN }',
        '{ "value": Infinity }',
        '{ "value": 01 }',
        '{ "value": "unescaped\nline" }',
        "{" * 1500,
    ],
)
def test_malformed_results_remain_opaque(payload):
    from app.services.llm.prompt_transport import compact_tool_json

    messages = [{"role": "tool", "content": payload, "tool_call_id": "opaque"}]
    assert compact_tool_json(messages) == messages


def test_transport_preserves_json_escaping_multimodal_and_disabled_payload(monkeypatch):
    from app.services.llm.prompt_transport import compact_tool_json

    values = ["with  spaces", 'quoted " value', "\\", '\\"', "\n\t", "中文", "\\u0020"]
    messages = [
        {"role": "tool", "content": json.dumps(values, indent=2, ensure_ascii=True)},
        {"role": "tool", "content": [{"type": "text", "text": '{ "n": 1 }'}]},
    ]
    result = compact_tool_json(messages)
    assert json.loads(result[0]["content"]) == values
    assert result[1] == messages[1]
    monkeypatch.setattr(ae.settings, "domain_prompt_optimization", False)
    assert ae.AgentExecutor._transport_messages(object(), messages) is messages


def test_budget_distinguishes_dialogue_tool_results_and_call_arguments():
    calls = [{'id': 'read', 'type': 'function', 'function': {'name': 'health_query', 'arguments': '{"dimension":"sleep"}'}}]
    messages = [
        {'role': 'system', 'content': 'SYS'},
        {'role': 'assistant', 'content': 'previous'},
        {'role': 'user', 'content': 'question'},
        {'role': 'assistant', 'content': '', 'tool_calls': calls},
        {'role': 'tool', 'content': '{"records":[]}'},
    ]
    budget = ae._prompt_payload_budget(messages)
    assert budget['tool_result_chars'] == len('{"records":[]}')
    assert budget['dialogue_chars'] == len('previous')
    assert budget['tool_call_chars'] == len(json.dumps(calls, ensure_ascii=False, separators=(',', ':')))
    assert budget['history_chars'] == budget['dialogue_chars'] + budget['tool_result_chars']
    assert budget['input_approx_tokens'] == (len('SYSpreviousquestion{"records":[]}') + budget['tool_call_chars']) // 4
