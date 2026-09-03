# -*- coding: utf-8 -*-
"""小巴 QUERY 回答里泄漏工具结果原始 JSON 的抑制护栏 (Fix A)。

回归 bug: 弱模型 (qwen3.7-max) 在合成轮把工具结果原始 JSON 数组粘进可见回答,
例如对"午餐的wagas没有记录下来吗?"回复:
    `让我查一下今天的饮食记录…[{"record_date":"2026-07-01","meal_type":"breakfast",...}]`
而不是"今天只有早餐记录,没有午餐"。

护栏是**锚定**的 (anchored allowlist, 非"任何 JSON"):
  - 内嵌 JSON 的键必须与已知工具结果字段白名单相交 ≥ 阈值才判泄漏;
  - 用户主动要的 ```json 代码块 / app 渲染的 ```reva-ui``` 图表块**绝不**被动;
  - 仅提及字段名的普通散文永不触发。
两方向都要钉死 (纪律见 memory「加固一道闸后必对加固本身跑对抗复审」)。
"""
import json

import pytest

from app.services.agent_executor import (
    AgentExecutor,
    _leaks_tool_result_json,
    _streaming_leak_forming,
    _natural_language_from_tool_results,
)


# ── 谓词单测: 泄漏方向 (必须判 True) ─────────────────────────────────────────


def test_preamble_plus_embedded_tool_result_array_is_a_leak():
    txt = (
        "让我查一下今天的饮食记录…"
        '[{"record_date":"2026-07-01","meal_type":"breakfast",'
        '"food_items":"小米粥","calories":220}]'
    )
    assert _leaks_tool_result_json(txt) is True


def test_bare_tool_result_object_is_a_leak():
    txt = '{"record_date":"2026-07-01","meal_type":"lunch","protein":30}'
    assert _leaks_tool_result_json(txt) is True


def test_smart_quote_leak_from_weak_model_is_caught():
    # 弱模型吐全角引号的非法 JSON — 宽松解析仍要识别为泄漏。
    txt = '让我看看…[{“record_date”:“2026-07-01”,“meal_type”:“breakfast”,“calories”:220}]'
    assert _leaks_tool_result_json(txt) is True


def test_streaming_forming_catches_truncated_leak_early():
    # 流式期 JSON 还没吐完、raw_decode 尚不能解析,但已现两个带引号冒号的白名单键。
    partial = '今天的记录[{"meal_type":"breakfast","food_id":"x"'
    assert _streaming_leak_forming(partial) is True


# ── 谓词单测: 非泄漏方向 (必须判 False, 不误伤) ──────────────────────────────


def test_user_requested_json_code_block_is_not_touched():
    txt = (
        "这是你要的 JSON:\n"
        "```json\n"
        '{"record_date":"2026-07-01","meal_type":"breakfast"}\n'
        "```"
    )
    assert _leaks_tool_result_json(txt) is False
    assert _streaming_leak_forming(txt) is False


def test_reva_ui_chart_block_is_not_touched():
    txt = (
        "你的睡眠趋势:\n"
        "```reva-ui\n"
        '{"type":"line_chart","data":[{"record_date":"2026-07-01"}]}\n'
        "```"
    )
    assert _leaks_tool_result_json(txt) is False
    assert _streaming_leak_forming(txt) is False


def test_menu_share_block_is_not_touched():
    txt = (
        "今晚晚餐建议:\n"
        "```menu_share\n"
        '{"title":"晚餐","items":[{"name":"鸡胸肉","calories":220}]}\n'
        "```"
    )
    assert _leaks_tool_result_json(txt) is False
    assert _streaming_leak_forming(txt) is False


def test_prose_merely_mentioning_a_field_name_is_not_a_leak():
    txt = "今天 record_date 是 7 月 1 号, 你的 meal_type 只有早餐, 没有午餐。"
    assert _leaks_tool_result_json(txt) is False
    assert _streaming_leak_forming(txt) is False


def test_single_stray_allowlist_field_is_not_a_leak():
    # 只有一个白名单字段 (< 2 命中阈值) — 可能是用户主动贴的合法 JSON, 不动。
    assert _leaks_tool_result_json('{"calories": 500}') is False
    assert _streaming_leak_forming('结果:{"weight": 72}') is False


def test_long_analysis_then_small_json_is_not_over_alarmed():
    # 一整句分析后才嵌一个小 JSON — 前言超过阈值, 宁可漏判也不误伤合法分析。
    txt = (
        "你的睡眠质量本周有所改善,HRV 从 45 上升到 52,深睡比例提升。综合来看总体向好。"
        '这里给出一个数据示例(仅供参考):{"weight":72,"protein":30}'
    )
    assert _leaks_tool_result_json(txt) is False
    assert _streaming_leak_forming(txt) is False


def test_non_allowlist_json_is_not_a_leak():
    # menu_share / reva-ui 字段 (title/reason) 不在工具结果白名单 → 不误判。
    assert _leaks_tool_result_json('{"title":"晚餐","reason":"控碳"}') is False


# ── 兜底: 工具结果 → 中性人话 ────────────────────────────────────────────────


def test_natural_language_fallback_prefers_tool_message_field():
    msgs = [{"role": "tool", "content": json.dumps({"message": "今天只有早餐记录,没有午餐"}, ensure_ascii=False)}]
    assert _natural_language_from_tool_results(msgs) == "今天只有早餐记录,没有午餐"


@pytest.mark.asyncio
async def test_tool_round_preamble_is_not_streamed_or_persisted(
    db,
    auth_user_and_headers,
):
    """工具决策轮 content 是模型自述, 不属于最终回答。"""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = {"n": 0}
    preamble = (
        "I'll pull today's activity data to give you an accurate summary.\n\n"
        "Let me query your wearable and activity records.\n\n"
        "I'll query your activity data for today."
    )
    final_answer = "今天活动汇总: 步数 8000, 活动量稳定。"

    async def fake_call_llm_stream(messages, tools):
        calls["n"] += 1
        if calls["n"] == 1:
            assert tools
            yield {"type": "content", "text": preamble}
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "c1",
                "type": "function",
                "function": {
                    "name": "health_query",
                    "arguments": json.dumps(
                        {"dimension": "activity", "days": 1},
                        ensure_ascii=False,
                    ),
                },
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
            return
        yield {"type": "content", "text": final_answer}
        yield {"type": "finish", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        return json.dumps({"message": "今天步数 8000"}, ensure_ascii=False)

    executor._call_llm_stream = fake_call_llm_stream
    executor._execute_tool = fake_execute_tool

    events = [
        e async for e in executor.run_stream(
            user_id=user.id,
            message="总结我这一天的活动",
            user_auth_token="test-token",
        )
    ]

    token_texts = "".join(
        e["data"]["content"] for e in events if e.get("event") == "token"
    )
    assert "I'll pull" not in token_texts
    assert "Let me query" not in token_texts
    assert final_answer in token_texts

    from app.models.agent_conversation import AgentMessage

    saved = db.query(AgentMessage).filter_by(role="assistant").one()
    assert "I'll pull" not in saved.content
    assert "Let me query" not in saved.content
    assert final_answer in saved.content


# ── 端到端 run_stream: (a) 泄漏被抑制 → 落库自然语言, 不含裸 JSON ──────────────


async def test_run_stream_query_json_leak_is_suppressed_and_stored_clean(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    rounds = []

    leak_deltas = [
        "让我查一下今天的饮食记录…",
        '[{"record_date":"2026-07-01",',
        '"meal_type":"breakfast",',
        '"food_items":"小米粥","calories":220}]',
    ]

    async def fake_call_llm_stream(messages, tools):
        rounds.append(len(rounds))
        if len(rounds) == 1:
            # round 1: 结构化查询工具调用
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "health_query",
                             "arguments": json.dumps({"dimension": "diet", "days": 1})},
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            # round 2 (合成轮, round_tools 空): 弱模型泄漏工具结果 JSON
            for d in leak_deltas:
                yield {"type": "content", "text": d}
            yield {"type": "finish", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        # 工具结果自带一句人话 message → 兜底直接用它, 无需再调模型。
        return json.dumps({"message": "今天只有早餐记录,没有午餐"}, ensure_ascii=False)

    executor._call_llm_stream = fake_call_llm_stream
    executor._execute_tool = fake_execute_tool

    events = [
        e async for e in executor.run_stream(
            user_id=user.id, message="午餐的wagas没有记录下来吗?", user_auth_token="test-token",
        )
    ]

    token_texts = "".join(
        e["data"]["content"] for e in events if e.get("event") == "token"
    )
    # 原始 JSON / 字段名绝不外泄 (live token 侧)
    assert "record_date" not in token_texts
    assert "meal_type" not in token_texts
    assert '[{"' not in token_texts
    # 换成自然语言
    assert "今天只有早餐记录,没有午餐" in token_texts

    # 落库的完整回复也是干净的 (reload 侧)
    from app.models.agent_conversation import AgentMessage
    saved = db.query(AgentMessage).filter_by(role="assistant").one()
    assert "record_date" not in saved.content
    assert "meal_type" not in saved.content
    assert "今天只有早餐记录,没有午餐" in saved.content


# ── 端到端 run_stream: (b) 用户要的 ```json``` / ```reva-ui``` 块不被动 ─────────


async def test_run_stream_user_requested_json_block_is_not_suppressed(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)

    # 用户明确要一段 JSON 示例 — fenced ```json 块含白名单字段 (calories/protein/carbs)。
    # 若护栏是"任何含白名单键的 JSON 都吃掉", 这段就会被误伤; 正确行为是:遇 fenced
    # 围栏一律豁免, 原样流给用户。(用不含 food_items/meal_type 的对象, 避免撞上既有
    # inline tool-call 恢复路径 — 那是另一条护栏, 与本 leak-suppressor 无关。)
    answer_deltas = [
        "当然, 这是营养字段的 JSON 示例:\n",
        "```json\n",
        '{"calories": 220,',
        '"protein": 30,',
        '"carbs": 12}\n',
        "```",
    ]

    async def fake_call_llm_stream(messages, tools):
        for d in answer_deltas:
            yield {"type": "content", "text": d}
        yield {"type": "finish", "finish_reason": "stop"}

    executor._call_llm_stream = fake_call_llm_stream

    events = [
        e async for e in executor.run_stream(
            user_id=user.id, message="给我一个营养字段的 JSON 示例", user_auth_token=None,
        )
    ]

    token_texts = "".join(
        e["data"]["content"] for e in events if e.get("event") == "token"
    )
    # fenced 代码块原样保留 (用户主动要的内容不能被 leak-suppressor 吃掉)
    assert "```json" in token_texts
    assert '"calories": 220' in token_texts
    assert '"protein": 30' in token_texts

    # 落库同样完整保留 (reload 侧)
    from app.models.agent_conversation import AgentMessage
    saved = db.query(AgentMessage).filter_by(role="assistant").one()
    assert "```json" in saved.content
    assert '"calories": 220' in saved.content
