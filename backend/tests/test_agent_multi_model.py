"""多模型综合分析 (商用三强 panel) — 单元 + 编排集成测试。

验证: lead 带工具只执行一次 (不重复写库)、GPT/Gemini 并发独立分析、
Claude 综合, 单条 assistant 消息落库, done 事件 mode=multi_model。
"""
import json

import pytest

from app.services.agent_executor import (
    AgentExecutor,
    _build_multi_model_synthesis_prompt,
    _extract_multi_model_flag,
    _gathered_data_context,
)


def test_extract_multi_model_flag():
    assert _extract_multi_model_flag('{"multi_model": true}') is True
    assert _extract_multi_model_flag('{"multi_model": false}') is False
    assert _extract_multi_model_flag('{"model_id": "gpt-5.5"}') is False
    assert _extract_multi_model_flag(None) is False
    assert _extract_multi_model_flag("not json") is False


def test_gathered_data_context_extracts_tool_results_only():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
        {"role": "tool", "tool_call_id": "1", "content": "睡眠评分 79"},
        {"role": "tool", "tool_call_id": "2", "content": "HRV 56ms"},
    ]
    ctx = _gathered_data_context(messages)
    assert "睡眠评分 79" in ctx
    assert "HRV 56ms" in ctx
    assert "sys" not in ctx and "q" not in ctx


def test_synthesis_prompt_includes_question_and_all_analyses():
    prompt = _build_multi_model_synthesis_prompt(
        "我最近睡眠怎么样",
        [("Claude Opus 4.7", "A 分析"), ("GPT-5.5", "B 分析"), ("Gemini 3.1 Pro", "C 分析")],
    )
    assert "我最近睡眠怎么样" in prompt
    for label in ("Claude Opus 4.7", "GPT-5.5", "Gemini 3.1 Pro"):
        assert label in prompt
    assert "A 分析" in prompt and "B 分析" in prompt and "C 分析" in prompt
    assert "共识结论" in prompt and "分歧" in prompt


@pytest.mark.asyncio
async def test_multi_model_stream_lead_tools_once_then_synthesizes(db, auth_user_and_headers, monkeypatch):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])

    # Lead loop: round 1 → one write tool call; round 2 → final analysis text.
    lead_calls = {"n": 0}

    async def fake_call_llm(messages, tools):
        lead_calls["n"] += 1
        if lead_calls["n"] == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [{
                    "id": "c1", "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "diet",
                            "data": {"food_items": "鸡胸肉", "meal_type": "lunch"},
                        }),
                    },
                }],
            }
        return {"content": "LEAD ANALYSIS", "finish_reason": "stop"}

    tool_runs = []

    async def fake_execute_tool(name, args, token):
        tool_runs.append(name)
        from app.models.agent_conversation import AgentMessage

        db.expire_all()
        user_message = db.query(AgentMessage).filter(AgentMessage.role == "user").one()
        operations = user_message.meta["write_operations"]
        assert [operation["status"] for operation in operations.values()] == [
            "planned",
        ]
        return '{"id":812,"food_items":"鸡胸肉","meal_type":"lunch"}'

    monkeypatch.setattr(executor, "_call_llm", fake_call_llm)
    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)

    synth_user_prompts = []

    class FakeProvider:
        def __init__(self, model_id):
            self.model = model_id

        async def chat(self, **kwargs):
            messages = kwargs["messages"]
            system = messages[0]["content"]
            user_msg = messages[-1]["content"]
            if "综合专家" in system:  # synthesis call
                synth_user_prompts.append(user_msg)
                return {"content": "SYNTHESIS REPORT", "finish_reason": "stop"}
            return {"content": f"PERSP[{self.model}]", "finish_reason": "stop"}

    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        lambda model_id: FakeProvider(model_id),
    )

    events = []
    async for ev in executor._run_multi_model_stream(
        user.id,
        "记录午餐并综合分析",
        None,
        None,
        '{"multi_model": true}',
        "turn-multi-write",
    ):
        events.append(ev)

    kinds = [e["event"] for e in events]
    assert kinds[:2] == ["request_persisted", "agent_start"]
    assert "token" in kinds and kinds[-1] == "done"

    # lead tool executed exactly once (panel must NOT triplicate writes)
    assert tool_runs == ["health_record"]

    # streamed answer is the synthesis
    streamed = "".join(e["data"]["content"] for e in events if e["event"] == "token")
    assert streamed == "SYNTHESIS REPORT"

    # synthesis saw lead + both perspectives
    assert len(synth_user_prompts) == 1
    sp = synth_user_prompts[0]
    assert "LEAD ANALYSIS" in sp
    assert "PERSP[gpt-5.5]" in sp
    assert "PERSP[gemini-3.1-pro]" in sp

    # done event carries multi_model mode + the saved message persisted the synthesis
    done = events[-1]["data"]
    assert done["mode"] == "multi_model"
    assert "Claude Opus 4.7" in done["model"] and "GPT-5.5" in done["model"]

    from app.services.agent_conversation_service import AgentConversationService
    conv = AgentConversationService(db).get_conversation_detail(user.id, done["conversation_id"])
    assistant_msgs = [m for m in conv.messages if m.role == "assistant"]
    user_msgs = [m for m in conv.messages if m.role == "user"]
    assert len(assistant_msgs) == 1  # exactly one synthesis message, not one per panel model
    assert "SYNTHESIS REPORT" in (assistant_msgs[0].content or "")
    assert user_msgs[0].meta["write_state"]["status"] == "verified"
    assert user_msgs[0].meta["write_receipts"][0]["resource_id"] == "812"


@pytest.mark.asyncio
async def test_multi_model_simple_record_stops_after_verified_receipt(
    db, auth_user_and_headers, monkeypatch
):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")
    monkeypatch.setattr(
        "app.services.agent_executor.get_health_tools",
        lambda subset=None: [],
    )
    lead_calls = 0
    executed = []

    async def fake_call_llm(messages, tools):
        nonlocal lead_calls
        lead_calls += 1
        return {
            "content": "模型声称已经记录。",
            "finish_reason": "stop",
        }

    async def fake_execute_tool(name, args, token):
        parsed = json.loads(args) if isinstance(args, str) else args
        executed.append((name, parsed))
        return json.dumps(
            {
                "id": 913,
                "record_id": 913,
                "resource_type": "water_record",
                "status": "verified",
                "success": True,
                "message": "已记录饮水 500ml",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(executor, "_call_llm", fake_call_llm)
    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("simple record must not enter panel synthesis")
        ),
    )

    events = [
        event
        async for event in executor._run_multi_model_stream(
            user.id,
            "记录喝水五百毫升",
            None,
            None,
            '{"multi_model": true}',
            "turn-multi-simple-water",
        )
    ]

    assert lead_calls == 2
    assert executed == [(
        "health_record",
        {
            "record_type": "water",
            "data": {"amount": 500},
        },
    )]
    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    assert rendered == "已记录饮水 500ml"
    assert events[-1]["data"]["completion_status"] == "complete"
    assert len(events[-1]["data"]["write_receipts"]) == 1


@pytest.mark.asyncio
async def test_multi_model_nutrition_rejection_stops_before_panel_synthesis(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_write_outcome import local_write_rejection

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])
    lead_calls = 0

    async def fake_call_llm(messages, tools):
        nonlocal lead_calls
        lead_calls += 1
        if lead_calls == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [{
                    "id": "incomplete-breakfast",
                    "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "diet",
                            "data": {
                                "meal_type": "breakfast",
                                "food_items": "一个包子、一个茶叶蛋、一碗粥",
                            },
                        }, ensure_ascii=False),
                    },
                }],
            }
        return {
            "content": "早餐已经记录好了。",
            "finish_reason": "stop",
        }

    async def reject_incomplete_nutrition(name, args, token):
        return local_write_rejection(
            "diet_nutrition_incomplete",
            message=(
                "饮食记录必须先根据食物和份量估算完整营养，并提供 "
                "calories (>0)、protein、carbs、fat、fiber。"
            ),
        )

    monkeypatch.setattr(executor, "_call_llm", fake_call_llm)
    monkeypatch.setattr(executor, "_execute_tool", reject_incomplete_nutrition)
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("panel synthesis must not hide a rejected write")
        ),
    )

    events = [
        event
        async for event in executor._run_multi_model_stream(
            user.id,
            "记录早餐，一个包子、一个茶叶蛋、一碗粥，计算热量和营养成分。",
            None,
            None,
            '{"multi_model": true}',
            "turn-multi-incomplete-diet",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    done = events[-1]["data"]

    assert lead_calls >= 2
    assert "完整营养" in rendered
    assert "早餐已经记录好了" not in rendered
    assert done["completion_status"] == "error"
    assert done["write_receipts"] == []


@pytest.mark.asyncio
async def test_multi_model_validation_rejects_success_claim_without_receipt(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_write_outcome import local_write_rejection

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])
    lead_calls = 0

    async def fake_call_llm(messages, tools):
        nonlocal lead_calls
        lead_calls += 1
        if lead_calls == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [{
                    "id": "sleep-missing-times",
                    "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "sleep",
                            "data": {"sleep_quality": 5},
                        }),
                    },
                }],
            }
        return {
            "content": "睡眠记录已经保存好了。",
            "finish_reason": "stop",
        }

    async def reject_missing_times(name, args, token):
        return local_write_rejection(
            "tool_validation_failed",
            message="睡眠记录缺少 bedtime、wake_time。",
        )

    monkeypatch.setattr(executor, "_call_llm", fake_call_llm)
    monkeypatch.setattr(executor, "_execute_tool", reject_missing_times)
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("panel synthesis must not hide a rejected write")
        ),
    )

    events = [
        event
        async for event in executor._run_multi_model_stream(
            user.id,
            "记录昨晚睡眠质量很好",
            None,
            None,
            '{"multi_model": true}',
            "turn-multi-sleep-false-success",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    done = events[-1]["data"]

    assert lead_calls >= 2
    assert "这次没有写入" in rendered
    assert "缺少 bedtime、wake_time" in rendered
    assert "已经保存好了" not in rendered
    assert done["completion_status"] == "error"
    assert done["write_receipts"] == []


@pytest.mark.asyncio
async def test_multi_model_partial_success_cannot_hide_independent_rejection(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_write_outcome import local_write_rejection

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])
    lead_calls = 0

    async def fake_call_llm(messages, tools):
        nonlocal lead_calls
        lead_calls += 1
        if lead_calls == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "sleep-missing-times",
                        "type": "function",
                        "function": {
                            "name": "health_record",
                            "arguments": json.dumps({
                                "record_type": "sleep",
                                "data": {"sleep_quality": 5},
                            }),
                        },
                    },
                    {
                        "id": "water-complete",
                        "type": "function",
                        "function": {
                            "name": "health_record",
                            "arguments": json.dumps({
                                "record_type": "water",
                                "data": {"amount": 500},
                            }),
                        },
                    },
                ],
            }
        return {
            "content": "两项记录都已经保存好了。",
            "finish_reason": "stop",
        }

    async def execute_mixed_writes(name, args, token):
        payload = json.loads(args)
        if payload["record_type"] == "sleep":
            return local_write_rejection(
                "tool_validation_failed",
                message="睡眠记录缺少 bedtime、wake_time。",
            )
        return json.dumps({
            "id": 921,
            "resource_type": "water_record",
            "amount": 500,
        })

    monkeypatch.setattr(executor, "_call_llm", fake_call_llm)
    monkeypatch.setattr(executor, "_execute_tool", execute_mixed_writes)
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("panel synthesis must not hide a partial write rejection")
        ),
    )

    events = [
        event
        async for event in executor._run_multi_model_stream(
            user.id,
            "请完成两项健康记录。",
            None,
            None,
            '{"multi_model": true}',
            "turn-multi-partial-rejection",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    done = events[-1]["data"]

    assert "另有 1 项记录已完成并取得回执" in rendered
    assert "缺少 bedtime、wake_time" in rendered
    assert "两项记录都已经保存好了" not in rendered
    assert done["completion_status"] == "error"
    assert len(done["write_receipts"]) == 1


@pytest.mark.asyncio
async def test_multi_model_identityless_write_fails_closed_before_panel_synthesis(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])

    async def fake_call_llm(messages, tools):
        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [{
                "id": "delete-1",
                "type": "function",
                "function": {
                    "name": "health_manage",
                    "arguments": json.dumps({
                        "record_type": "diet",
                        "operation": "delete",
                        "record_id": 42,
                    }),
                },
            }],
        }

    async def fake_execute_tool(name, args, token):
        return '{"message":"Record deleted successfully"}'

    monkeypatch.setattr(executor, "_call_llm", fake_call_llm)
    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("panel synthesis must not run after an unverified write")
        ),
    )

    events = [
        event
        async for event in executor._run_multi_model_stream(
            user.id,
            "删除饮食记录 42",
            None,
            None,
            '{"multi_model": true}',
            "turn-multi-delete-no-id",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    assert "不能确认" in rendered
    assert "deleted successfully" not in rendered.lower()
    done = events[-1]["data"]
    assert done["completion_status"] == "error"
    assert done["write_receipts"] == []


@pytest.mark.asyncio
async def test_multi_model_http_500_write_is_uncertain_and_retry_bypasses_panel(
    db, auth_user_and_headers, monkeypatch
):
    from app.models.agent_conversation import AgentMessage

    user, _ = auth_user_and_headers
    turn_id = "turn-multi-committed-then-500"
    message = "记录午餐并综合分析"
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])

    async def first_llm_call(messages, tools):
        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [{
                "id": "write-500",
                "type": "function",
                "function": {
                    "name": "health_record",
                    "arguments": json.dumps({
                        "record_type": "diet",
                        "data": {"food_items": "鸡胸肉", "meal_type": "lunch"},
                    }),
                },
            }],
        }

    async def committed_then_500(name, args, token):
        return "Error: upstream returned 500 after request dispatch"

    monkeypatch.setattr(executor, "_call_llm", first_llm_call)
    monkeypatch.setattr(executor, "_execute_tool", committed_then_500)
    first_events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=message,
            user_auth_token="test-token",
            extra_context='{"multi_model": true}',
            client_turn_id=turn_id,
        )
    ]
    assert first_events[-1]["data"]["completion_status"] == "error"

    user_message = db.query(AgentMessage).filter(
        AgentMessage.role == "user",
        AgentMessage.content == message,
    ).one()
    assert user_message.meta["write_state"]["status"] == "uncertain"
    for assistant in db.query(AgentMessage).filter(
        AgentMessage.role == "assistant",
        AgentMessage.conversation_id == user_message.conversation_id,
    ).all():
        db.delete(assistant)
    db.commit()

    retry_llm_calls = 0
    retry_executor = AgentExecutor(db)

    async def retry_llm_call(messages, tools):
        nonlocal retry_llm_calls
        retry_llm_calls += 1
        return {"content": "不应再次进入多模型面板", "finish_reason": "stop"}

    monkeypatch.setattr(retry_executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr(retry_executor, "_call_llm", retry_llm_call)
    retry_events = [
        event
        async for event in retry_executor.run_stream(
            user_id=user.id,
            message=message,
            user_auth_token="test-token",
            extra_context='{"multi_model": true}',
            client_turn_id=turn_id,
        )
    ]

    assert retry_llm_calls == 0
    assert "没有自动重试" in "".join(
        event["data"].get("content", "")
        for event in retry_events
        if event.get("event") == "token"
    )


@pytest.mark.asyncio
async def test_multi_model_duplicate_writes_execute_once(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])
    arguments = json.dumps({
        "record_type": "diet",
        "data": {"food_items": "鸡胸肉", "meal_type": "lunch"},
    })
    lead_calls = 0
    tool_calls = 0

    async def fake_llm_call(messages, tools):
        nonlocal lead_calls
        lead_calls += 1
        if lead_calls == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {"id": "duplicate-1", "type": "function", "function": {"name": "health_record", "arguments": arguments}},
                    {"id": "duplicate-2", "type": "function", "function": {"name": "health_record", "arguments": arguments}},
                ],
            }
        return {"content": "LEAD", "finish_reason": "stop"}

    async def fake_execute_tool(name, args, token):
        nonlocal tool_calls
        tool_calls += 1
        return json.dumps({"id": 950 + tool_calls, "food_items": "鸡胸肉"})

    class FakeProvider:
        def __init__(self, model_id):
            self.model = model_id

        async def chat(self, **kwargs):
            if "综合专家" in kwargs["messages"][0]["content"]:
                return {"content": "SYNTHESIS", "finish_reason": "stop"}
            return {"content": "PERSPECTIVE", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm", fake_llm_call)
    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        lambda model_id: FakeProvider(model_id),
    )

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="记录午餐并综合分析",
            user_auth_token="test-token",
            extra_context='{"multi_model": true}',
            client_turn_id="turn-multi-duplicate-write",
        )
    ]

    assert tool_calls == 1
    duplicate_results = [
        event["data"]
        for event in events
        if event.get("event") == "tool_result"
        and event["data"].get("tool") == "health_record"
    ]
    assert len(duplicate_results) == 2
    assert duplicate_results[1]["replayed"] is True
    assert len(events[-1]["data"]["write_receipts"]) == 1


@pytest.mark.asyncio
async def test_multi_model_checkpoints_all_planned_writes_before_dispatch(
    db, auth_user_and_headers, monkeypatch
):
    from app.models.agent_conversation import AgentMessage

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])
    arguments = [
        json.dumps({"record_type": "diet", "operation": "delete", "record_id": 1201}),
        json.dumps({"record_type": "diet", "operation": "delete", "record_id": 1202}),
    ]

    async def fake_llm_call(messages, tools):
        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {"id": "a", "type": "function", "function": {"name": "health_manage", "arguments": arguments[0]}},
                {"id": "b", "type": "function", "function": {"name": "health_manage", "arguments": arguments[1]}},
            ],
        }

    checked = False

    async def fake_execute_tool(name, args, token):
        nonlocal checked
        if not checked:
            db.expire_all()
            user_message = db.query(AgentMessage).filter(
                AgentMessage.role == "user",
                AgentMessage.content == "多模型删除两条记录",
            ).one()
            operations = user_message.meta["write_operations"]
            assert len(operations) == 2
            assert sorted(operation["status"] for operation in operations.values()) == [
                "planned",
                "planned",
            ]
            checked = True
        record_id = json.loads(args)["record_id"]
        return json.dumps({
            "id": record_id,
            "record_id": record_id,
            "resource_type": "diet_record",
        })

    monkeypatch.setattr(executor, "_call_llm", fake_llm_call)
    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("test stops after proving the plan checkpoint")
        ),
    )

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="多模型删除两条记录",
            user_auth_token="test-token",
            extra_context='{"multi_model": true}',
            client_turn_id="turn-multi-planned-writes",
        )
    ]
    assert checked is True
    assert events[-1]["data"]["completion_status"] == "error"
