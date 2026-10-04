"""The full-task harness must bound egress and keep failures visible."""
import asyncio
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from eval.full_task_prompt_benchmark import (
    BenchmarkStopped, CallBudget, MeasuredProvider, Scenario,
    run_sample, seed_synthetic_records,
)


class Scripted:
    provider_name = "synthetic"
    model = "synthetic"

    async def chat_stream(self, **kwargs):
        yield {"type": "content", "text": "合成回答"}
        yield {"type": "finish", "finish_reason": "stop"}


@pytest.mark.asyncio
async def test_call_cap_is_checked_before_provider_creation():
    created, rows = [], []
    def factory():
        created.append(True)
        return Scripted()
    provider = MeasuredProvider(factory, "synthetic", CallBudget(1), rows, live=False)
    _ = [event async for event in provider.chat_stream(messages=[], max_tokens=9999)]
    with pytest.raises(BenchmarkStopped, match="call_budget"):
        _ = [event async for event in provider.chat_stream(messages=[])]
    assert len(created) == len(rows) == 1
    assert rows[0]["token_source"] == "synthetic"
    assert rows[0]["input_tokens"] is None


@pytest.mark.asyncio
async def test_payload_and_output_bounds_do_not_mutate_original_arguments():
    captured, rows = [], []
    class Provider(Scripted):
        async def chat_stream(self, **kwargs):
            captured.append(kwargs)
            async for event in super().chat_stream(**kwargs):
                yield event
    provider = MeasuredProvider(Provider, "synthetic", CallBudget(2), rows, live=False)
    kwargs = {"messages": [{"role": "user", "content": "合成输入"}], "max_tokens": 8000}
    before = deepcopy(kwargs)
    _ = [event async for event in provider.chat_stream(**kwargs)]
    assert kwargs == before
    assert captured[0]["max_tokens"] == 1200
    assert captured[0]["stream_options"] == {"include_usage": True}
    wire = json.dumps(captured[0], ensure_ascii=False, sort_keys=True, default=str).encode()
    assert rows[0]["payload_sha256"] == hashlib.sha256(wire).hexdigest()
    assert rows[0]["input_bytes"] == len(wire)
    with pytest.raises(BenchmarkStopped, match="input_budget"):
        _ = [event async for event in provider.chat_stream(messages=[{"content": "X" * 300000}])]
    assert len(captured) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["provider_failure", "missing_finish", "length"])
async def test_provider_failure_never_becomes_a_successful_or_retried_sample(kind):
    rows = []
    class Broken(Scripted):
        async def chat_stream(self, **kwargs):
            if kind == "provider_failure":
                raise RuntimeError("do not persist raw exception payload")
            yield {"type": "content", "text": "incomplete"}
            if kind == "length":
                yield {"type": "finish", "finish_reason": "length"}
    provider = MeasuredProvider(Broken, "synthetic", CallBudget(2), rows, live=False)
    with pytest.raises(BenchmarkStopped):
        _ = [event async for event in provider.chat_stream(messages=[])]
    assert len(rows) == 1 and rows[0]["error_type"]
    assert rows[0]["wall_seconds"] >= 0
    assert "do not persist" not in str(rows)


@pytest.mark.asyncio
async def test_cancel_closes_provider_and_retains_call_failure():
    rows, closed = [], []
    class Cancelled(Scripted):
        async def chat_stream(self, **kwargs):
            try:
                yield {"type": "content", "text": "partial"}
                raise asyncio.CancelledError()
            finally:
                closed.append(True)
    provider = MeasuredProvider(Cancelled, "synthetic", CallBudget(2), rows, live=False)
    with pytest.raises(asyncio.CancelledError):
        _ = [event async for event in provider.chat_stream(messages=[])]
    assert closed == [True]
    assert rows[0]["error_type"] == "CancelledError"


@pytest.mark.asyncio
async def test_live_missing_api_usage_is_a_failure():
    rows = []
    provider = MeasuredProvider(Scripted, "synthetic", CallBudget(2), rows, live=True)
    with pytest.raises(BenchmarkStopped, match="api_usage"):
        _ = [event async for event in provider.chat_stream(messages=[])]
    assert rows[0]["token_source"] == "unknown"


@pytest.mark.asyncio
async def test_usage_is_collected_after_finish_before_releasing_finish_to_consumer():
    from app.services.llm.usage_tracker import _capture_usage_entry
    rows = []
    class UsageFixture(Scripted):
        async def chat_stream(self, **kwargs):
            async for event in super().chat_stream(**kwargs):
                yield event
            # Unit fixture only: represents the usage wrapper's finally block.
            _capture_usage_entry({"token_source": "api", "prompt_tokens": 123, "completion_tokens": 7,
                                  "cached_tokens": None, "model": "unit-fixture", "success": True})
    provider = MeasuredProvider(UsageFixture, "unit-fixture", CallBudget(1), rows, live=True)
    events = [event async for event in provider.chat_stream(messages=[])]
    assert events[-1]["finish_reason"] == "stop"
    assert rows[0]["input_tokens"] == 123 and rows[0]["output_tokens"] == 7
    assert rows[0]["cached_tokens"] == [None]
    assert rows[0]["actual_models"] == ["unit-fixture"]


@pytest.mark.asyncio
async def test_per_task_limit_cannot_borrow_from_larger_batch_budget():
    rows = []
    provider = MeasuredProvider(Scripted, "synthetic", CallBudget(12), rows, live=False)
    for _ in range(3):
        _ = [event async for event in provider.chat_stream(messages=[])]
    with pytest.raises(BenchmarkStopped, match="sample_call_budget"):
        _ = [event async for event in provider.chat_stream(messages=[])]
    assert len(rows) == 3 and provider.budget.used == 3


@pytest.mark.parametrize("url,env", [("sqlite:////tmp/not-an-eval.db", "test"),
                                     ("postgresql://localhost/not-an-eval", "test"),
                                     ("sqlite:///:memory:", "production")])
def test_non_ephemeral_database_is_rejected_without_connecting(monkeypatch, url, env):
    from sqlalchemy.engine import make_url
    from app.config import settings
    from eval.full_task_prompt_benchmark import require_ephemeral
    monkeypatch.setattr(settings, "app_env", env)
    db = SimpleNamespace(get_bind=lambda: SimpleNamespace(url=make_url(url)))
    with pytest.raises(RuntimeError, match="test_in_memory"):
        require_ephemeral(db)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["available", "empty", "read_failure"])
async def test_full_pi_task_preserves_read_contract_and_persistence(db, auth_user_and_headers, monkeypatch, state):
    from app.config import settings
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr("app.utils.redis_cache.get_redis_client", lambda: None)
    user, _ = auth_user_and_headers
    scenario = Scenario("synthetic-" + state, 7, state)
    seed_synthetic_records(db, user.id, scenario)
    rows = []
    for variant in ("baseline", "p1", "p2", "combined"):
        row = await run_sample(db, user.id, scenario, variant, "qwen3.8-max", CallBudget(12), live=False)
        assert row["status"] == "passed_contracts", row
        assert row["quality"]["semantic_review"] == "required"
        assert row["quality"]["stream_matches_saved"]
        assert row["quality"]["health_rows_unchanged"]
        assert row["agent_kernel"] == "pi"
        assert all(call["token_source"] == "synthetic" for call in row["calls"])
        rows.append(row)
    assert [len(row["calls"]) for row in rows] == [2, 2, 1, 1]
    assert rows[0]["tool_contracts"] == rows[1]["tool_contracts"] == rows[2]["tool_contracts"] == rows[3]["tool_contracts"]


@pytest.mark.asyncio
@pytest.mark.parametrize("allow_knowledge", [False, True])
async def test_analysis_screen_runs_real_empty_kb_without_widening_read_screen(
    db, auth_user_and_headers, monkeypatch, allow_knowledge,
):
    from app.config import settings
    from eval.full_task_prompt_benchmark import ScriptedProvider

    monkeypatch.setattr(settings, "app_env", "test")
    user, _ = auth_user_and_headers
    scenario = Scenario("analysis-empty-kb", 7, "available", allow_knowledge=allow_knowledge)
    seed_synthetic_records(db, user.id, scenario)

    class WithKnowledge(ScriptedProvider):
        async def chat_stream(self, **kwargs):
            async for event in super().chat_stream(**kwargs):
                if event.get("type") == "tool_calls":
                    event["tool_calls"].append({"id": "fixture-knowledge", "type": "function", "function": {
                        "name": "knowledge_search", "arguments": json.dumps({"query": "睡眠和饮食"})}})
                yield event

    row = await run_sample(db, user.id, scenario, "baseline", "qwen3.8-max", CallBudget(3),
                           live=False, provider_factory=lambda: WithKnowledge(scenario))
    if allow_knowledge:
        assert row["status"] == "passed_contracts", row
        assert any(d["action"] == "allow" for d in row["gateway_decisions"])
        assert len(row["knowledge_contracts"]) == 1
        assert row["knowledge_contracts"][0]["honest_empty_kb"]
    else:
        assert row["status"] == "failed"
        assert row["rejected_tools"] == [{"name": "knowledge_search", "reason": "out_of_scope"}]
        assert row["knowledge_contracts"] == []


@pytest.mark.asyncio
async def test_gateway_denial_keeps_narrow_read_scope_diagnostics(db, auth_user_and_headers, monkeypatch):
    from app.config import settings
    from eval.full_task_prompt_benchmark import ScriptedProvider

    monkeypatch.setattr(settings, "app_env", "test")
    user, _ = auth_user_and_headers
    scenario = Scenario("scope-denial", 7, "available")
    seed_synthetic_records(db, user.id, scenario)

    class WrongDimension(ScriptedProvider):
        async def chat_stream(self, **kwargs):
            async for event in super().chat_stream(**kwargs):
                if event.get("type") == "tool_calls":
                    event["tool_calls"][0]["function"]["arguments"] = json.dumps({"queries": [
                        {"dimension": "heart_rate", "days": 7, "extra": "do-not-save-this"}]})
                yield event

    row = await run_sample(db, user.id, scenario, "baseline", "qwen3.8-max", CallBudget(3),
                           live=False, provider_factory=lambda: WrongDimension(scenario))
    assert row["status"] != "passed_contracts"
    denied = [d for d in row["gateway_decisions"] if d["action"] == "block"]
    assert denied and denied[0]["reason"] == "health_query_dimension_conflict"
    assert denied[0]["requested_read_scope"] == [{"dimension": "heart_rate", "days": 7}]
    assert "do-not-save-this" not in str(row["gateway_decisions"])


@pytest.mark.asyncio
async def test_task_cancellation_retains_row_and_restores_routing(db, auth_user_and_headers, monkeypatch):
    from app.config import settings
    from app.services.llm.providers import openai_provider
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "decision_mode", "shadow")
    monkeypatch.setattr(settings, "staged_response_mode", "on")
    monkeypatch.setattr(settings, "llm_auto_recovery_enabled", True)
    class Cancelled(Scripted):
        async def chat_stream(self, **kwargs):
            assert settings.decision_mode == settings.staged_response_mode == "off"
            assert settings.llm_auto_recovery_enabled is False
            assert openai_provider._DEFAULT_MAX_RETRIES == 0
            raise asyncio.CancelledError()
            yield  # async generator
    user, _ = auth_user_and_headers
    scenario = Scenario("cancel", 7, "available")
    seed_synthetic_records(db, user.id, scenario)
    with pytest.raises(asyncio.CancelledError) as caught:
        await run_sample(db, user.id, scenario, "baseline", "qwen3.8-max", CallBudget(3), live=False, provider_factory=Cancelled)
    row = caught.value.benchmark_sample
    assert row["status"] == "cancelled" and len(row["calls"]) == 1
    assert row["calls"][0]["error_type"] == "CancelledError"
    assert row["evaluation_seconds"] >= row["wall_seconds"] >= 0
    assert settings.decision_mode == "shadow" and settings.staged_response_mode == "on"
    assert settings.llm_auto_recovery_enabled is True


def load_cli():
    path = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_prompt_full_task.py"
    spec = importlib.util.spec_from_file_location("full_task_cli_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_baseline_only_plan_does_not_inject_experiments(tmp_path):
    cli = load_cli()
    args = SimpleNamespace(case=["owned_read_7d_available"], model=["qwen3.8-max"], variant=None,
                           repetitions=1, max_api_calls=3, scripted=False, include_live_llm=False,
                           baseline_only=True, output=tmp_path / "plan.json")
    assert await cli.run(args) == 0
    report = json.loads(args.output.read_text())
    assert report["variants"] == ["baseline"] and report["planned_tasks"] == 1
    assert report["status"] == "plan_only" and report["rows"] == []
    assert report["requested_max_output_tokens_per_call"] == 1200
    args.variant = ["combined"]
    with pytest.raises(ValueError, match="conflicts"):
        await cli.run(args)


@pytest.mark.asyncio
async def test_existing_retry_enabled_sdk_client_is_not_reused(db, auth_user_and_headers, monkeypatch):
    from app.config import settings
    from app.services.llm.providers import openai_provider as op
    from eval.full_task_prompt_benchmark import ScriptedProvider
    monkeypatch.setattr(settings, "app_env", "test")
    user, _ = auth_user_and_headers
    scenario = Scenario("client-cache", 7, "available")
    seed_synthetic_records(db, user.id, scenario)
    old_key = op._client_cache_key({"api_key": "unit-test-placeholder"})
    old_client, constructed = object(), []
    monkeypatch.setattr(op, "_ASYNC_CLIENT_CACHE", {old_key: old_client})
    async def unused_send():
        raise AssertionError("unit fixture must never send")
    def sdk_fixture(**kwargs):
        constructed.append(kwargs)
        return SimpleNamespace(_client=SimpleNamespace(event_hooks={}, send=unused_send))
    monkeypatch.setattr("openai.AsyncOpenAI", sdk_fixture)
    def provider_factory():
        raw = op.OpenAIProvider(api_key="unit-test-placeholder")
        assert raw._get_async_client() is not old_client
        assert constructed[-1]["max_retries"] == 0
        return ScriptedProvider(scenario)
    row = await run_sample(db, user.id, scenario, "combined", "qwen3.8-max", CallBudget(3), live=False, provider_factory=provider_factory)
    assert row["status"] == "passed_contracts", row
    assert len(constructed) == 1
    assert op._ASYNC_CLIENT_CACHE[old_key] is old_client
    assert op.OpenAIProvider(api_key="unit-test-placeholder")._client_kwargs() == {"api_key": "unit-test-placeholder"}


@pytest.mark.asyncio
async def test_unexpected_write_proposals_cannot_mutate_health_rows(db, auth_user_and_headers, monkeypatch):
    from app.config import settings
    from eval.full_task_prompt_benchmark import health_digest
    monkeypatch.setattr(settings, "app_env", "test")
    user, _ = auth_user_and_headers
    scenario = Scenario("unexpected-write", 7, "available")
    seed_synthetic_records(db, user.id, scenario)
    before = health_digest(db)
    class WrongTool:
        async def chat_stream(self, **kwargs):
            yield {"type": "tool_calls", "tool_calls": [{"id": "unexpected-write", "type": "function", "function": {
                "name": "health_record", "arguments": json.dumps({"record_type": "diet", "operation": "create",
                "data": {"food_name": "must-not-write", "calories": 999}})}}]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
    row = await run_sample(db, user.id, scenario, "baseline", "qwen3.8-max", CallBudget(3), live=False, provider_factory=WrongTool)
    assert row["status"] in {"failed", "failed_contracts"} and len(row["calls"]) <= 3
    assert before == health_digest(db)
    assert row["tool_contracts"] == []


@pytest.mark.asyncio
async def test_caught_context_database_error_still_fails_sample(db, auth_user_and_headers, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError
    from app.config import settings
    from eval.full_task_prompt_benchmark import ScriptedProvider
    monkeypatch.setattr(settings, "app_env", "test")
    user, _ = auth_user_and_headers
    scenario = Scenario("caught-database-error", 7, "available")
    seed_synthetic_records(db, user.id, scenario)
    class BrokenContext(ScriptedProvider):
        async def chat_stream(self, **kwargs):
            try:
                db.execute(text("SELECT * FROM intentionally_missing_eval_table"))
            except SQLAlchemyError:
                pass  # Simulate an application collector's handled degradation.
            async for event in super().chat_stream(**kwargs):
                yield event
    row = await run_sample(db, user.id, scenario, "combined", "qwen3.8-max", CallBudget(3), live=False,
                           provider_factory=lambda: BrokenContext(scenario))
    assert row["status"] == "failed_contracts" and row["database_errors"] == ["OperationalError"]
    assert row["quality"]["database_context_intact"] is False


@pytest.mark.asyncio
async def test_cli_cancel_saves_partial_sample_before_propagating(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "app_env", "test")
    cli = load_cli()
    async def cancel_sample(*args, **kwargs):
        exc = asyncio.CancelledError()
        exc.benchmark_sample = {"model": "qwen3.8-max", "variant": "baseline", "calls": [], "status": "cancelled", "wall_seconds": None}
        raise exc
    monkeypatch.setattr(cli, "run_sample", cancel_sample)
    args = SimpleNamespace(case=["owned_read_7d_available"], model=["qwen3.8-max"], variant=["p2"],
                           repetitions=1, max_api_calls=6, scripted=True, include_live_llm=False, output=tmp_path / "report.json")
    with pytest.raises(asyncio.CancelledError):
        await cli.run(args)
    report = json.loads(args.output.read_text())
    assert report["status"] == "cancelled" and len(report["rows"]) == 1
    assert report["summary"][0]["failed_tasks"] == 1
    assert report["summary"][0]["wall_seconds_all_tasks"]["p50"] is None
