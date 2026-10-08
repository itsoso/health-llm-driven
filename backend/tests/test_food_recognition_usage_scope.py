"""Food helper attribution must not escape into the enclosing agent request."""
import asyncio
import json

import pytest

from app.services.ai.food_recognition import FoodRecognitionService
from app.services import ai_consent
from app.services.llm import usage_tracker as usage


_FOOD_RESPONSE = json.dumps({"foods": [{
    "name": "苹果", "quantity": "1个", "calories": 80,
    "protein": 0.5, "carbs": 20, "fat": 0.3,
}]})


@pytest.fixture
def request_context():
    capture = []
    bindings = (
        (usage._caller_ctx, "agent_executor"),
        (usage._user_id_ctx, 321),
        (usage._user_is_admin_ctx, False),
        (usage._run_id_ctx, "synthetic-run"),
        (usage._usage_capture_ctx, capture),
        (ai_consent._user_ctx, 321),
    )
    tokens = [(var, var.set(value)) for var, value in bindings]
    try:
        yield capture
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def _assert_request_context(capture):
    assert usage.get_caller_user_id() == 321
    assert usage._user_is_admin_ctx.get() is False
    assert usage._run_id_ctx.get() == "synthetic-run"
    assert usage._usage_capture_ctx.get() is capture
    assert ai_consent._user_ctx.get() == 321


@pytest.mark.parametrize("method,caller", [
    ("recognize_food_from_base64", "food_recognition.from_base64"),
    ("recognize_food_from_url", "food_recognition.from_url"),
])
@pytest.mark.parametrize("outcome", ["success", "empty", "error", "cancel"])
def test_food_call_restores_enclosing_attribution(request_context, method, caller, outcome):
    class Provider:
        async def chat_with_vision(self, **kwargs):
            assert usage._caller_ctx.get() == caller
            _assert_request_context(request_context)
            usage._capture_usage_entry({"caller": usage._caller_ctx.get()})
            if outcome == "error":
                raise RuntimeError("synthetic failure")
            if outcome == "cancel":
                raise asyncio.CancelledError()
            return "" if outcome == "empty" else _FOOD_RESPONSE

    async def scenario():
        service = FoodRecognitionService()
        service._provider = Provider()
        if outcome == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await getattr(service, method)("synthetic-input")
        else:
            result = await getattr(service, method)("synthetic-input")
            if outcome in {"error", "empty"}:
                assert result["success"] is False
            else:
                assert result["success"] is True
        assert usage._caller_ctx.get() == "agent_executor"
        _assert_request_context(request_context)

    asyncio.run(scenario())
    assert request_context == [{"caller": caller}]


def test_caller_scope_restores_nested_and_exception_context(request_context):
    with usage.caller_scope("outer"):
        with pytest.raises(ValueError, match="synthetic"):
            with usage.caller_scope("inner"):
                assert usage._caller_ctx.get() == "inner"
                _assert_request_context(request_context)
                raise ValueError("synthetic")
        assert usage._caller_ctx.get() == "outer"
    assert usage._caller_ctx.get() == "agent_executor"
    _assert_request_context(request_context)


def test_overlapping_food_calls_keep_separate_callers(request_context):
    async def scenario():
        both_entered = asyncio.Event()
        callers = []

        class Provider:
            async def chat_with_vision(self, **kwargs):
                expected = usage._caller_ctx.get()
                callers.append(expected)
                if len(callers) == 2:
                    both_entered.set()
                await asyncio.wait_for(both_entered.wait(), timeout=1)
                assert usage._caller_ctx.get() == expected
                _assert_request_context(request_context)
                return _FOOD_RESPONSE

        service = FoodRecognitionService()
        service._provider = Provider()

        async def call(method):
            result = await getattr(service, method)("synthetic-input")
            assert result["success"] is True
            assert usage._caller_ctx.get() == "agent_executor"

        await asyncio.gather(call("recognize_food_from_base64"), call("recognize_food_from_url"))
        assert set(callers) == {"food_recognition.from_base64", "food_recognition.from_url"}
        assert usage._caller_ctx.get() == "agent_executor"

    asyncio.run(scenario())


@pytest.mark.parametrize("inside_event_loop", [False, True])
def test_text_estimate_preserves_request_context_across_sync_bridge(request_context, inside_event_loop):
    observed = []

    class Provider:
        async def chat(self, **kwargs):
            observed.append(usage._caller_ctx.get())
            _assert_request_context(request_context)
            usage._capture_usage_entry({"caller": usage._caller_ctx.get()})
            return json.dumps({"foods": []})

    service = FoodRecognitionService()
    service._provider = Provider()

    def call():
        result = service.estimate_nutrition_from_text("synthetic-food")
        assert result["success"] is True
        assert usage._caller_ctx.get() == "agent_executor"
        _assert_request_context(request_context)

    async def scenario():
        call()

    if inside_event_loop:
        asyncio.run(scenario())
    else:
        call()
    assert observed == ["food_recognition.estimate_nutrition"]
    assert request_context == [{"caller": "food_recognition.estimate_nutrition"}]
