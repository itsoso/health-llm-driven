"""Recovery-data quality must tighten, never relax, exercise advice."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import agent_executor as ae
from app.services.agent_executor import AgentExecutor


def _evaluate(*, message, result, snapshot, args=None, tool_name="health_query"):
    evaluator = getattr(ae, "_evaluate_recovery_data_guard", None)
    assert evaluator is not None, "recovery data guard is not implemented"
    return evaluator(
        message,
        tool_name=tool_name,
        args=args or {"dimension": "sleep", "days": 2},
        result=result,
        wearable_snapshot=snapshot,
    )


def _healthy_snapshot():
    return {
        "metrics": {
            "total_sleep_duration": {"confidence": "high"},
            "hrv": {"confidence": "high"},
        },
        "data_quality_issues": [],
    }


def test_missing_recovery_core_signal_degrades_and_forbids_high_intensity():
    decision = _evaluate(
        message="昨晚睡得怎样，今天是否适合锻炼？",
        result='{"status":"no_data","message":"没有足够的睡眠数据"}',
        snapshot={"metrics": {}, "data_quality_issues": []},
    )

    assert decision is not None
    assert decision.status == "degraded"
    assert "missing_core_signal" in decision.reason_codes
    assert "不得建议高强度" in decision.model_directive
    assert "数据不足" in decision.model_directive


def test_stale_or_conflicting_recovery_signal_degrades():
    snapshot = _healthy_snapshot()
    snapshot["data_quality_issues"] = [
        {"kind": "stale", "metric": "hrv"},
        {"kind": "conflict", "metric": "total_sleep_duration"},
    ]

    decision = _evaluate(
        message="结合恢复状态判断今天训练强度",
        result='{"status":"success","days_analyzed":2}',
        snapshot=snapshot,
    )

    assert decision is not None
    assert decision.reason_codes == ("stale_signal", "conflicting_signal")


def test_implausible_recovery_result_degrades_even_with_complete_snapshot():
    decision = _evaluate(
        message="恢复怎么样，今天能跑间歇吗？",
        result=(
            '{"status":"success","_data_plausibility_warning":'
            '[{"name":"heart_rate","value":400}]}'
        ),
        snapshot=_healthy_snapshot(),
    )

    assert decision is not None
    assert decision.reason_codes == ("implausible_signal",)


def test_healthy_recovery_data_keeps_normal_route():
    decision = _evaluate(
        message="昨晚睡得怎样，今天是否适合锻炼？",
        result='{"status":"success","days_analyzed":2}',
        snapshot=_healthy_snapshot(),
    )

    assert decision is not None
    assert decision.status == "ok"
    assert decision.reason_codes == ()
    assert decision.model_directive == ""


def test_non_recovery_step_query_does_not_activate_guard():
    decision = _evaluate(
        message="今天走了多少步？",
        result="可穿戴 daily 数据: 步数 8000",
        snapshot={"metrics": {}, "data_quality_issues": []},
        args={"dimension": "activity", "days": 1},
    )

    assert decision is None


@pytest.mark.parametrize(
    "message",
    [
        "昨晚睡了4小时，今天能练腿吗？",
        "最近休息得不好，今天能做HIIT吗？",
        "这两天很疲劳，今天是否应该跑步？",
        "昨晚没睡好，今天还能健身吗？",
        "昨晚没睡好，今天去健身房合适吗？",
        "昨晚没睡好，今天健身好吗？",
        "昨天只睡了三小时，今天去跑步怎么样？",
        "昨晚睡得很差，今天训练行不行？",
        "昨晚失眠了，今天健身会不会太累？",
        "昨晚没休息好，今天做力量训练有问题吗？",
        "昨晚睡得不行，今天还去健身？",
        "最近休息差，这两天先不先跑步？",
        "我睡得不好，去健身安全吗？",
        "睡得不好，还去健身？",
    ],
)
def test_natural_recovery_exercise_advice_language_activates_guard(message):
    decision = _evaluate(
        message=message,
        result='{"status":"no_data"}',
        snapshot={"metrics": {}, "data_quality_issues": []},
    )

    assert decision is not None
    assert decision.status == "degraded"


def test_recovery_relationship_question_without_advice_does_not_activate_guard():
    decision = _evaluate(
        message="为什么运动后睡眠变差？",
        result='{"status":"success"}',
        snapshot=_healthy_snapshot(),
    )

    assert decision is None


def test_general_recovery_relationship_question_does_not_activate_guard():
    decision = _evaluate(
        message="为什么睡眠不足时不适合高强度训练？",
        result='{"status":"success"}',
        snapshot=_healthy_snapshot(),
    )

    assert decision is None


def test_general_recovery_effect_question_does_not_activate_guard():
    decision = _evaluate(
        message="睡眠如何影响运动表现？",
        result='{"status":"success"}',
        snapshot=_healthy_snapshot(),
    )

    assert decision is None


def test_general_recovery_relationship_synonym_does_not_activate_guard():
    decision = _evaluate(
        message="睡眠和运动有什么联系？",
        result='{"status":"success"}',
        snapshot=_healthy_snapshot(),
    )

    assert decision is None


def test_recovery_exercise_decision_is_forced_off_multi_model_route():
    classifier = getattr(ae, "_is_recovery_exercise_advice_message", None)
    assert classifier is not None, "multi-model recovery routing guard is missing"

    assert classifier("昨晚没睡好，今天还能健身吗？") is True
    assert classifier("昨晚没睡好，今天健身好吗？") is True
    assert classifier("昨天只睡了三小时，今天去跑步怎么样？") is True
    assert classifier("昨晚睡得很差，今天训练行不行？") is True
    assert classifier("昨晚失眠了，今天健身会不会太累？") is True
    assert classifier("昨晚没休息好，今天做力量训练有问题吗？") is True
    assert classifier("我睡得不好，去健身安全吗？") is True
    assert classifier("为什么睡眠不足时不适合高强度训练？") is False


@pytest.mark.parametrize(
    "result",
    [
        '{"status":"error","message":"wearable read failed"}',
        '{"status":"failed","error":"timeout"}',
        "wearable service unavailable",
        "可穿戴数据请求超时",
        "上游连接失败",
    ],
)
def test_structured_or_plain_read_failures_fail_closed(result):
    decision = _evaluate(
        message="昨晚睡得怎样，今天是否适合锻炼？",
        result=result,
        snapshot=_healthy_snapshot(),
    )

    assert decision is not None
    assert decision.status == "degraded"
    assert decision.reason_codes == ("read_failed",)


def test_batch_nested_plausibility_warning_fails_closed():
    decision = _evaluate(
        message="结合恢复状态判断今天是否适合训练",
        result=(
            '{"status":"success","results":[{"dimension":"hrv",'
            '"_data_plausibility_warning":[{"value":999}]}]}'
        ),
        snapshot=_healthy_snapshot(),
        tool_name="health_query_batch",
        args={"queries": [{"dimension": "hrv"}, {"dimension": "sleep"}]},
    )

    assert decision is not None
    assert decision.reason_codes == ("implausible_signal",)


def test_guard_failure_fails_closed_for_recovery_advice():
    decision = _evaluate(
        message="今天恢复怎么样，适合训练吗？",
        result='{"status":"success"}',
        snapshot=None,
    )

    assert decision is not None
    assert decision.status == "degraded"
    assert decision.reason_codes == ("guard_unavailable",)


def test_degraded_guard_forces_reasoning_model_even_from_balanced_selection(db):
    executor = AgentExecutor(db)
    executor._staged_response_mode = "on"
    executor._staged_answer_task_tier = "balanced"
    executor._staged_answer_model_selected = True
    executor._request_model_id = "qwen3.7-plus"
    decision = _evaluate(
        message="昨晚睡得怎样，今天是否适合锻炼？",
        result='{"status":"no_data"}',
        snapshot={"metrics": {}, "data_quality_issues": []},
    )

    activator = getattr(executor, "_activate_recovery_data_guard", None)
    assert activator is not None, "recovery guard is not wired to model routing"
    with patch(
        "app.services.llm.task_routing.pick_model_id_by_tier",
        return_value="qwen3.7-max",
    ):
        escalated = activator(decision)

    assert escalated is True
    assert executor._staged_answer_task_tier == "high_stakes"
    assert executor._request_model_id == "qwen3.7-max"
    assert "staged_answer_recovery_data_degraded" in executor._model_fallback_reasons


@pytest.mark.parametrize("picker_failure", ["none", "raise"])
def test_recovery_escalation_picker_failure_uses_verified_non_fast_fallback(
    db,
    picker_failure,
):
    executor = AgentExecutor(db)
    executor._staged_response_mode = "on"
    executor._staged_answer_task_tier = "balanced"
    executor._staged_answer_model_selected = False
    executor._request_model_id = "qwen3.6-flash"
    decision = _evaluate(
        message="昨晚睡得怎样，今天是否适合锻炼？",
        result='{"status":"no_data"}',
        snapshot={"metrics": {}, "data_quality_issues": []},
    )

    picker = (
        patch(
            "app.services.llm.task_routing.pick_model_id_by_tier",
            side_effect=RuntimeError("registry route unavailable"),
        )
        if picker_failure == "raise"
        else patch(
            "app.services.llm.task_routing.pick_model_id_by_tier",
            return_value=None,
        )
    )
    with picker, patch(
        "app.services.llm.model_registry.list_models",
        return_value=[
            SimpleNamespace(id="qwen3.7-plus", speed_tier="balanced"),
            SimpleNamespace(id="qwen3.6-flash", speed_tier="fast"),
        ],
    ):
        executor._activate_recovery_data_guard(decision)

    assert executor._request_model_id == "qwen3.7-plus"
    assert executor._staged_answer_task_tier == "high_stakes"
    assert "staged_answer_recovery_data_degraded_quality_fallback" in (
        executor._model_fallback_reasons
    )


@pytest.mark.parametrize("registry_result", ["raise", "fast_only"])
def test_recovery_escalation_never_keeps_fast_when_quality_registry_unavailable(
    db,
    registry_result,
):
    executor = AgentExecutor(db)
    executor._staged_response_mode = "on"
    executor._staged_answer_task_tier = "balanced"
    executor._request_model_id = "qwen3.6-flash"
    decision = _evaluate(
        message="昨晚没睡好，今天还能健身吗？",
        result="可穿戴数据请求超时",
        snapshot=_healthy_snapshot(),
    )

    registry = (
        patch(
            "app.services.llm.model_registry.list_models",
            side_effect=RuntimeError("registry unavailable"),
        )
        if registry_result == "raise"
        else patch(
            "app.services.llm.model_registry.list_models",
            return_value=[SimpleNamespace(id="qwen3.6-flash", speed_tier="fast")],
        )
    )
    with patch(
        "app.services.llm.task_routing.pick_model_id_by_tier",
        return_value=None,
    ), registry:
        executor._activate_recovery_data_guard(decision)

    assert executor._request_model_id == "qwen3.7-max"
    assert executor._request_model_id != "qwen3.6-flash"
    assert executor._staged_answer_task_tier == "high_stakes"
    assert "staged_answer_recovery_data_degraded_quality_fallback" in (
        executor._model_fallback_reasons
    )


def test_recovery_quality_provider_failure_never_falls_back_to_fast_user_model(db):
    executor = AgentExecutor(db)
    executor._staged_response_mode = "on"
    executor._staged_answer_task_tier = "balanced"
    executor._request_model_id = "qwen3.6-flash"
    executor._current_user_id = 1
    decision = _evaluate(
        message="昨晚没睡好，今天还能健身吗？",
        result="可穿戴数据请求超时",
        snapshot=_healthy_snapshot(),
    )

    with patch(
        "app.services.llm.task_routing.pick_model_id_by_tier",
        return_value=None,
    ), patch(
        "app.services.llm.model_registry.list_models",
        side_effect=RuntimeError("registry unavailable"),
    ):
        executor._activate_recovery_data_guard(decision)

    with patch(
        "app.services.llm.factory.create_provider_for_model_id",
        side_effect=RuntimeError("hard fallback provider unavailable"),
    ), patch(
        "app.services.llm.factory.create_provider_for_user",
    ) as user_provider:
        with pytest.raises(RuntimeError, match="recovery quality provider unavailable"):
            executor._resolve_chat_provider([])

    user_provider.assert_not_called()


@pytest.mark.asyncio
async def test_recovery_quality_guard_rejects_fast_direct_nonstream_model(
    db,
    monkeypatch,
):
    executor = AgentExecutor(db)
    executor._recovery_data_guard_requires_non_fast_model = True
    monkeypatch.setattr(ae.settings, "agent_base_url", "https://agent.invalid")
    monkeypatch.setattr(ae.settings, "agent_api_key", "test-key")
    monkeypatch.setattr(ae.settings, "agent_model", "qwen3.6-flash")
    direct = AsyncMock()

    with patch.object(executor, "_call_llm_direct", direct):
        with pytest.raises(RuntimeError, match="recovery quality provider unavailable"):
            await executor._call_llm([], [])

    direct.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_quality_guard_rejects_fast_direct_stream_model(
    db,
    monkeypatch,
):
    executor = AgentExecutor(db)
    executor._recovery_data_guard_requires_non_fast_model = True
    monkeypatch.setattr(ae.settings, "agent_base_url", "https://agent.invalid")
    monkeypatch.setattr(ae.settings, "agent_api_key", "test-key")
    monkeypatch.setattr(ae.settings, "agent_model", "qwen3.6-flash")
    direct = AsyncMock()

    with patch.object(executor, "_call_llm_direct", direct):
        with pytest.raises(RuntimeError, match="recovery quality provider unavailable"):
            async for _event in executor._call_llm_stream([], []):
                pass

    direct.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_quality_fallback_helper_rejects_fast_provider(db):
    executor = AgentExecutor(db)
    executor._recovery_data_guard_requires_non_fast_model = True
    executor._request_model_id = "qwen3.7-max"
    fast_provider = SimpleNamespace(
        model="qwen3.6-flash",
        chat=AsyncMock(return_value={"content": "可以高强度训练"}),
    )

    with patch(
        "app.services.llm.task_routing.pick_model_id_by_tier",
        return_value="qwen3.7-max",
    ), patch(
        "app.services.llm.factory.create_provider_for_model_id",
        return_value=fast_provider,
    ):
        with pytest.raises(RuntimeError, match="recovery quality provider unavailable"):
            await executor._call_llm_fallback_provider([])

    fast_provider.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_data_insufficiency_does_not_accept_fast_fallback_text(db):
    executor = AgentExecutor(db)
    executor._recovery_data_guard_requires_non_fast_model = True
    executor._request_model_id = "qwen3.7-max"
    fast_provider = SimpleNamespace(
        model="qwen3.6-flash",
        chat=AsyncMock(return_value={"content": "可以高强度训练"}),
    )

    with patch(
        "app.services.llm.task_routing.pick_model_id_by_tier",
        return_value="qwen3.7-max",
    ), patch(
        "app.services.llm.factory.create_provider_for_model_id",
        return_value=fast_provider,
    ):
        recovered = await executor._recover_data_insufficiency(
            [{"role": "user", "content": "昨晚没睡好，今天还能健身吗？"}]
        )

    assert recovered == ""
    fast_provider.chat.assert_not_awaited()


def test_recovery_evaluator_exception_fails_closed(db):
    executor = AgentExecutor(db)
    evaluator = getattr(executor, "_evaluate_recovery_data_guard_safely", None)
    assert evaluator is not None, "runtime guard wrapper is not implemented"

    with patch(
        "app.services.agent_executor._evaluate_recovery_data_guard",
        side_effect=RuntimeError("unexpected shape"),
    ):
        decision = evaluator(
            "昨晚睡得怎样，今天是否适合锻炼？",
            tool_name="health_query",
            args={"dimension": "sleep", "days": 2},
            result='{"status":"success"}',
        )

    assert decision.status == "degraded"
    assert decision.reason_codes == ("guard_unavailable",)


@pytest.mark.asyncio
async def test_recovery_tool_result_escalates_before_synthesis_and_exposes_safe_meta(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr("app.services.agent_executor.settings.staged_response_mode", "on")
    monkeypatch.setattr(
        "app.services.llm.task_routing.classify_answer_task_tier",
        lambda *_a, **_k: "balanced",
    )
    monkeypatch.setattr(
        "app.services.llm.task_routing.pick_model_id_by_tier",
        lambda tier, **_k: (
            "qwen3.7-max" if tier == "high_stakes" else "qwen3.7-plus"
        ),
    )
    monkeypatch.setattr(
        "app.services.agent_executor.get_health_tools",
        lambda subset=None: [{
            "type": "function",
            "function": {
                "name": "health_query",
                "description": "x",
                "parameters": {"type": "object", "properties": {}},
            },
        }],
    )
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")
    monkeypatch.setattr(
        "app.services.agent_executor.is_data_insufficiency_response",
        lambda _text: False,
    )
    monkeypatch.setattr(
        "app.services.wearable_router.build_snapshot",
        lambda *_a, **_k: {"metrics": {}, "data_quality_issues": []},
    )

    synthesis_messages = []
    rounds = 0

    async def fake_stream(messages, round_tools):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            yield {
                "type": "tool_calls",
                "tool_calls": [{
                    "id": "recovery-read",
                    "function": {
                        "name": "health_query",
                        "arguments": '{"dimension":"sleep","days":2}',
                    },
                }],
            }
            yield {"type": "finish", "finish_reason": "tool_calls"}
            return
        synthesis_messages.extend(messages)
        yield {"type": "content", "text": "数据不足，今天只做轻松步行。"}
        yield {"type": "finish", "finish_reason": "stop"}

    async def fake_execute_tool(name, args, token):
        return '{"status":"no_data","message":"没有足够的睡眠数据"}'

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="昨晚睡得怎样，今天是否适合锻炼？",
            user_auth_token="test-token",
            client_turn_id="recovery-data-guard-integration",
        )
    ]

    tool_prompt = "\n".join(
        str(item.get("content") or "")
        for item in synthesis_messages
        if item.get("role") == "tool"
    )
    done = next(event for event in events if event.get("event") == "done")
    assert "不得建议高强度" in tool_prompt
    assert executor._request_model_id == "qwen3.7-max"
    assert done["data"]["answer_task_tier"] == "high_stakes"
    assert done["data"]["recovery_data_guard"] == {
        "status": "degraded",
        "reason_codes": ["missing_core_signal", "read_failed"],
        "model_escalated": True,
    }
