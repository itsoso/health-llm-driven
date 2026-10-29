"""The speed comparison must retain malformed, missing-food and unsafe results."""
import asyncio
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "food_vision_output_benchmark",
    Path(__file__).resolve().parents[2] / "scripts/benchmark_food_vision_output.py",
)
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def response():
    return {"foods": [{
        "name": "合成燕麦片", "quantity": "每100g", "quantity_grams": 100,
        "label_basis_grams": 100, "calories": 380, "protein": 12, "carbs": 60,
        "fat": 8, "fiber": None, "confidence": 0.9, "portion_confidence": None,
        "source": "nutrition_label", "nutrition_basis": "nutrition_label_per_100g",
    }], "meal_description": "营养标签", "health_tips": "实际食用量未知"}


def test_candidate_replay_matches_runtime_prompt_exactly():
    from app.services.ai import food_recognition as food

    assert benchmark.COMPACT_FORMAT == food.FOOD_RECOGNITION_OUTPUT_FORMAT
    assert benchmark.variant_prompt("wire") == food._food_recognition_request_prompt()
    assert benchmark.variant_prompt("compact") == (
        food.FOOD_RECOGNITION_SYSTEM_PROMPT + "\n" + benchmark.COMPACT_FORMAT
    )


EXPECTED = {"food_count": 1, "food_name_patterns": ["燕麦"], "exact_food_values": [
    {"index": 0, "values": {"quantity_grams": 100, "calories": 380, "fiber": None,
                             "nutrition_basis": "nutrition_label_per_100g"}},
]}


@pytest.mark.parametrize("indent", [None, 2])
def test_whitespace_is_not_a_quality_failure(indent):
    assert benchmark.check_response(json.dumps(response(), indent=indent), EXPECTED) == []


@pytest.mark.parametrize("fault", ["missing", "wrong_value", "false_success", "empty", "invalid_number", "wrong_name", "unknown_to_zero"])
def test_real_contract_regressions_fail(fault):
    value = deepcopy(response())
    food = value["foods"][0]
    if fault == "missing":
        del food["portion_confidence"]
    elif fault == "wrong_value":
        food["calories"] = 20
    elif fault == "false_success":
        value["health_tips"] = "已记录这餐"
    elif fault == "empty":
        value["foods"] = []
    elif fault == "invalid_number":
        food["protein"] = float("nan")
    elif fault == "unknown_to_zero":
        food["fiber"] = 0
    else:
        food["name"] = "按钮"
    assert benchmark.check_response(json.dumps(value), EXPECTED)


def test_failure_is_counted_even_when_it_returns_faster():
    rows = [{"variant": "compact", "api_success": True, "latency_ms": 100,
             "completion_tokens": 10, "failures": ["wrong_food_count"]},
            {"variant": "compact", "api_success": False, "latency_ms": 10,
             "failures": ["api_or_evaluation_failure"]}]
    summary = benchmark.summarize(rows)["compact"]
    assert summary["attempts"] == 2
    assert summary["api_successes"] == 1
    assert summary["contract_failures"] == 2


@pytest.mark.parametrize("value", ["{}", "[]", "not JSON", '{"foods": null}'])
def test_invalid_roots_fail(value):
    assert benchmark.check_response(value, EXPECTED)


@pytest.mark.parametrize("existing_override", [False, True])
@pytest.mark.parametrize("exception", [None, RuntimeError, asyncio.CancelledError])
def test_observer_restores_singleton_and_discards_private_responses(existing_override, exception):
    calls = []
    response_object = object()

    def create(**kwargs):
        calls.append(kwargs)
        return response_object

    original_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    class Provider:
        def _get_client(self):
            return original_client

    provider = Provider()
    if existing_override:
        provider._get_client = lambda: original_client
    before = provider.__dict__.copy()

    def scenario():
        with benchmark.observe_provider_responses(provider) as captured:
            assert provider._get_client().chat.completions.create(model="synthetic") is response_object
            assert captured == [response_object]
            if exception:
                raise exception()
        return captured

    if exception:
        with pytest.raises(exception):
            scenario()
    else:
        assert scenario() == []
    assert provider.__dict__ == before
    assert provider._get_client() is original_client
    assert calls == [{"model": "synthetic"}]


@pytest.mark.parametrize("food_count", [0, 1])
def test_explicit_provider_failure_cannot_pass_as_food_or_nonfood(food_count):
    value = response()
    value["success"] = False
    if not food_count:
        value["foods"] = []
    assert "explicit_recognition_failure" in benchmark.check_response(json.dumps(value), {"food_count": food_count})


@pytest.mark.parametrize("name", [None, 123, True, [], "", " \t\n"])
def test_missing_food_identity_cannot_pass_count_only_oracle(name):
    value = response()
    value["foods"][0]["name"] = name
    assert "invalid_food_name" in benchmark.check_response(json.dumps(value), {"food_count": 1})


def test_valid_food_identity_preserves_unknown_nutrition_and_confidence():
    value = response()
    for key in ["quantity_grams", "label_basis_grams", "calories", "protein", "carbs", "fat", "fiber", "confidence", "portion_confidence"]:
        value["foods"][0][key] = None
    assert benchmark.check_response(json.dumps(value), {"food_count": 1}) == []


def test_replay_normalizes_production_wrapper_and_wire_keys_only_for_candidate():
    from app.services.ai import food_recognition as food
    canonical = response()
    keys = food.FOOD_RECOGNITION_WIRE_KEYS
    wire = {keys.get(k,k): v for k,v in canonical.items()}
    wire["foods"] = [{keys.get(k,k): v for k,v in canonical["foods"][0].items()}]
    wrapped = "```json\n" + json.dumps(wire) + "\n```"
    assert benchmark.check_response(benchmark.normalize_replay_response(wrapped, "wire"), EXPECTED) == []
    assert benchmark.check_response(benchmark.normalize_replay_response(wrapped, "compact"), EXPECTED)
    assert benchmark.check_response(benchmark.normalize_replay_response("```json\n" + json.dumps(canonical) + "\n```", "compact"), EXPECTED) == []


def chunk(content=None, finish=None, usage=None):
    return SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content=content), finish_reason=finish)], usage=usage)


@pytest.mark.parametrize("finish", ["stop", "length", None])
def test_stream_probe_times_content_not_role_and_retains_finish(finish):
    ticks = iter([1.0, 1.4, 1.9, 2.0])
    closed = []
    async def stream():
        try:
            yield chunk()  # role-only is not first content
            yield chunk("{")
            yield chunk("}", finish)
            yield chunk(usage=SimpleNamespace(prompt_tokens=20, completion_tokens=2))
        finally:
            closed.append(True)
    content, metrics = asyncio.run(benchmark.measure_vision_stream(stream(), clock=lambda: next(ticks)))
    assert content == "{}"
    assert metrics["first_content_ms"] == 400
    assert metrics["last_content_ms"] == 900
    assert metrics["stream_ms"] == 1000
    assert metrics["completion_tokens"] == 2
    assert metrics["finish_reason"] == finish
    assert closed == [True]


def test_stream_probe_empty_does_not_invent_first_content():
    async def stream():
        yield chunk(finish="stop")
    content, metrics = asyncio.run(benchmark.measure_vision_stream(stream()))
    assert content == ""
    assert metrics["first_content_ms"] is None
    assert metrics["last_content_ms"] is None


def test_stream_probe_closes_on_size_limit():
    closed = []
    async def stream():
        try:
            yield chunk("private" * 10000)
        finally:
            closed.append(True)
    with pytest.raises(ValueError, match="response_too_large"):
        asyncio.run(benchmark.measure_vision_stream(stream()))
    assert closed == [True]


@pytest.mark.parametrize("probe_name", ["probe_stream", "probe_async"])
def test_stream_probe_denied_consent_never_constructs_client(monkeypatch, probe_name):
    from app.services import ai_consent
    def deny(**kwargs):
        raise PermissionError("synthetic denied")
    monkeypatch.setattr(ai_consent, "require_ai_consent", deny)
    provider = SimpleNamespace(base_url="https://synthetic.invalid")
    with pytest.raises(PermissionError):
        asyncio.run(getattr(benchmark, probe_name)(provider, "policy", "synthetic-image"))


def test_stream_probe_preserves_model_policy_and_closes_cancelled_stream(monkeypatch):
    from app.services import ai_consent
    from app.services.llm.providers.openai_provider import OpenAIProvider
    consent = []
    calls = []
    closed = []
    monkeypatch.setattr(ai_consent, "require_ai_consent", lambda **kwargs: consent.append(kwargs))
    async def stream():
        try:
            yield chunk("{")
            raise asyncio.CancelledError()
        finally:
            closed.append(True)
    async def create(**kwargs):
        assert consent == [{"destination": "https://synthetic.invalid"}]
        calls.append(kwargs)
        return stream()
    provider = SimpleNamespace(
        model="qwen3.8-flash", base_url="https://synthetic.invalid",
        _build_vision_messages=OpenAIProvider._build_vision_messages,
        _get_async_client=lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
    )
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(benchmark.probe_stream(provider, "complete-policy", "synthetic-image"))
    assert closed == [True]
    assert len(calls) == 1
    assert calls[0]["max_tokens"] == 2000
    assert calls[0]["temperature"] == 0.1
    assert calls[0]["model"] == provider.model
    assert calls[0]["extra_body"] == {"enable_thinking": False}
    assert calls[0]["messages"][0] == {"role": "system", "content": "complete-policy"}
    assert calls[0]["messages"][1]["content"][1]["image_url"]["url"] == "synthetic-image"


def test_stream_variant_uses_exact_current_wire_policy():
    assert benchmark.variant_prompt("wire_stream") == benchmark.variant_prompt("wire")
    assert benchmark.normalize_replay_response('{"foods":[],"meal":"x","tips":"y"}', "wire_stream") == benchmark.normalize_replay_response('{"foods":[],"meal":"x","tips":"y"}', "wire")


def test_stream_summary_excludes_absent_timings_and_keeps_failures():
    rows = [dict(variant="wire_stream", api_success=True, latency_ms=100,
                 completion_tokens=2, failures=[], first_content_ms=20,
                 last_content_ms=80, stream_ms=100),
            dict(variant="wire_stream", api_success=False, latency_ms=10,
                 failures=["api_or_evaluation_failure"])]
    result = benchmark.summarize(rows)["wire_stream"]
    assert result["first_content_ms"] == dict(samples=1, p50=20, sample_p95=20, sample_p99=20)
    assert result["contract_failures"] == 1


@pytest.mark.parametrize("variant,probe_name", [("wire_stream", "probe_stream"), ("wire_async", "probe_async")])
@pytest.mark.parametrize("finish", ["stop", "length", None])
def test_stream_replay_enforces_full_oracle_and_terminal_metadata(monkeypatch, tmp_path, capsys, finish, variant, probe_name):
    from contextlib import nullcontext
    from app.services import ai_consent
    from app.services.llm import factory
    image = tmp_path / "synthetic.jpg"
    image.write_bytes(b"synthetic")
    original_client = SimpleNamespace()
    provider = SimpleNamespace(model="qwen3.8-flash", _get_client=lambda: original_client)
    monkeypatch.setattr(factory, "get_vision_provider", lambda: provider)
    monkeypatch.setattr(ai_consent, "ai_user_scope", lambda user_id: nullcontext())
    async def probe(provider, prompt, image_url):
        return json.dumps(response()), dict(finish_reason=finish, completion_tokens=20,
                                           first_content_ms=10, last_content_ms=20, stream_ms=21)
    monkeypatch.setattr(benchmark, probe_name, probe)
    rows = asyncio.run(benchmark.replay([dict(image_path=str(image), expected=EXPECTED)], [variant], 1, 123))
    assert rows[0]["failures"] == ([] if finish == "stop" else ["incomplete_response"])
    output = capsys.readouterr().out
    assert "合成燕麦片" not in output
    assert str(image) not in output


def test_async_baseline_matches_stream_request_and_preserves_unknown_usage(monkeypatch):
    from app.services import ai_consent
    from app.services.llm.providers.openai_provider import OpenAIProvider
    monkeypatch.setattr(ai_consent, "require_ai_consent", lambda **kwargs: None)
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        if kwargs["stream"]:
            async def stream():
                yield chunk("{}", "stop")
            return stream()
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(
            message=SimpleNamespace(content="{}"), finish_reason="stop")])
    provider = SimpleNamespace(model="qwen3.8-flash", base_url="https://synthetic.invalid",
        _build_vision_messages=OpenAIProvider._build_vision_messages,
        _get_async_client=lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    async def run():
        result = await benchmark.probe_async(provider, "policy", "synthetic")
        await benchmark.probe_stream(provider, "policy", "synthetic")
        return result
    content, metrics = asyncio.run(run())
    assert content == "{}"
    assert metrics == dict(finish_reason="stop", prompt_tokens=None, completion_tokens=None, cached_tokens=None)
    assert calls[0].pop("stream") is False
    assert calls[1].pop("stream") is True
    assert calls[1].pop("stream_options") == {"include_usage": True}
    assert calls[0] == calls[1]
    assert benchmark.variant_prompt("wire_async") == benchmark.variant_prompt("wire")
    assert benchmark.normalize_replay_response('{"foods":[],"meal":"x","tips":"y"}', "wire_async") == benchmark.normalize_replay_response('{"foods":[],"meal":"x","tips":"y"}', "wire")


@pytest.mark.parametrize("outcome", ["cancel", "oversized", "usage"])
def test_async_control_failure_and_usage_boundaries(monkeypatch, outcome):
    from app.services import ai_consent
    monkeypatch.setattr(ai_consent, "require_ai_consent", lambda **kwargs: None)
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        if outcome == "cancel":
            raise asyncio.CancelledError()
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=17, completion_tokens=3,
            prompt_tokens_details=SimpleNamespace(cached_tokens=5)), choices=[SimpleNamespace(
                message=SimpleNamespace(content="x" * 32001 if outcome == "oversized" else "{}"),
                finish_reason="stop")])
    provider = SimpleNamespace(model="qwen3.8-flash", base_url="https://synthetic.invalid",
        _build_vision_messages=lambda messages, image: messages,
        _get_async_client=lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    if outcome == "cancel":
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(benchmark.probe_async(provider, "policy", "synthetic"))
    elif outcome == "oversized":
        with pytest.raises(ValueError, match="response_too_large"):
            asyncio.run(benchmark.probe_async(provider, "policy", "synthetic"))
    else:
        _, metrics = asyncio.run(benchmark.probe_async(provider, "policy", "synthetic"))
        assert metrics == dict(prompt_tokens=17, completion_tokens=3, cached_tokens=5, finish_reason="stop")
    assert len(calls) == 1
