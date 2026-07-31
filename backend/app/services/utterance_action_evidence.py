"""Typed evidence primitives for deterministic utterance authorization.

This module only preserves raw spans and clinician-provider provenance.  It
does not authorize actions; action extraction and reduction belong to the
classifier integration layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

ActionKind: TypeAlias = Literal[
    "read",
    "save",
    "update",
    "delete",
    "sync",
    "advice",
    "media",
    "plan",
    "reminder",
]
ActorKind: TypeAlias = Literal["user", "clinician", "ambiguous"]
PolarityKind: TypeAlias = Literal["positive", "negative"]
ModalityKind: TypeAlias = Literal["command", "question", "statement"]
TargetKind: TypeAlias = Literal[
    "clinician_content",
    "clinician_record",
    "symptom",
    "medication",
    "diet",
    "weight",
    "health_record",
    "media",
    "plan",
    "reminder",
    "unknown",
]
ProviderRelationKind: TypeAlias = Literal["report", "basis", "unresolved"]

_CLINICIAN_PROVIDERS = (
    "物理治疗师",
    "主治医生",
    "康复师",
    "理疗师",
    "医生",
    "医师",
    "大夫",
)
_BASIS_MARKERS = ("根据", "依据", "按照")
_REPORT_MARKERS = (
    "告诉",
    "表示",
    "认为",
    "诊断",
    "判断",
    "建议",
    "要求",
    "让我",
    "说",
    "称",
)
_REPORT_DELIMITERS = ("：", ":")


def _validate_span(*, start: int, end: int, label: str) -> None:
    if start < 0 or end < start:
        raise ValueError(f"{label} must satisfy 0 <= start <= end")


@dataclass(frozen=True)
class ActionEvidence:
    start: int
    end: int
    action: ActionKind
    actor: ActorKind
    target: TargetKind
    target_start: int
    target_end: int
    polarity: PolarityKind
    modality: ModalityKind
    provenance: str

    def __post_init__(self) -> None:
        _validate_span(start=self.start, end=self.end, label="action span")
        _validate_span(
            start=self.target_start,
            end=self.target_end,
            label="target span",
        )


@dataclass(frozen=True)
class ProviderEvidence:
    start: int
    end: int
    provider: str
    relation: ProviderRelationKind

    def __post_init__(self) -> None:
        _validate_span(start=self.start, end=self.end, label="provider span")


@dataclass(frozen=True)
class EvidenceParse:
    text: str
    clinician_bearing: bool
    providers: tuple[ProviderEvidence, ...]
    actions: tuple[ActionEvidence, ...]


def _skip_whitespace_left(text: str, end: int) -> int:
    cursor = end
    while cursor > 0 and text[cursor - 1].isspace():
        cursor -= 1
    return cursor


def _skip_whitespace_right(text: str, start: int) -> int:
    cursor = start
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    return cursor


def _has_marker_ending_at(
    text: str,
    end: int,
    markers: tuple[str, ...],
) -> bool:
    for marker in markers:
        start = end - len(marker)
        if start >= 0 and text.startswith(marker, start, end):
            return True
    return False


def _has_marker_starting_at(
    text: str,
    start: int,
    markers: tuple[str, ...],
) -> bool:
    return any(text.startswith(marker, start) for marker in markers)


def _provider_relation(
    text: str,
    *,
    start: int,
    end: int,
) -> ProviderRelationKind:
    before = _skip_whitespace_left(text, start)
    if _has_marker_ending_at(text, before, _BASIS_MARKERS):
        return "basis"

    after = _skip_whitespace_right(text, end)
    if _has_marker_starting_at(text, after, _REPORT_MARKERS):
        return "report"
    if after < len(text) and text[after] in _REPORT_DELIMITERS:
        return "report"
    return "unresolved"


def _scan_providers(text: str) -> tuple[ProviderEvidence, ...]:
    providers: list[ProviderEvidence] = []
    cursor = 0
    while cursor < len(text):
        provider = next(
            (
                candidate
                for candidate in _CLINICIAN_PROVIDERS
                if text.startswith(candidate, cursor)
            ),
            None,
        )
        if provider is None:
            cursor += 1
            continue

        end = cursor + len(provider)
        providers.append(
            ProviderEvidence(
                start=cursor,
                end=end,
                provider=provider,
                relation=_provider_relation(text, start=cursor, end=end),
            )
        )
        cursor = end
    return tuple(providers)


def parse_action_evidence(text: str) -> EvidenceParse:
    """Return raw clinician-provider evidence without authorizing actions."""

    providers = _scan_providers(text)
    return EvidenceParse(
        text=text,
        clinician_bearing=bool(providers),
        providers=providers,
        actions=(),
    )
