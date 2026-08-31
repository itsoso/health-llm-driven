"""Thinking-process status SSE events + fast-route answer max_tokens cap.

Two additive latency/UX features on the 小巴 hot path (AgentExecutor.run_stream):

1. Real thinking-process status events (思考过程可视化). The mac client used to guess
   "正在思考…" by elapsed time; the backend now emits REAL stage events with the exact
   contract:
       {"event": "status", "data": {"stage": <str>, "detail": <str|None>, "round": <int|None>}}
   Emitted at: vision pre-pass, top of each tool-loop round (thinking/synthesis), and
   right before each serial tool executes (tool, with a short Chinese label).

2. Fast-route answer max_tokens cap. Fast-routed simple record/query turns cap answer
   generation at FAST_ROUTE_ANSWER_MAX_TOKENS (2000); everything else keeps
   ANSWER_MAX_TOKENS (8000). The tail decode of a simple answer is part of the latency.
"""
import json

import pytest

from app.config import settings

from app.services.agent_executor import (
    ANSWER_MAX_TOKENS,
    FAST_ROUTE_ANSWER_MAX_TOKENS,
    AgentExecutor,
    _apply_authorized_symptom_payload,
    _apply_authorized_rhinitis_payload,
    _apply_server_health_record_provenance,
    _bind_named_knowledge_source_to_tool_calls,
    _build_deterministic_named_knowledge_tool_call,
    _build_deterministic_symptom_tool_call,
    _extract_clear_rhinitis_record,
    _symptom_write_authorized_by_current_turn,
    _tool_status_label,
)
from app.services.llm import model_registry as reg


# ──── tool → status label map ────

@pytest.mark.parametrize("name,label", [
    ("health_query", "查询健康数据"),
    ("health_record", "写入记录"),
    ("health_manage", "管理记录"),
    ("health_analysis", "深度分析"),
    ("knowledge_search", "检索知识库"),
    ("realtime_search", "联网搜索"),
])
def test_tool_status_label_maps_known_tools(name, label):
    assert _tool_status_label(name) == label


def test_tool_status_label_unknown_falls_back_to_raw_name():
    assert _tool_status_label("some_new_tool") == "some_new_tool"
    assert _tool_status_label(None) == "工具"


# ──── shared wiring ────

def _statuses(events):
    """Extract (stage, detail, round) tuples from status events, in emit order."""
    out = []
    for e in events:
        if e.get("event") == "status":
            d = e["data"]
            out.append((d["stage"], d.get("detail"), d.get("round")))
    return out


async def _run(
    executor,
    message,
    images=None,
    extra_context=None,
    user_id=1,
    client_turn_id=None,
    channel=None,
    run_id=None,
    attempt_id=None,
):
    return [
        event
        async for event in executor.run_stream(
            user_id=user_id,
            message=message,
            user_auth_token="test-token",
            images=images,
            extra_context=extra_context,
            client_turn_id=client_turn_id,
            channel=channel,
            run_id=run_id,
            attempt_id=attempt_id,
        )
    ]


def test_deterministic_symptom_tool_call_accepts_clear_statement_only():
    call = _build_deterministic_symptom_tool_call(
        "还是有腰疼的症状。",
        write_receipts=[],
    )

    assert call is not None
    assert call["function"]["name"] == "health_record"
    assert call["function"]["arguments"] == (
        '{"record_type": "symptom", "data": {'
        '"body_part": "musculoskeletal", '
        '"description": "还是有腰疼的症状"}}'
    )


def test_deterministic_symptom_tool_call_accepts_natural_sneeze_recording():
    call = _build_deterministic_symptom_tool_call(
        "记录下来刚才打了一个喷嚏。",
        write_receipts=[],
    )

    assert call is not None
    assert json.loads(call["function"]["arguments"]) == {
        "record_type": "symptom",
        "data": {
            "body_part": "respiratory",
            "description": "记录下来刚才打了一个喷嚏",
        },
    }


def test_deterministic_symptom_tool_call_keeps_questions_on_advice_path():
    assert _build_deterministic_symptom_tool_call(
        "腰疼怎么办？",
        write_receipts=[],
    ) is None


@pytest.mark.parametrize(
    "message",
    [
        "没有腰疼的症状。",
        "我不头疼。",
        "不头痛。",
        "我朋友头痛。",
        "同事头痛，帮我记录一下。",
        "我老婆腰疼，记录一下。",
        "他头痛。",
        "她腰疼。",
        "他打了一个喷嚏。",
        "她打了一个喷嚏。",
        "我说他打喷嚏，帮我记录一下。",
        "小王打喷嚏，帮我记录一下。",
        "我爸打喷嚏，帮我记录一下。",
        "他在打喷嚏，帮我记录一下。",
        "她正在打喷嚏，帮我记录一下。",
        "我爸刚才打了一个喷嚏，帮我记录一下。",
        "他也打喷嚏，帮我记录一下。",
        "他刚打喷嚏，帮我记录一下。",
        "他已经打喷嚏，帮我记录一下。",
        "小王偶尔打喷嚏，帮我记录一下。",
        "他今天早上在办公室连续打了一个喷嚏，帮我记录一下。",
        "我刚才打了一个喷嚏然后他也鼻塞，帮我记录一下。",
        "我刚才打了一个喷嚏但是他也鼻塞，帮我记录一下。",
        "检查报告提示膝盖疼。",
        "能否记录我刚才打了一个喷嚏？",
        "可否记录我刚才打了一个喷嚏？",
        "可不可以记录我刚才打了一个喷嚏？",
        "附件里记录了腰疼。",
        "记录我头疼，不对，现在不疼了",
        "记录我头疼但现在不疼了",
        "记录我头疼后来不疼了",
    ],
)
def test_deterministic_symptom_tool_call_rejects_non_self_or_negated_text(message):
    assert _build_deterministic_symptom_tool_call(
        message,
        write_receipts=[],
    ) is None


def test_deterministic_symptom_tool_call_rejects_attachments():
    assert _build_deterministic_symptom_tool_call(
        "还是有腰疼的症状。",
        write_receipts=[],
        has_attachment=True,
    ) is None


def test_named_knowledge_request_recovers_previous_health_question():
    call = _build_deterministic_named_knowledge_tool_call(
        "基于皮皮妈妈的一家之言的知识库作答。",
        recent_messages=[
            {"role": "user", "content": "如果新冠发烧，需要吃哪些补剂？"},
            {"role": "assistant", "content": "先说结论：补剂不能治疗新冠。"},
        ],
    )

    assert call is not None
    assert call["function"]["name"] == "knowledge_search"
    assert json.loads(call["function"]["arguments"]) == {
        "query": "如果新冠发烧，需要吃哪些补剂？",
        "knowledge_source": "皮皮妈妈的一家之言",
    }


def test_named_knowledge_correction_keeps_original_question():
    call = _build_deterministic_named_knowledge_tool_call(
        "益家知研 这个在我知识库中",
        recent_messages=[
            {"role": "user", "content": "如果新冠发烧 需要吃哪些补剂？"},
            {"role": "assistant", "content": "请告诉我想使用哪个知识库。"},
            {"role": "user", "content": "基于皮皮妈妈的一家之言的知识库作答。"},
            {"role": "assistant", "content": "我没有访问这个知识库的能力。"},
        ],
    )

    assert call is not None
    assert json.loads(call["function"]["arguments"]) == {
        "query": "如果新冠发烧 需要吃哪些补剂？",
        "knowledge_source": "益家知研",
    }


def test_named_knowledge_request_overrides_model_generic_search_args():
    calls = [{
        "id": "model-call",
        "type": "function",
        "function": {
            "name": "knowledge_search",
            "arguments": json.dumps({"query": "益家知研"}, ensure_ascii=False),
        },
    }]

    bound = _bind_named_knowledge_source_to_tool_calls(
        calls,
        message="益家知研 这个在我知识库中",
        recent_messages=[
            {"role": "user", "content": "如果新冠发烧 需要吃哪些补剂？"},
            {"role": "assistant", "content": "请告诉我知识库名称。"},
        ],
    )

    assert json.loads(bound[0]["function"]["arguments"]) == {
        "query": "如果新冠发烧 需要吃哪些补剂？",
        "knowledge_source": "益家知研",
    }


@pytest.mark.parametrize(
    "message",
    [
        "益家知研最近怎么样？",
        "我用益家知研记录了补剂。",
        "我没有用益家知研回答这个问题。",
        "不要用益家知研回答。",
        "请不要用系统知识库回答。",
        "小王根据蓝鲸健康库回答了睡眠问题。",
        "我用益家知研回答了一个问题。",
        "我把知识库整理好了。",
        "根据知识库回答。",
    ],
)
def test_named_knowledge_fallback_rejects_non_source_requests(message):
    assert _build_deterministic_named_knowledge_tool_call(
        message,
        recent_messages=[],
    ) is None


@pytest.mark.parametrize(
    "message",
    ["用益家知研回答", "请用益家知研回答", "帮我用益家知研回答"],
)
def test_named_knowledge_fallback_accepts_use_source_instruction(message):
    call = _build_deterministic_named_knowledge_tool_call(
        message,
        recent_messages=[
            {"role": "user", "content": "如果新冠发烧，需要吃哪些补剂？"},
        ],
    )

    assert call is not None
    arguments = json.loads(call["function"]["arguments"])
    assert arguments == {
        "query": "如果新冠发烧，需要吃哪些补剂？",
        "knowledge_source": "益家知研",
    }


@pytest.mark.parametrize(
    ("message", "expected_source"),
    [
        ("基于不存在的私人知识库回答：睡眠怎么办", "不存在的私人知识库"),
        ("用蓝鲸健康库回答：睡眠怎么办", "蓝鲸健康库"),
        ("用系统知识库测试版回答：睡眠怎么办", "系统知识库测试版"),
    ],
)
def test_named_knowledge_fallback_preserves_unknown_source_name(
    message,
    expected_source,
):
    call = _build_deterministic_named_knowledge_tool_call(
        message,
        recent_messages=[],
    )

    assert call is not None
    arguments = json.loads(call["function"]["arguments"])
    assert arguments["knowledge_source"] == expected_source


def test_named_knowledge_query_skips_non_health_acknowledgement():
    call = _build_deterministic_named_knowledge_tool_call(
        "基于益家知研作答",
        recent_messages=[
            {"role": "user", "content": "如果新冠发烧，需要吃哪些补剂？"},
            {"role": "assistant", "content": "请指定知识来源。"},
            {"role": "user", "content": "谢谢"},
            {"role": "assistant", "content": "不客气。"},
        ],
    )

    assert call is not None
    arguments = json.loads(call["function"]["arguments"])
    assert arguments["query"] == "如果新冠发烧，需要吃哪些补剂？"


def test_named_knowledge_source_only_request_needs_preceding_health_query():
    assert _build_deterministic_named_knowledge_tool_call(
        "基于益家知研作答",
        recent_messages=[
            {"role": "user", "content": "谢谢"},
            {"role": "assistant", "content": "不客气。"},
        ],
    ) is None


@pytest.mark.asyncio
async def test_named_knowledge_fallback_buffers_model_denial_until_source_result(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title="指定知识库")
    service.save_message(conv.id, "user", "如果新冠发烧，需要吃哪些补剂？")
    service.save_message(conv.id, "assistant", "请告诉我希望使用哪个知识库。")

    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    monkeypatch.setattr(
        "app.services.agent_executor.settings.task_tiered_routing",
        False,
    )
    monkeypatch.setattr(
        "app.services.agent_executor.get_health_tools",
        lambda subset=None: [{
            "type": "function",
            "function": {
                "name": "knowledge_search",
                "description": "x",
                "parameters": {"type": "object", "properties": {}},
            },
        }],
    )
    executed = []
    rounds = 0

    async def fake_execute_tool(name, args, token):
        executed.append((name, json.loads(args)))
        return "source_status=not_released\n不得声称已搜索该来源。"

    async def fake_stream(messages, round_tools):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            yield {"type": "content", "text": "错误地说：我没有访问这个知识库的能力。"}
        else:
            yield {"type": "content", "text": "该来源存在，但尚未进入已审定知识库。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)
    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            conversation_id=conv.id,
            message="基于皮皮妈妈的一家之言的知识库作答。",
            user_auth_token="test-token",
        )
    ]

    visible = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    assert "错误地说" not in visible
    assert "该来源存在" in visible
    assert executed == [(
        "knowledge_search",
        {
            "query": "如果新冠发烧，需要吃哪些补剂？",
            "knowledge_source": "皮皮妈妈的一家之言",
        },
    )]


@pytest.mark.parametrize(
    "message",
    [
        "没有腰疼的症状。",
        "我不头疼。",
        "我朋友头痛。",
        "同事头痛，帮我记录一下。",
        "我老婆腰疼，记录一下。",
        "他头痛。",
        "她腰疼。",
        "我说他打喷嚏，帮我记录一下。",
        "小王打喷嚏，帮我记录一下。",
        "我爸打喷嚏，帮我记录一下。",
        "他在打喷嚏，帮我记录一下。",
        "她正在打喷嚏，帮我记录一下。",
        "我爸刚才打了一个喷嚏，帮我记录一下。",
        "他也打喷嚏，帮我记录一下。",
        "他刚打喷嚏，帮我记录一下。",
        "他已经打喷嚏，帮我记录一下。",
        "小王偶尔打喷嚏，帮我记录一下。",
        "他今天早上在办公室连续打了一个喷嚏，帮我记录一下。",
        "我刚才打了一个喷嚏然后他也鼻塞，帮我记录一下。",
        "我刚才打了一个喷嚏但是他也鼻塞，帮我记录一下。",
        "检查报告提示膝盖疼。",
        "能否记录我刚才打了一个喷嚏？",
        "可否记录我刚才打了一个喷嚏？",
        "可不可以记录我刚才打了一个喷嚏？",
    ],
)
def test_symptom_write_authorization_rejects_unsafe_current_turns(message):
    assert not _symptom_write_authorized_by_current_turn(message, [])


def test_symptom_write_authorization_requires_current_statement_not_confirmation():
    assert not _symptom_write_authorized_by_current_turn(
        "确认",
        [{"role": "assistant", "content": "我准备记录症状：还是有腰疼。要不要记录？"}],
    )


def test_symptom_write_authorization_rejects_stale_confirmation_after_user_message():
    assert not _symptom_write_authorized_by_current_turn(
        "确认",
        [
            {"role": "assistant", "content": "我准备记录症状：头痛。要不要记录？"},
            {"role": "user", "content": "不是这个"},
        ],
    )


def test_symptom_write_authorization_rejects_non_symptom_confirmation_prompt():
    assert not _symptom_write_authorized_by_current_turn(
        "确认",
        [{"role": "assistant", "content": "我已确认症状，接下来继续分析。"}],
    )


def test_authorized_symptom_payload_discards_model_inference():
    payload = _apply_authorized_symptom_payload(
        {
            "record_type": "symptom",
            "data": {
                "body_part": "musculoskeletal",
                "description": "MRI报告显示右膝半月板损伤",
                "overall_severity": 8,
            },
        },
        {"body_part": "musculoskeletal", "description": "腰疼"},
    )

    assert payload == {
        "record_type": "symptom",
        "data": {"body_part": "musculoskeletal", "description": "腰疼"},
    }


def test_compound_symptom_provenance_is_derived_from_current_turn_fact():
    args = _apply_server_health_record_provenance(
        "health_record",
        {
            "record_type": "symptom",
            "data": {"body_part": "head", "description": "我头疼"},
        },
        execution_source="structured_or_recovered",
        has_attachment=False,
        diet_photo_auto_save=False,
        contextual_diet_recorded=False,
        contextual_supplement_names=(),
        user_message="记录我头疼有多严重",
    )

    marker = args["_server_authorized_health_record_fields"]
    assert dict(marker.values) == {
        "symptom_payload": {"body_part": "head", "description": "我头疼"}
    }


@pytest.mark.parametrize(
    "message",
    (
        "记录我头疼，不对，现在不疼了",
        "记录我头疼但现在不疼了",
        "记录我头疼后来不疼了",
    ),
)
def test_retracted_symptom_does_not_receive_server_write_authorization(message):
    args = _apply_server_health_record_provenance(
        "health_record",
        {
            "record_type": "symptom",
            "data": {"body_part": "head", "description": "我头疼"},
        },
        execution_source="structured_or_recovered",
        has_attachment=False,
        diet_photo_auto_save=False,
        contextual_diet_recorded=False,
        contextual_supplement_names=(),
        user_message=message,
    )

    assert "_server_authorized_health_record_fields" not in args


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("记录下来刚才打了一个喷嚏。", {"sneezing": 1}),
        ("我刚才连续打了3个喷嚏，记录一下。", {"sneezing": 3}),
        ("今天有鼻塞，程度3级。", {"congestion": 3}),
        ("今天流鼻涕。", {"runny_nose": 1}),
    ],
)
def test_clear_rhinitis_record_extracts_only_explicit_user_fields(message, expected):
    assert _extract_clear_rhinitis_record(message) == expected


def test_authorized_rhinitis_payload_discards_model_inference():
    payload = _apply_authorized_rhinitis_payload(
        {
            "record_type": "rhinitis",
            "data": {"sneezing": 99, "congestion": 3, "runny_nose": 3},
        },
        {"sneezing": 1},
    )

    assert payload == {"record_type": "rhinitis", "data": {"sneezing": 1}}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "没有腰疼的症状。",
        "我不头疼。",
        "我朋友头痛。",
        "检查报告提示膝盖疼。",
    ],
)
async def test_structured_symptom_write_is_blocked_before_gateway(
    db, message
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = message
    executor._current_turn_recent_messages = []

    result = await executor._execute_tool_impl(
        "health_record",
        {
            "record_type": "symptom",
            "data": {
                "body_part": "musculoskeletal",
                "description": "模型自行生成的症状",
            },
        },
        "test-token",
    )

    rejection = json.loads(result)
    assert rejection["status"] == "rejected"
    assert rejection["dispatch_started"] is False
    assert rejection["error_code"] == "symptom_write_not_authorized"


@pytest.mark.asyncio
async def test_rhinitis_write_uses_user_values_not_model_values(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录下来刚才打了一个喷嚏。"
    executor._current_turn_recent_messages = []
    executor._current_turn_has_attachment = False
    executor._agent_kernel_preflight_tool = lambda *args, **kwargs: None
    captured = {}

    async def fake_health_record(base, headers, args):
        captured["args"] = args
        return '{"id": 55, "status": "recorded"}'

    monkeypatch.setattr(executor, "_exec_health_record", fake_health_record)
    result = await executor._execute_tool_impl(
        "health_record",
        {
            "record_type": "rhinitis",
            "data": {"sneezing": 99, "congestion": 3, "runny_nose": 3},
        },
        "test-token",
    )

    assert '"id": 55' in result
    assert captured["args"]["record_type"] == "rhinitis"
    assert captured["args"]["data"]["sneezing"] == 1
    assert captured["args"]["data"]["congestion"] == 0
    assert captured["args"]["data"]["runny_nose"] == 0
    assert captured["args"]["data"].get("sneezing") != 99


@pytest.mark.asyncio
async def test_structured_symptom_write_uses_current_statement_before_api(
    db, monkeypatch
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "还是有腰疼的症状。"
    executor._current_turn_recent_messages = []
    executor._agent_kernel_preflight_tool = lambda *args, **kwargs: None
    captured = {}

    def fake_validate(tool_name, args, **kwargs):
        return {"error": None, "data": args}

    async def fake_health_record(base_url, headers, args):
        captured.update(args)
        return '{"id": 7, "resource_type": "symptom"}'

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        fake_validate,
    )
    monkeypatch.setattr(executor, "_exec_health_record", fake_health_record)

    result = await executor._execute_tool_impl(
        "health_record",
        {
            "record_type": "symptom",
            "data": {
                "body_part": "musculoskeletal",
                "description": "MRI报告显示右膝半月板损伤",
                "overall_severity": 8,
            },
        },
        "test-token",
    )

    assert '"id": 7' in result
    assert captured == {
        "record_type": "symptom",
        "data": {
            "body_part": "musculoskeletal",
            "description": "还是有腰疼的症状",
            "record_date": executor._agent_kernel_reference_now().date().isoformat(),
        },
    }


@pytest.mark.asyncio
async def test_structured_symptom_write_is_blocked_on_attachment_turn(db):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "还是有腰疼的症状。"
    executor._current_turn_recent_messages = []
    executor._current_turn_has_attachment = True

    result = await executor._execute_tool_impl(
        "health_record",
        {
            "record_type": "symptom",
            "data": {
                "body_part": "musculoskeletal",
                "description": "还是有腰疼的症状",
            },
        },
        "test-token",
    )

    assert json.loads(result) == {
        "status": "rejected",
        "success": False,
        "dispatch_started": False,
        "error_code": "symptom_attachment_not_supported",
        "message": "带附件的消息不能自动写入症状记录。",
        "recovery_guidance": "请在不带附件的新消息中直接复述要记录的本人症状。",
    }


@pytest.mark.asyncio
async def test_rhinitis_write_is_blocked_on_attachment_turn_with_local_rejection(db):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录下来刚才打了一个喷嚏。"
    executor._current_turn_recent_messages = []
    executor._current_turn_has_attachment = True

    result = await executor._execute_tool_impl(
        "health_record",
        {
            "record_type": "rhinitis",
            "data": {"sneezing": 1},
        },
        "test-token",
    )

    rejection = json.loads(result)
    assert rejection["status"] == "rejected"
    assert rejection["dispatch_started"] is False
    assert rejection["error_code"] == "rhinitis_attachment_not_supported"


@pytest.mark.asyncio
async def test_malformed_tool_arguments_return_local_rejection(db):
    executor = AgentExecutor(db)

    result = await executor._execute_tool_impl(
        "health_record",
        "not-json-at-all",
        "test-token",
    )

    rejection = json.loads(result)
    assert rejection["status"] == "rejected"
    assert rejection["dispatch_started"] is False
    assert rejection["error_code"] == "tool_arguments_invalid"


@pytest.mark.asyncio
async def test_executor_uses_canonical_runtime_identity(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "已处理。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(
        executor,
        "记录运行身份",
        user_id=user.id,
        client_turn_id="turn-runtime-identity",
        run_id="run-canonical-42",
        attempt_id="attempt-canonical-1",
    )

    snapshot = executor._agent_kernel_snapshot
    assert snapshot is not None
    assert snapshot.context.run_id == "run-canonical-42"
    done = next(event for event in events if event.get("event") == "done")
    assert done["data"]["run_id"] == "run-canonical-42"
    assert done["data"]["attempt_id"] == "attempt-canonical-1"
    assert done["data"]["kernel_trace"]["run_id"] == "run-canonical-42"


@pytest.mark.asyncio
async def test_clear_symptom_is_written_when_model_only_returns_text(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    monkeypatch.setattr(
        "app.services.agent_executor.get_health_tools",
        lambda subset=None: [
            {
                "type": "function",
                "function": {
                    "name": "health_record",
                    "description": "x",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ],
    )
    executed = []

    async def fake_execute_tool(name, args, token):
        executed.append((name, args))
        return (
            '{"id": 42, "resource_type": "symptom_record", '
            '"description": "还是有腰疼的症状", '
            '"created_at": "2026-07-19T17:00:00+08:00"}'
        )

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "我先帮你看看。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)
    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    monkeypatch.setattr(
        "app.services.agent_executor._post_record_quality_response",
        lambda *args, **kwargs: None,
    )

    events = await _run(
        executor,
        "还是有腰疼的症状。",
        user_id=user.id,
        client_turn_id="turn-symptom-deterministic-fallback",
        channel="typed",
    )

    assert len(executed) == 1
    assert executed[0][0] == "health_record"
    args = json.loads(executed[0][1])
    assert args["record_type"] == "symptom"
    assert args["data"]["body_part"] == "musculoskeletal"
    assert args["data"]["description"] == "还是有腰疼的症状"
    assert "已记录" in "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    done = next(event for event in events if event.get("event") == "done")
    assert done["data"]["write_receipts"][0]["resource_id"] == "42"


@pytest.mark.asyncio
async def test_request_persisted_event_and_messages_keep_client_turn_identity(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "已经保存本轮请求。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(
        executor,
        "记录本轮身份",
        user_id=user.id,
        client_turn_id="turn-mobile-42",
    )

    persisted = next(event for event in events if event.get("event") == "request_persisted")
    assert persisted["data"]["conversation_id"] > 0
    assert persisted["data"]["user_message_id"] > 0
    assert persisted["data"]["client_turn_id"] == "turn-mobile-42"

    from app.models.agent_conversation import AgentMessage

    saved = (
        db.query(AgentMessage)
        .filter(AgentMessage.conversation_id == persisted["data"]["conversation_id"])
        .order_by(AgentMessage.id.asc())
        .all()
    )
    assert [message.role for message in saved] == ["user", "assistant"]
    assert saved[0].meta["client_turn_id"] == "turn-mobile-42"
    assert saved[1].meta["client_turn_id"] == "turn-mobile-42"
    snapshot = executor._agent_kernel_snapshot
    assert snapshot is not None
    assert snapshot.envelope.client_turn_id == "turn-mobile-42"
    assert snapshot.envelope.source_message_id == str(persisted["data"]["user_message_id"])
    done = next(event for event in events if event.get("event") == "done")
    assert done["data"]["kernel_trace"]["run_id"] == snapshot.context.run_id
    assert done["data"]["kernel_trace"]["blocked_tools"] == 0


@pytest.mark.asyncio
async def test_repeated_client_turn_replays_without_executing_the_agent_twice(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    calls = 0

    async def fake_stream(messages, round_tools):
        nonlocal calls
        calls += 1
        yield {"type": "content", "text": "只执行一次。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    first = await _run(
        executor,
        "记录本轮身份",
        user_id=user.id,
        client_turn_id="turn-idempotent-42",
    )
    second = await _run(
        executor,
        "记录本轮身份",
        user_id=user.id,
        client_turn_id="turn-idempotent-42",
    )

    first_done = next(event for event in first if event.get("event") == "done")
    second_done = next(event for event in second if event.get("event") == "done")
    assert calls == 1
    assert second_done["data"]["conversation_id"] == first_done["data"]["conversation_id"]
    assert second_done["data"]["message_id"] == first_done["data"]["message_id"]
    second_text = "".join(
        event["data"].get("content", "")
        for event in second
        if event.get("event") == "token"
    )
    # record 意图但 0 工具执行 → 如实"还没记下来"(不谎报成功、也不谎称写库失败)
    assert "还没记下来" in second_text
    assert "没有成功写入数据库" not in second_text
    assert "只执行一次" not in second_text


@pytest.mark.asyncio
async def test_retryable_finalized_turn_reexecutes_without_write_checkpoint(
    db, auth_user_and_headers, monkeypatch
):
    """可重试的历史失败回合不能把旧错误原样 replay 给用户。"""
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title="失败后重试")
    service.save_user_message_once(
        conv.id,
        user.id,
        "刚才请求",
        client_turn_id="turn-retryable-finalized",
        meta={"client_turn_id": "turn-retryable-finalized"},
    )
    service.save_message(
        conv.id,
        "assistant",
        "旧的失败回复",
        meta={
            "write_receipts": [],
            "completion_status": "error",
            "turn_outcome": {
                "category": "tool_blocked",
                "retryable": True,
            },
            "client_turn_finalized": True,
            "client_turn_id": "turn-retryable-finalized",
        },
        client_turn_id="turn-retryable-finalized",
        client_turn_user_id=user.id,
    )

    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    calls = 0

    async def fake_stream(messages, round_tools):
        nonlocal calls
        calls += 1
        yield {"type": "content", "text": "重新执行成功"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(
        executor,
        "刚才请求",
        user_id=user.id,
        client_turn_id="turn-retryable-finalized",
    )

    assert calls == 1
    done = next(event for event in events if event.get("event") == "done")
    assert done["data"].get("replayed") is not True
    assert "重新执行成功" in "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )


@pytest.mark.asyncio
async def test_finalized_turn_with_user_write_checkpoint_still_replays(
    db, auth_user_and_headers, monkeypatch
):
    """用户消息上的未知写入检查点优先于助手侧的可重试标记。"""
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title="未知写入状态")
    service.save_user_message_once(
        conv.id,
        user.id,
        "记录午餐",
        client_turn_id="turn-user-write-checkpoint",
        meta={
            "client_turn_id": "turn-user-write-checkpoint",
            "write_state": {
                "status": "in_flight",
                "tool": "health_record",
                "fingerprint": "write-uncertain",
            },
        },
    )
    service.save_message(
        conv.id,
        "assistant",
        "旧的未知状态回复",
        meta={
            "write_receipts": [],
            "completion_status": "error",
            "turn_outcome": {
                "category": "tool_failed",
                "retryable": True,
            },
            "client_turn_finalized": True,
            "client_turn_id": "turn-user-write-checkpoint",
        },
        client_turn_id="turn-user-write-checkpoint",
        client_turn_user_id=user.id,
    )

    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)

    async def must_not_call_llm(*args, **kwargs):
        raise AssertionError("unknown write state must not be executed again")
        yield  # pragma: no cover

    monkeypatch.setattr(executor, "_call_llm_stream", must_not_call_llm)
    events = await _run(
        executor,
        "记录午餐",
        user_id=user.id,
        client_turn_id="turn-user-write-checkpoint",
    )

    done = next(event for event in events if event.get("event") == "done")
    assert done["data"].get("replayed") is True
    assert "旧的未知状态回复" in "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )


@pytest.mark.asyncio
async def test_legacy_finalized_error_without_write_metadata_still_replays(
    db, auth_user_and_headers, monkeypatch
):
    """旧回合缺少写入证据时只能重放，不能把缺失当成未写入。"""
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title="旧失败回合")
    service.save_user_message_once(
        conv.id,
        user.id,
        "还是有腰疼的症状。",
        client_turn_id="turn-legacy-finalized-error",
        meta={"client_turn_id": "turn-legacy-finalized-error"},
    )
    service.save_message(
        conv.id,
        "assistant",
        "旧版本失败回复",
        meta={
            "completion_status": "error",
            "client_turn_finalized": True,
            "client_turn_id": "turn-legacy-finalized-error",
        },
        client_turn_id="turn-legacy-finalized-error",
        client_turn_user_id=user.id,
    )

    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)

    async def must_not_call_llm(*args, **kwargs):
        raise AssertionError("legacy finalized error must stay fail-closed")
        yield  # pragma: no cover

    monkeypatch.setattr(executor, "_call_llm_stream", must_not_call_llm)
    events = await _run(
        executor,
        "还是有腰疼的症状。",
        user_id=user.id,
        client_turn_id="turn-legacy-finalized-error",
    )

    done = next(event for event in events if event.get("event") == "done")
    assert done["data"].get("replayed") is True
    visible = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    assert "旧版本失败回复" not in visible
    assert "未经过当前健康安全校验" in visible
    assert done["data"]["health_evidence_replay_sanitized"] is True
    assert done["data"]["cards"] == []


@pytest.mark.parametrize(
    "malformed_meta",
    [
        {"write_plan": {}},
        {"write_plan": {"sealed": False}},
        {"write_operations": {"fingerprint": {"status": "rejected"}}},
        {"write_operations": []},
        {"write_shadow": []},
    ],
)
def test_finalized_turn_replay_policy_blocks_any_write_metadata_shape(malformed_meta):
    """写入元数据只要出现就不允许靠形状猜测安全地重执行。"""
    from types import SimpleNamespace

    assistant = SimpleNamespace(
        meta={
            "client_turn_finalized": True,
            "write_receipts": [],
            "turn_outcome": {"category": "tool_failed", "retryable": True},
            **malformed_meta,
        }
    )
    source = SimpleNamespace(meta={})

    assert AgentExecutor._should_replay_finalized_assistant(assistant, source) is True


@pytest.mark.parametrize("assistant_meta", [None, {}, [], "malformed"])
def test_finalized_turn_replay_policy_blocks_malformed_assistant_meta(assistant_meta):
    """助手元数据缺失或类型异常时不允许把旧回合重新执行。"""
    from types import SimpleNamespace

    assistant = SimpleNamespace(meta=assistant_meta)
    assert AgentExecutor._should_replay_finalized_assistant(assistant) is True


@pytest.mark.parametrize("source_meta", [[], "malformed", 0])
def test_finalized_turn_replay_policy_blocks_malformed_source_meta(source_meta):
    """用户消息元数据类型异常时不允许重新执行。"""
    from types import SimpleNamespace

    assistant = SimpleNamespace(
        meta={
            "client_turn_finalized": True,
            "write_receipts": [],
            "turn_outcome": {"category": "tool_failed", "retryable": True},
        }
    )
    source = SimpleNamespace(meta=source_meta)

    assert AgentExecutor._should_replay_finalized_assistant(assistant, source) is True


def test_partial_turn_replay_policy_blocks_missing_source_message():
    """没有 durable user message 时，partial 回合不能被接管。"""
    from types import SimpleNamespace

    assistant = SimpleNamespace(meta={"client_turn_finalized": False})

    assert AgentExecutor._should_replay_finalized_assistant(assistant) is True


@pytest.mark.asyncio
async def test_malformed_finalized_assistant_meta_replays_without_crashing(
    db, auth_user_and_headers, monkeypatch
):
    """malformed metadata 也必须能安全重放，不得触发二次 LLM。"""
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title="畸形回放")
    service.save_user_message_once(
        conv.id,
        user.id,
        "查询我的记录",
        client_turn_id="turn-malformed-replay",
        meta={"client_turn_id": "turn-malformed-replay"},
    )
    assistant = service.save_message(
        conv.id,
        "assistant",
        "旧的可见回复",
        client_turn_id="turn-malformed-replay",
        client_turn_user_id=user.id,
    )
    assistant.meta = ["malformed"]
    db.commit()

    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)

    async def must_not_call_llm(*args, **kwargs):
        raise AssertionError("malformed finalized rows must replay")
        yield  # pragma: no cover

    monkeypatch.setattr(executor, "_call_llm_stream", must_not_call_llm)
    events = await _run(
        executor,
        "查询我的记录",
        user_id=user.id,
        client_turn_id="turn-malformed-replay",
    )

    done = next(event for event in events if event.get("event") == "done")
    assert done["data"].get("replayed") is True
    assert "旧的可见回复" in "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )


@pytest.mark.asyncio
async def test_same_client_turn_id_is_isolated_between_accounts(
    db, auth_user_and_headers, monkeypatch
):
    from tests.conftest import create_authenticated_user

    first_user, _ = auth_user_and_headers
    second_user, _ = create_authenticated_user(db)
    first_executor = AgentExecutor(db)
    second_executor = AgentExecutor(db)
    _wire_min(first_executor, monkeypatch)
    _wire_min(second_executor, monkeypatch)
    calls = []

    async def first_stream(messages, round_tools):
        calls.append(first_user.id)
        yield {"type": "content", "text": "账号一"}
        yield {"type": "finish", "finish_reason": "stop"}

    async def second_stream(messages, round_tools):
        calls.append(second_user.id)
        yield {"type": "content", "text": "账号二"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(first_executor, "_call_llm_stream", first_stream)
    monkeypatch.setattr(second_executor, "_call_llm_stream", second_stream)
    await _run(
        first_executor,
        "查询今天状态",
        user_id=first_user.id,
        client_turn_id="turn-shared-name",
    )
    await _run(
        second_executor,
        "查询今天状态",
        user_id=second_user.id,
        client_turn_id="turn-shared-name",
    )

    assert calls == [first_user.id, second_user.id]


@pytest.mark.asyncio
async def test_duplicate_turn_never_replays_an_unfinalized_assistant(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title="并发回放")
    service.save_user_message_once(
        conv.id,
        user.id,
        "记录午餐",
        client_turn_id="turn-unfinalized",
        meta={"client_turn_id": "turn-unfinalized"},
    )
    service.save_message(
        conv.id,
        "assistant",
        "尚未写完回执 metadata",
        client_turn_id="turn-unfinalized",
        client_turn_user_id=user.id,
    )
    monkeypatch.setattr(
        "app.services.agent_executor.CLIENT_TURN_REPLAY_WAIT_SECONDS",
        0,
    )
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "恢复后完成"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(
        executor,
        "记录午餐",
        user_id=user.id,
        client_turn_id="turn-unfinalized",
    )

    replayed_text = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    assert "尚未写完回执 metadata" not in replayed_text
    done = next(event for event in events if event.get("event") == "done")
    assert done["data"]["completion_status"] == "complete"


@pytest.mark.asyncio
async def test_orphaned_acknowledged_turn_is_taken_over_without_duplicate_user_message(
    db, auth_user_and_headers, monkeypatch
):
    from app.models.agent_conversation import AgentMessage
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title="崩溃恢复")
    service.save_user_message_once(
        conv.id,
        user.id,
        "记录午餐",
        client_turn_id="turn-worker-crashed",
        meta={"client_turn_id": "turn-worker-crashed"},
    )
    service.save_message(
        conv.id,
        "assistant",
        "旧 worker 只写了一半",
        client_turn_id="turn-worker-crashed",
        client_turn_user_id=user.id,
    )
    monkeypatch.setattr(
        "app.services.agent_executor.CLIENT_TURN_REPLAY_WAIT_SECONDS",
        0,
    )

    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    calls = 0

    async def fake_stream(messages, round_tools):
        nonlocal calls
        calls += 1
        yield {"type": "content", "text": "新 worker 已接管并完成。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(
        executor,
        "记录午餐",
        user_id=user.id,
        client_turn_id="turn-worker-crashed",
    )

    assert calls == 1
    replayed_text = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    # 接管后仍然没有真实写入工具回执时，记录意图必须保持 fail-closed；
    # 不能因为新 worker 的自然语言声称而把操作当作已完成。
    assert "还没记下来" in replayed_text
    assert "新 worker 已接管并完成。" not in replayed_text
    saved = (
        db.query(AgentMessage)
        .filter(AgentMessage.conversation_id == conv.id)
        .order_by(AgentMessage.id.asc())
        .all()
    )
    assert [message.role for message in saved] == ["user", "assistant"]
    assert saved[-1].meta["client_turn_finalized"] is True
    assert saved[-1].content != "旧 worker 只写了一半"


@pytest.mark.asyncio
async def test_orphaned_turn_with_in_flight_write_is_not_executed_again(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title="写入状态未知")
    service.save_user_message_once(
        conv.id,
        user.id,
        "记录午餐",
        client_turn_id="turn-write-in-flight",
        meta={
            "client_turn_id": "turn-write-in-flight",
            "write_state": {
                "status": "in_flight",
                "tool": "health_record",
                "fingerprint": "write-1",
            },
        },
    )
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)

    async def must_not_call_llm(*args, **kwargs):
        raise AssertionError("an uncertain write must not be executed again")
        yield  # pragma: no cover

    monkeypatch.setattr(executor, "_call_llm_stream", must_not_call_llm)
    events = await _run(
        executor,
        "记录午餐",
        user_id=user.id,
        client_turn_id="turn-write-in-flight",
    )

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    assert "避免重复写入" in rendered
    assert "先查询" in rendered
    done = next(event for event in events if event.get("event") == "done")
    assert done["data"]["completion_status"] == "error"


@pytest.mark.asyncio
async def test_orphaned_turn_with_verified_write_recovers_its_receipt_without_reexecution(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    receipt = {
        "operation_id": "health_record:diet_record:701",
        "status": "verified",
        "resource_type": "diet_record",
        "resource_id": "701",
        "completed_at": "2026-07-10T12:00:00+00:00",
        "verified": True,
    }
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title="恢复写入回执")
    user_message, _ = service.save_user_message_once(
        conv.id,
        user.id,
        "记录午餐",
        client_turn_id="turn-write-verified",
        meta={"client_turn_id": "turn-write-verified"},
    )
    executor = AgentExecutor(db)
    write_args = {
        "record_type": "diet",
        "data": {"food_items": "午餐"},
    }
    executor._persist_turn_expected_writes(
        user_message,
        [("health_record", write_args)],
    )
    executor._persist_turn_write_state(
        user_message,
        status="verified",
        tool_name="health_record",
        parsed_args=write_args,
        receipt=receipt,
    )
    _wire_min(executor, monkeypatch)

    async def must_not_call_llm(*args, **kwargs):
        raise AssertionError("a verified write must not be executed again")
        yield  # pragma: no cover

    monkeypatch.setattr(executor, "_call_llm_stream", must_not_call_llm)
    events = await _run(
        executor,
        "记录午餐",
        user_id=user.id,
        client_turn_id="turn-write-verified",
    )

    done = next(event for event in events if event.get("event") == "done")
    assert done["data"]["completion_status"] == "complete"
    assert done["data"]["write_receipts"] == [receipt]
    assert "写入已完成" in "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )


@pytest.mark.asyncio
async def test_lock_contender_reclaims_turn_when_owner_dies_before_user_message(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    attempts = 0
    releases = 0

    def fake_acquire(self, user_id, client_turn_id):
        nonlocal attempts
        attempts += 1
        return attempts >= 2

    def fake_release(self, user_id, client_turn_id):
        nonlocal releases
        releases += 1

    monkeypatch.setattr(
        AgentConversationService,
        "try_acquire_client_turn_execution",
        fake_acquire,
    )
    monkeypatch.setattr(
        AgentConversationService,
        "release_client_turn_execution",
        fake_release,
    )
    monkeypatch.setattr(
        "app.services.agent_executor.CLIENT_TURN_REPLAY_WAIT_SECONDS",
        0.2,
    )

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "已恢复处理。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(
        executor,
        "记录午餐",
        user_id=user.id,
        client_turn_id="turn-owner-died-before-claim",
    )

    assert attempts >= 2
    assert releases == 1
    assert any(event.get("event") == "request_persisted" for event in events)
    done = next(event for event in events if event.get("event") == "done")
    assert done["data"]["message_id"] is not None


@pytest.mark.asyncio
async def test_write_state_is_persisted_before_execution_and_verified_with_receipt(
    db, auth_user_and_headers, monkeypatch
):
    from app.models.agent_conversation import AgentMessage

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    rounds = 0

    async def fake_stream(messages, round_tools):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            yield {
                "type": "tool_calls",
                "tool_calls": [{
                    "id": "write-1",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "diet",
                            "data": {
                                "meal_type": "lunch",
                                "food_items": "鸡胸肉",
                                "calories": 165,
                                "protein": 31,
                                "carbs": 0,
                                "fat": 3.6,
                                "fiber": 0,
                            },
                        }, ensure_ascii=False),
                    },
                }],
            }
            yield {"type": "finish", "finish_reason": "tool_calls"}
            return
        yield {"type": "content", "text": "午餐已记录。"}
        yield {"type": "finish", "finish_reason": "stop"}

    async def fake_health_record(base_url, headers, args):
        db.expire_all()
        user_message = (
            db.query(AgentMessage)
            .filter(AgentMessage.role == "user")
            .one()
        )
        assert user_message.meta["write_state"]["status"] == "in_flight"
        assert user_message.meta["write_state"]["tool"] == "health_record"
        assert user_message.meta["write_state"]["fingerprint"]
        return '{"id":701,"food_items":"鸡胸肉","created_at":"2026-07-10T12:00:00Z"}'

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    monkeypatch.setattr(executor, "_exec_health_record", fake_health_record)
    monkeypatch.setattr(
        "app.services.agent_executor._post_record_quality_response",
        lambda *args, **kwargs: None,
    )

    events = await _run(
        executor,
        "记录午餐鸡胸肉",
        user_id=user.id,
        client_turn_id="turn-write-checkpoint",
    )

    db.expire_all()
    user_message = db.query(AgentMessage).filter(AgentMessage.role == "user").one()
    assert user_message.meta["write_state"]["status"] == "verified"
    assert user_message.meta["write_receipts"][0]["resource_id"] == "701"
    done = next(event for event in events if event.get("event") == "done")
    assert done["data"]["write_receipts"] == user_message.meta["write_receipts"]


@pytest.mark.asyncio
async def test_image_persistence_failure_emits_no_durable_ack_or_message(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    uploads = iter(["/api/v1/upload/files/chat/1/first.jpg", None])
    monkeypatch.setattr(executor, "_upload_chat_image", lambda *args: next(uploads))

    with pytest.raises(RuntimeError, match="chat_image_persistence_failed"):
        await _run(
            executor,
            "分析两张午餐照片",
            images=[
                {"base64": "AA==", "type": "jpeg"},
                {"base64": "AA==", "type": "jpeg"},
            ],
            user_id=user.id,
            client_turn_id="turn-image-failure",
        )

    from app.models.agent_conversation import AgentMessage

    assert db.query(AgentMessage).count() == 0


@pytest.mark.asyncio
async def test_image_reference_attach_failure_cleans_uploaded_private_file(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    uploaded_url = f"/api/v1/upload/files/chat/{user.id}/orphan-after-delete.jpg"
    cleaned: list[str] = []
    monkeypatch.setattr(executor, "_upload_chat_image", lambda *args: uploaded_url)
    monkeypatch.setattr(
        AgentConversationService,
        "update_user_message_after_image_upload",
        lambda *args, **kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.chat_utils.delete_chat_image",
        lambda url, owner_id: cleaned.append(url),
    )

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "不应执行到这里。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)

    with pytest.raises(RuntimeError, match="chat_image_message_missing"):
        await _run(
            executor,
            "分析午餐照片",
            images=[{"base64": "AA==", "type": "jpeg"}],
            user_id=user.id,
            client_turn_id="turn-image-deleted-before-attach",
        )

    assert cleaned == [uploaded_url]


@pytest.mark.asyncio
async def test_user_message_insert_failure_happens_before_chat_image_upload(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    uploaded_url = f"/api/v1/upload/files/chat/{user.id}/orphan.jpg"
    uploaded: list[str] = []
    cleaned: list[str] = []
    monkeypatch.setattr(
        executor,
        "_upload_chat_image",
        lambda *args: uploaded.append(uploaded_url) or uploaded_url,
    )
    monkeypatch.setattr(
        AgentConversationService,
        "save_user_message_once",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db insert failed")),
    )
    monkeypatch.setattr(
        "app.services.chat_utils.delete_chat_image",
        lambda url, owner_id: cleaned.append(url),
    )

    with pytest.raises(RuntimeError, match="db insert failed"):
        await _run(
            executor,
            "分析午餐照片",
            images=[{"base64": "AA==", "type": "jpeg"}],
            user_id=user.id,
            client_turn_id="turn-image-db-failure",
        )

    assert uploaded == []
    assert cleaned == []


@pytest.mark.asyncio
async def test_recovered_turn_reuses_its_already_persisted_chat_images(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title="图片恢复")
    stored_url = f"/api/v1/upload/files/chat/{user.id}/persisted.jpg"
    service.save_user_message_once(
        conv.id,
        user.id,
        "分析午餐照片\n[附图: 1张]",
        client_turn_id="turn-image-recovered",
        image_url=f'["{stored_url}"]',
        meta={"client_turn_id": "turn-image-recovered"},
    )
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    monkeypatch.setattr(
        executor,
        "_upload_chat_image",
        lambda *args: (_ for _ in ()).throw(AssertionError("must reuse persisted image")),
    )

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "图片已恢复。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(
        executor,
        "分析午餐照片",
        images=[{"base64": "AA==", "type": "jpeg"}],
        user_id=user.id,
        client_turn_id="turn-image-recovered",
    )

    persisted = next(event for event in events if event.get("event") == "request_persisted")
    assert persisted["data"]["image_urls"] == [stored_url]
    assert any(event.get("event") == "done" for event in events)


def _wire_min(executor, monkeypatch):
    """Minimal wiring so run_stream reaches the round loop without real LLM/provider."""
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    # Keep legacy-event assertions independent from the developer's local .env;
    # staged-response tests below opt in explicitly on the executor instance.
    monkeypatch.setattr("app.services.agent_executor.settings.staged_response_mode", "off")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [{
        "type": "function",
        "function": {"name": "health_query", "description": "x",
                     "parameters": {"type": "object", "properties": {}}},
    }])
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")


# ──── status events: order on a mocked tool turn ────

@pytest.mark.asyncio
async def test_status_events_order_vision_thinking_tool_synthesis(
    db, auth_user_and_headers, monkeypatch
):
    """A photo turn that calls a tool then synthesizes emits, in order:
    vision → thinking(r1) → tool(r1) → synthesis(r2)."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)

    # Force the vision pre-pass path (independent vision, not raw-image direct send).
    monkeypatch.setattr(executor, "_should_send_raw_images_to_primary_model", lambda uid: False)

    async def _no_import(*a, **k):
        return None

    async def _vision(*a, **k):
        return "图里是一份早餐"

    monkeypatch.setattr(executor, "_try_import_medical_report_images", _no_import)
    monkeypatch.setattr(executor, "_analyze_image_with_vision", _vision)

    # Round 1 → one tool call; round 2 → final answer (no tools).
    calls = {"round": 0}

    async def fake_stream(messages, round_tools):
        calls["round"] += 1
        if calls["round"] == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "c1",
                "function": {"name": "health_query", "arguments": "{}"},
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "查到了。"}
            yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)

    async def fake_exec(name, args, token):
        return "今天步数 8000"

    monkeypatch.setattr(executor, "_execute_tool", fake_exec)
    # After a tool ran, force the deterministic synthesis (no-tools) answer round so the
    # round-2 status is 'synthesis' rather than 'thinking'.
    orig = executor._should_synthesize_with_requested_model_after_tools
    monkeypatch.setattr(
        executor,
        "_should_synthesize_with_requested_model_after_tools",
        lambda n: n > 0 or orig(n),
    )

    events = await _run(
        executor,
        "看看我今天的步数",
        images=[{"base64": "AA==", "mime_type": "image/png"}],
        user_id=user.id,
    )
    stages = _statuses(events)

    # exact ordered contract
    assert stages == [
        ("vision", None, None),
        ("thinking", None, 1),
        ("tool", "查询健康数据", 1),
        ("synthesis", None, 2),
    ]


@pytest.mark.asyncio
async def test_status_no_vision_when_raw_images_sent_direct(
    db, auth_user_and_headers, monkeypatch
):
    """Raw images go straight to a multimodal model → NO separate vision pre-pass →
    no 'vision' status event."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    monkeypatch.setattr(executor, "_should_send_raw_images_to_primary_model", lambda uid: True)

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "好的"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)

    events = await _run(
        executor,
        "看看这张图",
        images=[{"base64": "AA==", "mime_type": "image/png"}],
        user_id=user.id,
    )
    stages = _statuses(events)
    assert ("vision", None, None) not in stages
    # a plain no-tool answer turn still emits a thinking status for round 1
    assert ("thinking", None, 1) in stages


@pytest.mark.asyncio
async def test_status_thinking_only_for_plain_text_turn(
    db, auth_user_and_headers, monkeypatch
):
    """No images, no tools → just a single 'thinking' status (no vision/tool/synthesis)."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "你好呀"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)

    events = await _run(executor, "你好呀", user_id=user.id)
    stages = _statuses(events)
    assert stages == [("thinking", None, 1)]


# ──── fast-route answer max_tokens cap ────

def _capture_stream_max_tokens(executor, monkeypatch):
    """Patch the provider resolution so _call_llm_stream records the max_tokens it passes."""
    captured = {}

    class _Prov:
        model = "cap-test"

        async def chat_stream(self, **kwargs):
            captured["max_tokens"] = kwargs.get("max_tokens")
            yield {"type": "content", "text": "OK"}
            yield {"type": "finish", "finish_reason": "stop"}

    # _call_llm_stream calls self._resolve_chat_provider(tools) → (provider, pass_tools)
    monkeypatch.setattr(executor, "_resolve_chat_provider", lambda tools: (_Prov(), None))
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    return captured


@pytest.mark.asyncio
async def test_fast_routed_turn_caps_answer_max_tokens(
    db, auth_user_and_headers, monkeypatch
):
    """Fast-routed simple turn → answer max_tokens capped to FAST_ROUTE_ANSWER_MAX_TOKENS."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    captured = _capture_stream_max_tokens(executor, monkeypatch)
    # ensure the fast route actually fires (env-agnostic)
    monkeypatch.setattr(reg, "pick_fast_tool_model_id", lambda **_k: "deepseek-v4-flash")

    await _run(executor, "查一下我今天喝了多少水", user_id=user.id)

    assert executor._fast_route_simple_turn is True
    assert captured["max_tokens"] == FAST_ROUTE_ANSWER_MAX_TOKENS
    assert FAST_ROUTE_ANSWER_MAX_TOKENS == 2000


@pytest.mark.asyncio
async def test_non_fast_turn_keeps_full_answer_max_tokens(
    db, auth_user_and_headers, monkeypatch
):
    """Analysis/复盘 turn (not fast-routed) → keeps full ANSWER_MAX_TOKENS (8000)."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    captured = _capture_stream_max_tokens(executor, monkeypatch)
    monkeypatch.setattr(reg, "pick_fast_tool_model_id", lambda **_k: "deepseek-v4-flash")

    await _run(executor, "综合分析我的健康趋势", user_id=user.id)

    assert executor._fast_route_simple_turn is False
    assert captured["max_tokens"] == ANSWER_MAX_TOKENS
    assert ANSWER_MAX_TOKENS == 8000


@pytest.mark.asyncio
async def test_staged_balanced_turn_uses_bounded_answer_budget(db):
    """Balanced staged answers must not retain the generic 8k decode tail."""
    balanced_budget = getattr(
        __import__("app.services.agent_executor", fromlist=["BALANCED_ANSWER_MAX_TOKENS"]),
        "BALANCED_ANSWER_MAX_TOKENS",
        None,
    )
    assert balanced_budget is not None, "balanced answer budget is not implemented"
    executor = AgentExecutor(db)
    executor._fast_route_simple_turn = False
    executor._staged_response_mode = "on"
    executor._staged_answer_task_tier = "balanced"

    assert executor._answer_max_tokens() == balanced_budget
    assert balanced_budget == 3000


@pytest.mark.asyncio
async def test_staged_high_stakes_keeps_full_quality_budget(db):
    executor = AgentExecutor(db)
    executor._fast_route_simple_turn = False
    executor._staged_response_mode = "on"
    executor._staged_answer_task_tier = "high_stakes"

    assert executor._answer_max_tokens() == ANSWER_MAX_TOKENS


@pytest.mark.asyncio
async def test_health_evidence_turn_uses_bounded_verified_answer_budget(db):
    health_budget = getattr(
        __import__("app.services.agent_executor", fromlist=["HEALTH_EVIDENCE_ANSWER_MAX_TOKENS"]),
        "HEALTH_EVIDENCE_ANSWER_MAX_TOKENS",
        None,
    )
    assert health_budget is not None, "health evidence answer budget is not implemented"
    executor = AgentExecutor(db)
    executor._fast_route_simple_turn = False
    executor._staged_response_mode = "on"
    executor._staged_answer_task_tier = "high_stakes"
    executor._health_evidence_answer_budget_active = True

    assert executor._answer_max_tokens() == health_budget
    assert health_budget == 1200


@pytest.mark.asyncio
async def test_health_evidence_answer_budget_can_roll_back_without_code_change(
    db,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "health_evidence_answer_max_tokens",
        ANSWER_MAX_TOKENS,
        raising=False,
    )
    executor = AgentExecutor(db)
    executor._health_evidence_answer_budget_active = True

    assert executor._answer_max_tokens() == ANSWER_MAX_TOKENS


@pytest.mark.asyncio
async def test_staged_flag_off_keeps_legacy_full_budget(db):
    executor = AgentExecutor(db)
    executor._fast_route_simple_turn = False
    executor._staged_response_mode = "off"
    executor._staged_answer_task_tier = "balanced"

    assert executor._answer_max_tokens() == ANSWER_MAX_TOKENS


@pytest.mark.asyncio
async def test_answer_max_tokens_helper_switches_on_flag(db):
    """Unit: _answer_max_tokens returns capped only when the fast-route flag is set."""
    executor = AgentExecutor(db)
    executor._fast_route_simple_turn = False
    assert executor._answer_max_tokens() == ANSWER_MAX_TOKENS
    executor._fast_route_simple_turn = True
    assert executor._answer_max_tokens() == FAST_ROUTE_ANSWER_MAX_TOKENS
