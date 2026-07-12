# -*- coding: utf-8 -*-
"""A4 (plan rank9): 每回合系统知识库证据卡 memo —— pre-round-1 算一次, done 复用,
避免同回合第二次 build_twin(use_cache=False) 全量重建 (拖慢 done/receipts 与 /send)。

不变量:
  1. 同 (user,message) 无写 → 只算一次 (dedup, 消除 done 侧重建);
  2. 回合内发生写 (_turn_twin_write_occurred) → done 侧强制重算, 绝不服务写前 Twin;
  3. None 结果也 memo (避免 done 侧无谓的 twin fallback 重建);
  4. e2e: 无写回合整回合只算一次, done 卡沿用 pre-round-1 结果。
"""
import json
from unittest.mock import MagicMock

import pytest

from app.services.agent_executor import AgentExecutor, _TURN_CARD_UNSET


def _spy(cards):
    calls = {"n": 0}

    def compute(user_id, message):
        calls["n"] += 1
        return cards(calls["n"]) if callable(cards) else cards

    return compute, calls


def test_card_memoized_within_turn_no_write():
    ex = AgentExecutor(db=MagicMock())
    compute, calls = _spy(lambda n: {"type": "system_knowledge_evidence", "data": {"n": n}})
    ex._compute_system_knowledge_evidence_card = compute

    c1 = ex._build_system_knowledge_evidence_card(7, "MTHFR-TT 该注意什么?")
    c2 = ex._build_system_knowledge_evidence_card(7, "MTHFR-TT 该注意什么?")

    assert calls["n"] == 1  # 只算一次
    assert c1 is c2


def test_card_rebuilt_after_write_not_stale():
    """核心 staleness 门: 回合内写后, done 侧不得服务写前 Twin 的卡。"""
    ex = AgentExecutor(db=MagicMock())
    compute, calls = _spy(lambda n: {"data": {"version": n}})
    ex._compute_system_knowledge_evidence_card = compute

    pre = ex._build_system_knowledge_evidence_card(7, "记一下血糖 6.1，顺便说说要注意啥")
    assert calls["n"] == 1
    assert pre["data"]["version"] == 1

    # 回合内发生写 (health_record / 化验导入等)
    ex._turn_twin_write_occurred = True

    post = ex._build_system_knowledge_evidence_card(7, "记一下血糖 6.1，顺便说说要注意啥")
    assert calls["n"] == 2  # 重算, 不复用写前 memo
    assert post["data"]["version"] == 2


def test_card_memo_keyed_on_message():
    ex = AgentExecutor(db=MagicMock())
    compute, calls = _spy(lambda n: {"data": {"n": n}})
    ex._compute_system_knowledge_evidence_card = compute

    ex._build_system_knowledge_evidence_card(7, "问题一")
    ex._build_system_knowledge_evidence_card(7, "问题二")  # 不同 message → 重算
    assert calls["n"] == 2


def test_none_result_is_memoized():
    """compute 返回 None (无匹配) 也 memo → done 不再触发无谓的 twin fallback 重建。"""
    ex = AgentExecutor(db=MagicMock())
    compute, calls = _spy(lambda n: None)
    ex._compute_system_knowledge_evidence_card = compute

    assert ex._build_system_knowledge_evidence_card(7, "无关问题") is None
    assert ex._build_system_knowledge_evidence_card(7, "无关问题") is None
    assert calls["n"] == 1


def test_initial_memo_is_unset():
    ex = AgentExecutor(db=MagicMock())
    assert ex._turn_evidence_card is _TURN_CARD_UNSET
    assert ex._turn_twin_write_occurred is False


# ── e2e: 无写回合整回合只算一次, done 卡沿用 pre-round-1 结果 ──────────────


def _wire(executor, monkeypatch, provider):
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", False)
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda **k: [])
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_user", lambda uid, db, **k: provider
    )
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")


@pytest.mark.asyncio
async def test_no_write_turn_computes_card_once_end_to_end(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = {"n": 0}

    def compute(user_id, message):
        calls["n"] += 1
        return {"type": "system_knowledge_evidence",
                "data": {"entity": {"title": "T"}, "claims": [{"doc_id": "c1"}]}}

    executor._compute_system_knowledge_evidence_card = compute

    class FakeProvider:
        model = "qwen3.7-max"

        async def chat_stream(self, **kwargs):
            yield {"type": "content", "text": "分析结论"}
            yield {"type": "finish", "finish_reason": "stop"}

        async def chat(self, **kwargs):
            return {"content": "分析结论", "finish_reason": "stop"}

    _wire(executor, monkeypatch, FakeProvider())

    events = [
        e async for e in executor.run_stream(
            user_id=user.id, message="帮我分析一下我的 MTHFR 基因该注意什么",
            user_auth_token="test-token",
        )
    ]
    done = events[-1]["data"]

    # 无写回合: pre-round-1 算一次, done 复用 memo → compute 只被调 1 次。
    assert calls["n"] == 1, calls
    # done 侧仍带上证据卡 (沿用 memo)。
    card_events = [e for e in events if e.get("event") == "card"
                   and e["data"].get("anchor") == "system_knowledge_evidence"]
    assert card_events, [e.get("event") for e in events]
