"""Actual orchestrator boundaries, not tool JSON, attest reusable reports."""

from contextlib import nullcontext
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.orchestrator import orchestrator as orch
from app.orchestrator.schema import Intent, OrchestratorRequest, SpecialistFinding
from app.services.episode.validator import TextValidationResult
from app.services.orchestrator_delivery import capture_report
from app.twin.schema import HealthTwin, TwinMeta

QUESTION = "请综合分析我的健康状况"
TEXT = "现有记录尚不足以评估整体恢复。请补充最近一晚的睡眠时长。"


def provider(monkeypatch):
    result = {"content": TEXT, "finish_reason": "stop"}
    fake = SimpleNamespace(model="verified-model", chat=AsyncMock(return_value=result))
    monkeypatch.setattr("app.services.llm.get_llm_provider", lambda: fake)
    monkeypatch.setattr("app.services.llm.factory.create_provider_for_user", lambda *a, **k: fake)
    monkeypatch.setattr(orch.settings, "orchestrator_synthesis_model_id", "")
    return fake


@pytest.mark.asyncio
async def test_only_active_mega_requests_metadata_and_captures_actual_result(monkeypatch):
    fake = provider(monkeypatch)
    with capture_report(41, "turn", "tool", QUESTION) as capture:
        text = await orch._call_llm("system", QUESTION, allow_synthesis_override=True)
        assert fake.chat.call_args.kwargs.get("return_metadata") is True
        safety = orch._safety_wrap(text, source="orchestrator.run")
        assert safety.safe_text == text
        receipt = capture.seal(QUESTION, text, evidence_complete=True, mode="off", persisted_card_ids=[])
        assert receipt is not None and receipt.model == "verified-model"


@pytest.mark.asyncio
@pytest.mark.parametrize("active,mega", [(False, True), (False, False), (True, False)])
async def test_inactive_and_nonmega_payloads_are_unchanged(monkeypatch, active, mega):
    fake = provider(monkeypatch)
    with capture_report(41, "turn", "tool", QUESTION) if active else nullcontext():
        assert await orch._call_llm("system", QUESTION, allow_synthesis_override=mega) == TEXT
    assert "return_metadata" not in fake.chat.call_args.kwargs


@pytest.mark.asyncio
async def test_provider_fallback_cannot_mask_failed_generation(monkeypatch):
    fake = provider(monkeypatch)
    fake.chat.side_effect = RuntimeError("synthetic upstream failure")
    fallback = SimpleNamespace(model="fallback-model", chat=AsyncMock(return_value={"content": TEXT, "finish_reason": "stop"}))
    monkeypatch.setattr("app.services.llm.factory.create_llm_provider", lambda *a, **k: fallback)
    monkeypatch.setattr("app.services.llm.usage_tracker.wrap_provider", lambda p: p)
    monkeypatch.setattr("app.services.llm.pii_scrub.wrap_provider_pii_scrub", lambda p: p)
    with capture_report(41, "turn", "tool", QUESTION) as capture:
        text = await orch._call_llm("system", QUESTION, allow_synthesis_override=True)
        assert text == TEXT
        orch._safety_wrap(text, source="orchestrator.run")
        assert capture.seal(QUESTION, text, evidence_complete=True, mode="off", persisted_card_ids=[]) is None


@pytest.mark.asyncio
async def test_validator_exception_fallback_is_not_attestation(monkeypatch):
    provider(monkeypatch)
    monkeypatch.setattr(orch, "validate_text", lambda text: (_ for _ in ()).throw(RuntimeError("validator failed")))
    with capture_report(41, "turn", "tool", QUESTION) as capture:
        text = await orch._call_llm("system", QUESTION, allow_synthesis_override=True)
        assert orch._safety_wrap(text, source="orchestrator.run").safe_text == TEXT
        assert capture.seal(QUESTION, text, evidence_complete=True, mode="off", persisted_card_ids=[]) is None


def evidence():
    return {
        "user_id": 41,
        "twin": HealthTwin(meta=TwinMeta(user_id=41, generated_at=datetime.now(UTC))),
        "specialists": [SimpleNamespace(name="recovery_coach")],
        "findings": [SpecialistFinding(specialist_name="recovery_coach", category="recovery", summary="数据不足")],
        "timings": {"failed": [], "timed_out": []},
        "kb_resolution": orch._TurnKBResolution({}, "", 0, 1, True, 0),
        "evidence_policy_trace": {"blocked_count": 0},
        "memory_trace": {"stages": {name: {"ok": False, "error": None} for name in (
            "conversation", "case_timeline", "directives", "hybrid",
        )}},
        "conflict_block": "", "realtime_block": "",
    }


@pytest.mark.parametrize("failure", [
    "failed", "timed_out", "missing_timings", "raw_error", "missing_finding", "duplicate_finding",
    "twin_partition", "twin_partial", "wrong_owner", "kb_failure", "blocked", "unknown_blocked",
    "conflict", "realtime", "memory_error", "memory_missing", "memory_unknown_status",
])
def test_evidence_completeness_fails_closed(failure):
    args = evidence()
    assert orch._report_evidence_complete(**args) is True
    if failure in {"failed", "timed_out"}:
        args["timings"][failure] = ["recovery_coach"]
    elif failure == "missing_timings":
        args["timings"] = {}
    elif failure == "raw_error":
        args["findings"][0].raw["error"] = "synthetic failure"
    elif failure == "missing_finding":
        args["findings"] = []
    elif failure == "duplicate_finding":
        args["findings"] *= 2
    elif failure == "twin_partition":
        args["twin"].meta.failed_partitions = ["sleep"]
    elif failure == "twin_partial":
        args["twin"].meta.cache_status = "partial"
    elif failure == "wrong_owner":
        args["twin"].meta.user_id = 42
    elif failure == "kb_failure":
        args["kb_resolution"] = replace(args["kb_resolution"], lookup_ok=False)
    elif failure == "blocked":
        args["evidence_policy_trace"]["blocked_count"] = 1
    elif failure == "unknown_blocked":
        args["evidence_policy_trace"] = {}
    elif failure == "conflict":
        args["conflict_block"] = "待仲裁冲突"
    elif failure == "realtime":
        args["realtime_block"] = "未审核网页"
    elif failure == "memory_error":
        args["memory_trace"]["stages"]["directives"]["error"] = "synthetic failure"
    elif failure == "memory_missing":
        args["memory_trace"] = {}
    elif failure == "memory_unknown_status":
        args["memory_trace"]["stages"]["hybrid"]["ok"] = 1
    assert orch._report_evidence_complete(**args) is False


def prepare_run(monkeypatch):
    fake = provider(monkeypatch)
    args = evidence()
    monkeypatch.setattr(orch.settings, "orchestrator_parallel_synthesis", "off")
    monkeypatch.setattr(orch, "_maybe_build_genui_chart", lambda *a: None)
    monkeypatch.setattr(orch, "build_twin", lambda *a: args["twin"])
    monkeypatch.setattr(orch, "classify_intent", lambda q: Intent(raw_query=q, categories=["recovery"]))
    monkeypatch.setattr(orch, "_select_specialists", lambda *a: args["specialists"])

    def run_specialists(*a, timings, **kwargs):
        timings.update(args["timings"])
        return args["findings"]

    monkeypatch.setattr(orch, "_run_specialists", run_specialists)
    monkeypatch.setattr(orch, "_resolve_turn_system_knowledge", lambda *a, **k: args["kb_resolution"])
    monkeypatch.setattr(orch, "_attach_kb_evidence_to_findings", lambda *a, **k: {})
    monkeypatch.setattr(orch, "_apply_planner_evidence_policy", lambda f: (f, args["evidence_policy_trace"]))
    monkeypatch.setattr(orch, "_run_cross_review_and_arbitration", AsyncMock(side_effect=lambda *a: args["conflict_block"]))
    monkeypatch.setattr(orch, "_build_synthesis_prompt", lambda *a, **k: ("system", "user"))
    monkeypatch.setattr(orch, "_inject_memory", lambda *a, **k: ("user", args["memory_trace"]))
    monkeypatch.setattr(orch, "_persist_proposed_cards", lambda *a: [])
    monkeypatch.setattr("app.services.iqs_search.fetch_realtime_evidence", AsyncMock(return_value=""))
    for path in (
        "app.services.clinical_journal_service.get_active_case_briefs",
        "app.services.clinical_journal_service.write_soap_entry",
        "app.services.memory_extractor.extract_from_specialist_finding",
        "app.services.system_knowledge_service.record_kb_citation_usage",
        "app.agents.audit.log_specialist_findings", "app.agents.audit.log_orchestrator_run",
    ):
        monkeypatch.setattr(path, lambda *a, **k: [])
    return fake, args


@pytest.mark.asyncio
async def test_run_seals_from_actual_llm_validator_and_complete_stage_results(monkeypatch):
    fake, _ = prepare_run(monkeypatch)
    with capture_report(41, "turn", "tool", QUESTION) as capture:
        response = await orch.run_orchestrator(object(), 41, OrchestratorRequest(query=QUESTION))
        assert response.synthesis == TEXT
        assert capture.receipt is not None
        assert capture.receipt.text == response.synthesis
        assert capture.consume(capture.receipt) is not None
    assert fake.chat.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["cross_review_none", "cards", "memory", "specialist", "wrong_capture_owner", "unknown_mode", "shadow"])
async def test_actual_run_keeps_response_but_refuses_receipt_on_incomplete_stage(monkeypatch, failure):
    _, args = prepare_run(monkeypatch)
    if failure == "cross_review_none":
        monkeypatch.setattr(orch, "_run_cross_review_and_arbitration", AsyncMock(return_value=None))
        monkeypatch.setattr(orch, "_fallback_cross_review_block", lambda *a: "")
    elif failure == "cards":
        monkeypatch.setattr(orch, "_persist_proposed_cards", lambda *a: [1])
    elif failure == "memory":
        args["memory_trace"]["stages"]["conversation"]["error"] = "failure"
    elif failure == "specialist":
        args["findings"][0].raw["error"] = "failure"
    elif failure == "unknown_mode":
        monkeypatch.setattr(orch.settings, "orchestrator_parallel_synthesis", "unknown")
    elif failure == "shadow":
        monkeypatch.setattr(orch.settings, "orchestrator_parallel_synthesis", "shadow")
    owner = 42 if failure == "wrong_capture_owner" else 41
    with capture_report(owner, "turn", "tool", QUESTION) as capture:
        response = await orch.run_orchestrator(object(), 41, OrchestratorRequest(query=QUESTION))
        assert response.synthesis == TEXT
        assert capture.receipt is None


def record_complete(capture):
    capture.record_generation({"content": TEXT, "finish_reason": "stop"}, "verified-model")
    capture.record_validation(TEXT, TextValidationResult(ok=True, action="pass", safe_text=TEXT))


def assert_not_sealable(capture):
    assert capture.seal(QUESTION, TEXT, evidence_complete=True, mode="off", persisted_card_ids=[]) is None


@pytest.mark.asyncio
async def test_cancelled_generation_is_not_reclassified_as_single_successful_retry(monkeypatch):
    fake = provider(monkeypatch)
    fake.chat.side_effect = asyncio.CancelledError()
    with capture_report(41, "turn", "tool", QUESTION) as capture:
        with pytest.raises(asyncio.CancelledError):
            await orch._call_llm("system", QUESTION, allow_synthesis_override=True)
        fake.chat.side_effect = None
        text = await orch._call_llm("system", QUESTION, allow_synthesis_override=True)
        orch._safety_wrap(text, source="orchestrator.run")
        assert_not_sealable(capture)


@pytest.mark.parametrize("failed_stage", ["conversation", "case_timeline", "directives", "hybrid"])
def test_memory_exception_even_without_error_message_poison_receipt(monkeypatch, failed_stage):
    paths = {
        "conversation": "app.services.conversation_memory_service.get_relevant_memories",
        "case_timeline": "app.services.clinical_journal_service.get_recent_case_summary",
        "directives": "app.services.directive_parser.get_active_directives_for_prompt",
        "hybrid": "app.services.hybrid_search.hybrid_retrieve",
    }
    for path in paths.values():
        monkeypatch.setattr(path, lambda *a, **k: [])
    monkeypatch.setattr("app.services.clinical_journal_service._pick_primary_metric", lambda *a: "sleep")
    monkeypatch.setattr("app.agents.audit.log_memory_injection", lambda *a, **k: None)
    monkeypatch.setattr(paths[failed_stage], lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    with capture_report(41, "turn", "tool", QUESTION) as capture:
        record_complete(capture)
        orch._inject_memory(object(), 41, "prompt", findings=evidence()["findings"])
        assert_not_sealable(capture)


@pytest.mark.parametrize("failed_stage", ["setup", "lookup", "formatter", "attach"])
def test_recovered_knowledge_errors_never_attest_complete_evidence(monkeypatch, failed_stage):
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic KB failure")

    monkeypatch.setattr(orch, "_system_kb_twin_payload", lambda *a: {})
    monkeypatch.setattr(orch, "_new_kb_lookup_session", lambda *a, **k: SimpleNamespace(rollback=lambda: None, close=lambda: None))
    monkeypatch.setattr("app.services.system_knowledge_service.lookup_for_twin", lambda *a: {"claims": []})
    monkeypatch.setattr("app.services.system_knowledge_service.format_system_knowledge_result_for_prompt", lambda *a, **k: "")
    failure_paths = {
        "setup": "app.orchestrator.orchestrator._system_kb_twin_payload",
        "lookup": "app.services.system_knowledge_service.lookup_for_twin",
        "formatter": "app.services.system_knowledge_service.format_system_knowledge_result_for_prompt",
        "attach": "app.services.system_knowledge_service.attach_system_knowledge_evidence",
    }
    monkeypatch.setattr(failure_paths[failed_stage], fail)
    with capture_report(41, "turn", "tool", QUESTION) as capture:
        record_complete(capture)
        if failed_stage == "attach":
            orch._attach_kb_evidence_to_findings(object(), evidence()["twin"], evidence()["findings"])
        else:
            orch._resolve_turn_system_knowledge(object(), evidence()["twin"], enabled=True)
        assert_not_sealable(capture)


@pytest.mark.asyncio
async def test_usage_wrapper_internal_recovery_cannot_appear_as_one_original_model_generation(monkeypatch):
    import app.services.llm.recovery as recovery
    import app.services.llm.usage_tracker as tracker

    monkeypatch.setattr(tracker, "_enforce_monthly_token_quota", lambda **kwargs: None)
    usage = []
    monkeypatch.setattr(tracker, "record_usage", lambda **kwargs: usage.append(kwargs))
    monkeypatch.setattr(orch.settings, "llm_auto_recovery_enabled", True)
    monkeypatch.setattr(orch.settings, "llm_recovery_model_id", "gpt-5.5")
    monkeypatch.setattr(orch.settings, "orchestrator_synthesis_model_id", "")
    monkeypatch.setattr(recovery, "_env_available", lambda model_id: True)
    primary_chat = AsyncMock(side_effect=RuntimeError("503 service unavailable"))
    fallback_chat = AsyncMock(return_value={"content": TEXT, "finish_reason": "stop"})
    primary = tracker.wrap_provider(SimpleNamespace(
        provider_name="tokenplan", model="qwen3.7-plus", chat=primary_chat,
    ))
    fallback = tracker.wrap_provider(SimpleNamespace(
        provider_name="langbridge-proxy", model="gpt-5.5", chat=fallback_chat,
    ))
    monkeypatch.setattr(recovery, "create_provider_for_model_id", lambda model_id: fallback)
    monkeypatch.setattr("app.services.llm.get_llm_provider", lambda: primary)
    monkeypatch.setattr("app.services.llm.factory.create_provider_for_user", lambda *a, **k: primary)
    with capture_report(41, "turn", "tool", QUESTION) as capture:
        text = await orch._call_llm("system", QUESTION, allow_synthesis_override=True)
        assert text == TEXT
        orch._safety_wrap(text, source="orchestrator.run")
        assert_not_sealable(capture)
    assert primary_chat.await_count == fallback_chat.await_count == 1
    assert any(row["success"] is False and row.get("recovery_action") == "fallback_attempted" for row in usage)
    assert any(row["success"] is True and row["model"] == "gpt-5.5" for row in usage)
