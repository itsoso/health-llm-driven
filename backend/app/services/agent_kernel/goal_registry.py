"""Immutable extension registries for typed Agent goal contracts."""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from app.services.agent_kernel.types import (
    ActionableReference,
    AgentEnvelope,
    ExecutionContext,
    GoalSpec,
    IntentFrame,
)


class GoalCompiler(Protocol):
    def __call__(
        self,
        *,
        envelope: AgentEnvelope,
        context: ExecutionContext,
        intent: IntentFrame,
        actionable_references: Sequence[ActionableReference],
    ) -> GoalSpec | None: ...


class GoalPromptRenderer(Protocol):
    def __call__(self, goal: GoalSpec) -> str: ...


class GoalVerifier(Protocol):
    def __call__(
        self,
        goal: GoalSpec,
        *,
        write_receipts: Sequence[dict[str, Any]],
        verification_result: Any,
    ) -> Any: ...


@dataclass(frozen=True)
class GoalCompilerSpec:
    name: str
    compiler: GoalCompiler


@dataclass(frozen=True)
class GoalPromptSpec:
    kind: str
    renderer: GoalPromptRenderer


@dataclass(frozen=True)
class GoalVerifierSpec:
    kind: str
    verifier: GoalVerifier


@dataclass(frozen=True)
class GoalCompilerRegistry:
    specs: tuple[GoalCompilerSpec, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "specs", tuple(self.specs))
        _require_unique(
            (spec.name for spec in self.specs),
            label="goal compiler",
        )

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.specs)

    def compile(
        self,
        *,
        envelope: AgentEnvelope,
        context: ExecutionContext,
        intent: IntentFrame,
        actionable_references: Sequence[ActionableReference],
    ) -> GoalSpec | None:
        for spec in self.specs:
            goal = spec.compiler(
                envelope=envelope,
                context=context,
                intent=intent,
                actionable_references=actionable_references,
            )
            if goal is not None:
                return goal
        return None


@dataclass(frozen=True)
class GoalPromptRegistry:
    specs: tuple[GoalPromptSpec, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "specs", tuple(self.specs))
        _require_unique(
            (spec.kind for spec in self.specs),
            label="goal prompt",
        )

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(spec.kind for spec in self.specs)

    def render(self, goal: GoalSpec | None) -> str:
        if goal is None:
            return ""
        for spec in self.specs:
            if spec.kind == goal.kind:
                return spec.renderer(goal)
        return ""


@dataclass(frozen=True)
class GoalVerifierRegistry:
    specs: tuple[GoalVerifierSpec, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "specs", tuple(self.specs))
        _require_unique(
            (spec.kind for spec in self.specs),
            label="goal verifier",
        )

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(spec.kind for spec in self.specs)

    def verify(
        self,
        goal: GoalSpec,
        *,
        write_receipts: Sequence[dict[str, Any]],
        verification_result: Any,
    ) -> Any | None:
        for spec in self.specs:
            if spec.kind == goal.kind:
                return spec.verifier(
                    goal,
                    write_receipts=write_receipts,
                    verification_result=verification_result,
                )
        return None


def _require_unique(values: Iterable[str], *, label: str) -> None:
    seen: set[str] = set()
    for raw_value in values:
        value = str(raw_value or "").strip()
        if not value:
            raise ValueError(f"{label} name must not be empty")
        if value in seen:
            raise ValueError(f"duplicate {label}: {value}")
        seen.add(value)
