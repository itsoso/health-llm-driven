"""test_orchestrator_stream_persistent —— G-W9 客户端断开 background task 继续.

同 G-W8 模式: bg task 在 client disconnect 后跑完 audit / journal /
memory extract / specialist finding 落库.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.models.user import User
from app.orchestrator import orchestrator as orch_module
from app.orchestrator.orchestrator import stream_orchestrator, _BACKGROUND_STREAM_TASKS
from app.orchestrator.schema import OrchestratorRequest, SpecialistFinding
from app.twin.schema import HealthTwin, TwinMeta


@pytest.fixture(autouse=True)
def patch_session_local(db):
    """bg task 走 `from app.database import SessionLocal`, 测试让它复用 fixture db.
    ProxyDB 复用 test db, .close() 是 no-op (fixture 自己会关).
    """
    class _DBProxy:
        def __init__(self, real):
            object.__setattr__(self, "_real", real)
        def __getattr__(self, name):
            if name == "close":
                return lambda: None
            return getattr(self._real, name)
        def __setattr__(self, name, val):
            setattr(self._real, name, val)

    def _factory():
        return _DBProxy(db)

    with patch("app.database.SessionLocal", new=_factory):
        yield


def _make_user(db, name="orch_stream"):
    u = User(
        username=f"{name}_{uuid.uuid4().hex[:8]}",
        email=f"{name}_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name=name,
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


async def _fake_stream_llm(system_prompt, user_prompt, *, lite_mode=False):
    for i in range(5):
        await asyncio.sleep(0.05)
        yield f"chunk{i}"


async def _wait_bg():
    if _BACKGROUND_STREAM_TASKS:
        await asyncio.gather(*list(_BACKGROUND_STREAM_TASKS), return_exceptions=True)


@pytest.mark.asyncio
async def test_full_stream_yields_chunks_and_done(db):
    user = _make_user(db, "full_orch_stream")
    req = OrchestratorRequest(query="我最近 HRV 下降", source="chat")

    events = []
    with patch.object(orch_module, "_stream_llm", new=_fake_stream_llm):
        async for raw in stream_orchestrator(db, user.id, req):
            events.append(raw)

    await _wait_bg()

    chunk_events = [e for e in events if e.startswith("event: chunk\n")]
    done_events = [e for e in events if e.startswith("event: done\n")]
    assert len(chunk_events) >= 5
    assert len(done_events) == 1


@pytest.mark.asyncio
async def test_client_disconnect_background_task_still_audits(db):
    """client 早断 → generator 退出 → bg task 继续完成 audit 落库."""
    from app.models.agent_audit_log import AgentAuditLog

    user = _make_user(db, "orch_disc")
    req = OrchestratorRequest(query="早断测试", source="chat")

    consumed = 0
    with patch.object(orch_module, "_stream_llm", new=_fake_stream_llm):
        async for _raw in stream_orchestrator(db, user.id, req):
            consumed += 1
            if consumed >= 1:
                break

    await _wait_bg()

    audits = db.query(AgentAuditLog).filter(
        AgentAuditLog.user_id == user.id,
        AgentAuditLog.agent_type == "orchestrator",
    ).all()
    assert len(audits) >= 1, "bg task 应完成 orchestrator.run audit"


@pytest.mark.asyncio
async def test_immediate_disconnect_still_saves_audit(db):
    from app.models.agent_audit_log import AgentAuditLog

    user = _make_user(db, "orch_immediate")
    req = OrchestratorRequest(query="立刻断", source="chat")

    with patch.object(orch_module, "_stream_llm", new=_fake_stream_llm):
        async for _raw in stream_orchestrator(db, user.id, req):
            break

    await _wait_bg()

    audits = db.query(AgentAuditLog).filter(
        AgentAuditLog.user_id == user.id,
        AgentAuditLog.agent_type == "orchestrator",
    ).all()
    assert len(audits) >= 1


@pytest.mark.asyncio
async def test_stream_reuses_single_kb_snapshot_and_exposes_stage_perf(db, monkeypatch):
    user = _make_user(db, "orch_kb_reuse")
    captured: dict = {}
    lookup_calls = 0
    cross_review_calls = 0
    twin = HealthTwin(
        meta=TwinMeta(
            user_id=user.id,
            generated_at=datetime(2026, 8, 11, tzinfo=UTC),
        )
    )
    findings = [
        SpecialistFinding(
            specialist_name="movement_coach",
            category="movement",
            summary="恢复不足，今天降低跑步强度",
            findings=[{"title": "降低跑步强度", "action": "改为恢复活动"}],
        ),
        SpecialistFinding(
            specialist_name="movement_coach",
            category="movement",
            summary="今天只做恢复活动，避免高强度跑步",
            findings=[{"title": "恢复活动", "action": "避免高强度跑步"}],
        ),
    ]

    def fake_lookup(_db, _payload):
        nonlocal lookup_calls
        lookup_calls += 1
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

    def no_conflicts(*_args, **_kwargs):
        nonlocal cross_review_calls
        cross_review_calls += 1
        return []

    def fake_run_specialists(_twin, _specialists, _context, timings):
        timings.update({"parallel_wall_ms": 0, "recovery_ms": 0, "failed": []})
        return findings

    async def fake_iqs(_query):
        return ""

    async def fake_stream(system_prompt, user_prompt, *, lite_mode=False):
        captured["user_prompt"] = user_prompt
        yield "测试合成结果。"

    def capture_orchestrator_run(**kwargs):
        captured["audit_perf"] = dict(kwargs["perf_breakdown"])

    monkeypatch.setattr(orch_module, "build_twin", lambda *_args, **_kwargs: twin)
    monkeypatch.setattr(
        orch_module,
        "_select_specialists",
        lambda *_args, **_kwargs: [SimpleNamespace(name="movement_coach")],
    )
    monkeypatch.setattr(orch_module, "_run_specialists", fake_run_specialists)
    monkeypatch.setattr(orch_module, "_stream_llm", fake_stream)
    monkeypatch.setattr(
        orch_module,
        "_inject_memory",
        lambda _db, _user_id, prompt, **_kwargs: (prompt, {"stages": {}}),
    )
    monkeypatch.setattr(orch_module, "_persist_proposed_cards", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        orch_module,
        "_build_specialist_credit_block",
        lambda *_args, **_kwargs: "",
    )
    monkeypatch.setattr(
        orch_module,
        "_build_per_specialist_track_block",
        lambda *_args, **_kwargs: "",
    )
    monkeypatch.setattr(
        orch_module,
        "_build_persona_addendum",
        lambda *_args, **_kwargs: "",
    )
    monkeypatch.setattr(
        "app.services.system_knowledge_service.lookup_for_twin",
        fake_lookup,
    )
    monkeypatch.setattr("app.orchestrator.cross_review.detect_conflicts", no_conflicts)
    monkeypatch.setattr("app.services.iqs_search.fetch_realtime_evidence", fake_iqs)
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

    events = []
    async for raw in stream_orchestrator(
        db,
        user.id,
        OrchestratorRequest(query="分析我今天的训练恢复", source="chat"),
    ):
        events.append(raw)

    done_raw = next(event for event in events if event.startswith("event: done\n"))
    done_payload = json.loads(done_raw.split("data: ", 1)[1])
    specialist_payloads = [
        json.loads(event.split("data: ", 1)[1])
        for event in events
        if event.startswith("event: specialist\n")
    ]

    assert lookup_calls == 1
    assert cross_review_calls == 1
    assert done_payload["perf"] == captured["audit_perf"]
    assert done_payload["perf"]["kb_lookup_count"] == 1
    assert done_payload["perf"]["kb_lookup_reuse_count"] >= 1
    assert done_payload["perf"]["kb_claim_count"] == 1
    assert done_payload["perf"]["kb_lookup_ok"] is True
    assert done_payload["perf"]["twin_wall_ms"] >= 0
    assert done_payload["perf"]["cross_review_ms"] >= 0
    assert done_payload["perf"]["iqs_ms"] >= 0
    assert "恢复不足时降低跑步强度" in captured["user_prompt"]
    assert all(
        payload["evidence_refs"] == ["claim:c_recovery_low_reduce_intensity"]
        for payload in specialist_payloads
    )
