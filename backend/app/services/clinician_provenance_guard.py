"""Narrow provenance guard for clinician-attributed user turns.

This module only decides whether a clinician-bearing turn is context, advice,
an explicit doctor-feedback write, or an ambiguous action.  It deliberately
does not classify general user actions.  Unknown structures fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias
import unicodedata

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
_ACTION_JOINER_SUFFIXES = (
    "与此同时",
    "除此之外",
    "然后",
    "随后",
    "接着",
    "顺便",
    "同时",
    "以及",
    "并且",
    "但是",
    "可是",
    "不过",
)
_ACTION_JOINER_CHARS = frozenset("且和与及并但")
# These roots only invalidate a previously proven feedback-write envelope.
# They are never used to authorize or classify general user actions.
_WRITE_ENVELOPE_BLOCKED_ROOTS = (
    "删除",
    "删掉",
    "移除",
    "修改",
    "调整",
    "更新",
    "同步",
    "提醒",
    "保存",
    "记录",
    "录入",
    "写入",
    "创建",
    "设置",
    "生成",
    "制定",
    "安排",
    "制作",
    "渲染",
)
_REPORT_FILLERS = frozenset(" 是为：:，,")
_CONTENT_SEPARATORS = frozenset("：:,，")
_CONTENT_PLACEHOLDERS = frozenset(
    {"待补充", "待填写", "暂无", "未知", "不详", "无", "NA", "N/A"}
)
_NON_HUMAN_PROVIDER_PREFIXES = ("宠物", "动物", "兽")
_LEGACY_OPERATION_ROOTS = ("查看", "查询", "删除", "删掉", "移除")
_LEGACY_CLINICIAN_OBJECT_SUFFIXES = (
    "诊断记录",
    "诊断报告",
    "诊断书",
    "诊断文档",
    "诊断档案",
    "文档",
    "档案",
)
_REASONS_BY_KIND: dict[DecisionKind, frozenset[str]] = {
    "none": frozenset(
        {
            "no_clinician_signal",
            "no_clinician_report",
            "legacy_clinician_record_operation",
        }
    ),
    "clinician_context": frozenset({"clinician_report"}),
    "clinician_advice": frozenset(
        {"clinician_question", "clinician_consultation"}
    ),
    "explicit_doctor_feedback_write": frozenset(
        {"explicit_feedback_write", "explicit_feedback_write_after_report"}
    ),
    "ambiguous_clinician_action": frozenset(
        {
            "soft_boundary_followup",
            "coordinated_clinician_action",
            "feedback_write_missing_content",
            "feedback_write_question",
        }
    ),
}


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
        allowed_reasons = _REASONS_BY_KIND.get(self.kind)
        if allowed_reasons is None:
            raise ValueError(f"unknown decision kind: {self.kind}")
        if self.reason_code not in allowed_reasons:
            raise ValueError(
                f"reason {self.reason_code!r} is invalid for kind {self.kind!r}"
            )
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
            if not (
                self.command_start
                <= self.provider_start
                < self.provider_end
                <= self.command_end
            ):
                raise ValueError("provider span must be contained by command span")
            if self.command_end > self.content_start:
                raise ValueError("command span must precede content span")
        elif self.command_start is not None or self.command_end is not None:
            raise ValueError("non-writes cannot expose an authorizing command")
        if (
            self.provider_end is not None
            and self.content_start is not None
            and self.provider_end > self.content_start
        ):
            raise ValueError("provider span must precede content span")

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
    status: Literal[
        "valid",
        "missing_content",
        "coordinated",
        "question",
    ]


@dataclass(frozen=True)
class _Report:
    segment_index: int
    provider: _Span
    content: _Span | None


def _is_ignorable(char: str) -> bool:
    return char.isspace() or unicodedata.category(char) == "Cf"


def _trim(raw: str, start: int, end: int) -> _Span:
    while start < end and _is_ignorable(raw[start]):
        start += 1
    while end > start and _is_ignorable(raw[end - 1]):
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


def _first_provider(raw: str, span: _Span) -> tuple[_Span, str] | None:
    matches = _provider_matches(raw, span)
    return matches[0] if matches else None


def _has_nonhuman_provider_prefix(raw: str, position: int) -> bool:
    for prefix in _NON_HUMAN_PROVIDER_PREFIXES:
        start = position - len(prefix)
        if start >= 0 and raw[start:position] == prefix:
            return True
    return False


def _provider_matches(
    raw: str,
    span: _Span,
) -> tuple[tuple[_Span, str], ...]:
    candidates: list[tuple[_Span, str]] = []
    for term in CLINICIAN_PROVIDER_TERMS:
        position = raw.find(term, span.start, span.end)
        while position >= 0:
            if not _has_nonhuman_provider_prefix(raw, position):
                candidates.append(
                    (_Span(position, position + len(term)), term)
                )
            position = raw.find(term, position + len(term), span.end)
    candidates.sort(key=lambda item: (item[0].start, -len(item[1])))
    matches: list[tuple[_Span, str]] = []
    for candidate in candidates:
        if matches and candidate[0].start < matches[-1][0].end:
            continue
        matches.append(candidate)
    return tuple(matches)


def _skip_spaces(raw: str, position: int, end: int) -> int:
    while position < end and _is_ignorable(raw[position]):
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


def _strip_ignorable_end(raw: str, start: int, end: int) -> int:
    while end > start and _is_ignorable(raw[end - 1]):
        end -= 1
    return end


def _second_action_prefix_kind(
    raw: str,
    *,
    span_start: int,
    action_start: int,
) -> Literal["soft", "coordinated"] | None:
    prefix_end = _strip_ignorable_end(raw, span_start, action_start)
    polite_found = False
    for polite in CLINICIAN_STRICT_COMMAND_PREFIXES:
        polite_start = prefix_end - len(polite)
        if polite_start >= span_start and raw[polite_start:prefix_end] == polite:
            prefix_end = _strip_ignorable_end(raw, span_start, polite_start)
            polite_found = True
            break
    if prefix_end <= span_start:
        return None
    prefix = raw[span_start:prefix_end]
    if not any(
        unicodedata.category(char)[0] in {"L", "N"}
        for char in prefix
    ):
        return None
    last_char = raw[prefix_end - 1]
    if unicodedata.category(last_char).startswith("P"):
        return "soft" if last_char in "，," else "coordinated"
    if polite_found:
        return "coordinated"
    if last_char in _ACTION_JOINER_CHARS:
        return "coordinated"
    if any(prefix.endswith(joiner) for joiner in _ACTION_JOINER_SUFFIXES):
        return "coordinated"
    return None


def _second_action_kind(
    raw: str,
    span: _Span,
) -> Literal["soft", "coordinated"] | None:
    best: tuple[int, Literal["soft", "coordinated"]] | None = None
    for root in _WRITE_ENVELOPE_BLOCKED_ROOTS:
        position = raw.find(root, span.start, span.end)
        while position >= 0:
            kind = _second_action_prefix_kind(
                raw,
                span_start=span.start,
                action_start=position,
            )
            if kind is not None and (best is None or position < best[0]):
                best = (position, kind)
            position = raw.find(root, position + len(root), span.end)
    return best[1] if best else None


def _consume_content_prefix(raw: str, position: int, end: int) -> int:
    while position < end:
        char = raw[position]
        if _is_ignorable(char) or char in _CONTENT_SEPARATORS:
            position += 1
            continue
        break
    return position


def _content_is_substantive(raw: str, content: _Span) -> bool:
    text = raw[content.start : content.end]
    normalized = "".join(char for char in text if not _is_ignorable(char))
    normalized = normalized.strip("：:,，。.!！?？、;；")
    if not normalized or normalized.upper() in _CONTENT_PLACEHOLDERS:
        return False
    if normalized in CLINICIAN_REPORT_NOUN_CONTINUATIONS:
        return False
    return any(
        unicodedata.category(char)[0] in {"L", "N"}
        for char in normalized
    )


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
    position = _consume_content_prefix(
        raw,
        feedback_object.end,
        segment.end,
    )
    command = _trim(raw, segment.start, feedback_object.end)
    content = _trim(raw, position, segment.end)
    if (
        content.start >= content.end
        or not _content_is_substantive(raw, content)
    ):
        return _WriteCandidate(
            segment_index=segment_index,
            provider=provider,
            content=None,
            command=None,
            status="missing_content",
        )
    if _span_is_question(raw, segment):
        return _WriteCandidate(
            segment_index=segment_index,
            provider=provider,
            content=content,
            command=None,
            status="question",
        )
    if _second_action_kind(raw, content) is not None:
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
    providers = _provider_matches(raw, segment)
    if not providers:
        return None
    predicates: list[tuple[_Span, str]] = []
    for surface in CLINICIAN_REPORT_PREDICATES:
        position = raw.find(surface, segment.start, segment.end)
        while position >= 0:
            predicates.append(
                (_Span(position, position + len(surface)), surface)
            )
            position = raw.find(
                surface,
                position + len(surface),
                segment.end,
            )
    predicates.sort(key=lambda item: (item[0].start, -len(item[1])))
    provider: _Span | None = None
    predicate: _Span | None = None
    for predicate_candidate, surface in predicates:
        clause_start = segment.start
        for boundary in _SOFT_BOUNDARIES:
            boundary_position = raw.rfind(
                boundary,
                segment.start,
                predicate_candidate.start,
            )
            clause_start = max(clause_start, boundary_position + 1)
        local_providers = tuple(
            match
            for match, _ in providers
            if clause_start <= match.start
            and match.end <= predicate_candidate.start
        )
        if not local_providers:
            continue
        if _predicate_is_record_noun(
            raw,
            surface,
            predicate_candidate.end,
            segment.end,
        ):
            continue
        provider = local_providers[-1]
        predicate = predicate_candidate
        break
    if provider is None or predicate is None:
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


def _report_followup_kind(
    raw: str,
    report: _Report,
) -> Literal["soft", "coordinated"] | None:
    if report.content is None:
        return None
    return _second_action_kind(raw, report.content)


def _report_contains_blocked_root(raw: str, report: _Report) -> bool:
    if report.content is None:
        return False
    text = raw[report.content.start : report.content.end]
    return any(root in text for root in _WRITE_ENVELOPE_BLOCKED_ROOTS)


def _standalone_legacy_provider(
    raw: str,
    segments: tuple[_Span, ...],
) -> _Span | None:
    if len(segments) != 1:
        return None
    segment = segments[0]
    root = _starts_with_term(
        raw,
        _LEGACY_OPERATION_ROOTS,
        position=segment.start,
        end=segment.end,
    )
    if root is None:
        return None
    position = _skip_spaces(raw, root[0].end, segment.end)
    provider_match = _starts_with_term(
        raw,
        CLINICIAN_PROVIDER_TERMS,
        position=position,
        end=segment.end,
    )
    if provider_match is None:
        return None
    provider, _ = provider_match
    position = _skip_spaces(raw, provider.end, segment.end)
    object_match = _starts_with_term(
        raw,
        _LEGACY_CLINICIAN_OBJECT_SUFFIXES,
        position=position,
        end=segment.end,
    )
    if object_match is None:
        return None
    object_span, _ = object_match
    if _skip_spaces(raw, object_span.end, segment.end) != segment.end:
        return None
    return provider


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

    legacy_provider = _standalone_legacy_provider(raw, segments)
    if legacy_provider is not None:
        return _decision(
            raw,
            kind="none",
            reason_code="legacy_clinician_record_operation",
            provider=legacy_provider,
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
        if candidate.status == "question":
            return _ambiguous_candidate(
                raw,
                candidate,
                reason_code="feedback_write_question",
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
            followup_kind = _report_followup_kind(raw, preceding_report)
            contains_blocked_root = _report_contains_blocked_root(
                raw,
                preceding_report,
            )
            if (
                _span_is_question(raw, segments[0])
                or followup_kind is not None
                or contains_blocked_root
            ):
                return _ambiguous_candidate(
                    raw,
                    candidate,
                    reason_code=(
                        "soft_boundary_followup"
                        if followup_kind == "soft"
                        and not contains_blocked_root
                        else "coordinated_clinician_action"
                    ),
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
        if len(segments) > 1:
            followup_kind = _report_followup_kind(raw, report)
            return _decision(
                raw,
                kind="ambiguous_clinician_action",
                reason_code=(
                    "soft_boundary_followup"
                    if followup_kind == "soft"
                    else "coordinated_clinician_action"
                ),
                provider=report.provider,
                content=report.content,
            )
        if _contains_question(raw):
            return _decision(
                raw,
                kind="clinician_advice",
                reason_code="clinician_question",
                provider=report.provider,
                content=report.content,
            )
        followup_kind = _report_followup_kind(raw, report)
        if followup_kind == "soft":
            return _decision(
                raw,
                kind="ambiguous_clinician_action",
                reason_code="soft_boundary_followup",
                provider=report.provider,
                content=report.content,
            )
        if followup_kind == "coordinated":
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
