"""Typed evidence primitives for deterministic utterance authorization.

This evidence layer owns raw-span extraction and action reduction; the
classifier integration layer only maps reduced evidence to its public intent
contract.  The initial primitives below preserve clinician provenance without
authorizing actions.
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

_CLINICIAN_PROVIDERS = tuple(
    sorted(
        (
            "主治医生",
            "物理治疗师",
            "康复师",
            "理疗师",
            "医生",
            "医师",
            "大夫",
        ),
        key=len,
        reverse=True,
    )
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
_REPORT_NOUN_CONTINUATIONS = {
    "诊断": ("记录", "报告", "结果", "证明", "清单", "列表"),
    "建议": ("记录", "报告", "清单", "列表", "文档"),
}


def _validate_span(
    *,
    start: int,
    end: int,
    label: str,
    allow_empty: bool = False,
) -> None:
    is_empty = start == end
    if start < 0 or end < start or (is_empty and not allow_empty):
        relation = "<=" if allow_empty else "<"
        empty_note = "possibly empty" if allow_empty else "non-empty"
        raise ValueError(
            f"{label} must be {empty_note} and satisfy "
            f"0 <= start {relation} end"
        )


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
            allow_empty=self.target == "unknown",
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

    def __post_init__(self) -> None:
        if self.clinician_bearing != bool(self.providers):
            raise ValueError(
                "clinician_bearing must equal bool(providers)"
            )

        _validate_provider_evidence(self.text, self.providers)
        _validate_action_evidence(self.text, self.actions)


def _validate_ordered(
    evidence: tuple[ProviderEvidence, ...] | tuple[ActionEvidence, ...],
    *,
    label: str,
) -> None:
    previous_start = -1
    for item in evidence:
        if item.start <= previous_start:
            raise ValueError(
                f"{label} must be ordered strictly by raw start offset"
            )
        previous_start = item.start


def _validate_provider_evidence(
    text: str,
    providers: tuple[ProviderEvidence, ...],
) -> None:
    _validate_ordered(providers, label="providers")
    for provider in providers:
        if provider.end > len(text):
            raise ValueError("provider span must fall within text")
        if text[provider.start : provider.end] != provider.provider:
            raise ValueError("provider raw slice must equal provider")


def _validate_action_evidence(
    text: str,
    actions: tuple[ActionEvidence, ...],
) -> None:
    _validate_ordered(actions, label="actions")
    for action in actions:
        if action.end > len(text):
            raise ValueError("action span must fall within text")
        if action.target_end > len(text):
            raise ValueError("target span must fall within text")


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


def _marker_starting_at(
    text: str,
    start: int,
    markers: tuple[str, ...],
) -> str | None:
    return next(
        (marker for marker in markers if text.startswith(marker, start)),
        None,
    )


def _is_report_predicate(
    text: str,
    *,
    marker: str,
    marker_start: int,
) -> bool:
    content_start = _skip_whitespace_right(
        text,
        marker_start + len(marker),
    )
    if content_start >= len(text):
        return False
    return not any(
        text.startswith(noun, content_start)
        for noun in _REPORT_NOUN_CONTINUATIONS.get(marker, ())
    )


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
    report_marker = _marker_starting_at(text, after, _REPORT_MARKERS)
    if report_marker is not None:
        if _is_report_predicate(
            text,
            marker=report_marker,
            marker_start=after,
        ):
            return "report"
        return "unresolved"
    if after < len(text) and text[after] in _REPORT_DELIMITERS:
        content_start = _skip_whitespace_right(text, after + 1)
        return "report" if content_start < len(text) else "unresolved"
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
