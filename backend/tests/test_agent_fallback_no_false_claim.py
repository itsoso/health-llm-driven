# -*- coding: utf-8 -*-
"""诚实不变量第三宣称面: 空回复重试链的 _fallback_text_from_tool_results 绝不谎报写入。

与 turn 6334 修复(test_agent_stream_no_false_record_claim.py)同一不变量、不同出口:
模型两轮都返回空文本时,空回复重试链会从最新工具结果组装兜底文案 —— 旧实现不看
本轮是否真的写入,只要 dict 里有 food_items/summary/preview 就答"已完成记录：…",
有 id/record_id 就答"已完成记录。",纯文本结果答"已完成操作：…"。若在**纯查询/分析
回合**(health_query 读数、health_manage list)触发双空重试,就是查询回合谎报写入。

prod 频率实测 0 次(content LIKE '%已完成记录%' / '%已完成操作%' 均无),但逻辑上是活洞。

修复(fail-closed): _fallback_text_from_tool_results 增加 keyword-only 参数
has_verified_write(默认 False —— 新调用点忘传参也绝不凭空宣称写入),调用点按
write_receipts(可验证写入回执,与 turn 6334 修复同一权威判定)传入:
  - 无回执: food_items/summary/preview → "查到：…"(查询味,不宣称写入);
    id-only 字典 / 结构化残片(含 manage-list 数组)→ 空串交回重试链
    (链有界: compact retry → fallback provider → 硬兜底文案,不会重试风暴);
  - 有回执: 与旧行为逐字节一致("已完成记录：…" / "已完成记录。" / "已完成操作：…"),
    不 over-suppress(memory「加固一道闸后必对加固本身跑对抗复审」的双向钉死)。
"""
import json

import pytest

from app.services.agent_executor import AgentExecutor, _fallback_text_from_tool_results
from app.models.agent_conversation import AgentMessage

_WRITE_CLAIMS = ("已完成记录", "已完成操作", "已记录")


def _tokens(events) -> str:
    return "".join(
        e["data"]["content"] for e in events if e.get("event") == "token"
    )


def _assert_no_write_claim(text: str) -> None:
    for claim in _WRITE_CLAIMS:
        assert claim not in text, text


# ── 单元层: 函数本体的双模行为 ────────────────────────────────────────────────


def test_unit_default_is_fail_closed_no_write_claim():
    """不传参 = fail-closed: 即使 dict 长得像记录回执,也绝不宣称写入。"""
    messages = [{"role": "tool", "content": json.dumps(
        {"food_items": "燕麦粥、水煮蛋", "total_calories": 320}, ensure_ascii=False)}]
    text = _fallback_text_from_tool_results(messages)
    _assert_no_write_claim(text)
    assert text == "查到：燕麦粥、水煮蛋"


def test_unit_no_write_receipt_query_flavor_variants():
    """无回执: 三个旧宣称分支全部改口/收口,且绝不裸露结构化残片。"""
    # food_items/summary/preview → 查询味。
    for key in ("food_items", "summary", "preview"):
        text = _fallback_text_from_tool_results(
            [{"role": "tool", "content": json.dumps({key: "步数 4474"}, ensure_ascii=False)}],
            has_verified_write=False,
        )
        _assert_no_write_claim(text)
        assert text == "查到：步数 4474"

    # id-only 字典(查询返回的记录对象)→ 空串交回重试链,不宣称任何事。
    for payload in ({"id": 35}, {"record_id": 35}):
        text = _fallback_text_from_tool_results(
            [{"role": "tool", "content": json.dumps(payload)}],
            has_verified_write=False,
        )
        assert text == ""

    # manage-list 数组(turn 6334 的读结果形状)→ 空串,绝不 "已完成操作：[{..." 泄漏。
    text = _fallback_text_from_tool_results(
        [{"role": "tool", "content": json.dumps([{"id": 35}, {"id": 34}])}],
        has_verified_write=False,
    )
    assert text == ""

    # 纯文本读数(可穿戴 readout)→ 查询味前缀,不是 "已完成操作："。
    text = _fallback_text_from_tool_results(
        [{"role": "tool", "content": "可穿戴 daily 数据: 2026-07-13 步数 4474"}],
        has_verified_write=False,
    )
    _assert_no_write_claim(text)
    assert text.startswith("查到：可穿戴 daily 数据")


def test_unit_verified_write_keeps_legacy_confirmations():
    """有回执: 旧行为逐字节保留,gate 不 over-suppress 真写入的确认。"""
    text = _fallback_text_from_tool_results(
        [{"role": "tool", "content": json.dumps({"food_items": "牛排、沙拉"}, ensure_ascii=False)}],
        has_verified_write=True,
    )
    assert text == "已完成记录：牛排、沙拉"

    text = _fallback_text_from_tool_results(
        [{"role": "tool", "content": json.dumps({"id": 701})}],
        has_verified_write=True,
    )
    assert text == "已完成记录。"

    text = _fallback_text_from_tool_results(
        [{"role": "tool", "content": "OK saved row 701"}],
        has_verified_write=True,
    )
    assert text == "已完成操作：OK saved row 701"


def test_unit_tool_message_passthrough_both_modes():
    """工具自带 message 是工具自己的话(诚实归属),两个模式都原样透传。"""
    messages = [{"role": "tool", "content": json.dumps(
        {"message": "已记录饮水 500ml", "id": 701}, ensure_ascii=False)}]
    assert _fallback_text_from_tool_results(messages, has_verified_write=True) == "已记录饮水 500ml"
    messages = [{"role": "tool", "content": json.dumps(
        {"message": "最近 3 天共 5 条饮食记录", "count": 5}, ensure_ascii=False)}]
    assert _fallback_text_from_tool_results(messages, has_verified_write=False) == "最近 3 天共 5 条饮食记录"


# ── 流式对抗: 纯查询回合 + 双空重试 → 兜底绝不谎报写入 ────────────────────────


async def test_query_turn_double_empty_retry_fallback_never_claims_write(db, auth_user_and_headers):
    """对抗主case: 纯查询问句(疑问守卫兜住,非记录路由) + 只读工具返回带 food_items 的
    dict + 模型合成轮与重试轮都吐空 → 兜底文本必须是查询味,绝不含
    已完成记录/已完成操作/已记录。"""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    rounds = []

    query_question = "我今天早餐吃了什么?"
    from app.services import agent_executor as ae
    # 前置断言: 疑问守卫命中("什么"+"?"),这确实是查询回合而非记录回合。
    assert ae._RECORD_INTERROGATIVE_GUARD_RE.search(query_question)

    async def fake_call_llm_stream(messages, tools):
        rounds.append(len(rounds))
        if len(rounds) == 1:
            yield {"type": "tool_calls", "tool_calls": [
                {"id": "c1", "type": "function", "function": {
                    "name": "health_query",
                    "arguments": json.dumps({"dimension": "diet", "days": 1})}},
            ]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            # 合成轮: 空文本(触发空回复重试链)。
            yield {"type": "finish", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        # 只读查询结果 —— dict 带 food_items,旧兜底会谎报"已完成记录：…"。
        return json.dumps(
            {"food_items": "燕麦粥、水煮蛋、拿铁", "total_calories": 480},
            ensure_ascii=False,
        )

    async def fake_call_llm(messages, tools):
        # 重试轮也空 → 走 _fallback_text_from_tool_results。
        return {"content": "", "finish_reason": "stop"}

    executor._call_llm_stream = fake_call_llm_stream
    executor._execute_tool = fake_execute_tool
    executor._call_llm = fake_call_llm

    events = [
        e async for e in executor.run_stream(
            user_id=user.id, message=query_question, user_auth_token="test-token",
        )
    ]
    reply = _tokens(events)

    # 诚实不变量: 零写入回合的兜底绝不宣称写入。
    _assert_no_write_claim(reply)
    assert "✅" not in reply, reply
    # 非空承重(防重试风暴/防静默空回复),且把查到的数据用查询味口径带出来。
    assert reply.strip(), reply
    assert "燕麦粥" in reply, reply

    # 落库(reload 侧)同样干净。
    saved = db.query(AgentMessage).filter_by(role="assistant").one()
    _assert_no_write_claim(saved.content)


async def test_query_turn_list_result_double_empty_retry_no_claim_no_leak(db, auth_user_and_headers):
    """对抗次case: manage-list 数组结果(turn 6334 的读形状) + 双空重试 → 兜底
    既不宣称"已完成操作",也不把 `[{"id":...}]` 裸 JSON 泄给用户;整条链走到
    硬兜底文案收尾(非空,有界,不风暴)。"""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    rounds = []

    async def fake_call_llm_stream(messages, tools):
        rounds.append(len(rounds))
        if len(rounds) == 1:
            yield {"type": "tool_calls", "tool_calls": [
                {"id": "c1", "type": "function", "function": {
                    "name": "health_manage",
                    "arguments": json.dumps({"operation": "list", "record_type": "diet"})}},
            ]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "finish", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        return json.dumps([{"id": 35}, {"id": 34}, {"id": 33}], ensure_ascii=False)

    async def fake_call_llm(messages, tools):
        return {"content": "", "finish_reason": "stop"}

    async def fake_call_llm_fallback_provider(messages):
        return {"content": "", "finish_reason": "stop"}

    executor._call_llm_stream = fake_call_llm_stream
    executor._execute_tool = fake_execute_tool
    executor._call_llm = fake_call_llm
    executor._call_llm_fallback_provider = fake_call_llm_fallback_provider

    events = [
        e async for e in executor.run_stream(
            user_id=user.id, message="帮我看看最近的饮食记录都有哪些?",
            user_auth_token="test-token",
        )
    ]
    reply = _tokens(events)

    _assert_no_write_claim(reply)
    assert "[{" not in reply and '"id"' not in reply, reply  # 不泄漏裸数组
    assert reply.strip(), reply  # 链末端硬兜底保证非空


# ── 正向控制: 真写入回合的双空重试,兜底仍确认"已完成记录" ──────────────────────


async def test_verified_write_double_empty_retry_still_confirms(db, auth_user_and_headers):
    """反向证伪(不 over-suppress): 非 fast-record 路由 + health_record 真写入
    (结构化回执 → write_receipts 非空) + 双空重试 → 兜底照常"已完成记录：…"。"""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    rounds = []

    record_message = "晚饭吃的牛排和沙拉,帮我登记一下。"
    from app.services import agent_executor as ae
    # 前置断言: 不命中记录意图正则 → 走普通(非 fast-record)路径,才能到空回复重试链。
    assert not ae._RECORD_INTENT_RE.search(record_message)

    async def fake_call_llm_stream(messages, tools):
        rounds.append(len(rounds))
        if len(rounds) == 1:
            yield {"type": "tool_calls", "tool_calls": [
                {"id": "c1", "type": "function", "function": {
                    "name": "health_record",
                    "arguments": json.dumps({"record_type": "diet",
                                             "data": {"food_items": "牛排、沙拉"}})}},
            ]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "finish", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        # 结构化写入回执(id + resource_type,无 message 字段 → 兜底走 food_items 分支)。
        return json.dumps(
            {"id": 702, "resource_type": "diet_record", "food_items": "牛排、沙拉"},
            ensure_ascii=False,
        )

    async def fake_call_llm(messages, tools):
        return {"content": "", "finish_reason": "stop"}

    executor._call_llm_stream = fake_call_llm_stream
    executor._execute_tool = fake_execute_tool
    executor._call_llm = fake_call_llm

    events = [
        e async for e in executor.run_stream(
            user_id=user.id, message=record_message, user_auth_token="test-token",
        )
    ]
    reply = _tokens(events)

    # 真写入 + 双空重试 → 兜底确认照常产出。
    assert "已完成记录" in reply, reply
    assert "牛排、沙拉" in reply, reply
