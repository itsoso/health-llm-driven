import pytest

from app.services.agent_kernel.goal_registry import (
    GoalCompilerRegistry,
    GoalCompilerSpec,
    GoalPromptRegistry,
    GoalPromptSpec,
    GoalVerifierRegistry,
    GoalVerifierSpec,
)
from app.services.agent_kernel.types import (
    AgentEnvelope,
    ExecutionContext,
    GoalSpec,
    IntentFrame,
)


def _inputs():
    envelope = AgentEnvelope(user_id=1, channel="mobile", text="test")
    context = ExecutionContext.for_test(user_id=1, channel="mobile")
    intent = IntentFrame(
        raw="test",
        normalized="test",
        primary="chat",
        domain="general",
        operation="none",
        confidence=1.0,
    )
    return envelope, context, intent


def test_compiler_registry_uses_first_matching_compiler_in_declared_order():
    calls: list[str] = []

    def miss(**_kwargs):
        calls.append("miss")
        return None

    def match(**_kwargs):
        calls.append("match")
        return GoalSpec(kind="answer", domain="general", operation="read")

    def must_not_run(**_kwargs):
        calls.append("late")
        return GoalSpec(kind="chat", domain="general", operation="none")

    registry = GoalCompilerRegistry(
        (
            GoalCompilerSpec(name="miss", compiler=miss),
            GoalCompilerSpec(name="match", compiler=match),
            GoalCompilerSpec(name="late", compiler=must_not_run),
        )
    )
    envelope, context, intent = _inputs()

    result = registry.compile(
        envelope=envelope,
        context=context,
        intent=intent,
        actionable_references=(),
    )

    assert result is not None
    assert result.kind == "answer"
    assert calls == ["miss", "match"]
    assert registry.names == ("miss", "match", "late")


def test_registries_reject_duplicate_names_and_kinds():
    def compiler(**_kwargs):
        return None

    def renderer(_goal):
        return ""

    def verifier(_goal, *, write_receipts, verification_result):
        return (write_receipts, verification_result)

    with pytest.raises(ValueError, match="duplicate goal compiler"):
        GoalCompilerRegistry(
            (
                GoalCompilerSpec(name="duplicate", compiler=compiler),
                GoalCompilerSpec(name="duplicate", compiler=compiler),
            )
        )

    with pytest.raises(ValueError, match="duplicate goal prompt"):
        GoalPromptRegistry(
            (
                GoalPromptSpec(kind="duplicate", renderer=renderer),
                GoalPromptSpec(kind="duplicate", renderer=renderer),
            )
        )

    with pytest.raises(ValueError, match="duplicate goal verifier"):
        GoalVerifierRegistry(
            (
                GoalVerifierSpec(kind="duplicate", verifier=verifier),
                GoalVerifierSpec(kind="duplicate", verifier=verifier),
            )
        )


def test_prompt_and_verifier_registries_dispatch_by_exact_goal_kind():
    prompt_registry = GoalPromptRegistry(
        (
            GoalPromptSpec(
                kind="verified_task",
                renderer=lambda goal: f"contract:{goal.operation}",
            ),
        )
    )
    verifier_registry = GoalVerifierRegistry(
        (
            GoalVerifierSpec(
                kind="verified_task",
                verifier=lambda goal, **_kwargs: f"verified:{goal.kind}",
            ),
        )
    )
    goal = GoalSpec(
        kind="verified_task",
        domain="general",
        operation="update",
        requires_verification=True,
    )

    assert prompt_registry.render(goal) == "contract:update"
    assert prompt_registry.render(
        GoalSpec(kind="chat", domain="general", operation="none")
    ) == ""
    assert verifier_registry.verify(
        goal,
        write_receipts=(),
        verification_result=None,
    ) == "verified:verified_task"
    assert verifier_registry.kinds == ("verified_task",)
