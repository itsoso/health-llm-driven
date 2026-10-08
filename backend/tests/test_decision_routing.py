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
    monkeypatch.setattr(settings, "decision_admin_control_enabled", False)
    monkeypatch.setattr(settings, "decision_min_confidence", 0.8)


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
        "查询最近的睡眠记录", user_id=1, baseline_tier="balanced"
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


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["on", "shadow"])
@pytest.mark.parametrize("tier_confidence,capability_confidence", [(0.4, 0.95), (0.95, 0.4)])
async def test_each_question_is_accepted_independently(
    route_config, monkeypatch, mode, tier_confidence, capability_confidence
):
    monkeypatch.setattr(settings, "decision_mode", mode)
    result = fake_result("high_stakes")
    result.answers["answer_tier"]["confidence"] = tier_confidence
    result.answers["capability"]["confidence"] = capability_confidence
    wire(monkeypatch, result)
    outcome = await routing.decide_route("查询睡眠记录", user_id=1, baseline_tier="balanced")

    assert outcome.status == ("accepted" if tier_confidence >= 0.8 else "partial")
    assert outcome.effective_tier == (
        "high_stakes" if mode == "on" and tier_confidence >= 0.8 else "balanced"
    )
    assert outcome.capability == ("health_query" if capability_confidence >= 0.8 else None)
    assert bool(outcome.prompt_hint()) == (mode == "on" and capability_confidence >= 0.8)
    assert outcome.reason == ("tier_low_confidence" if tier_confidence < 0.8 else "capability_low_confidence")
    assert outcome.metadata()["tier_confidence"] == tier_confidence
    assert outcome.metadata()["capability_confidence"] == capability_confidence


@pytest.mark.asyncio
@pytest.mark.parametrize("baseline", ["high_stakes", "unknown"])
@pytest.mark.parametrize("confidence", [0.79, 0.8])
async def test_quality_ceiling_only_asks_for_capability(
    route_config, monkeypatch, baseline, confidence
):
    result = fake_result(confidence=confidence)
    del result.answers["answer_tier"]
    seen = wire(monkeypatch, result)
    outcome = await routing.decide_route("查询记录", user_id=1, baseline_tier=baseline)

    assert set(seen[0][0].questions) == {"capability"}
    assert outcome.effective_tier == "high_stakes"
    assert outcome.suggested_tier is None
    assert outcome.tier_confidence is None
    assert outcome.status == ("partial" if confidence >= 0.8 else "abstained")
    assert bool(outcome.prompt_hint()) == (confidence >= 0.8)


@pytest.mark.asyncio
async def test_control_disabled_during_partial_decision_discards_all_advice(route_config, monkeypatch):
    modes = iter(["on", "off"])
    monkeypatch.setattr(routing, "runtime_mode", lambda: next(modes))
    result = fake_result("high_stakes", confidence=0.4)
    result.answers["capability"]["confidence"] = 0.99
    wire(monkeypatch, result)
    outcome = await routing.decide_route("查询睡眠", user_id=1, baseline_tier="balanced")
    assert outcome.status == "fallback"
    assert outcome.reason == "configuration_changed"
    assert outcome.effective_tier == "balanced"
    assert outcome.capability is None
    assert outcome.prompt_hint() == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("message,reason", [
    ("记录体重70公斤", "write_intent"),
    ("帮我记录喝水200毫升", "write_intent"),
    ("删除昨天的体重记录", "write_intent"),
    ("记一杯水，300毫升", "read_intent_unconfirmed"),
])
async def test_confident_lookup_cannot_redirect_write_or_ambiguous_request(
    route_config, monkeypatch, message, reason
):
    result = fake_result("high_stakes")
    wire(monkeypatch, result)
    outcome = await routing.decide_route(message, user_id=1, baseline_tier="balanced")
    assert outcome.effective_tier == "high_stakes"
    assert outcome.capability is None
    assert outcome.prompt_hint() == ""
    assert outcome.reason == reason


@pytest.mark.asyncio
@pytest.mark.parametrize("selected_model", [None, "explicit-fast"])
@pytest.mark.parametrize("baseline", ["balanced", "high_stakes"])
async def test_capability_only_does_not_activate_model_routing_but_keeps_safety_floor(
    route_config, db, monkeypatch, selected_model, baseline
):
    from types import SimpleNamespace
    from app.services.agent_executor import AgentExecutor

    result = fake_result("high_stakes", confidence=0.4)
    result.answers["capability"]["confidence"] = 0.99
    wire(monkeypatch, result)
    executor = AgentExecutor(db)
    executor._decision_route = await routing.decide_route(
        "查询睡眠记录", user_id=1, baseline_tier=baseline
    )
    monkeypatch.setattr(settings, "staged_response_mode", "off")
    monkeypatch.setattr("app.services.llm.model_registry.get_model", lambda _: SimpleNamespace(speed_tier="fast"))
    monkeypatch.setattr("app.services.llm.task_routing.pick_model_id_by_tier", lambda *a, **kw: "quality-model")
    executor._request_model_id = selected_model
    executor._configure_staged_answer_routing(
        "查询睡眠记录", has_attachments=False, preclassified_tier=baseline
    )
    assert executor._decision_route.status == "partial"
    assert executor._decision_route.prompt_hint()
    assert executor._request_model_id == ("quality-model" if baseline == "high_stakes" else selected_model)
    assert executor._staged_answer_model_selected == (baseline == "high_stakes")


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
