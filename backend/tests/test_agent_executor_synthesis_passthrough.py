# -*- coding: utf-8 -*-
"""Pi keeps ownership of synthesis regardless of obsolete passthrough flags.

The final model answer still passes the shared output guard and preserves safe
menu-share cards. Tool-side candidate answers are never stored as shadow text.
"""
import json

import pytest

from app.config import settings
from app.models.agent_conversation import AgentMessage
from app.services.agent_executor import AgentExecutor
from app.services.inline_cards import extract_inline_card_blocks


# orchestrator 自产、已过 R4 的合成答案(passthrough 会直接透传它)。
_ORCH_SYNTH = "根据你近一周的数据,睡眠与恢复整体稳定;建议保持规律作息,傍晚少量有氧。"
# 二次合成轮(强模型复述)会产出的、可区分的另一段文本。
_RESYNTH = "综合来看,你的恢复状态良好,继续保持即可。"


def _orch_tool_result(synthesis: str) -> str:
    """模拟 _exec_health_analysis → _project_orchestrator_result 的投影形(带 synthesis 字段)。"""
    return json.dumps(
        {
            "synthesis": synthesis,
            "intent": "recovery",
            "used_specialists": ["RecoveryCoach"],
            "findings": [],
            "perf": {"total_ms": 3200},
        },
        ensure_ascii=False,
    )


def _make_executor(db, *, orch_synthesis: str = _ORCH_SYNTH, extra_tool: bool = False, final_synthesis: str = _RESYNTH):
    """装配一个 executor,round1 调 orchestrator(可选再并一个 health_query),round2 二次合成。

    返回 (executor, rounds_list)。rounds_list 记录 _call_llm_stream 被调用的次数 ——
    Pi 完整执行工具轮和最终回答轮，旧 passthrough 开关不改变循环所有权。
    """
    executor = AgentExecutor(db)
    rounds: list = []

    async def fake_call_llm_stream(messages, tools):
        rounds.append(len(rounds))
        if len(rounds) == 1:
            tool_calls = [
                {
                    "id": "orch1",
                    "type": "function",
                    "function": {
                        "name": "health_analysis",
                        "arguments": json.dumps(
                            {"analysis_type": "orchestrator", "question": "综合分析一下我的恢复"},
                            ensure_ascii=False,
                        ),
                    },
                }
            ]
            if extra_tool:
                tool_calls.append(
                    {
                        "id": "q1",
                        "type": "function",
                        "function": {
                            "name": "health_query",
                            "arguments": json.dumps({"dimension": "sleep", "days": 7}),
                        },
                    }
                )
            yield {"type": "tool_calls", "tool_calls": tool_calls}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            # round2 = 二次合成轮(仅在未短路时到达):产出可区分的复述文本。
            yield {"type": "content", "text": final_synthesis}
            yield {"type": "finish", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        if tool_name == "health_analysis":
            return _orch_tool_result(orch_synthesis)
        if tool_name == "health_query":
            # 查询结果自带一句人话 message(证明多工具回合确实拿了别的数据要融合)。
            return json.dumps({"message": "近 7 天平均睡眠 7.1 小时"}, ensure_ascii=False)
        return json.dumps({"message": "ok"}, ensure_ascii=False)

    executor._call_llm_stream = fake_call_llm_stream
    executor._execute_tool = fake_execute_tool
    return executor, rounds


async def _run(executor, message="帮我综合分析一下我的睡眠和恢复"):
    events = [
        e
        async for e in executor.run_stream(
            user_id=1, message=message, user_auth_token="test-token",
        )
    ]
    tokens = "".join(
        e["data"]["content"] for e in events if e.get("event") == "token"
    )
    done = next((e["data"] for e in events if e.get("event") == "done"), {})
    return events, tokens, done


# ── off:默认,逐字节现状(双合成照跑,零 passthrough meta) ─────────────────────


async def test_off_is_byte_identical_double_synthesis(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    monkeypatch.setattr(settings, "orchestrator_synthesis_passthrough", "off", raising=False)
    executor, rounds = _make_executor(db)
    _events, tokens, done = await _run(executor)

    # 二次合成确实跑了(两轮 _call_llm_stream);用户看到的是复述文本,不是透传。
    assert len(rounds) == 2
    assert _RESYNTH in tokens
    assert _ORCH_SYNTH not in tokens
    # 无任何 passthrough meta。
    saved = db.query(AgentMessage).filter_by(role="assistant").one()
    assert "shadow_passthrough" not in (saved.meta or {})
    assert "synthesis_passthrough" not in (saved.meta or {})
    assert "synthesis_passthrough" not in done


# ── shadow:用户可见行为不变(双合成),但落 would-be passthrough 到 meta ───────────


async def test_legacy_shadow_flag_does_not_store_candidate_answers(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    monkeypatch.setattr(settings, "orchestrator_synthesis_passthrough", "shadow", raising=False)
    executor, rounds = _make_executor(db)
    _events, tokens, _done = await _run(executor)

    # 行为逐字节不变:二次合成照跑,用户看到复述文本。
    assert len(rounds) == 2
    assert _RESYNTH in tokens
    assert _ORCH_SYNTH not in tokens

    saved = db.query(AgentMessage).filter_by(role="assistant").one()
    assert "shadow_passthrough" not in (saved.meta or {})
    assert "synthesis_passthrough" not in (saved.meta or {})


async def test_legacy_shadow_flag_does_not_persist_long_orchestrator_candidate(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    monkeypatch.setattr(settings, "orchestrator_synthesis_passthrough", "shadow", raising=False)
    long_synth = "长" * 5000
    executor, _rounds = _make_executor(db, orch_synthesis=long_synth)
    await _run(executor)
    saved = db.query(AgentMessage).filter_by(role="assistant").one()
    assert "shadow_passthrough" not in (saved.meta or {})
    assert "长" * 4000 not in saved.content


# ── on:单工具深分析回合短路二次合成(透传 orchestrator synthesis) ──────────────


async def test_legacy_passthrough_flag_keeps_pi_final_model_turn(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    monkeypatch.setattr(settings, "orchestrator_synthesis_passthrough", "on", raising=False)
    executor, rounds = _make_executor(db)
    _events, tokens, done = await _run(executor)

    assert len(rounds) == 2
    assert _RESYNTH in tokens
    assert _ORCH_SYNTH not in tokens
    saved = db.query(AgentMessage).filter_by(role="assistant").one()
    assert _RESYNTH in saved.content
    assert "synthesis_passthrough" not in (saved.meta or {})
    assert "synthesis_passthrough" not in done
    assert done.get("completion_status") == "complete"


async def test_on_multi_tool_still_resynthesizes_fail_closed(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    monkeypatch.setattr(settings, "orchestrator_synthesis_passthrough", "on", raising=False)
    # 回合还并调了 health_query → 最终答案需要融合两个工具结果 → fail-closed 保留二次合成。
    executor, rounds = _make_executor(db, extra_tool=True)
    _events, tokens, _done = await _run(executor)

    assert len(rounds) == 2  # 二次合成照跑
    assert _RESYNTH in tokens
    saved = db.query(AgentMessage).filter_by(role="assistant").one()
    assert "synthesis_passthrough" not in (saved.meta or {})  # 未短路


# ── on:passthrough 文本过同一条出站护栏链(两向钉死) ─────────────────────────


async def test_pi_final_answer_suppresses_raw_json_leak(db, auth_user_and_headers, monkeypatch):
    """orchestrator synthesis 若混入裸工具结果 JSON,passthrough 也要抑制(不逃 leak 护栏)。"""
    user, _ = auth_user_and_headers
    monkeypatch.setattr(settings, "orchestrator_synthesis_passthrough", "on", raising=False)
    leak = (
        "查询结果如下:"
        '[{"record_date":"2026-07-01","meal_type":"breakfast","calories":500}]'
    )
    executor, rounds = _make_executor(db, orch_synthesis=leak, final_synthesis=leak)
    _events, tokens, _done = await _run(executor)

    assert len(rounds) == 2  # Shared final-answer guard, after the real Pi model turn.
    # 裸 JSON / 字段名绝不外泄(token 侧)。
    assert "record_date" not in tokens
    assert "meal_type" not in tokens
    assert '[{"' not in tokens
    # 落库同样干净。
    saved = db.query(AgentMessage).filter_by(role="assistant").one()
    assert "record_date" not in saved.content
    assert "meal_type" not in saved.content


async def test_pi_final_answer_preserves_menu_share_fence_for_extraction(
    db, auth_user_and_headers, monkeypatch
):
    """orchestrator synthesis 带 ```menu_share 围栏 → 不被 leak 护栏吃掉,消费层可提取成卡。"""
    user, _ = auth_user_and_headers
    monkeypatch.setattr(settings, "orchestrator_synthesis_passthrough", "on", raising=False)
    menu = (
        "给你搭一份晚餐:\n"
        "```menu_share\n"
        '{"title":"高蛋白晚餐","items":[{"name":"鸡胸肉","kcal":220},{"name":"西兰花"}]}\n'
        "```"
    )
    executor, rounds = _make_executor(db, orch_synthesis=menu, final_synthesis=menu)
    _events, tokens, _done = await _run(executor)

    assert len(rounds) == 2
    # 围栏原样透传到 token 流(未被 marker/leak 护栏剥离)。
    assert "```menu_share" in tokens
    assert "鸡胸肉" in tokens
    # 消费层(api/agent.py join token 流后)能把它提取成结构化卡片。
    cards = extract_inline_card_blocks(tokens)
    assert any(c.get("type") == "menu_share" for c in cards)
    card = next(c for c in cards if c["type"] == "menu_share")
    assert card["data"]["title"] == "高蛋白晚餐"
