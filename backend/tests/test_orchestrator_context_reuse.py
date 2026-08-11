"""Turn-scoped KB reuse and cross-review state regression tests."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.orchestrator import orchestrator as orch_mod
from app.orchestrator.cross_review import Conflict
from app.orchestrator.schema import OrchestratorRequest, SpecialistFinding
from app.models.system_knowledge import KBDocument
from app.twin.schema import HealthTwin, TwinMeta


def _twin(user_id: int = 1) -> HealthTwin:
    return HealthTwin(
        meta=TwinMeta(
            user_id=user_id,
            generated_at=datetime(2026, 8, 11, tzinfo=UTC),
        )
    )


def _finding() -> SpecialistFinding:
    return SpecialistFinding(
        specialist_name="movement_coach",
        category="movement",
        summary="恢复不足，今天降低跑步强度",
        findings=[{"title": "降低跑步强度", "action": "改为恢复活动"}],
    )


def _kb_lookup_result() -> dict:
    return {
        "entities": [],
        "contextual_entities": [],
        "claims": [
            {
                "doc_id": "claim:c_recovery_low_reduce_intensity",
                "entity_type": "intervention",
                "entity_id": "recovery-training",
                "title": "恢复不足时降低跑步强度",
                "summary": "恢复不足时降低训练强度并改为恢复活动。",
                "confidence": 0.82,
                "evidence_level": "A",
                "sources": ["source:test"],
                "metadata": {"domain": "movement"},
            }
        ],
        "claim_boundary": "test-boundary",
    }


def _patch_nonstream_side_effects(monkeypatch, captured: dict) -> None:
    async def fake_call_llm(system_prompt, user_prompt, **_kwargs):
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        return "测试合成结果。"

    def capture_orchestrator_run(**kwargs):
        captured["perf"] = kwargs["perf_breakdown"]

    monkeypatch.setattr(orch_mod, "_call_llm", fake_call_llm)
    monkeypatch.setattr(
        orch_mod,
        "_inject_memory",
        lambda _db, _user_id, prompt, **_kwargs: (prompt, {"stages": {}}),
    )
    monkeypatch.setattr(orch_mod, "_persist_proposed_cards", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(orch_mod, "_build_specialist_credit_block", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(
        orch_mod,
        "_build_per_specialist_track_block",
        lambda *_args, **_kwargs: "",
    )
    monkeypatch.setattr(orch_mod, "_build_persona_addendum", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(orch_mod.parallel_synthesis, "resolve_mode", lambda _value: "off")
    monkeypatch.setattr(
        "app.services.clinical_journal_service.get_active_case_briefs",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "app.services.clinical_journal_service.write_soap_entry",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.memory_extractor.extract_from_specialist_finding",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.system_knowledge_service.record_kb_citation_usage",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.api.judgment_feedback.get_recent_negative_feedback",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "app.agents.audit.log_specialist_findings",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.agents.audit.log_orchestrator_run",
        capture_orchestrator_run,
    )


@pytest.mark.parametrize(
    ("lookup_result", "expected_claim_count", "expected_refs", "has_kb_block"),
    [
        (
            _kb_lookup_result(),
            1,
            ["claim:c_recovery_low_reduce_intensity"],
            True,
        ),
        ({}, 0, [], False),
    ],
    ids=["claim-hit", "falsey-zero-hit"],
)
@pytest.mark.asyncio
async def test_nonstream_orchestrator_reuses_single_kb_snapshot_and_records_metrics(
    monkeypatch,
    db,
    lookup_result,
    expected_claim_count,
    expected_refs,
    has_kb_block,
):
    captured: dict = {}
    lookup_calls = 0
    cross_review_calls = 0
    findings = [_finding(), _finding()]

    def fake_lookup(_db, _payload):
        nonlocal lookup_calls
        lookup_calls += 1
        assert _db is not db
        assert _db.get_bind() is db.get_bind()
        assert _db.info["app_user_id"] == 1
        return lookup_result

    def no_conflicts(*_args, **_kwargs):
        nonlocal cross_review_calls
        cross_review_calls += 1
        return []

    def fake_run_specialists(_twin, _specialists, _context, timings):
        timings.update({"parallel_wall_ms": 0, "recovery_ms": 0, "failed": []})
        return findings

    async def fake_iqs(_query):
        return ""

    _patch_nonstream_side_effects(monkeypatch, captured)
    monkeypatch.setattr(orch_mod, "build_twin", lambda _db, user_id: _twin(user_id))
    monkeypatch.setattr(
        orch_mod,
        "_select_specialists",
        lambda *_args, **_kwargs: [SimpleNamespace(name="movement_coach")],
    )
    monkeypatch.setattr(orch_mod, "_run_specialists", fake_run_specialists)
    monkeypatch.setattr(
        "app.services.system_knowledge_service.lookup_for_twin",
        fake_lookup,
    )
    monkeypatch.setattr("app.orchestrator.cross_review.detect_conflicts", no_conflicts)
    monkeypatch.setattr("app.services.iqs_search.fetch_realtime_evidence", fake_iqs)

    response = await orch_mod.run_orchestrator(
        db,
        1,
        OrchestratorRequest(query="分析我今天的训练恢复", stream=False),
    )

    perf = captured["perf"]
    assert lookup_calls == 1
    assert cross_review_calls == 1
    assert perf["kb_lookup_count"] == 1
    assert perf["kb_lookup_ok"] is True
    assert perf["kb_claim_count"] == expected_claim_count
    assert perf["kb_lookup_reuse_count"] == 2
    assert perf["twin_wall_ms"] >= 0
    assert perf["kb_lookup_ms"] >= 0
    assert perf["cross_review_ms"] >= 0
    assert perf["iqs_ms"] >= 0
    assert ("## 系统知识库相关条目" in captured["user_prompt"]) is has_kb_block
    assert all(
        finding.evidence_refs == expected_refs
        for finding in response.findings
    )


def test_kb_lookup_reuse_count_accounts_for_exception_retry():
    findings = [_finding(), _finding()]
    for finding in findings:
        finding.raw["evidence_resolution"] = {"support_status": "supported"}

    def resolution(*, lookup_count: int, lookup_ok: bool):
        return orch_mod._TurnKBResolution(
            lookup_result=_kb_lookup_result(),
            prompt_text="",
            lookup_ms=0,
            lookup_count=lookup_count,
            lookup_ok=lookup_ok,
            claim_count=1,
        )

    assert orch_mod._count_avoided_kb_lookups(
        findings,
        resolution(lookup_count=1, lookup_ok=True),
    ) == 2
    assert orch_mod._count_avoided_kb_lookups(
        findings,
        resolution(lookup_count=2, lookup_ok=True),
    ) == 1
    assert orch_mod._count_avoided_kb_lookups(
        findings,
        resolution(lookup_count=2, lookup_ok=False),
    ) == 0


@pytest.mark.asyncio
async def test_nonstream_lite_orchestrator_records_zero_kb_metrics(monkeypatch, db):
    captured: dict = {}

    def unexpected_lookup(*_args, **_kwargs):
        raise AssertionError("lite turn must not resolve system knowledge")

    def fake_run_specialists(_twin, _specialists, _context, timings):
        timings.update({"parallel_wall_ms": 0, "recovery_ms": 0, "failed": []})
        return []

    _patch_nonstream_side_effects(monkeypatch, captured)
    monkeypatch.setattr(orch_mod, "build_twin", lambda _db, user_id: _twin(user_id))
    monkeypatch.setattr(orch_mod, "_select_specialists", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(orch_mod, "_run_specialists", fake_run_specialists)
    monkeypatch.setattr(
        "app.services.system_knowledge_service.lookup_for_twin",
        unexpected_lookup,
    )
    monkeypatch.setattr(
        "app.orchestrator.cross_review.detect_conflicts",
        lambda *_args, **_kwargs: [],
    )

    await orch_mod.run_orchestrator(
        db,
        1,
        OrchestratorRequest(query="你好", stream=False),
    )

    perf = captured["perf"]
    assert perf["lite_mode"] is True
    assert perf["kb_lookup_count"] == 0
    assert perf["kb_lookup_reuse_count"] == 0
    assert perf["kb_claim_count"] == 0
    assert perf["kb_lookup_ok"] is True
    assert perf["iqs_ms"] == 0


def test_turn_kb_resolution_retries_once_after_exception(monkeypatch, db):
    lookup_calls = 0

    def flaky_lookup(_db, _payload):
        nonlocal lookup_calls
        lookup_calls += 1
        if lookup_calls == 1:
            raise RuntimeError("temporary lookup failure")
        return _kb_lookup_result()

    monkeypatch.setattr(
        "app.services.system_knowledge_service.lookup_for_twin",
        flaky_lookup,
    )

    resolution = orch_mod._resolve_turn_system_knowledge(
        db,
        _twin(),
        enabled=True,
    )

    assert lookup_calls == 2
    assert resolution.lookup_count == 2
    assert resolution.lookup_ok is True
    assert resolution.claim_count == 1
    assert "恢复不足时降低跑步强度" in resolution.prompt_text


def test_new_kb_lookup_session_uses_caller_bind_and_tenant(db):
    db.info["app_user_id"] = 42

    lookup_db = orch_mod._new_kb_lookup_session(db, fallback_user_id=1)

    try:
        assert lookup_db is not db
        assert lookup_db.get_bind() is db.get_bind()
        assert lookup_db.info["app_user_id"] == 42
    finally:
        lookup_db.close()


def test_turn_kb_resolution_reads_committed_claim_from_caller_bind(monkeypatch, db):
    db.add(
        KBDocument(
            doc_id="claim:c_weight_waist_tracking",
            doc_type="claim",
            entity_type="intervention",
            entity_id="weight-waist-tracking",
            title="体重和腰围晨起记录",
            summary="减重和代谢风险管理应跟踪体重与腰围趋势。",
            confidence=0.72,
            evidence_level="B",
            applies_when=["twin.goals.weight_loss.active == true"],
            sources=["source:test"],
            last_confirmed=datetime(2026, 8, 11, tzinfo=UTC),
            metadata_json={"review_status": "reviewed"},
        )
    )
    db.commit()
    monkeypatch.setattr(
        orch_mod,
        "_system_kb_twin_payload",
        lambda _twin: {"goals": {"weight_loss": {"active": True}}},
    )

    resolution = orch_mod._resolve_turn_system_knowledge(
        db,
        _twin(),
        enabled=True,
    )

    assert resolution.lookup_ok is True
    assert resolution.lookup_count == 1
    assert [claim["doc_id"] for claim in resolution.lookup_result["claims"]] == [
        "claim:c_weight_waist_tracking"
    ]


def test_turn_kb_resolution_mapper_failure_is_fail_soft(monkeypatch, db):
    def failed_mapper(_twin):
        raise RuntimeError("invalid twin mapping")

    def unexpected_session(*_args, **_kwargs):
        raise AssertionError("mapper failure must not open a lookup session")

    monkeypatch.setattr(orch_mod, "_system_kb_twin_payload", failed_mapper)
    monkeypatch.setattr(
        orch_mod,
        "_new_kb_lookup_session",
        unexpected_session,
        raising=False,
    )

    resolution = orch_mod._resolve_turn_system_knowledge(
        db,
        _twin(),
        enabled=True,
    )

    assert resolution.lookup_ok is False
    assert resolution.lookup_count == 0
    assert resolution.claim_count == 0
    assert resolution.lookup_result["claims"] == []
    assert resolution.prompt_text == ""


def test_turn_kb_resolution_stops_after_two_failures_and_cleans_owned_sessions(
    monkeypatch,
):
    lookup_calls = 0
    attempt_sessions = []

    class AttemptSession:
        def __init__(self):
            self.info = {}
            self.rollback_calls = 0
            self.close_calls = 0

        def rollback(self):
            self.rollback_calls += 1

        def close(self):
            self.close_calls += 1

    def make_attempt_session():
        session = AttemptSession()
        attempt_sessions.append(session)
        return session

    def failed_lookup(_db, _payload):
        nonlocal lookup_calls
        lookup_calls += 1
        raise RuntimeError("persistent lookup failure")

    monkeypatch.setattr(
        "app.services.system_knowledge_service.lookup_for_twin",
        failed_lookup,
    )
    monkeypatch.setattr(
        orch_mod,
        "_new_kb_lookup_session",
        lambda _db, fallback_user_id: make_attempt_session(),
        raising=False,
    )

    resolution = orch_mod._resolve_turn_system_knowledge(
        SimpleNamespace(info={"app_user_id": 42}),
        _twin(),
        enabled=True,
    )

    assert lookup_calls == 2
    assert resolution.lookup_count == 2
    assert resolution.lookup_ok is False
    assert resolution.claim_count == 0
    assert resolution.lookup_result["claims"] == []
    assert resolution.prompt_text == ""
    assert len(attempt_sessions) == 2
    assert [session.rollback_calls for session in attempt_sessions] == [1, 1]
    assert [session.close_calls for session in attempt_sessions] == [1, 1]


def test_turn_kb_resolution_retries_in_isolated_session_without_caller_rollback(
    monkeypatch,
):
    lookup_sessions = []
    caller_rollback_calls = 0
    attempt_rollbacks = [0, 0]
    attempt_closes = [0, 0]

    def caller_rollback():
        nonlocal caller_rollback_calls
        caller_rollback_calls += 1

    caller_db = SimpleNamespace(
        info={"app_user_id": 42},
        rollback=caller_rollback,
    )
    attempt_dbs = [
        SimpleNamespace(
            info={},
            rollback=lambda: attempt_rollbacks.__setitem__(
                0, attempt_rollbacks[0] + 1
            ),
            close=lambda: attempt_closes.__setitem__(0, attempt_closes[0] + 1),
        ),
        SimpleNamespace(
            info={},
            rollback=lambda: attempt_rollbacks.__setitem__(
                1, attempt_rollbacks[1] + 1
            ),
            close=lambda: attempt_closes.__setitem__(1, attempt_closes[1] + 1),
        ),
    ]
    session_factory_results = iter(attempt_dbs)

    def flaky_lookup(session, _payload):
        lookup_sessions.append(session)
        if session is caller_db or session is attempt_dbs[0]:
            raise RuntimeError("failed read transaction")
        assert session is attempt_dbs[1]
        return _kb_lookup_result()

    monkeypatch.setattr(
        "app.services.system_knowledge_service.lookup_for_twin",
        flaky_lookup,
    )
    monkeypatch.setattr(
        orch_mod,
        "_new_kb_lookup_session",
        lambda _db, fallback_user_id: next(session_factory_results),
        raising=False,
    )

    resolution = orch_mod._resolve_turn_system_knowledge(
        caller_db,
        _twin(),
        enabled=True,
    )

    assert resolution.lookup_ok is True
    assert lookup_sessions == attempt_dbs
    assert caller_rollback_calls == 0
    assert attempt_rollbacks == [1, 0]
    assert attempt_closes == [1, 1]


def test_turn_kb_resolution_formatter_failure_keeps_lookup_for_findings(
    monkeypatch, db
):
    lookup_calls = 0

    def successful_lookup(_db, _payload):
        nonlocal lookup_calls
        lookup_calls += 1
        return _kb_lookup_result()

    def failed_formatter(*_args, **_kwargs):
        raise RuntimeError("prompt rendering failed")

    monkeypatch.setattr(
        "app.services.system_knowledge_service.lookup_for_twin",
        successful_lookup,
    )
    monkeypatch.setattr(
        "app.services.system_knowledge_service.format_system_knowledge_result_for_prompt",
        failed_formatter,
    )

    resolution = orch_mod._resolve_turn_system_knowledge(
        db,
        _twin(),
        enabled=True,
    )

    assert lookup_calls == 1
    assert resolution.lookup_count == 1
    assert resolution.lookup_ok is True
    assert resolution.claim_count == 1
    assert resolution.lookup_result == _kb_lookup_result()
    assert resolution.prompt_text == ""


def test_cross_review_precomputed_empty_does_not_repeat_detection(monkeypatch):
    detection_calls = 0

    def fake_detect(*_args, **_kwargs):
        nonlocal detection_calls
        detection_calls += 1
        return []

    monkeypatch.setattr("app.orchestrator.cross_review.detect_conflicts", fake_detect)

    _, user_prompt = orch_mod._build_synthesis_prompt(
        "今天能跑步吗？",
        _twin(),
        [_finding()],
        conflict_arb_block="",
        lite_mode=True,
    )

    assert detection_calls == 0
    assert "Specialist 矛盾" not in user_prompt


def test_cross_review_none_runs_one_prompt_fallback(monkeypatch):
    detection_calls = 0

    def fake_detect(*_args, **_kwargs):
        nonlocal detection_calls
        detection_calls += 1
        return []

    monkeypatch.setattr("app.orchestrator.cross_review.detect_conflicts", fake_detect)

    orch_mod._build_synthesis_prompt(
        "今天能跑步吗？",
        _twin(),
        [_finding()],
        conflict_arb_block=None,
        lite_mode=True,
    )

    assert detection_calls == 1


def test_cross_review_precomputed_block_is_injected_without_detection(monkeypatch):
    def unexpected_detect(*_args, **_kwargs):
        raise AssertionError("precomputed conflict block must not be recomputed")

    monkeypatch.setattr("app.orchestrator.cross_review.detect_conflicts", unexpected_detect)
    block = "## Specialist 矛盾\n- 以恢复限制为准"

    _, user_prompt = orch_mod._build_synthesis_prompt(
        "今天能跑步吗？",
        _twin(),
        [_finding()],
        conflict_arb_block=block,
        lite_mode=True,
    )

    assert block in user_prompt


@pytest.mark.asyncio
async def test_cross_review_detection_exception_returns_none(monkeypatch):
    def failed_detect(*_args, **_kwargs):
        raise RuntimeError("temporary cross-review failure")

    monkeypatch.setattr("app.orchestrator.cross_review.detect_conflicts", failed_detect)

    result = await orch_mod._run_cross_review_and_arbitration(
        [_finding()],
        _twin(),
        db=None,
        user_id=1,
    )

    assert result is None


@pytest.mark.asyncio
async def test_cross_review_resolver_retries_only_after_detection_exception(monkeypatch):
    detection_calls = 0
    conflict = Conflict(
        specialist_a="movement_coach",
        specialist_b="recovery_coach",
        severity="soft",
        description="训练建议与恢复限制冲突",
        resolution_hint="以恢复限制为准",
    )

    def flaky_detect(*_args, **_kwargs):
        nonlocal detection_calls
        detection_calls += 1
        if detection_calls == 1:
            raise RuntimeError("temporary cross-review failure")
        return [conflict]

    monkeypatch.setattr("app.orchestrator.cross_review.detect_conflicts", flaky_detect)

    result = await orch_mod._resolve_cross_review_block(
        [_finding()],
        _twin(),
        db=None,
        user_id=1,
    )

    assert detection_calls == 2
    assert result is not None
    assert "训练建议与恢复限制冲突" in result


@pytest.mark.asyncio
async def test_cross_review_fallback_block_is_shared_by_mega_and_parallel(
    monkeypatch, db
):
    captured: dict = {}
    detection_calls = 0
    conflict = Conflict(
        specialist_a="movement_coach",
        specialist_b="recovery_coach",
        severity="soft",
        description="训练建议与恢复限制冲突",
        resolution_hint="以恢复限制为准",
    )

    def flaky_detect(*_args, **_kwargs):
        nonlocal detection_calls
        detection_calls += 1
        if detection_calls == 1:
            raise RuntimeError("temporary cross-review failure")
        return [conflict]

    def fake_run_specialists(_twin, _specialists, _context, timings):
        timings.update({"parallel_wall_ms": 0, "recovery_ms": 0, "failed": []})
        return [_finding()]

    async def fake_iqs(_query):
        return ""

    async def fake_parallel_sectioned(**kwargs):
        captured["parallel_arb_block"] = kwargs["arb_block"]
        return "测试合成结果。", {"section_count": 1}

    original_build_prompt = orch_mod._build_synthesis_prompt

    def capture_build_prompt(*args, **kwargs):
        captured["mega_arb_block"] = kwargs["conflict_arb_block"]
        return original_build_prompt(*args, **kwargs)

    _patch_nonstream_side_effects(monkeypatch, captured)
    monkeypatch.setattr(orch_mod, "build_twin", lambda _db, user_id: _twin(user_id))
    monkeypatch.setattr(
        orch_mod,
        "_select_specialists",
        lambda *_args, **_kwargs: [SimpleNamespace(name="movement_coach")],
    )
    monkeypatch.setattr(orch_mod, "_run_specialists", fake_run_specialists)
    monkeypatch.setattr(
        "app.services.system_knowledge_service.lookup_for_twin",
        lambda *_args, **_kwargs: _kb_lookup_result(),
    )
    monkeypatch.setattr("app.orchestrator.cross_review.detect_conflicts", flaky_detect)
    monkeypatch.setattr("app.services.iqs_search.fetch_realtime_evidence", fake_iqs)
    monkeypatch.setattr(orch_mod, "_build_synthesis_prompt", capture_build_prompt)
    monkeypatch.setattr(orch_mod.parallel_synthesis, "resolve_mode", lambda _value: "on")
    monkeypatch.setattr(
        orch_mod.parallel_synthesis,
        "report_shaped",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        orch_mod.parallel_synthesis,
        "run_parallel_sectioned",
        fake_parallel_sectioned,
    )

    await orch_mod.run_orchestrator(
        db,
        1,
        OrchestratorRequest(query="分析我今天的训练恢复", stream=False),
    )

    assert detection_calls == 2
    assert captured["mega_arb_block"] == captured["parallel_arb_block"]
    assert "训练建议与恢复限制冲突" in captured["mega_arb_block"]


@pytest.mark.asyncio
async def test_cross_review_resolver_does_not_retry_successful_empty(monkeypatch):
    detection_calls = 0

    def no_conflicts(*_args, **_kwargs):
        nonlocal detection_calls
        detection_calls += 1
        return []

    monkeypatch.setattr("app.orchestrator.cross_review.detect_conflicts", no_conflicts)

    result = await orch_mod._resolve_cross_review_block(
        [_finding()],
        _twin(),
        db=None,
        user_id=1,
    )

    assert result == ""
    assert detection_calls == 1
