# -*- coding: utf-8 -*-
"""诚实不变量: 查询/分析回合绝不谎报写入("✅ 已记录")。

Live prod violation (2026-07-13, agent_messages id=6334, user 3):
  问题「从我的基因、生活习惯、睡眠、心率、HRV 记录出发,推断一下我胃溃疡的根因。」
  —— 纯分析/查询,无任何记录意图 —— 却答:
    「已查到相关记录，但这轮没能整理成回答；请再说一次要改哪一条
     ✅ 已记录
     可穿戴 daily 数据 (最近 8 天, …): …
     查到 10 条记录（记录号: 35, 34, 33, 30, 32）」
  meta: tools_used=[health_query, health_manage], write_receipts=[], finish_reason=tool_calls。
  本轮**没有任何写入**(write_receipts 空),纯读工具却被答成"✅ 已记录"。

双重误判复合:
  1. _prefer_fast_record_model 误判: _RECORD_INTENT_RE 命中名词"记录"(HRV 记录),
     _ADVICE_OR_ANALYSIS_RE 未含"推断/根因" → 分析问句被当成记录意图。
  2. 名字级写工具判断: _round_executed_write_tool / _turn_had_write_tool 用
     `tool ∈ {health_record, health_manage}` 判"写",把 health_manage 的 list/query(读,
     用来找记录 ID)误判为写 → 触发确定性"已记录…"兜底。

修复(诚实不变量,fail-closed): 确定性"已记录…"回复只允许在本轮产生了**可验证的
写入回执**(write_receipts,由 _write_tool_attempted 判定: health_manage 仅
update/delete 算写)后出现。无回执 → fall through 合成轮,让模型用工具结果作答。

两方向都钉死(memory「加固一道闸后必对加固本身跑对抗复审」):
  - 只读回合(含 health_manage list) → 绝不"已记录"(test 1 / test 2);
  - 真写入回合 → 仍正常"已记录…"确认,不被过度抑制(test 3 正向控制)。
"""
import json
from unittest.mock import AsyncMock

from app.services.agent_executor import AgentExecutor
from app.services.utterance_intent_classifier import classify_agent_utterance
from app.models.agent_conversation import AgentMessage


def _tokens(events) -> str:
    return "".join(
        e["data"]["content"] for e in events if e.get("event") == "token"
    )


# ── Test 1: 旗舰复现 — 分析问句 + 只读工具(query + manage-list) → 绝不谎报写入 ──


async def test_analysis_turn_with_read_only_tools_never_claims_record(db, auth_user_and_headers):
    """turn 6334 的精确复现: 分析问句被误路由为记录 (_prefer_fast_record_model),
    本轮只有 health_query + health_manage(list),无写入 → 必须 fall through 合成轮,
    绝不吐出 ✅ 已记录 / 要改哪一条 / 查到 N 条 / 裸工具结果。"""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    rounds = []

    # 分析问句(与 prod 逐字一致): 即使含“记录”名词，也必须落到语义分析回合。
    analysis_question = "从我的基因、生活习惯、睡眠、心率、HRV 记录出发,推断一下我胃溃疡的根因。"
    assert classify_agent_utterance(analysis_question).primary == "advice"

    honest_analysis = "根据你的 HRV、睡眠与作息数据,胃溃疡更可能与压力和不规律饮食相关(相关非因果)。"

    async def fake_call_llm_stream(messages, tools):
        rounds.append(len(rounds))
        if len(rounds) == 1:
            # round 1: 三个**只读**工具调用, 无文本内容, finish=tool_calls。
            yield {"type": "tool_calls", "tool_calls": [
                {"id": "c1", "type": "function", "function": {
                    "name": "health_query",
                    "arguments": json.dumps({"dimension": "wearable", "days": 8})}},
                {"id": "c2", "type": "function", "function": {
                    "name": "health_query",
                    "arguments": json.dumps({"dimension": "steps", "days": 1})}},
                {"id": "c3", "type": "function", "function": {
                    "name": "health_manage",
                    "arguments": json.dumps({"operation": "list", "record_type": "diet"})}},
            ]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            # round 2 (合成轮): 模型用工具结果给出诚实分析。
            for ch in honest_analysis:
                yield {"type": "content", "text": ch}
            yield {"type": "finish", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
        if tool_name == "health_query" and args.get("dimension") == "wearable":
            # 可穿戴纯文本读数 (prod 里走 show-as-is 分支被 dump 进正文)。
            return (
                "可穿戴 daily 数据 (最近 8 天, 多源按设备优先级合并): 数据源: apple-watch, garmin, "
                "unknown。 - 2026-07-13: 总消耗 56kcal - 2026-07-12: 步数 4474, 静息心率 59bpm"
            )
        if tool_name == "health_query":
            # dict 无 message 字段 + 无可识别记录形状 → prod 里被 _friendly_record_confirmation
            # 误判成裸 "✅ 已记录"。
            return json.dumps({"id": 5, "steps": 4474}, ensure_ascii=False)
        if tool_name == "health_manage":
            # list 结果 = 记录数组 (读,找 ID) → prod 里被答成 "查到 N 条记录"。
            return json.dumps(
                [{"id": 35}, {"id": 34}, {"id": 33}, {"id": 30}, {"id": 32}],
                ensure_ascii=False,
            )
        raise AssertionError(f"unexpected tool {tool_name}")

    executor._call_llm_stream = fake_call_llm_stream
    executor._execute_tool = fake_execute_tool

    events = [
        e async for e in executor.run_stream(
            user_id=user.id, message=analysis_question, user_auth_token="test-token",
        )
    ]
    reply = _tokens(events)

    # 诚实不变量: 只读回合绝不谎报写入。
    assert "已记录" not in reply, reply
    assert "✅" not in reply, reply
    assert "要改哪一条" not in reply, reply
    assert "查到" not in reply and "条记录" not in reply, reply
    # 裸工具结果也不外泄。
    assert "apple-watch" not in reply and "数据源" not in reply, reply
    assert "[{" not in reply and '"steps"' not in reply, reply
    # 走到了合成轮 (round 2 存在) 并给出诚实分析。
    assert len(rounds) >= 2, rounds
    assert "胃溃疡" in reply, reply

    # 落库(reload 侧)同样干净。
    saved = db.query(AgentMessage).filter_by(role="assistant").one()
    assert "已记录" not in saved.content
    assert "要改哪一条" not in saved.content
    assert "查到" not in saved.content


# ── Test 2: 记录**修改/删除**回合的 list-only 轮 — 找 ID 时也绝不谎报 ──────────────


async def test_record_modify_list_lookup_round_never_claims_record(db, auth_user_and_headers):
    """用户要**删除**一条记录 → 模型先 health_manage(list) 找 ID(读,未删)。
    本轮无写入回执 → 绝不"✅ 已记录"(prod 5868/5559/4661 那一类的病根)。"""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    rounds = []

    modify_question = "删除今天下午加餐那条记录。"
    intent = classify_agent_utterance(modify_question)
    assert (intent.primary, intent.operation) == ("mutate", "delete")

    honest_lookup = "找到今天下午加餐那条记录(记录号 34),确认要删除吗?"

    async def fake_call_llm_stream(messages, tools):
        rounds.append(len(rounds))
        if len(rounds) == 1:
            for ch in "已删除今天的下午加餐。":
                yield {"type": "content", "text": ch}
            yield {"type": "tool_calls", "tool_calls": [
                {"id": "c1", "type": "function", "function": {
                    "name": "health_manage",
                    "arguments": json.dumps({"operation": "list", "record_type": "diet"})}},
            ]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            for ch in honest_lookup:
                yield {"type": "content", "text": ch}
            yield {"type": "finish", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        return json.dumps([{"id": 34, "meal_type": "snack"}], ensure_ascii=False)

    executor._call_llm_stream = fake_call_llm_stream
    executor._execute_tool = fake_execute_tool

    events = [
        e async for e in executor.run_stream(
            user_id=user.id, message=modify_question, user_auth_token="test-token",
        )
    ]
    reply = _tokens(events)

    assert "已记录" not in reply, reply
    assert "✅" not in reply, reply
    assert "已删除" not in reply, reply  # 还没删,更不能谎称删了
    assert len(rounds) >= 2, rounds
    assert "确认要删除吗" in reply, reply


# ── Test 3: 正向控制 — 真写入回合仍正常确认,不被过度抑制 ──────────────────────


async def test_verified_write_still_confirms_record(db, auth_user_and_headers):
    """反向证伪(不 over-suppress): health_record 真写入 → 结构化回执(id)→ write_receipts
    非空 → 确定性"已记录…"确认照常产出。gate 只挡无回执的假宣称,不挡真写入。"""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    rounds = []

    record_question = "记录一下我喝了 500ml 水。"
    assert classify_agent_utterance(record_question).primary == "write"

    async def fake_call_llm_stream(messages, tools):
        rounds.append(len(rounds))
        # 单轮: 写工具调用后 finish=tool_calls (fast-record 路径跳过合成轮)。
        yield {"type": "tool_calls", "tool_calls": [
            {"id": "c1", "type": "function", "function": {
                "name": "health_record",
                "arguments": json.dumps({"record_type": "water",
                                         "data": {"amount": 500, "drink_type": "water"}})}},
        ]}
        yield {"type": "finish", "finish_reason": "tool_calls"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        # 结构化写入回执: 带 id + resource_type + 人话 message。
        return json.dumps(
            {"id": 701, "resource_type": "water_record", "amount": 500,
             "drink_type": "water", "message": "已记录饮水 500ml"},
            ensure_ascii=False,
        )

    executor._call_llm_stream = fake_call_llm_stream
    executor._execute_tool = fake_execute_tool

    events = [
        e async for e in executor.run_stream(
            user_id=user.id, message=record_question, user_auth_token="test-token",
        )
    ]
    reply = _tokens(events)

    # 真写入 → 确认照常。
    assert "已记录" in reply, reply
    # 单轮直出,未被逼进合成轮 (证明 gate 没把真写入误当只读)。
    assert len(rounds) == 1, rounds


async def test_record_intent_with_only_read_tool_cannot_claim_recorded(
    db, auth_user_and_headers
):
    """Counter-regression for the pending-confirmation fix.

    A read tool is still not a write attempt. The second model round cannot turn
    that read result into a fake success claim, and meta must keep the no-write
    signal observable.
    """
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    rounds = 0

    async def fake_call_llm_stream(messages, tools):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            yield {
                "type": "tool_calls",
                "tool_calls": [{
                    "id": "read-weight",
                    "type": "function",
                    "function": {
                        "name": "health_query",
                        "arguments": json.dumps({"dimension": "weight", "days": 1}),
                    },
                }],
            }
            yield {"type": "finish", "finish_reason": "tool_calls"}
            return
        for ch in "已记录体重 71.4kg。":
            yield {"type": "content", "text": ch}
        yield {"type": "finish", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        assert tool_name == "health_query"
        return json.dumps({"weight": 71.4}, ensure_ascii=False)

    executor._call_llm_stream = fake_call_llm_stream
    executor._execute_tool = fake_execute_tool

    events = [
        event async for event in executor.run_stream(
            user_id=user.id,
            message="记录体重 71.4kg",
            user_auth_token="test-token",
        )
    ]
    reply = _tokens(events)
    done = next(event for event in events if event.get("event") == "done")

    assert "已记录体重" not in reply
    assert done["data"]["write_receipts"] == []
    assert done["data"]["record_intent_no_tool"] is True


async def test_second_write_failure_never_streams_success_preamble(
    db, auth_user_and_headers
):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    rounds = 0
    tool_calls = 0
    message = "把第一条和第二条饮水记录都改成 500ml。"
    assert classify_agent_utterance(message).primary == "mutate"

    async def fake_call_llm_stream(messages, tools):
        nonlocal rounds
        rounds += 1
        preamble = "第一条已修改。" if rounds == 1 else "第二条也已修改。"
        for ch in preamble:
            yield {"type": "content", "text": ch}
        record_id = rounds
        yield {"type": "tool_calls", "tool_calls": [{
            "id": f"write-{rounds}",
            "type": "function",
            "function": {
                "name": "health_manage",
                "arguments": json.dumps({
                    "record_type": "water",
                    "operation": "update",
                    "record_id": record_id,
                    "data": {"amount": 500},
                }),
            },
        }]}
        yield {"type": "finish", "finish_reason": "tool_calls"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        nonlocal tool_calls
        tool_calls += 1
        if tool_calls == 1:
            return json.dumps({
                "id": 1,
                "resource_type": "water_record",
                "message": "第一条饮水记录已修改",
            }, ensure_ascii=False)
        return "Error: update failed"

    executor._call_llm_stream = fake_call_llm_stream
    executor._execute_tool = fake_execute_tool

    events = [
        event async for event in executor.run_stream(
            user_id=user.id,
            message=message,
            user_auth_token="test-token",
        )
    ]
    reply = _tokens(events)

    assert tool_calls == 2
    assert "第一条已修改" not in reply
    assert "第二条也已修改" not in reply
    assert "无法确认" in reply or "暂时" in reply


# ── Test 4: 生产实锤 — 模型零工具 + 确定性写入失败 → 绝不谎称已记录 ──


async def test_failed_deterministic_symptom_write_never_streams_the_claim(
    db, auth_user_and_headers
):
    """founder 2026-07-17 09:21 生产现场逐字复现(user=3, 24h 内 2 次)。

    弱模型对「麦当劳店记录打了一个喷嚏。」**一个工具都没调**, 直接吐出
    「✅ **症状已记录**:打喷嚏(上午 09:21)」—— 这段字**已经流到屏幕上**。
    founder 看到绿对勾就不会重记, 那条带环境线索(油烟)的喷嚏永久丢失。

    此前 :7228 的诚实覆盖(final_text=_record_intent_needs_detail_message +
    streamed_to_client=False)**本身是对的**, 但它跑在 token 已 yield 之后 —— 只改了落库
    消息, 救不回已下发的字。修法 = 在 :6374 的下发门里加 not (_prefer_fast_record_model
    and tool_executed_count == 0), 让既有的覆盖真正生效。

    现在明确症状陈述会补一次确定性 health_record 写入。这条测试
    故意让该写入失败，验证未经回执的「已记录」仍然不会流到屏幕。
    """
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)

    sneeze_msg = "麦当劳店记录打了一个喷嚏。"
    # 前置断言: 该句仍是明确写入回合，不能因无工具调用而谎称成功。
    assert classify_agent_utterance(sneeze_msg).primary == "write"

    the_lie = "✅ **症状已记录**:打喷嚏(上午 09:21)\n\n是在店里闻到油烟味诱发的吗?"
    tools_called = []

    async def fake_call_llm_stream(messages, tools):
        # 生产现场:零 tool_calls, 直接把"已记录"当答案吐出来。
        for ch in the_lie:
            yield {"type": "content", "text": ch}
        yield {"type": "finish", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        tools_called.append(tool_name)
        raise RuntimeError("模拟症状写入失败")

    executor._call_llm_stream = fake_call_llm_stream
    executor._execute_tool = fake_execute_tool

    events = [
        e async for e in executor.run_stream(
            user_id=user.id, message=sneeze_msg, user_auth_token="test-token",
        )
    ]
    reply = _tokens(events)

    assert tools_called == ["health_record"], "明确症状应尝试确定性写入"
    # 承重墙: 未经验证的写入声明**绝不**出现在下发给用户的 token 流里。
    assert "已记录" not in reply, f"未验证的『已记录』流到了用户屏幕上: {reply!r}"
    assert "✅" not in reply, reply
    # 而且要给出诚实的替代文案(不是留空)。
    assert reply.strip(), "抑制之后必须补发诚实回复, 不能什么都不发"


async def test_partial_diet_correction_uses_deterministic_update_without_false_claim(
    db, auth_user_and_headers
):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    message = "今天我没吃那么多，晚餐的两千大卡只有吃了四分之一"
    rounds = 0
    executed = []

    async def fake_call_llm_stream(messages, tools):
        nonlocal rounds
        rounds += 1
        text = (
            "好的，已经帮你保存晚餐。"
            if rounds == 1
            else "已按实际吃掉的四分之一更新晚餐。"
        )
        for ch in text:
            yield {"type": "content", "text": ch}
        yield {"type": "finish", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        executed.append((tool_name, args))
        return json.dumps({
            "id": 829,
            "resource_type": "diet_record",
            "message": "已更新晚餐记录",
        }, ensure_ascii=False)

    executor._call_llm_stream = fake_call_llm_stream
    executor._api_get_json = AsyncMock(return_value=([{
        "id": 829,
        "meal_type": "dinner",
        "food_items": "三文鱼 + 黎麦沙拉 + 羊乳酪",
        "calories": 2000,
        "protein": 80,
        "carbs": 120,
        "fat": 100,
        "fiber": 16,
    }], None))
    executor._execute_tool = fake_execute_tool

    events = [
        event async for event in executor.run_stream(
            user_id=user.id,
            message=message,
            user_auth_token="test-token",
        )
    ]
    reply = _tokens(events)

    assert executed == [(
        "health_manage",
        {
            "record_type": "diet",
            "operation": "update",
            "record_id": 829,
            "data": {
                "meal_type": "dinner",
                "calories": 500.0,
                "protein": 20.0,
                "carbs": 30.0,
                "fat": 25.0,
                "fiber": 4.0,
            },
        },
    )]
    assert "好的，已经帮你保存晚餐" not in reply
    assert "已按实际吃掉的四分之一更新晚餐" in reply


async def test_ambiguous_partial_diet_correction_never_claims_an_update(
    db, auth_user_and_headers
):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    message = "午餐没有全吃完，只吃了三分之一"
    rounds = 0
    executed = []

    async def fake_call_llm_stream(messages, tools):
        nonlocal rounds
        rounds += 1
        text = "已按三分之一更新午餐。"
        for ch in text:
            yield {"type": "content", "text": ch}
        yield {"type": "finish", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        executed.append((tool_name, args))
        return json.dumps([
            {"id": 830, "meal_type": "lunch", "calories": 600},
            {"id": 829, "meal_type": "lunch", "calories": 450},
        ], ensure_ascii=False)

    executor._call_llm_stream = fake_call_llm_stream
    executor._api_get_json = AsyncMock(return_value=([
        {"id": 830, "meal_type": "lunch", "calories": 600},
        {"id": 829, "meal_type": "lunch", "calories": 450},
    ], None))
    executor._execute_tool = fake_execute_tool

    events = [
        event async for event in executor.run_stream(
            user_id=user.id,
            message=message,
            user_auth_token="test-token",
        )
    ]
    reply = _tokens(events)

    assert executed and executed[0][1]["operation"] == "list"
    assert all(args["operation"] != "update" for _name, args in executed)
    assert "已按三分之一更新午餐" not in reply
    assert "多条" in reply and "选择" in reply
