import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config import settings
from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.system_knowledge import KBDocument
from app.services.agent_executor import AgentExecutor
from app.services.health_evidence import (
    SafetyProfileContext,
    classify_health_intent,
    compile_health_evidence_turn,
)
from app.twin.schema import HealthTwin, TwinMeta
from app.services.system_knowledge_importer import import_system_kb_artifacts
from app.services.system_knowledge_service import search_knowledge


NOW = datetime(2026, 7, 29, tzinfo=UTC)
FULLY_SCREENED_QUERY = (
    "腰痛，没有排尿困难或大小便异常，没有会阴或鞍区麻木；"
    "没有双腿麻木或无力；没有严重外伤；没有发热或严重感染；"
    "没有不明原因体重下降；没有癌症史"
)
_CLAIMS_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "system_kb_v2_seed"
    / "claims.jsonl"
)
_SEED_DIR = _CLAIMS_PATH.parent

def _authority_result(
    expected_id: str = "claim:c_low_back_serious_cause_screening_boundary",
) -> dict:
    for line in _CLAIMS_PATH.read_text(encoding="utf-8").splitlines():
        document = json.loads(line)
        if document.get("doc_id") == expected_id:
            return {"score": 0.99, "document": document}
    raise AssertionError(f"published claim missing: {expected_id}")


def _turn(user_id: int, query: str):
    expected_id = (
        "claim:c_low_back_self_management_activity_boundary"
        if query == FULLY_SCREENED_QUERY
        else "claim:c_low_back_serious_cause_screening_boundary"
    )
    return compile_health_evidence_turn(
        twin=HealthTwin(meta=TwinMeta(user_id=user_id, generated_at=NOW)),
        intent=classify_health_intent(query),
        authority_results=[_authority_result(expected_id)],
        safety_profile=SafetyProfileContext(population="adults_16_plus"),
        now=NOW,
    )


@pytest.mark.asyncio
async def test_flag_off_legacy_knowledge_search_cannot_release_low_back_pack(
    db,
    monkeypatch,
):
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", False)
    counts = import_system_kb_artifacts(
        db,
        _SEED_DIR,
        actor="test:flag_off_low_back_isolation",
    )
    assert counts["skipped_documents"] == 0
    sentinel = "MALICIOUS_HELD_LOW_BACK_SENTINEL_7A91"
    held_claim = db.get(
        KBDocument,
        "claim:c_low_back_emergency_neurologic_red_flags",
    )
    assert held_claim is not None
    held_claim.summary = sentinel
    held_claim.body = sentinel
    db.commit()

    generic = search_knowledge(
        db,
        "腰痛 大小便失禁 会阴麻木",
        limit=20,
    )
    output = await AgentExecutor(db)._exec_knowledge_search(
        {"query": "腰痛 大小便失禁 会阴麻木"}
    )

    assert sentinel not in str(generic)
    assert sentinel not in output


def _install_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    user_id: int,
    query: str,
) -> None:
    import app.services.health_evidence as health_evidence

    monkeypatch.setattr(
        settings,
        "health_evidence_runtime_enabled",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        health_evidence,
        "build_health_evidence_turn",
        lambda db, *, user_id, query, intent, now=None: _turn(user_id, query),
        raising=False,
    )


def _install_stream(
    executor: AgentExecutor,
    chunks: list[str],
    captured: list,
    captured_tools: list | None = None,
) -> None:
    async def fake_call_llm_stream(messages, tools):
        captured.append(messages)
        if captured_tools is not None:
            captured_tools.append(tools)
        for chunk in chunks:
            yield {"type": "content", "text": chunk}
        yield {"type": "finish", "finish_reason": "stop"}

    async def fake_call_llm(messages, tools):
        return {"content": "".join(chunks), "finish_reason": "stop"}

    executor._call_llm_stream = fake_call_llm_stream
    executor._call_llm = fake_call_llm


def _token_text(events: list[dict]) -> str:
    return "".join(
        str((event.get("data") or {}).get("content") or "")
        for event in events
        if event.get("event") == "token"
    )


def _last_user_content(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


@pytest.mark.asyncio
async def test_health_turn_injects_one_clinical_envelope_before_surface_format(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    query = FULLY_SCREENED_QUERY
    _install_runtime(monkeypatch, user_id=user.id, query=query)
    executor = AgentExecutor(db)
    captured: list[list[dict]] = []
    captured_tools: list[list[dict]] = []
    _install_stream(
        executor,
        [
            "目前信息不足，先确认警示征象。",
            "如有排尿困难、会阴麻木或双腿明显无力，请立即就医。",
        ],
        captured,
        captured_tools,
    )
    monkeypatch.setattr(
        executor,
        "_build_system_knowledge_prompt_context",
        lambda *_args, **_kwargs: pytest.fail(
            "health runtime must not invoke the legacy prompt retriever"
        ),
    )
    monkeypatch.setattr(
        executor,
        "_build_system_knowledge_evidence_card",
        lambda *_args, **_kwargs: pytest.fail(
            "health runtime must not build the legacy evidence card"
        ),
    )

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=query,
            extra_context=json.dumps(
                {
                    "client": "mac",
                    "model_id": "deepseek-v4-flash",
                    "desktop_markdown_response_instruction": "MAC_SURFACE_FORMAT",
                }
            ),
        )
    ]

    assert events[-1]["event"] == "done"
    assert len(captured) == 1
    assert captured_tools == [[]]
    assert executor._request_model_id == settings.health_evidence_model_id
    system_prompt = str(captured[0][0]["content"])
    turn_prompt = _last_user_content(captured[0])
    assert "## 用户健康档案" not in system_prompt
    assert turn_prompt.count("## 健康证据运行时") == 1
    assert turn_prompt.count("## 本轮个人健康证据") == 1
    assert turn_prompt.count("## 权威医学证据") == 1
    assert turn_prompt.index("## 健康证据运行时") < turn_prompt.index(
        "MAC_SURFACE_FORMAT"
    )
    assert "## 系统知识库相关条目" not in turn_prompt


@pytest.mark.asyncio
async def test_clarification_turn_bypasses_model_and_renders_policy(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    query = "我腰疼怎么办"
    _install_runtime(monkeypatch, user_id=user.id, query=query)
    executor = AgentExecutor(db)
    captured: list[list[dict]] = []
    _install_stream(executor, ["这段模型文本不应被请求。"], captured)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=query,
            channel="typed",
        )
    ]

    done = events[-1]["data"]
    assert captured == []
    assert done["llm_rounds"] == 0
    assert done["health_evidence_manifest"]["sufficiency"] == "clarify"
    assert "请先确认" in _token_text(events)


@pytest.mark.asyncio
async def test_health_turn_never_streams_unverified_model_text_and_persists_manifest(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    query = FULLY_SCREENED_QUERY
    _install_runtime(monkeypatch, user_id=user.id, query=query)
    executor = AgentExecutor(db)
    captured: list[list[dict]] = []
    unsafe = "你已经确诊腰椎间盘突出，不需要医生确认，先在家观察。"
    _install_stream(executor, [unsafe[:12], unsafe[12:]], captured)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=query,
            channel="typed",
        )
    ]

    done = events[-1]["data"]
    visible = _token_text(events)
    assert unsafe not in visible
    assert "已经确诊" not in visible
    assert "原回答未通过健康安全校验" in visible
    assert done["health_evidence_manifest"]["verifier_verdict"] == "block"
    assert done["health_evidence_manifest"]["intent"]["intent_id"] == (
        "health_advice.symptom.low_back_pain"
    )
    cards = [
        card for card in done["cards"] if card.get("type") == "health_evidence"
    ]
    assert len(cards) == 1
    assert cards[0]["data"] == done["health_evidence_manifest"]
    assert done["sources_used"] == ["个人健康上下文：symptom"]

    assistant = (
        db.query(AgentMessage)
        .filter(AgentMessage.role == "assistant")
        .order_by(AgentMessage.id.desc())
        .first()
    )
    assert assistant is not None
    assert assistant.content == visible
    assert assistant.meta["health_evidence_manifest"] == (
        done["health_evidence_manifest"]
    )
    assert assistant.meta["cards"][0]["type"] == "health_evidence"


@pytest.mark.asyncio
async def test_non_health_turn_keeps_existing_stream_contract(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    monkeypatch.setattr(
        settings,
        "health_evidence_runtime_enabled",
        True,
        raising=False,
    )
    executor = AgentExecutor(db)
    captured: list[list[dict]] = []
    _install_stream(executor, ["你好，", "今天想聊什么？"], captured)
    monkeypatch.setattr(
        executor,
        "_build_system_knowledge_prompt_context",
        lambda *_args, **_kwargs: "",
    )

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="你好",
            channel="typed",
        )
    ]

    assert _token_text(events) == "你好，今天想聊什么？"
    assert "health_evidence_manifest" not in events[-1]["data"]
    assert not any(
        card.get("type") == "health_evidence"
        for card in events[-1]["data"]["cards"]
    )


@pytest.mark.asyncio
async def test_bare_clinician_context_precedes_health_advice_release(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    import app.services.health_evidence as health_evidence

    user, _headers = auth_user_and_headers
    query = "医生诊断是腰痛由臀肌无力导致"
    build_calls: list[str] = []

    def build_turn(db_arg, *, user_id, query, intent, now=None):
        del db_arg, now
        build_calls.append(query)
        return _turn(user_id, query)

    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)
    monkeypatch.setattr(
        health_evidence,
        "build_health_evidence_turn",
        build_turn,
    )
    executor = AgentExecutor(db)
    captured: list[list[dict]] = []
    source_aware_reply = (
        "我理解这是你转述的医生判断/评估；"
        "本轮不会把它升格成 Reva 的诊断，也不会自动保存。"
    )
    _install_stream(executor, [source_aware_reply], captured)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=query,
            channel="typed",
        )
    ]

    done = events[-1]["data"]
    assert build_calls == []
    assert len(captured) == 1
    assert _token_text(events) == source_aware_reply
    assert "health_evidence_manifest" not in done
    assert done["tools_used"] == []
    assert done["write_receipts"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected_tools"),
    (
        (
            "根据医生诊断腰痛需要删除记录",
            [],
        ),
        (
            "请记录医生诊断：腰痛由臀肌无力导致",
            ["record_doctor_feedback"],
        ),
    ),
)
async def test_non_emergency_clinician_actions_precede_health_release(
    db,
    auth_user_and_headers,
    monkeypatch,
    query,
    expected_tools,
):
    import app.services.health_evidence as health_evidence

    user, _headers = auth_user_and_headers
    build_calls: list[str] = []

    def build_turn(db_arg, *, user_id, query, intent, now=None):
        del db_arg, now
        build_calls.append(query)
        return _turn(user_id, query)

    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)
    monkeypatch.setattr(
        health_evidence,
        "build_health_evidence_turn",
        build_turn,
    )
    executor = AgentExecutor(db)
    captured_messages: list[list[dict]] = []
    captured_tools: list[list[dict]] = []
    _install_stream(
        executor,
        ["本轮按临床来源护栏处理。"],
        captured_messages,
        captured_tools,
    )

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=query,
            channel="typed",
        )
    ]

    done = events[-1]["data"]
    assert build_calls == []
    assert len(captured_messages) == 1
    assert [
        (tool.get("function") or {}).get("name")
        for tool in captured_tools[0]
    ] == expected_tools
    assert "health_evidence_manifest" not in done


@pytest.mark.asyncio
async def test_clinician_advice_still_uses_health_evidence_runtime(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    import app.services.health_evidence as health_evidence

    user, _headers = auth_user_and_headers
    query = "医生说按医嘱调整腰痛训练会有什么风险？"
    build_calls: list[str] = []

    def build_turn(db_arg, *, user_id, query, intent, now=None):
        del db_arg, now
        build_calls.append(query)
        return _turn(user_id, query)

    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)
    monkeypatch.setattr(
        health_evidence,
        "build_health_evidence_turn",
        build_turn,
    )
    executor = AgentExecutor(db)
    captured: list[list[dict]] = []
    _install_stream(executor, ["需要结合证据判断。"], captured)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=query,
            channel="typed",
        )
    ]

    done = events[-1]["data"]
    assert build_calls == [query]
    assert done["health_evidence_manifest"]["intent"]["intent_id"] == (
        "health_advice.symptom.low_back_pain"
    )


@pytest.mark.asyncio
async def test_acute_red_flags_override_bare_clinician_context_precedence(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    query = "医生说我腰痛、排不出尿而且会阴麻木"
    _install_runtime(monkeypatch, user_id=user.id, query=query)
    executor = AgentExecutor(db)
    captured: list[list[dict]] = []
    _install_stream(executor, ["这段模型文本不应被请求。"], captured)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=query,
            channel="typed",
        )
    ]

    done = events[-1]["data"]
    assert captured == []
    assert done["health_evidence_manifest"]["risk_level"] == "emergency"
    assert "立即" in _token_text(events)


@pytest.mark.asyncio
async def test_health_runtime_compilation_failure_stays_failed_and_safe(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    import app.services.health_evidence as health_evidence

    user, _headers = auth_user_and_headers
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)
    monkeypatch.setattr(
        health_evidence,
        "build_health_evidence_turn",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("synthetic compiler failure")
        ),
    )
    executor = AgentExecutor(db)
    captured: list[list[dict]] = []
    unsafe = "你已经确诊腰椎间盘突出，不用医生确认。"
    _install_stream(executor, [unsafe], captured)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="我腰疼怎么办",
            channel="typed",
        )
    ]

    done = events[-1]["data"]
    manifest = done["health_evidence_manifest"]
    assert manifest["sufficiency"] == "safe_fallback"
    assert manifest["verifier_verdict"] == "block"
    assert {
        gap["category"]: gap["state"]
        for gap in manifest["gaps"]
    } == {
        "active_problem": "failed",
        "allergy": "failed",
        "chronic_condition": "failed",
        "medication": "failed",
        "symptom": "failed",
    }
    assert unsafe not in _token_text(events)


@pytest.mark.asyncio
async def test_named_released_source_resolves_before_buffered_health_synthesis(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    query = "用益家知研回答：我腰疼怎么办"
    _install_runtime(monkeypatch, user_id=user.id, query=query)
    executor = AgentExecutor(db)
    captured_messages: list[list[dict]] = []
    captured_tools: list[list[dict]] = []
    _install_stream(
        executor,
        ["已基于该指定来源的审定结论回答。"],
        captured_messages,
        captured_tools,
    )
    executed: list[tuple[str, dict]] = []

    async def fake_execute_tool(name, args, token):
        executed.append((name, json.loads(args)))
        return (
            "requested_source=益家知研\n"
            "resolved_source=yijia_reviewed\n"
            "source_status=released\n"
            "已检索该指定来源。"
        )

    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=query,
            channel="typed",
        )
    ]

    assert executed == [(
        "knowledge_search",
        {
            "query": query,
            "knowledge_source": "益家知研",
        },
    )]
    assert [tool["function"]["name"] for tool in captured_tools[0]] == [
        "knowledge_search"
    ]
    assert captured_tools[1] == []
    assert events[-1]["data"]["tools_used"] == ["knowledge_search"]


@pytest.mark.asyncio
async def test_named_released_source_cannot_suppress_emergency_release(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    query = "用益家知研回答：腰痛、排不出尿而且会阴麻木"
    _install_runtime(monkeypatch, user_id=user.id, query=query)
    executor = AgentExecutor(db)
    captured_messages: list[list[dict]] = []
    captured_tools: list[list[dict]] = []
    _install_stream(
        executor,
        ["可以先等等看。"],
        captured_messages,
        captured_tools,
    )
    executed: list[str] = []

    async def fake_execute_tool(name, args, token):
        executed.append(name)
        return "source_status=released\n已检索该指定来源。"

    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=query,
            channel="typed",
        )
    ]

    visible = _token_text(events)
    assert executed == ["knowledge_search"]
    assert "立即" in visible
    assert "急诊" in visible
    assert "等等看" not in visible
    assert events[-1]["data"]["health_evidence_manifest"]["risk_level"] == "emergency"


@pytest.mark.asyncio
async def test_emergency_health_turn_cannot_be_overwritten_by_record_fail_closed(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    query = "腰痛、排不出尿而且会阴麻木"
    _install_runtime(monkeypatch, user_id=user.id, query=query)
    executor = AgentExecutor(db)
    captured: list[list[dict]] = []
    captured_tools: list[list[dict]] = []
    _install_stream(
        executor,
        ["我会把这条症状记录下来。"],
        captured,
        captured_tools,
    )

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=query,
            channel="typed",
        )
    ]

    visible = _token_text(events)
    done = events[-1]["data"]
    assert "立即" in visible
    assert "急诊" in visible
    assert "记录下来" not in visible
    assert "想记录但还没记下来" not in visible
    assert done["health_evidence_manifest"]["risk_level"] == "emergency"
    assert done["health_evidence_manifest"]["verifier_verdict"] == "block"
    assert captured_tools == []
    assert done["llm_rounds"] == 0
    assert executor._prefer_fast_record_model is False


@pytest.mark.asyncio
async def test_structured_mobile_continuation_routes_without_keyword_guessing(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    import app.services.health_evidence as health_evidence

    user, _headers = auth_user_and_headers
    captured_turn: dict = {}
    parent_turn_id = "mobile-turn-991"
    parent_conversation = AgentConversation(
        user_id=user.id,
        title="腰痛影像判断",
    )
    db.add(parent_conversation)
    db.flush()
    db.add(
        AgentMessage(
            conversation_id=parent_conversation.id,
            role="user",
            content="我腰痛，是否需要马上做 MRI 影像检查？",
            client_turn_id=parent_turn_id,
        )
    )
    parent_assistant = AgentMessage(
        conversation_id=parent_conversation.id,
        role="assistant",
        content="请先补充警示征象。",
        meta={
            "client_turn_id": parent_turn_id,
            "health_evidence_manifest": {
                "intent": {
                    "intent_id": (
                        "health_advice.symptom.low_back_pain"
                    )
                }
            },
        },
    )
    db.add(parent_assistant)
    db.commit()

    def build_turn(db_arg, *, user_id, query, intent, now=None):
        del db_arg, now
        captured_turn.update(
            {
                "user_id": user_id,
                "query": query,
                "intent": intent,
            }
        )
        return compile_health_evidence_turn(
            twin=HealthTwin(
                meta=TwinMeta(user_id=user_id, generated_at=NOW)
            ),
            intent=intent,
            authority_results=[],
            safety_profile=SafetyProfileContext(
                population="adults_16_plus"
            ),
            now=NOW,
        )

    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)
    monkeypatch.setattr(
        health_evidence,
        "build_health_evidence_turn",
        build_turn,
    )
    executor = AgentExecutor(db)
    captured_messages: list[list[dict]] = []
    _install_stream(
        executor,
        ["我会把回答记录下来。"],
        captured_messages,
    )
    extra_context = json.dumps(
        {
            "health_evidence_continuation": {
                "version": "health-evidence-continuation.v1",
                "parent_intent_id": (
                    "health_advice.symptom.low_back_pain"
                ),
                "parent_message_id": parent_assistant.id,
                "parent_turn_id": parent_turn_id,
                "answers": [
                    {
                        "discriminator_id": "low_back.cauda_equina",
                        "answer": "yes",
                    }
                ],
            }
        },
        ensure_ascii=False,
    )

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="我的回答已提交",
            channel="typed",
            extra_context=extra_context,
        )
    ]

    visible = _token_text(events)
    assert captured_turn["intent"].intent_id == (
        "health_advice.symptom.low_back_pain"
    )
    assert captured_turn["intent"].risk_level.value == "emergency"
    assert (
        "排尿困难、膀胱/肠道控制改变或会阴感觉异常中至少一项为是"
        in captured_turn["query"]
    )
    assert "排不出尿并且会阴麻木" not in captured_turn["query"]
    assert "MRI" in captured_turn["query"]
    assert "立即" in visible
    assert "急诊" in visible
    assert "记录下来" not in visible
    assert captured_messages == []
    assert parent_turn_id not in visible


@pytest.mark.asyncio
async def test_health_turn_disables_pre_verifier_medication_and_recipe_bypasses(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services import procedure_recipe_service

    user, _headers = auth_user_and_headers
    query = FULLY_SCREENED_QUERY
    _install_runtime(monkeypatch, user_id=user.id, query=query)
    executor = AgentExecutor(db)
    captured: list[list[dict]] = []
    _install_stream(executor, ["先确认警示征象。"], captured)

    monkeypatch.setattr(
        executor,
        "_resolve_medication_batch_turn",
        lambda **_kwargs: pytest.fail(
            "health turns must not enter medication-batch early return"
        ),
    )
    monkeypatch.setattr(
        procedure_recipe_service,
        "match_trigger",
        lambda *_args, **_kwargs: pytest.fail(
            "health turns must not enter recipe early return"
        ),
    )

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=query,
            channel="typed",
        )
    ]

    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["health_evidence_manifest"]


@pytest.mark.asyncio
async def test_health_turn_discards_hallucinated_structured_tool_call(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    query = FULLY_SCREENED_QUERY
    _install_runtime(monkeypatch, user_id=user.id, query=query)
    executor = AgentExecutor(db)
    model_calls = 0

    async def fake_stream(_messages, tools):
        nonlocal model_calls
        model_calls += 1
        assert tools == []
        yield {
            "type": "tool_calls",
            "tool_calls": [
                {
                    "id": "hallucinated-health-write",
                    "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps(
                            {
                                "record_type": "symptom",
                                "data": {"symptom": "腰痛"},
                            },
                            ensure_ascii=False,
                        ),
                    },
                }
            ],
        }
        yield {"type": "finish", "finish_reason": "tool_calls"}

    async def fail_execute(*_args, **_kwargs):
        raise AssertionError("sealed health synthesis must execute no tool")

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    monkeypatch.setattr(executor, "_execute_tool", fail_execute)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=query,
            channel="typed",
        )
    ]

    done = events[-1]["data"]
    assert model_calls == 1
    assert not any(
        event.get("event") in {"tool_call", "tool_result"}
        for event in events
    )
    assert done["tools_used"] == []
    assert done["write_receipts"] == []
    assert "本轮模型未生成可发布的健康回答" not in _token_text(events)
    assert done["health_evidence_manifest"]["verifier_verdict"] == "repair"


@pytest.mark.asyncio
async def test_flag_off_legacy_health_replay_never_releases_unverified_answer(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _headers = auth_user_and_headers
    turn_id = "legacy-health-replay"
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(
        user.id,
        None,
        title="legacy health replay",
    )
    service.save_user_message_once(
        conversation.id,
        user.id,
        "腰疼怎么办",
        client_turn_id=turn_id,
        meta={"client_turn_id": turn_id},
    )
    unsafe = "已确诊腰椎间盘突出，建议布洛芬400mg每6小时一次。"
    service.save_message(
        conversation.id,
        "assistant",
        unsafe,
        meta={
            "completion_status": "complete",
            "client_turn_finalized": True,
            "client_turn_id": turn_id,
            "health_evidence_manifest": {
                "version": "health-evidence.legacy",
            },
        },
        client_turn_id=turn_id,
        client_turn_user_id=user.id,
    )
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", False)
    executor = AgentExecutor(db)

    async def must_not_call_llm(*_args, **_kwargs):
        raise AssertionError("durable replay must not execute the model")
        yield  # pragma: no cover

    monkeypatch.setattr(executor, "_call_llm_stream", must_not_call_llm)
    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="腰疼怎么办",
            client_turn_id=turn_id,
            channel="typed",
        )
    ]

    visible = _token_text(events)
    done = events[-1]["data"]
    assert unsafe not in visible
    assert "未经过当前健康安全校验" in visible
    assert done["replayed"] is True
    assert done["health_evidence_replay_sanitized"] is True
    assert done["cards"] == []
