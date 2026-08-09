"""只读工具回合级去重 — 修 founder 2026-07-14「列出喝水记录」health_query 空转 7 次(70s)。

贪婪模型每轮重发同参 health_query → 去重后**只真执行一次**、loop 收敛出最终答案。
"""
import pytest

from app.services.agent_executor import (
    AgentExecutor,
    _is_seen_readonly_call,
    _read_operation_fingerprint,
)


def _stream_from(fake_call_llm):
    async def fake_call_llm_stream(messages, tools):
        result = await fake_call_llm(messages, tools)
        if isinstance(result, dict):
            content = result.get("content") or ""
            if content:
                yield {"type": "content", "text": content}
            tool_calls = result.get("tool_calls")
            if tool_calls:
                yield {"type": "tool_calls", "tool_calls": tool_calls}
            yield {"type": "finish", "finish_reason": result.get("finish_reason")}
        else:
            text = str(result or "")
            if text:
                yield {"type": "content", "text": text}
            yield {"type": "finish", "finish_reason": "stop"}
    return fake_call_llm_stream


# ── 指纹单元测试 ──

def test_fingerprint_identical_args_same():
    # 核心保证: 模型重发**完全相同**的调用 → 同一指纹 → 去重(founder 的空转正是同参重发)
    a = _read_operation_fingerprint("health_query", {"dimension": "water"})
    b = _read_operation_fingerprint("health_query", {"dimension": "water"})
    assert a == b


def test_fingerprint_distinguishes_different_args():
    a = _read_operation_fingerprint("health_query", {"dimension": "water"})
    c = _read_operation_fingerprint("health_query", {"dimension": "sleep"})
    assert a != c


def test_fingerprint_distinguishes_different_health_query_batch_plans():
    first = {
        "queries": [{"dimension": "sleep", "days": 7, "agg": "avg"}],
    }
    second = {
        "queries": [{"dimension": "activity", "days": 30, "agg": "sum"}],
    }

    first_fingerprint = _read_operation_fingerprint("health_query_batch", first)
    second_fingerprint = _read_operation_fingerprint("health_query_batch", second)

    assert first_fingerprint != second_fingerprint
    seen = {first_fingerprint: ("sleep-result", "sleep-result")}
    second_call = {
        "function": {
            "name": "health_query_batch",
            "arguments": '{"queries":[{"dimension":"activity","days":30,"agg":"sum"}]}',
        }
    }
    assert _is_seen_readonly_call(second_call, seen) is False


def test_fingerprint_canonicalizes_equivalent_health_query_batch_aliases():
    aliased = {
        "queries": [
            {"type": "lab_results", "time_range": "14d", "agg": "AVG"},
        ],
    }
    canonical = {
        "queries": [
            {"dimension": "medical_exam", "days": 14, "agg": "avg"},
        ],
    }

    assert _read_operation_fingerprint(
        "health_query_batch", aliased
    ) == _read_operation_fingerprint("health_query_batch", canonical)


def test_is_seen_readonly_classifies_health_manage_by_operation():
    list_args = {"record_type": "diet", "operation": "list", "date": "today"}
    seen = {
        _read_operation_fingerprint("health_query", {"dimension": "water"}): ("r", "r"),
        _read_operation_fingerprint("health_manage", list_args): ("r", "r"),
    }
    read_tc = {"function": {"name": "health_query", "arguments": '{"dimension":"water"}'}}
    list_tc = {"function": {"name": "health_manage", "arguments": '{"record_type":"diet","operation":"list","date":"today"}'}}
    update_tc = {"function": {"name": "health_manage", "arguments": '{"record_type":"diet","operation":"update","record_id":1,"data":{"food_items":"粥"}}'}}
    assert _is_seen_readonly_call(read_tc, seen) is True
    assert _is_seen_readonly_call(list_tc, seen) is True
    assert _is_seen_readonly_call(update_tc, seen) is False


# ── 全 loop 去重 ──

@pytest.mark.asyncio
async def test_repeated_water_query_executed_once_and_terminates(db, auth_user_and_headers):
    """贪婪模型每轮重发同参 health_query(water) → 真执行恰 1 次(不是 7 次), loop 终止。"""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    exec_calls: list[str] = []

    async def fake_call_llm(messages, tools):
        last = str(messages[-1].get("content") or "")
        if "工具查询轮次已经用完" in last:  # 轮次耗尽的强制合成提示
            return "你今天共喝水 1000ml,分 5 次。"
        return {
            "content": "查一下饮水。\n",
            "tool_calls": [{
                "id": f"c{len(exec_calls)}",
                "type": "function",
                "function": {"name": "health_query", "arguments": '{"dimension":"water"}'},
            }],
        }

    async def fake_execute_tool(tool_name, args_raw, user_token):
        exec_calls.append(tool_name)
        return '{"total_amount":1000,"target_amount":2000,"records":[{"drink_time":"08:30:00","amount":1000}]}'

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        e async for e in executor.run_stream(
            user_id=user.id, message="列出我喝水的记录 包括时间和量", user_auth_token=None,
        )
    ]
    # 关键: health_query 只真执行 1 次(去重), 不是每轮真跑
    assert exec_calls.count("health_query") == 1, exec_calls
    # loop 终止并产出最终答案
    rendered = "".join(
        e["data"].get("content", "") for e in events if e.get("event") == "token"
    )
    assert rendered.strip(), "应产出最终答案文本"


@pytest.mark.asyncio
async def test_repeated_health_manage_list_executes_once(db, auth_user_and_headers):
    """health_manage 是混合工具；list 要去重，update/delete 仍走写入状态机。"""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    exec_calls: list[str] = []

    async def fake_call_llm(messages, tools):
        last = str(messages[-1].get("content") or "")
        if "工具查询轮次已经用完" in last:
            return "已找到今天的早餐。"
        return {
            "content": "",
            "tool_calls": [{
                "id": f"c{len(exec_calls)}",
                "type": "function",
                "function": {
                    "name": "health_manage",
                    "arguments": '{"record_type":"diet","operation":"list","date":"today","meal_type":"breakfast"}',
                },
            }],
        }

    async def fake_execute_tool(tool_name, args_raw, user_token):
        exec_calls.append(tool_name)
        return '[{"id":821,"meal_type":"breakfast"}]'

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        e async for e in executor.run_stream(
            user_id=user.id,
            message="列出今天早餐",
            user_auth_token=None,
        )
    ]

    assert exec_calls.count("health_manage") == 1
    assert any(event.get("event") == "done" for event in events)


@pytest.mark.asyncio
async def test_different_readonly_queries_both_execute(db, auth_user_and_headers):
    """反向不误伤: 不同参的两个只读查询各执行一次(去重只吃同参)。"""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    exec_calls: list[tuple] = []
    seq = ["water", "sleep"]

    async def fake_call_llm(messages, tools):
        last = str(messages[-1].get("content") or "")
        if "工具查询轮次已经用完" in last or not seq:
            return "已查完。"
        dim = seq.pop(0)
        return {
            "content": "",
            "tool_calls": [{
                "id": f"c{len(exec_calls)}",
                "type": "function",
                "function": {"name": "health_query", "arguments": f'{{"dimension":"{dim}"}}'},
            }],
        }

    async def fake_execute_tool(tool_name, args_raw, user_token):
        exec_calls.append((tool_name, args_raw))
        return '{"total_amount":1}'

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    _ = [e async for e in executor.run_stream(user_id=user.id, message="查饮水和睡眠", user_auth_token=None)]
    assert len(exec_calls) == 2  # water + sleep 各一次, 不同参不被去重


@pytest.mark.asyncio
async def test_semantically_identical_illness_reads_execute_once(
    db,
    auth_user_and_headers,
):
    """Policy projection converges different model payloads before dedup."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    exec_calls: list[tuple[str, object]] = []
    model_round = 0

    async def fake_call_llm(messages, tools):
        nonlocal model_round
        model_round += 1
        if model_round > 1:
            return "最近半年有口腔溃疡记录。"
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "illness-1",
                    "type": "function",
                    "function": {
                        "name": "health_query",
                        "arguments": '{"dimension":"illness","keyword":"口腔溃疡"}',
                    },
                },
                {
                    "id": "illness-2",
                    "type": "function",
                    "function": {
                        "name": "health_query",
                        "arguments": (
                            '{"dimension":"illness","keyword":"口腔溃疡",'
                            '"days":183}'
                        ),
                    },
                },
            ],
        }

    async def fake_execute_tool(tool_name, args_raw, user_token):
        exec_calls.append((tool_name, args_raw))
        return "[]"

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    _ = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="查询近半年口腔溃疡的记录",
            user_auth_token=None,
        )
    ]

    assert len(exec_calls) == 1
