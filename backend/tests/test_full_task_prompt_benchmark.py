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


def contract_diagnostics(row):
    return json.dumps({key: row.get(key) for key in (
        "case", "variant", "status", "quality", "tool_contracts",
        "database_errors", "database_error_details", "outcome", "agent_kernel",
        "error_type",
    )}, ensure_ascii=False, sort_keys=True)


class Scripted:
    provider_name = "synthetic"
    model = "synthetic"

    async def chat_stream(self, **kwargs):
        yield {"type": "content", "text": "合成回答"}
        yield {"type": "finish", "finish_reason": "stop"}


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [1, 31])
async def test_runtime_variant_keeps_rich_profile_and_actual_model_call_counts(db, auth_user_and_headers, monkeypatch, days):
    from app.config import settings
    from eval.full_task_prompt_benchmark import ScriptedProvider
    monkeypatch.setattr(settings, "app_env", "test")
    user, _ = auth_user_and_headers
    scenario = Scenario("runtime-rich", days, "available", rich_profile=True)
    seed_synthetic_records(db, user.id, scenario)
    inputs, rows = [], []
    class Capture(ScriptedProvider):
        async def chat_stream(self, **kwargs):
            if not kwargs.get("tools"):
                rules = kwargs["messages"][0]["content"]
                assert "不超过200字" in rules
                assert "800字" not in rules and "最多三条下一步" not in rules
                inputs.append(json.loads(kwargs["messages"][1]["content"]))
            async for event in super().chat_stream(**kwargs):
                yield event
    for variant in ("baseline", "runtime_preplan"):
        row = await run_sample(db, user.id, scenario, variant, "qwen3.8-max", CallBudget(3),
                               live=False, provider_factory=lambda: Capture(scenario))
        assert row["status"] == "passed_contracts", contract_diagnostics(row)
        assert row["runtime_preplanned"] == (variant == "runtime_preplan")
        assert row["runtime_model_call_count"] == len(row["calls"])
        rows.append(row)
    assert [len(r["calls"]) for r in rows] == [2, 1]
    assert inputs[0] == inputs[1]
    assert "23:30" in inputs[1]["time_context"]
    assert "时间: 23点 (深夜)" in inputs[1]["profile_context"]["text"]
    profile = inputs[1]["profile_context"]
    assert profile["authority"] == "background_not_current_read_or_new_consent"
    for token in ("花生", "慢性肾病", "合成长期处方"):
        assert token in profile["text"]
    assert rows[0]["answer"] == rows[1]["answer"]


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
async def test_answer_diagnostics_are_bounded_without_changing_stream_or_usage():
    rows = []
    class LongAnswer(Scripted):
        async def chat_stream(self, **kwargs):
            yield {"type": "content", "text": "合成" * 10000}
            yield {"type": "finish", "finish_reason": "stop"}
    provider = MeasuredProvider(LongAnswer, "synthetic", CallBudget(1), rows, live=False)
    events = [event async for event in provider.chat_stream(messages=[])]
    assert events[0]["text"] == "合成" * 10000
    assert rows[0]["answer_text"] == "合成" * 8000
    assert rows[0]["answer_text_truncated"] is True
    assert rows[0]["token_source"] == "synthetic" and rows[0]["input_tokens"] is None


@pytest.mark.asyncio
async def test_blocked_answer_keeps_original_for_synthetic_semantic_review(db, auth_user_and_headers, monkeypatch):
    from app.config import settings
    from eval.full_task_prompt_benchmark import ScriptedProvider

    monkeypatch.setattr(settings, "app_env", "test")
    user, _ = auth_user_and_headers
    scenario = Scenario("blocked-original", 7, "available")
    seed_synthetic_records(db, user.id, scenario)
    unsafe = "你全天营养摄入不足。"
    class UnsafeAnswer(ScriptedProvider):
        async def chat_stream(self, **kwargs):
            if not kwargs.get("tools"):
                yield {"type": "content", "text": unsafe}
                yield {"type": "finish", "finish_reason": "stop"}
            else:
                async for event in super().chat_stream(**kwargs):
                    yield event
    row = await run_sample(db, user.id, scenario, "baseline", "qwen3.8-flash", CallBudget(3),
                           live=False, provider_factory=lambda: UnsafeAnswer(scenario))
    assert row["status"] == "failed_contracts" and row["outcome"] == "blocked"
    assert row["calls"][-1]["answer_text"] == unsafe
    assert row["calls"][-1]["answer_text_truncated"] is False
    assert row["calls"][0]["answer_text"] is None
    assert unsafe not in row["answer"]


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
    for variant in ("baseline", "p1", "p2", "combined", "empty_terminal", "evidence_compact"):
        row = await run_sample(db, user.id, scenario, variant, "qwen3.8-max", CallBudget(12), live=False)
        assert row["status"] == "passed_contracts", contract_diagnostics(row)
        assert row["quality"]["semantic_review"] == "required"
        assert row["quality"]["stream_matches_saved"]
        assert row["quality"]["health_rows_unchanged"]
        assert row["agent_kernel"] == "pi"
        assert all(call["token_source"] == "synthetic" for call in row["calls"])
        rows.append(row)
    assert [len(row["calls"]) for row in rows] == (
        [1, 1, 0, 0, 1, 1] if state == "read_failure" else
        [2, 2, 1, 1, 1, 2] if state == "empty" else [2, 2, 1, 1, 2, 2])
    assert rows[0]["tool_contracts"] == rows[1]["tool_contracts"] == rows[2]["tool_contracts"] == rows[3]["tool_contracts"]


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [7, 31])
async def test_dense_evidence_reaches_provider_losslessly(db, auth_user_and_headers, monkeypatch, days):
    from app.config import settings
    from eval.full_task_prompt_benchmark import ScriptedProvider

    monkeypatch.setattr(settings, "app_env", "test")
    user, _ = auth_user_and_headers
    scenario = Scenario("dense", days, "available", dense_records=True)
    seed_synthetic_records(db, user.id, scenario)
    projections, rows = [], []

    class Capture(ScriptedProvider):
        async def chat_stream(self, **kwargs):
            if not kwargs.get("tools"):
                projections.append(deepcopy(kwargs["messages"]))
            async for event in super().chat_stream(**kwargs):
                yield event

    for variant in ("baseline", "evidence_compact"):
        row = await run_sample(db, user.id, scenario, variant, "qwen3.8-max", CallBudget(3),
                               live=False, provider_factory=lambda: Capture(scenario))
        assert row["status"] == "passed_contracts", contract_diagnostics(row)
        rows.append(row)
    assert rows[0]["answer"] == rows[1]["answer"]
    assert rows[0]["tool_contracts"] == rows[1]["tool_contracts"]
    baseline, compact = [json.loads(messages[1]["content"]) for messages in projections]
    assert "unknown_fields_ref" in json.dumps(compact)
    assert len(json.dumps(projections[1])) < len(json.dumps(projections[0]))
    for query in compact["read_evidence"]["queries"]:
        sets = query.pop("unknown_field_sets", None)
        if sets is not None:
            for record in query["records"]:
                record["unknown_fields"] = sets[record.pop("unknown_fields_ref")]
    assert compact == baseline
    diet = next(q for q in compact["read_evidence"]["queries"] if q["query"]["dimension"] == "diet")
    assert len(diet["records"]) == days + 1  # Same-name rows remain distinct.
    assert diet["records"][-1]["unknown_fields"]["calories"] == "null_in_result"


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
        assert row["status"] == "passed_contracts", contract_diagnostics(row)
        assert any(d["action"] == "allow" for d in row["gateway_decisions"])
        assert len(row["knowledge_contracts"]) == 1
        assert row["knowledge_contracts"][0]["honest_empty_kb"]
    else:
        assert row["status"] == "failed"
        assert row["rejected_tools"] == [{"name": "knowledge_search", "reason": "out_of_scope"}]
        assert row["knowledge_contracts"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", ["复盘", "总结"])
async def test_retrospective_request_completes_real_gateway_and_persistence(
    db, auth_user_and_headers, monkeypatch, verb,
):
    from app.config import settings

    monkeypatch.setattr(settings, "app_env", "test")
    user, _ = auth_user_and_headers
    scenario = Scenario("retrospective", 7, "available",
                        f"{verb}我最近7天的睡眠和饮食记录。", allow_knowledge=True)
    seed_synthetic_records(db, user.id, scenario)
    row = await run_sample(db, user.id, scenario, "baseline", "qwen3.8-flash", CallBudget(3), live=False)
    assert row["status"] == "passed_contracts", contract_diagnostics(row)
    assert row["outcome"] == "complete"
    assert row["quality"]["stream_matches_saved"]
    assert row["quality"]["health_rows_unchanged"]
    assert row["gateway_decisions"][0]["reason"] == "health_query_projected_to_calendar_window"


@pytest.mark.asyncio
@pytest.mark.parametrize("denials,foreign_owner", [(1, False), (2, False), (1, True)])
async def test_actual_provider_can_repair_rejected_read_before_synthesis(
    db, auth_user_and_headers, monkeypatch, denials, foreign_owner,
):
    from app.config import settings
    from eval.full_task_prompt_benchmark import ScriptedProvider

    monkeypatch.setattr(settings, "app_env", "test")
    user, _ = auth_user_and_headers
    scenario = Scenario("scope-repair", 7, "available", allow_knowledge=True)
    seed_synthetic_records(db, user.id, scenario)
    tool_availability = []

    class RepairingProvider(ScriptedProvider):
        async def chat_stream(self, **kwargs):
            tool_availability.append(bool(kwargs.get("tools")))
            if len(tool_availability) <= 2 and kwargs.get("tools"):
                bad = ({"dimension": "sleep", "days": 7, "user_id": user.id + 1} if foreign_owner else
                       {"dimension": "heart_rate", "days": 7})
                queries = ([bad] if len(tool_availability) <= denials else
                           [{"dimension": "sleep", "days": 7}, {"dimension": "diet", "days": 7}])
                yield {"type": "tool_calls", "tool_calls": [{"id": f"repair-{len(tool_availability)}",
                    "type": "function", "function": {"name": "health_query_batch",
                    "arguments": json.dumps({"queries": queries})}}]}
                yield {"type": "finish", "finish_reason": "tool_calls"}
            else:
                yield {"type": "content", "text": "本轮按实际查询结果回答，缺少的记录不能推断为健康正常。"}
                yield {"type": "finish", "finish_reason": "stop"}

    row = await run_sample(db, user.id, scenario, "baseline", "qwen3.8-flash", CallBudget(3),
                           live=False, provider_factory=lambda: RepairingProvider(scenario))
    assert tool_availability == ([True] if foreign_owner else [True, True, False]), row
    assert row["gateway_decisions"][0]["action"] == "block"
    assert row["quality"]["health_rows_unchanged"]
    assert row["quality"]["no_write_receipt"]
    if denials == 1 and not foreign_owner:
        assert row["status"] == "passed_contracts", contract_diagnostics(row)
        assert row["gateway_decisions"][1]["action"] == "allow"
    else:
        assert row["status"] == "failed_contracts", contract_diagnostics(row)
        assert not row["tool_contracts"]
        assert row["outcome"] != "complete"


@pytest.mark.asyncio
async def test_repaired_single_reads_with_infrastructure_failure_reach_final_answer(
    db, auth_user_and_headers, monkeypatch,
):
    from app.config import settings
    from eval.full_task_prompt_benchmark import ScriptedProvider

    monkeypatch.setattr(settings, "app_env", "test")
    user, _ = auth_user_and_headers
    scenario = Scenario("repaired-read-failure", 7, "read_failure", allow_knowledge=True)
    seed_synthetic_records(db, user.id, scenario)
    tools_seen = []

    class RepairingProvider(ScriptedProvider):
        async def chat_stream(self, **kwargs):
            tools_seen.append(bool(kwargs.get("tools")))
            if kwargs.get("tools"):
                dimensions = (["heart_rate"] if len(tools_seen) == 1 else
                              ["sleep", "diet"] if len(tools_seen) == 2 else ["sleep"])
                yield {"type": "tool_calls", "tool_calls": [
                    {"id": f"repair-{len(tools_seen)}-{dimension}", "type": "function",
                     "function": {"name": "health_query", "arguments": json.dumps(
                         {"dimension": dimension, "days": 7})}}
                    for dimension in dimensions]}
                yield {"type": "finish", "finish_reason": "tool_calls"}
            else:
                yield {"type": "content", "text": "本次查询失败，无法判断睡眠和饮食状况，请稍后重试。"}
                yield {"type": "finish", "finish_reason": "stop"}

    row = await run_sample(db, user.id, scenario, "baseline", "qwen3.8-flash", CallBudget(3),
                           live=False, provider_factory=lambda: RepairingProvider(scenario))
    assert tools_seen == [True, True, False], row
    assert row["status"] == "passed_contracts", contract_diagnostics(row)
    assert row["tool_budget"]["physical_dispatches"] == 4
    assert row["outcome"] == "failed"
    assert row["completion_status"] == "error"
    assert row["quality"]["stream_matches_saved"]
    assert row["quality"]["health_rows_unchanged"]


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
async def test_production_route_cli_requires_live_opt_in(tmp_path, monkeypatch):
    cli = load_cli()
    called = []
    async def sample(*args, **kwargs):
        called.append(True)
        raise AssertionError("must not run")
    monkeypatch.setattr(cli, "run_sample", sample)
    args = SimpleNamespace(case=["owned_read_7d_available"], model=["qwen3.8-max"], variant=None,
                           repetitions=1, max_api_calls=4, scripted=True, include_live_llm=False,
                           baseline_only=True, production_routing=True, output=tmp_path / "plan.json")
    with pytest.raises(ValueError, match="production_routing_requires_live_opt_in"):
        await cli.run(args)
    assert not called


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
    assert row["status"] == "passed_contracts", contract_diagnostics(row)
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


@pytest.mark.asyncio
@pytest.mark.parametrize("ignores_disabled_tools", [False, True])
async def test_exhausted_full_scope_read_failure_closes_without_model_read_loop(
    db, auth_user_and_headers, monkeypatch, ignores_disabled_tools,
):
    from app.config import settings
    from eval.full_task_prompt_benchmark import ScriptedProvider
    monkeypatch.setattr(settings, "app_env", "test")
    user, _ = auth_user_and_headers
    scenario = Scenario("exhausted-read", 7, "read_failure", allow_knowledge=True)
    seed_synthetic_records(db, user.id, scenario)
    available = []

    class RepeatAfterInfrastructureFailure(ScriptedProvider):
        async def chat_stream(self, **kwargs):
            available.append(bool(kwargs.get("tools")))
            index = len(available)
            calls = []
            if index == 1:
                calls = [("health_query_batch", {"queries": [
                    {"dimension": "sleep", "days": 7}, {"dimension": "diet", "days": 7}]})]
                if ignores_disabled_tools:
                    calls += [("knowledge_search", {"query": "睡眠和饮食"}),
                              ("health_query", {"dimension": "sleep", "days": 7})]
            elif index == 2 and (kwargs.get("tools") or ignores_disabled_tools):
                calls = [("knowledge_search", {"query": "睡眠和饮食"}),
                         ("health_query", {"dimension": "sleep", "days": 7})]
            if calls:
                yield {"type": "tool_calls", "tool_calls": [
                    {"id": f"exhausted-{index}-{i}", "type": "function", "function": {
                        "name": name, "arguments": json.dumps(args)}}
                    for i, (name, args) in enumerate(calls)]}
                yield {"type": "finish", "finish_reason": "tool_calls"}
            else:
                yield {"type": "content", "text": "本轮读取失败，无法确认睡眠和饮食记录，请稍后重试。"}
                yield {"type": "finish", "finish_reason": "stop"}

    row = await run_sample(db, user.id, scenario, "baseline", "qwen3.8-max", CallBudget(3),
                          live=False, provider_factory=lambda: RepeatAfterInfrastructureFailure(scenario))
    assert available == [True], row
    assert row["status"] == "passed_contracts", contract_diagnostics(row)
    assert len(row["tool_contracts"]) == 2 and all(c["failed"] for c in row["tool_contracts"])
    assert row["outcome"] == "failed" and row["completion_status"] == "error"
    assert row["quality"]["health_rows_unchanged"] and row["quality"]["no_write_receipt"]


@pytest.mark.asyncio
@pytest.mark.parametrize("with_knowledge", [False, True])
async def test_two_legitimate_single_reads_keep_existing_transient_retries(db, auth_user_and_headers, monkeypatch, with_knowledge):
    from app.config import settings
    from eval.full_task_prompt_benchmark import ScriptedProvider
    monkeypatch.setattr(settings, "app_env", "test")
    user, _ = auth_user_and_headers
    scenario = Scenario("single-read-retries", 7, "read_failure", allow_knowledge=True)
    seed_synthetic_records(db, user.id, scenario)
    class Singles(ScriptedProvider):
        async def chat_stream(self, **kwargs):
            if not any(m.get("role") == "tool" for m in kwargs['messages']):
                yield {"type": "tool_calls", "tool_calls": [
                    {"id": "single-"+d, "type": "function", "function": {
                        "name": "health_query", "arguments": json.dumps({"dimension": d, "days": 7})}}
                    for d in ("sleep", "diet")] + ([
                        {"id": "kb", "type": "function", "function": {"name": "knowledge_search", "arguments": json.dumps({"query": "睡眠和饮食"})}}] if with_knowledge else [])}
                yield {"type": "finish", "finish_reason": "tool_calls"}
            else:
                yield {"type": "content", "text": "本轮读取失败，无法确认睡眠和饮食记录。"}
                yield {"type": "finish", "finish_reason": "stop"}
    row = await run_sample(db, user.id, scenario, 'baseline', 'qwen3.8-max', CallBudget(3),
                          live=False, provider_factory=lambda: Singles(scenario))
    assert row['status'] == 'passed_contracts', contract_diagnostics(row)
    assert row['tool_attempts'] == (5 if with_knowledge else 4)
    assert row['tool_budget']['logical_executions'] == (3 if with_knowledge else 2)
    assert row['outcome'] == 'failed'


def test_tool_budget_bounds_both_levels_before_excess_dispatch():
    from eval.full_task_prompt_benchmark import ToolBudget
    per_request = ToolBudget()
    per_request.begin_execution()
    per_request.reserve_dispatch()
    per_request.reserve_dispatch()
    with pytest.raises(BenchmarkStopped, match='physical_tool_budget'):
        per_request.reserve_dispatch()
    total = ToolBudget()
    for _ in range(3):
        total.begin_execution()
        total.reserve_dispatch()
        total.reserve_dispatch()
    with pytest.raises(BenchmarkStopped, match='logical_tool_budget'):
        total.begin_execution()
    with pytest.raises(BenchmarkStopped, match='physical_tool_budget'):
        total.reserve_dispatch()
    assert total.physical_dispatches == 6


@pytest.mark.asyncio
@pytest.mark.parametrize('count', [3, 4])
async def test_logical_budget_counts_replays_and_blocks_excess_proposals_before_dispatch(db, auth_user_and_headers, monkeypatch, count):
    from app.config import settings
    from eval.full_task_prompt_benchmark import ScriptedProvider
    monkeypatch.setattr(settings, 'app_env', 'test')
    user, _ = auth_user_and_headers
    scenario = Scenario('logical-replay', 7, 'available', allow_knowledge=True)
    seed_synthetic_records(db, user.id, scenario)
    class Repeated(ScriptedProvider):
        async def chat_stream(self, **kwargs):
            async for event in super().chat_stream(**kwargs):
                if event.get('type') == 'tool_calls':
                    event['tool_calls'] = [{'id': 'replay-'+str(i), 'type':'function', 'function':{
                        'name':'health_query', 'arguments':json.dumps({'dimension':d,'days':7})}}
                        for i,d in enumerate(['sleep','sleep','diet']+(['diet'] if count==4 else []))]
                yield event
    row = await run_sample(db,user.id,scenario,'baseline','qwen3.8-max',CallBudget(3),live=False,
                           provider_factory=lambda:Repeated(scenario))
    if count == 4:
        assert row['stop_reason'] == 'model_tool_proposal_budget'
        assert row['tool_attempts'] == 0
    else:
        assert row['status'] == 'passed_contracts', contract_diagnostics(row)
        assert row['tool_budget']['logical_executions'] == 3
        assert row['tool_budget']['model_proposals'] == 3
        assert row['tool_attempts'] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["no_event", "reasoning", "content"])
async def test_timeout_keeps_stage_metrics_without_reasoning_or_exception_text(phase):
    rows = []
    hidden = "synthetic private reasoning must not be stored"
    class TimeoutStage:
        async def chat_stream(self, **kwargs):
            if phase != "no_event":
                yield {"type": phase, "text": hidden if phase == "reasoning" else "合成未完成回答"}
            raise TimeoutError("sensitive transport detail must not be stored")
    provider = MeasuredProvider(TimeoutStage, "synthetic", CallBudget(1), rows, live=False)
    with pytest.raises(BenchmarkStopped, match="provider_TimeoutError"):
        _ = [event async for event in provider.chat_stream(messages=[], thinking_budget=512)]
    row = rows[0]
    assert row["last_event_type"] == (None if phase == "no_event" else phase)
    assert row["event_counts"]["reasoning"] == int(phase == "reasoning")
    assert (row["first_reasoning_seconds"] is not None) == (phase == "reasoning")
    assert (row["first_event_seconds"] is not None) == (phase != "no_event")
    assert row["request_controls"] == {"temperature": 0, "max_tokens": 1200, "thinking_budget": 512}
    assert hidden not in json.dumps(row)
    assert "sensitive transport" not in json.dumps(row)
    assert row["input_tokens"] is None


@pytest.mark.asyncio
async def test_stage_metrics_do_not_change_events_or_payload():
    rows, captured = [], []
    expected = [{"type":"reasoning", "text":"hidden synthetic reasoning"},
                {"type":"content", "text":"合成答案"},
                {"type":"finish", "finish_reason":"stop"}]
    class Stages:
        async def chat_stream(self, **kwargs):
            captured.append(kwargs)
            for event in expected:
                yield event
    provider = MeasuredProvider(Stages, "synthetic", CallBudget(1), rows, live=False)
    events = [event async for event in provider.chat_stream(messages=[], enable_thinking=True)]
    assert events == expected
    row = rows[0]
    assert row["event_counts"] == {"reasoning":1, "content":1, "tool_calls":0, "finish":1, "other":0}
    assert row["first_event_seconds"] <= row["first_reasoning_seconds"] <= row["first_content_seconds"] <= row["last_event_seconds"]
    assert row["last_event_type"] == "finish"
    assert row["payload_sha256"] == hashlib.sha256(json.dumps(captured[0], ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    assert "hidden synthetic reasoning" not in json.dumps(row)


@pytest.mark.asyncio
async def test_production_controls_are_preserved_and_still_bounded():
    rows, seen = [], []
    class Capture(Scripted):
        async def chat_stream(self, **kwargs):
            seen.append(kwargs)
            async for event in super().chat_stream(**kwargs): yield event
    p = MeasuredProvider(Capture, "synthetic", CallBudget(1), rows, live=False, preserve_controls=True)
    _ = [e async for e in p.chat_stream(messages=[], model=None, temperature=0.3, max_tokens=8000)]
    assert seen[0]["temperature"] == 0.3 and seen[0]["max_tokens"] == 8000
    with pytest.raises(BenchmarkStopped, match="output_budget"):
        _ = [e async for e in p.chat_stream(messages=[], max_tokens=8001)]
    assert len(rows) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("decision_state", ["accepted", "abstained", "timeout"])
@pytest.mark.parametrize("variant", ["runtime_preplan", "preplan_budget512", "preplan_budget8192"])
async def test_production_route_keeps_real_resolver_quality_and_decision_budget(db, auth_user_and_headers, monkeypatch, decision_state, variant):
    from app.config import settings
    from app.services.agent_executor import AgentExecutor
    from app.services.llm import factory
    from eval.full_task_prompt_benchmark import ScriptedProvider
    from tests.test_decision_routing import wire, fake_result
    monkeypatch.setattr(settings, "app_env", "test")
    user, _ = auth_user_and_headers
    scenario = Scenario("real-route", 31, "available", rich_profile=True)
    seed_synthetic_records(db, user.id, scenario)
    from app.services.decisions import DecisionError
    seen_decisions = wire(monkeypatch, fake_result("balanced", confidence=0.1 if decision_state == "abstained" else 0.95),
                          error=DecisionError("timeout") if decision_state == "timeout" else None)
    from app.services.llm import task_routing
    picked_tiers = []
    real_picker = task_routing.pick_model_id_by_tier
    def pick(tier, **kwargs):
        picked_tiers.append(tier)
        return real_picker(tier, **kwargs)
    monkeypatch.setattr(task_routing, "pick_model_id_by_tier", pick)
    class Provider(ScriptedProvider):
        model = "qwen3.8-max"
        async def chat_stream(self, **kwargs):
            from app.services.llm.usage_tracker import _capture_usage_entry
            # A wire stub for exercising live-mode accounting, not API evidence.
            _capture_usage_entry({"token_source": "api", "prompt_tokens": 123, "completion_tokens": 7,
                                  "cached_tokens": None, "model": self.model, "success": True})
            async for event in super().chat_stream(**kwargs):
                yield event
    monkeypatch.setattr(factory, "create_provider_for_model_id", lambda *a, **k: Provider(scenario))
    calls = []
    original = AgentExecutor._resolve_chat_provider
    def resolve(self, tools):
        calls.append(bool(tools))
        return original(self, tools)
    monkeypatch.setattr(AgentExecutor, "_resolve_chat_provider", resolve)
    budget = CallBudget(2)
    row = await run_sample(db, user.id, scenario, variant, "qwen3.8-max", budget,
                           live=True, production_routing=True)
    assert row["status"] == ("failed_contracts" if decision_state == "timeout" else "passed_contracts"), contract_diagnostics(row)
    assert calls == [False] and len(seen_decisions) == 1
    assert len(row["calls"]) == 1 and len(row["decision_calls"]) == 1 and budget.used == 2
    assert row["decision_routing"]["provider"] == "laya"
    assert row["decision_routing"]["effective_tier"] == "balanced"
    assert row["decision_routing"]["status"] == ("fallback" if decision_state == "timeout" else decision_state)
    assert row["effective_model_id"] == "qwen3.8-max"
    assert row["calls"][0]["request_controls"] == {"temperature":0.3, "max_tokens":8000,
        **({"thinking_budget":int(variant.removeprefix("preplan_budget"))} if variant.startswith("preplan_budget") else {})}
    assert row["decision_calls"][0]["token_source"] == ("unknown" if decision_state == "timeout" else "api")
    assert picked_tiers == (["balanced"] if decision_state == "accepted" else [])


@pytest.mark.asyncio
async def test_library_production_route_rejects_nonlive_before_database_or_factories():
    with pytest.raises(ValueError, match="production_routing_requires_live_opt_in"):
        await run_sample(None, 1, Scenario("non-live", 7, "available"), "runtime_preplan",
                         "qwen3.8-max", CallBudget(2), live=False, production_routing=True)


def test_summary_counts_unknown_decision_usage_and_excludes_scripted_api_attempts():
    cli = load_cli()
    sample = {"model": "qwen3.8-max", "variant": "baseline", "status": "failed_contracts",
              "wall_seconds": 1, "live": True,
              "calls": [{"token_source": "api", "input_tokens": 100, "output_tokens": 10}],
              "decision_calls": [{"token_source": "unknown", "input_tokens": None, "output_tokens": None}]}
    result = cli.summary([sample])[0]
    assert result["all_api_usage_known"] is False
    assert result["usage_unknown_calls"] == 1 and result["total_api_attempts"] == 2
    sample.update(live=False, calls=[{"token_source": "synthetic"}], decision_calls=[])
    result = cli.summary([sample])[0]
    assert result["total_call_attempts"] == 1 and result["total_api_attempts"] == 0
    assert result["all_api_usage_known"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("models,production", [(None, True), (["qwen3.8-flash"], True), (["qwen3.8-max"], False)])
@pytest.mark.parametrize("variant", ["preplan_budget512", "preplan_budget8192"])
async def test_invalid_thinking_probe_batch_stops_before_any_baseline(tmp_path, monkeypatch, models, production, variant):
    cli = load_cli()
    called = []
    async def sample(*args, **kwargs):
        called.append(True)
        raise AssertionError("must not run")
    monkeypatch.setattr(cli, "run_sample", sample)
    args = SimpleNamespace(case=["analysis_31d_rich"], model=models, variant=[variant],
        repetitions=1, max_api_calls=16, scripted=False, include_live_llm=True,
        production_routing=production, output=tmp_path / "report.json")
    with pytest.raises(ValueError, match="thinking_probe_requires_live_max_route"):
        await cli.run(args)
    assert not called and not args.output.exists()


def test_benchmark_worker_rollback_cannot_erase_request_transaction(db, auth_user_and_headers):
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    user, _ = auth_user_and_headers
    db.execute(text('CREATE TABLE benchmark_transaction_probe (value INTEGER)'))
    db.commit()
    db.execute(text('INSERT INTO benchmark_transaction_probe VALUES (7)'))
    with sessionmaker(bind=db.get_bind())() as worker:
        assert worker.execute(text('SELECT id FROM users WHERE id = :id'), {'id': user.id}).scalar_one() == user.id
    db.commit()
    assert db.execute(text('SELECT value FROM benchmark_transaction_probe')).scalars().all() == [7]


def test_benchmark_workers_share_rows_not_dbapi_connections(db, auth_user_and_headers):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    user, _ = auth_user_and_headers
    sessions = sessionmaker(bind=db.get_bind())
    barrier = Barrier(4, timeout=5)
    request_connection = db.connection().connection.driver_connection
    def read():
        with sessions() as worker:
            connection = worker.connection().connection.driver_connection
            barrier.wait()
            row = worker.execute(text('SELECT id FROM users WHERE id = :id'), {'id': user.id}).scalar_one()
            return id(connection), row
    with ThreadPoolExecutor(max_workers=4) as workers:
        rows = list(workers.map(lambda _: read(), range(4)))
    assert len({connection for connection, _ in rows} | {id(request_connection)}) == 5
    assert [row for _, row in rows] == [user.id] * 4


@pytest.fixture
def db(benchmark_db):
    return benchmark_db


def test_ephemeral_engines_are_isolated_memory_only_and_disposed(monkeypatch):
    import sqlite3
    from sqlalchemy import text
    from app.config import settings
    from eval.ephemeral_database import create_ephemeral_engine
    monkeypatch.setattr(settings, 'app_env', 'test')
    connect = sqlite3.connect
    uris = []
    def observe(database, **kwargs):
        uris.append(database)
        assert database.startswith('file:reva-eval-')
        assert database.endswith('?mode=memory&cache=shared') and kwargs['uri'] is True
        return connect(database, **kwargs)
    monkeypatch.setattr(sqlite3, 'connect', observe)
    first, second = create_ephemeral_engine(), create_ephemeral_engine()
    try:
        with first.begin() as connection:
            connection.execute(text('CREATE TABLE isolated_probe (value INTEGER)'))
            assert connection.execute(text('PRAGMA database_list')).all() == [(0, 'main', '')]
        with second.connect() as connection:
            assert connection.execute(text("SELECT name FROM sqlite_master WHERE name = 'isolated_probe'")).all() == []
        assert uris[0] != uris[1]
    finally:
        first.dispose()
        second.dispose()
    # Reopening the exact first name after its last connection closes finds a
    # fresh empty memory database, not retained rows or a file on disk.
    connection = connect(uris[0], uri=True)
    try:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'isolated_probe'").fetchall() == []
    finally:
        connection.close()


def test_ephemeral_engine_rejects_non_test_environment_before_connecting(monkeypatch):
    from app.config import settings
    from eval.ephemeral_database import create_ephemeral_engine
    monkeypatch.setattr(settings, 'app_env', 'production')
    with pytest.raises(RuntimeError, match='test_in_memory'):
        create_ephemeral_engine()


@pytest.mark.asyncio
async def test_benchmark_retains_caught_worker_database_errors(db, auth_user_and_headers, monkeypatch):
    from sqlalchemy import text
    from app.twin import builder
    user, _ = auth_user_and_headers
    scenario = Scenario('caught-worker-database-error', 7, 'available')
    seed_synthetic_records(db, user.id, scenario)
    def broken_reader(worker_db, *args, **kwargs):
        worker_db.execute(text('SELECT synthetic_missing_column FROM users'))
    monkeypatch.setattr(builder, '_fill_mood', broken_reader)
    row = await run_sample(db, user.id, scenario, 'baseline', 'qwen3.8-max', CallBudget(3), live=False)
    assert row['status'] == 'failed_contracts', contract_diagnostics(row)
    assert row['quality']['database_context_intact'] is False
    assert row['database_errors'] and set(row['database_errors']) == {'OperationalError'}
    assert all(detail['sqlite_errorname'] == 'SQLITE_ERROR' and detail['statement_kind'] == 'SELECT'
               for detail in row['database_error_details'])
    assert 'synthetic_missing_column' not in contract_diagnostics(row)
