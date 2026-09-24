"""Provider-independent routing must preserve deterministic authority."""

import pytest
from fastapi import HTTPException

from app.config import settings
from app.services.decisions import DecisionError, DecisionResult
from app.services.decisions import routing


@pytest.fixture
def route_config(monkeypatch):
    monkeypatch.setattr(settings, "decision_mode", "on")
    monkeypatch.setattr(settings, "decision_provider", "laya")
    monkeypatch.setattr(settings, "decision_base_url", None)
    monkeypatch.setattr(settings, "decision_model", None)


def fake_result(tier="casual", confidence=0.95):
    return DecisionResult(
        "multilingual",
        {
            "answer_tier": {"choice": tier, "confidence": confidence},
            "capability": {"choice": "health_query", "confidence": confidence},
        },
        30,
        0,
    )


def wire(monkeypatch, result=None, error=None):
    seen = []

    class Provider:
        async def evaluate(self, request, *, user_id):
            seen.append((request, user_id))
            if error:
                raise error
            return result or fake_result()

    monkeypatch.setattr(routing, "provider_from_settings", lambda: Provider())
    return seen


@pytest.mark.asyncio
@pytest.mark.parametrize("floor", ["casual", "balanced", "high_stakes"])
async def test_never_downgrades_deterministic_floor(route_config, monkeypatch, floor):
    seen = wire(monkeypatch)
    outcome = await routing.decide_route("查询睡眠", user_id=7, baseline_tier=floor)
    assert outcome.effective_tier == floor
    assert seen[0][1] == 7
    assert set(seen[0][0].state) == {"message"}


@pytest.mark.asyncio
async def test_on_can_escalate_and_emit_bounded_capability_hint(
    route_config, monkeypatch
):
    wire(monkeypatch, fake_result("high_stakes"))
    outcome = await routing.decide_route(
        "需要复杂分析", user_id=1, baseline_tier="balanced"
    )
    assert outcome.effective_tier == "high_stakes"
    assert "health_query" in outcome.prompt_hint()
    assert "授权" in outcome.prompt_hint()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["off", "shadow"])
async def test_off_and_shadow_never_change_routing(route_config, monkeypatch, mode):
    monkeypatch.setattr(settings, "decision_mode", mode)
    seen = wire(monkeypatch, fake_result("high_stakes"))
    outcome = await routing.decide_route(
        "需要复杂分析", user_id=1, baseline_tier="balanced"
    )
    assert outcome.effective_tier == "balanced"
    assert outcome.prompt_hint() == ""
    assert len(seen) == (0 if mode == "off" else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        DecisionError("timeout"),
        HTTPException(403, detail={"code": "ai_consent_required"}),
    ],
)
async def test_failure_is_observable_and_keeps_existing_route(
    route_config, monkeypatch, error
):
    seen = wire(monkeypatch, error=error)
    outcome = await routing.decide_route(
        "查询睡眠", user_id=1, baseline_tier="balanced"
    )
    assert outcome.status == "fallback"
    assert outcome.reason in {"timeout", "consent_denied"}
    assert outcome.effective_tier == "balanced"
    assert outcome.prompt_hint() == ""
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_low_confidence_is_abstention(route_config, monkeypatch):
    wire(monkeypatch, fake_result("high_stakes", 0.4))
    outcome = await routing.decide_route(
        "需要分析", user_id=1, baseline_tier="balanced"
    )
    assert outcome.status == "abstained"
    assert outcome.effective_tier == "balanced"
    assert outcome.prompt_hint() == ""


def test_decision_owned_model_escalates_after_tool_evidence(
    route_config, db, monkeypatch
):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._decision_route = routing.RouteDecision(
        "on", "laya", "accepted", "balanced"
    )
    executor._staged_response_mode = "off"
    executor._staged_answer_task_tier = "balanced"
    executor._staged_answer_model_selected = True
    executor._request_model_id = "balanced-model"
    executor._turn_invoked_deep_analysis = True
    monkeypatch.setattr(
        "app.services.llm.task_routing.pick_model_id_by_tier",
        lambda *a, **kw: "quality-model",
    )
    executor._maybe_escalate_staged_answer_model()
    assert executor._request_model_id == "quality-model"
    assert executor._staged_answer_task_tier == "high_stakes"
