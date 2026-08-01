"""Narrow provenance guard for clinician-attributed user turns.

This module only decides whether a clinician-bearing turn is context, advice,
an explicit doctor-feedback write, or an ambiguous action.  It deliberately
does not classify general user actions.  Unknown structures fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from app.services.utterance_intent_lexicon import (
    CLINICIAN_CONSULTATION_TERMS,
    CLINICIAN_FEEDBACK_OBJECT_NOUNS,
    CLINICIAN_FEEDBACK_WRITE_ROOTS,
    CLINICIAN_PROVIDER_TERMS,
    CLINICIAN_REPORT_NOUN_CONTINUATIONS,
    CLINICIAN_REPORT_PREDICATES,
    CLINICIAN_STRICT_COMMAND_PREFIXES,
    QUESTION_SIGNALS,
)

__all__ = ("ClinicianTurnDecision", "classify_clinician_turn")

DecisionKind: TypeAlias = Literal[
    "none",
    "clinician_context",
    "clinician_advice",
    "explicit_doctor_feedback_write",
    "ambiguous_clinician_action",
]

_HARD_BOUNDARIES = frozenset("。；;！？!?\n")
_SOFT_BOUNDARIES = ("，", ",")
_COORDINATION_CUES = (
    "然后",
    "随后",
    "接着",
    "顺便",
    "同时还",
    "并且请",
    "再请",
)
_REPORT_FILLERS = frozenset(" 是为：:，,")


def _validate_optional_span(
    raw: str,
    start: int | None,
    end: int | None,
    *,
    label: str,
) -> None:
    if start is None or end is None:
        if start is not None or end is not None:
            raise ValueError(f"{label} offsets must both be set or both be null")
        return
    if start < 0 or end <= start or end > len(raw):
        raise ValueError(f"{label} offsets must be a non-empty raw span")


@dataclass(frozen=True)
class ClinicianTurnDecision:
    raw: str
    kind: DecisionKind
    provider_start: int | None
    provider_end: int | None
    content_start: int | None
    content_end: int | None
    command_start: int | None
    command_end: int | None
    reason_code: str

    def __post_init__(self) -> None:
        _validate_optional_span(
            self.raw,
            self.provider_start,
            self.provider_end,
            label="provider",
        )
        _validate_optional_span(
            self.raw,
            self.content_start,
            self.content_end,
            label="content",
        )
        _validate_optional_span(
            self.raw,
            self.command_start,
            self.command_end,
            label="command",
        )
        if self.kind == "explicit_doctor_feedback_write":
            if (
                self.provider_start is None
                or self.content_start is None
                or self.command_start is None
            ):
                raise ValueError("explicit feedback writes require all raw spans")
        elif self.command_start is not None or self.command_end is not None:
            raise ValueError("non-writes cannot expose an authorizing command")

    @property
    def authorizes_feedback_write(self) -> bool:
        return self.kind == "explicit_doctor_feedback_write"


@dataclass(frozen=True)
class _Span:
    start: int
    end: int


@dataclass(frozen=True)
class _WriteCandidate:
    segment_index: int
    provider: _Span
    content: _Span | None
    command: _Span | None
    status: Literal["valid", "missing_content", "coordinated"]


@dataclass(frozen=True)
class _Report:
    segment_index: int
    provider: _Span
    content: _Span | None


def _trim(raw: str, start: int, end: int) -> _Span:
    while start < end and raw[start].isspace():
        start += 1
    while end > start and raw[end - 1].isspace():
        end -= 1
    return _Span(start, end)


def _segments(raw: str) -> tuple[_Span, ...]:
    spans: list[_Span] = []
    start = 0
    for position, char in enumerate(raw):
        if char not in _HARD_BOUNDARIES:
            continue
        span = _trim(raw, start, position)
        if span.start < span.end:
            spans.append(span)
        start = position + 1
    span = _trim(raw, start, len(raw))
    if span.start < span.end:
        spans.append(span)
    return tuple(spans)


def _find_first(
    raw: str,
    terms: tuple[str, ...],
    *,
    start: int,
    end: int,
) -> tuple[_Span, str] | None:
    best: tuple[int, int, str] | None = None
    for term in terms:
        position = raw.find(term, start, end)
        if position < 0:
            continue
        candidate = (position, -len(term), term)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        return None
    position, negative_length, term = best
    return _Span(position, position - negative_length), term


def _first_provider(raw: str, span: _Span) -> tuple[_Span, str] | None:
    return _find_first(
        raw,
        CLINICIAN_PROVIDER_TERMS,
        start=span.start,
        end=span.end,
    )


def _skip_spaces(raw: str, position: int, end: int) -> int:
    while position < end and raw[position].isspace():
        position += 1
    return position


def _starts_with_term(
    raw: str,
    terms: tuple[str, ...],
    *,
    position: int,
    end: int,
) -> tuple[_Span, str] | None:
    for term in terms:
        term_end = position + len(term)
        if term_end <= end and raw[position:term_end] == term:
            return _Span(position, term_end), term
    return None


def _match_feedback_object(
    raw: str,
    *,
    position: int,
    end: int,
) -> tuple[_Span, _Span] | None:
    provider_match = _starts_with_term(
        raw,
        CLINICIAN_PROVIDER_TERMS,
        position=position,
        end=end,
    )
    if provider_match is None:
        return None
    provider, _ = provider_match
    noun_start = _skip_spaces(raw, provider.end, end)
    noun_match = _starts_with_term(
        raw,
        CLINICIAN_FEEDBACK_OBJECT_NOUNS,
        position=noun_start,
        end=end,
    )
    if noun_match is None:
        return None
    noun, _ = noun_match
    return provider, _Span(provider.start, noun.end)


def _has_coordination_ambiguity(raw: str, span: _Span) -> bool:
    text = raw[span.start : span.end]
    return any(cue in text for cue in (*_SOFT_BOUNDARIES, *_COORDINATION_CUES))


def _parse_write_segment(
    raw: str,
    segment: _Span,
    segment_index: int,
) -> _WriteCandidate | None:
    position = segment.start
    prefix = _starts_with_term(
        raw,
        CLINICIAN_STRICT_COMMAND_PREFIXES,
        position=position,
        end=segment.end,
    )
    if prefix is not None:
        position = _skip_spaces(raw, prefix[0].end, segment.end)

    root = _starts_with_term(
        raw,
        CLINICIAN_FEEDBACK_WRITE_ROOTS,
        position=position,
        end=segment.end,
    )
    if root is None:
        return None
    position = _skip_spaces(raw, root[0].end, segment.end)
    object_match = _match_feedback_object(
        raw,
        position=position,
        end=segment.end,
    )
    if object_match is None:
        return None
    provider, feedback_object = object_match
    position = _skip_spaces(raw, feedback_object.end, segment.end)
    if position >= segment.end or raw[position] not in "：:":
        return _WriteCandidate(
            segment_index=segment_index,
            provider=provider,
            content=None,
            command=None,
            status="missing_content",
        )

    command = _trim(raw, segment.start, position)
    content = _trim(raw, position + 1, segment.end)
    if content.start >= content.end:
        return _WriteCandidate(
            segment_index=segment_index,
            provider=provider,
            content=None,
            command=None,
            status="missing_content",
        )
    if _has_coordination_ambiguity(raw, content):
        return _WriteCandidate(
            segment_index=segment_index,
            provider=provider,
            content=content,
            command=None,
            status="coordinated",
        )
    return _WriteCandidate(
        segment_index=segment_index,
        provider=provider,
        content=content,
        command=command,
        status="valid",
    )


def _predicate_is_record_noun(
    raw: str,
    predicate: str,
    predicate_end: int,
    segment_end: int,
) -> bool:
    if predicate != "诊断":
        return False
    position = _skip_spaces(raw, predicate_end, segment_end)
    return _starts_with_term(
        raw,
        CLINICIAN_REPORT_NOUN_CONTINUATIONS,
        position=position,
        end=segment_end,
    ) is not None


def _find_report(
    raw: str,
    segment: _Span,
    segment_index: int,
) -> _Report | None:
    provider_match = _first_provider(raw, segment)
    if provider_match is None:
        return None
    provider, _ = provider_match
    predicate_match = _find_first(
        raw,
        CLINICIAN_REPORT_PREDICATES,
        start=provider.end,
        end=segment.end,
    )
    if predicate_match is None:
        return None
    predicate, surface = predicate_match
    if _predicate_is_record_noun(
        raw,
        surface,
        predicate.end,
        segment.end,
    ):
        return None

    content_start = predicate.end
    while (
        content_start < segment.end
        and raw[content_start] in _REPORT_FILLERS
    ):
        content_start += 1
    content = _trim(raw, content_start, segment.end)
    return _Report(
        segment_index=segment_index,
        provider=provider,
        content=content if content.start < content.end else None,
    )


def _contains_question(raw: str) -> bool:
    return any(signal in raw for signal in QUESTION_SIGNALS)


def _span_is_question(raw: str, span: _Span) -> bool:
    text = raw[span.start : span.end]
    return (
        any(signal in text for signal in QUESTION_SIGNALS)
        or span.end < len(raw)
        and raw[span.end] in "？?"
    )


def _has_soft_followup(raw: str, report: _Report) -> bool:
    if report.content is None:
        return False
    content = raw[report.content.start : report.content.end]
    return any(boundary in content for boundary in _SOFT_BOUNDARIES)


def _has_legacy_clinician_record(raw: str) -> bool:
    for provider in CLINICIAN_PROVIDER_TERMS:
        for noun in CLINICIAN_FEEDBACK_OBJECT_NOUNS:
            if f"{provider}{noun}记录" in raw:
                return True
    return False


def _decision(
    raw: str,
    *,
    kind: DecisionKind,
    reason_code: str,
    provider: _Span | None = None,
    content: _Span | None = None,
    command: _Span | None = None,
) -> ClinicianTurnDecision:
    return ClinicianTurnDecision(
        raw=raw,
        kind=kind,
        provider_start=provider.start if provider else None,
        provider_end=provider.end if provider else None,
        content_start=content.start if content else None,
        content_end=content.end if content else None,
        command_start=command.start if command else None,
        command_end=command.end if command else None,
        reason_code=reason_code,
    )


def _ambiguous_candidate(
    raw: str,
    candidate: _WriteCandidate,
    *,
    reason_code: str,
) -> ClinicianTurnDecision:
    return _decision(
        raw,
        kind="ambiguous_clinician_action",
        reason_code=reason_code,
        provider=candidate.provider,
        content=candidate.content,
    )


def classify_clinician_turn(raw: str) -> ClinicianTurnDecision:
    """Classify clinician provenance without authorizing general actions."""

    segments = _segments(raw)
    whole = _Span(0, len(raw))
    first_provider_match = _first_provider(raw, whole)
    if first_provider_match is None:
        return _decision(
            raw,
            kind="none",
            reason_code="no_clinician_signal",
        )
    first_provider, _ = first_provider_match

    candidates = tuple(
        candidate
        for index, segment in enumerate(segments)
        if (candidate := _parse_write_segment(raw, segment, index))
        is not None
    )
    reports = tuple(
        report
        for index, segment in enumerate(segments)
        if (report := _find_report(raw, segment, index)) is not None
    )

    if _has_legacy_clinician_record(raw):
        return _decision(
            raw,
            kind="none",
            reason_code="legacy_clinician_record_operation",
            provider=first_provider,
        )

    if len(candidates) > 1:
        return _ambiguous_candidate(
            raw,
            candidates[0],
            reason_code="coordinated_clinician_action",
        )
    if candidates:
        candidate = candidates[0]
        if candidate.status == "missing_content":
            return _ambiguous_candidate(
                raw,
                candidate,
                reason_code="feedback_write_missing_content",
            )
        if candidate.status == "coordinated":
            return _ambiguous_candidate(
                raw,
                candidate,
                reason_code="coordinated_clinician_action",
            )
        if len(segments) == 1:
            return _decision(
                raw,
                kind="explicit_doctor_feedback_write",
                reason_code="explicit_feedback_write",
                provider=candidate.provider,
                content=candidate.content,
                command=candidate.command,
            )
        preceding_reports = tuple(
            report
            for report in reports
            if report.segment_index == candidate.segment_index - 1
        )
        if (
            len(segments) == 2
            and candidate.segment_index == 1
            and len(preceding_reports) == 1
        ):
            preceding_report = preceding_reports[0]
            if (
                _span_is_question(raw, segments[0])
                or _has_soft_followup(raw, preceding_report)
                or preceding_report.content
                and _has_coordination_ambiguity(
                    raw,
                    preceding_report.content,
                )
            ):
                return _ambiguous_candidate(
                    raw,
                    candidate,
                    reason_code="coordinated_clinician_action",
                )
            return _decision(
                raw,
                kind="explicit_doctor_feedback_write",
                reason_code="explicit_feedback_write_after_report",
                provider=candidate.provider,
                content=candidate.content,
                command=candidate.command,
            )
        return _ambiguous_candidate(
            raw,
            candidate,
            reason_code="coordinated_clinician_action",
        )

    if reports:
        report = reports[0]
        if _contains_question(raw):
            return _decision(
                raw,
                kind="clinician_advice",
                reason_code="clinician_question",
                provider=report.provider,
                content=report.content,
            )
        if _has_soft_followup(raw, report):
            return _decision(
                raw,
                kind="ambiguous_clinician_action",
                reason_code="soft_boundary_followup",
                provider=report.provider,
                content=report.content,
            )
        if report.content and _has_coordination_ambiguity(raw, report.content):
            return _decision(
                raw,
                kind="ambiguous_clinician_action",
                reason_code="coordinated_clinician_action",
                provider=report.provider,
                content=report.content,
            )
        return _decision(
            raw,
            kind="clinician_context",
            reason_code="clinician_report",
            provider=report.provider,
            content=report.content,
        )

    if any(term in raw for term in CLINICIAN_CONSULTATION_TERMS):
        content = _trim(raw, first_provider.end, len(raw))
        return _decision(
            raw,
            kind="clinician_advice",
            reason_code="clinician_consultation",
            provider=first_provider,
            content=content if content.start < content.end else None,
        )
    if _contains_question(raw):
        return _decision(
            raw,
            kind="clinician_advice",
            reason_code="clinician_question",
            provider=first_provider,
        )
    return _decision(
        raw,
        kind="none",
        reason_code="no_clinician_report",
        provider=first_provider,
    )
