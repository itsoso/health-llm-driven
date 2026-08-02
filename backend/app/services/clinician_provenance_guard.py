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
    CLAUSE_ACTION_NEGATIONS,
    CLINICIAN_BASIS_TERMS,
    CLINICIAN_CONTEXT_WRITE_ACTIONS,
    CLINICIAN_CONSULTATION_TERMS,
    CLINICIAN_FEEDBACK_OBJECT_NOUNS,
    CLINICIAN_FEEDBACK_WRITE_ROOTS,
    CLINICIAN_PROVIDER_TERMS,
    CLINICIAN_REPORT_NOUN_CONTINUATIONS,
    CLINICIAN_REPORT_PREDICATES,
    CLINICIAN_STRICT_COMMAND_PREFIXES,
    MEDIA_CREATE_ACTIONS,
    MUTATE_ACTIONS,
    PLAN_CREATE_ACTIONS,
    PLAN_UPDATE_ACTIONS,
    QUESTION_SIGNALS,
    READ_ACTIONS,
    REMINDER_CREATE_ACTIONS,
    WRITE_ACTIONS,
    WRITE_COMMAND_PREFIXES,
)

__all__ = ("ClinicianTurnDecision", "classify_clinician_turn")

DecisionKind: TypeAlias = Literal[
    "none",
    "clinician_context",
    "clinician_advice",
    "explicit_doctor_feedback_write",
    "ambiguous_clinician_action",
]

_HARD_BOUNDARIES = frozenset("。；;！!\n")
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
    "另外",
    "再",
    "还",
)
_ACTION_JOINER_CHARS = frozenset("且和与及并但")
_MUTATION_ACTION_ROOTS = tuple(
    root
    for roots in MUTATE_ACTIONS.values()
    for root in roots
)
# Deny-only union: these existing legacy roots can close an otherwise proven
# feedback-write envelope, but can never authorize or classify a general act.
_DENY_ONLY_ACTION_ROOTS = tuple(
    dict.fromkeys(
        (
            *READ_ACTIONS,
            *WRITE_ACTIONS,
            *_MUTATION_ACTION_ROOTS,
            *REMINDER_CREATE_ACTIONS,
            *PLAN_CREATE_ACTIONS,
            *PLAN_UPDATE_ACTIONS,
            *MEDIA_CREATE_ACTIONS,
            *CLINICIAN_CONTEXT_WRITE_ACTIONS,
        )
    )
)
_ACTION_PREFIX_WRAPPERS = tuple(
    sorted(
        {
            *WRITE_COMMAND_PREFIXES,
            *CLINICIAN_STRICT_COMMAND_PREFIXES,
            "还",
            "另外",
        },
        key=lambda term: (-len(term), term),
    )
)
_HIGH_RISK_MUTATION_ROOTS = _MUTATION_ACTION_ROOTS
_LOCAL_ADVICE_PREDICATES = tuple(
    predicate
    for predicate in CLINICIAN_REPORT_PREDICATES
    if predicate in {"建议", "嘱咐", "要求"}
)
_LOCAL_ADVICE_MODIFIERS = ("如果需要", "必要时", "可酌情")
# Local morphology only: bare 让/叫 must not become global report predicates.
_CLINICIAN_INSTRUCTION_PREDICATES = ("交代", "要求", "嘱咐", "让", "叫")
_CLINICIAN_INSTRUCTION_REPORT_BRIDGES = ("告诉", "说")
_CLINICIAN_INSTRUCTION_RECIPIENTS = ("患者", "病人", "家属", "我", "你")
_CLINICIAN_PROVIDER_OBJECT_MARKERS = ("请教", "对", "向", "给", "问", "让")
_LOCAL_ADVICE_CLAUSE_BOUNDARIES = tuple(
    dict.fromkeys((*_SOFT_BOUNDARIES, *_HARD_BOUNDARIES, "：", ":"))
)
_NOTIFICATION_NOUN_CONTINUATIONS = (
    "记录",
    "报告",
    "书",
    "文档",
    "档案",
    "清单",
    "列表",
)
_MEDICAL_ADVICE_TARGETS = (
    "训练",
    "运动",
    "锻炼",
    "负重",
    "姿势",
    "动作",
    "康复",
    "肌肉",
    "关节",
    "症状",
    "剂量",
    "疗程",
    "复查",
)
_PROVIDER_BASIS_RELATIONS = ("根据", "依据", "依照", "按照")
_BASIS_RISK_ANALYSIS_TERMS = ("风险", "副作用")
_BASIS_MEANING_ANALYSIS_TERMS = ("是什么意思", "什么意思", "含义")
_QUOTE_PAIRS = (
    ("“", "”"),
    ("「", "」"),
    ("『", "』"),
    ("《", "》"),
    ("〈", "〉"),
    ('"', '"'),
    ("'", "'"),
)
_GUARD_QUESTION_SIGNALS = tuple(
    dict.fromkeys((*QUESTION_SIGNALS, "会不会", "能不能", "会否"))
)
_REPORT_FILLERS = frozenset(" 是为：:，,")
_CONTENT_SEPARATORS = frozenset("：:,，")
_CONTENT_PLACEHOLDERS = frozenset(
    {"待补充", "待填写", "暂无", "未知", "不详", "无", "NA", "N/A"}
)
_NON_HUMAN_PROVIDER_PREFIXES = ("宠物", "动物", "兽")
_LEGACY_CLINICIAN_OBJECT_SUFFIXES = (
    "诊断记录",
    "诊断报告",
    "诊断书",
    "诊断文档",
    "诊断档案",
    "文档",
    "档案",
)
_PRE_NEGATION_MODIFIERS = ("暂时", "现在", "先")
_POST_NEGATION_WRAPPERS = ("帮我", "立即", "再")
_NONREPORT_RECORD_SUFFIXES = ("报告知情同意记录",)
_CANONICAL_SENSITIVE_TERMS = tuple(
    dict.fromkeys(
        (
            *CLINICIAN_PROVIDER_TERMS,
            *_DENY_ONLY_ACTION_ROOTS,
            *CLINICIAN_FEEDBACK_OBJECT_NOUNS,
            "建议",
        )
    )
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
        {
            "clinician_question",
            "clinician_consultation",
            "clinician_instruction",
        }
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
            "negated_clinician_action",
            "unresolved_clinician_action",
            "obfuscated_clinician_action",
            "clinician_basis_action_requires_separate_command",
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
        "negated",
    ]


@dataclass(frozen=True)
class _Report:
    segment_index: int
    provider: _Span
    predicate: _Span
    content: _Span | None


@dataclass(frozen=True)
class _Instruction:
    segment_index: int
    provider: _Span
    predicate: _Span
    content: _Span


@dataclass(frozen=True)
class _CanonicalClause:
    text: str
    raw_positions: tuple[int, ...]


@dataclass(frozen=True)
class _BasisMutationMatch:
    clause: _CanonicalClause
    basis_start: int
    basis_end: int
    mutation_start: int
    mutation_end: int


def _is_ignorable(char: str) -> bool:
    return char.isspace() or unicodedata.category(char) == "Cf"


def _is_question_punctuation(char: str) -> bool:
    compatible = unicodedata.normalize("NFKC", char)
    if "?" in compatible:
        return True
    return "QUESTION MARK" in unicodedata.name(char, "")


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
        if char not in _HARD_BOUNDARIES and not _is_question_punctuation(char):
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


def _strip_action_wrappers_from_end(
    raw: str,
    *,
    start: int,
    end: int,
) -> tuple[int, bool, bool]:
    position = end
    saw_wrapper = False
    saw_gap = False
    while position > start:
        gap_end = position
        position = _strip_ignorable_end(raw, start, position)
        saw_gap = saw_gap or position < gap_end
        matched = next(
            (
                wrapper
                for wrapper in _ACTION_PREFIX_WRAPPERS
                if position - len(wrapper) >= start
                and raw[position - len(wrapper) : position] == wrapper
            ),
            None,
        )
        if matched is None:
            break
        position -= len(matched)
        saw_wrapper = True
    return position, saw_wrapper, saw_gap


def _second_action_prefix_kind(
    raw: str,
    *,
    span_start: int,
    action_start: int,
) -> Literal["soft", "coordinated"] | None:
    prefix_end, wrapper_found, gap_found = _strip_action_wrappers_from_end(
        raw,
        start=span_start,
        end=action_start,
    )
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
    if wrapper_found or gap_found:
        return "coordinated"
    if last_char in _ACTION_JOINER_CHARS:
        return "coordinated"
    if any(prefix.endswith(joiner) for joiner in _ACTION_JOINER_SUFFIXES):
        return "coordinated"
    return None


def _skip_local_advice_fillers(raw: str, position: int, end: int) -> int:
    while position < end:
        char = raw[position]
        if _is_ignorable(char) or char in "的：:,，":
            position += 1
            continue
        break
    return position


def _skip_optional_local_advice_modifier(
    raw: str,
    position: int,
    end: int,
) -> int:
    position = _skip_local_advice_fillers(raw, position, end)
    modifier = _starts_with_term(
        raw,
        _LOCAL_ADVICE_MODIFIERS,
        position=position,
        end=end,
    )
    if modifier is None:
        return position
    return _skip_local_advice_fillers(raw, modifier[0].end, end)


def _provider_is_clause_head(
    raw: str,
    *,
    span: _Span,
    provider: _Span,
) -> bool:
    scope_start = span.start
    if provider.start < scope_start:
        scope_start = max(
            raw.rfind(boundary, 0, provider.start) + 1
            for boundary in _HARD_BOUNDARIES
        )

    marker_end = provider.start
    while marker_end > scope_start:
        char = raw[marker_end - 1]
        if _is_ignorable(char) or char in "：:,，":
            marker_end -= 1
            continue
        break
    if any(
        raw[max(scope_start, marker_end - len(marker)) : marker_end]
        == marker
        for marker in _CLINICIAN_PROVIDER_OBJECT_MARKERS
    ):
        return False

    content_head = _skip_local_advice_fillers(
        raw,
        scope_start,
        provider.start,
    )
    if content_head == provider.start:
        return True

    boundary_start = max(
        raw.rfind(boundary, scope_start, provider.start)
        for boundary in _LOCAL_ADVICE_CLAUSE_BOUNDARIES
    )
    if boundary_start < scope_start:
        return False
    clause_head = _skip_local_advice_fillers(
        raw,
        boundary_start + 1,
        provider.start,
    )
    return clause_head == provider.start


def _is_locally_proven_clinician_advice(
    raw: str,
    *,
    span: _Span,
    action_start: int,
    root: str,
) -> bool:
    if _local_basis_targets_action(
        raw,
        span=span,
        action_start=action_start,
        root=root,
    ):
        return True
    local_start = max(0, action_start - 24)
    local_span = _Span(local_start, action_start)
    for provider, _ in reversed(_provider_matches(raw, local_span)):
        if not _provider_is_clause_head(
            raw,
            span=span,
            provider=provider,
        ):
            continue
        position = _skip_local_advice_fillers(
            raw,
            provider.end,
            action_start,
        )
        predicate = _starts_with_term(
            raw,
            _LOCAL_ADVICE_PREDICATES,
            position=position,
            end=action_start,
        )
        if predicate is None:
            continue
        position = _skip_optional_local_advice_modifier(
            raw,
            predicate[0].end,
            action_start,
        )
        if position == action_start:
            return True

    position = _skip_local_advice_fillers(raw, span.start, action_start)
    predicate = _starts_with_term(
        raw,
        _LOCAL_ADVICE_PREDICATES,
        position=position,
        end=action_start,
    )
    if predicate is not None:
        position = _skip_optional_local_advice_modifier(
            raw,
            predicate[0].end,
            action_start,
        )
        target_window = raw[
            action_start + len(root) : min(span.end, action_start + len(root) + 12)
        ]
        if position == action_start and any(
            target in target_window for target in _MEDICAL_ADVICE_TARGETS
        ):
            return True
    return False


def _second_action_kind(
    raw: str,
    span: _Span,
) -> Literal["soft", "coordinated"] | None:
    best: tuple[int, Literal["soft", "coordinated"]] | None = None
    for root in _DENY_ONLY_ACTION_ROOTS:
        position = raw.find(root, span.start, span.end)
        while position >= 0:
            if root in _HIGH_RISK_MUTATION_ROOTS:
                if _is_locally_proven_clinician_advice(
                    raw,
                    span=span,
                    action_start=position,
                    root=root,
                ):
                    position = raw.find(
                        root,
                        position + len(root),
                        span.end,
                    )
                    continue
                kind: Literal["soft", "coordinated"] | None = "coordinated"
            else:
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
    normalized = unicodedata.normalize(
        "NFKC",
        "".join(char for char in text if not _is_ignorable(char)),
    )
    start = 0
    end = len(normalized)
    while (
        start < end
        and unicodedata.category(normalized[start])[0] in {"P", "S", "Z"}
    ):
        start += 1
    while (
        end > start
        and unicodedata.category(normalized[end - 1])[0] in {"P", "S", "Z"}
    ):
        end -= 1
    normalized = normalized[start:end]
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

    negation_position = position
    modifier = _starts_with_term(
        raw,
        _PRE_NEGATION_MODIFIERS,
        position=negation_position,
        end=segment.end,
    )
    if modifier is not None:
        negation_position = _skip_spaces(
            raw,
            modifier[0].end,
            segment.end,
        )
    negation = _starts_with_term(
        raw,
        CLAUSE_ACTION_NEGATIONS,
        position=negation_position,
        end=segment.end,
    )
    if negation is not None:
        position = _skip_spaces(raw, negation[0].end, segment.end)
        while True:
            wrapper = _starts_with_term(
                raw,
                _POST_NEGATION_WRAPPERS,
                position=position,
                end=segment.end,
            )
            if wrapper is None:
                break
            position = _skip_spaces(raw, wrapper[0].end, segment.end)

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
    if negation is not None:
        return _WriteCandidate(
            segment_index=segment_index,
            provider=provider,
            content=(
                content
                if content.start < content.end
                and _content_is_substantive(raw, content)
                else None
            ),
            command=None,
            status="negated",
        )
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
    continuations = (
        CLINICIAN_REPORT_NOUN_CONTINUATIONS
        if predicate == "诊断"
        else _NOTIFICATION_NOUN_CONTINUATIONS
        if predicate == "告知"
        else ()
    )
    if not continuations:
        return False
    position = _skip_spaces(raw, predicate_end, segment_end)
    return _starts_with_term(
        raw,
        continuations,
        position=position,
        end=segment_end,
    ) is not None


def _notification_report_content_start(
    raw: str,
    *,
    surface: str,
    provider: _Span,
    predicate: _Span,
    segment_end: int,
) -> int | None:
    if surface != "告知":
        return predicate.end

    possessive_start = _skip_spaces(raw, provider.end, predicate.start)
    if possessive_start < predicate.start and raw[possessive_start] == "的":
        possessive_end = _skip_spaces(
            raw,
            possessive_start + 1,
            predicate.start,
        )
        if possessive_end == predicate.start:
            return None

    relation_start = _skip_spaces(raw, predicate.end, segment_end)
    if relation_start >= segment_end or raw[relation_start] != "的":
        return predicate.end

    copula_start = _skip_spaces(raw, relation_start + 1, segment_end)
    if (
        copula_start >= segment_end
        or raw[copula_start] not in {"是", "为"}
    ):
        return None
    return copula_start + 1


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
    report_content_start: int | None = None
    for predicate_candidate, surface in predicates:
        local_providers = tuple(
            (match, content_start)
            for match, _ in providers
            if match.end <= predicate_candidate.start
            and _provider_is_clause_head(
                raw,
                span=segment,
                provider=match,
            )
            and _skip_local_advice_fillers(
                raw,
                match.end,
                predicate_candidate.start,
            )
            == predicate_candidate.start
            if (content_start := _notification_report_content_start(
                raw,
                surface=surface,
                provider=match,
                predicate=predicate_candidate,
                segment_end=segment.end,
            ))
            is not None
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
        provider, report_content_start = local_providers[-1]
        predicate = predicate_candidate
        break
    if (
        provider is None
        or predicate is None
        or report_content_start is None
    ):
        return None

    content_start = report_content_start
    while (
        content_start < segment.end
        and raw[content_start] in _REPORT_FILLERS
    ):
        content_start += 1
    content = _trim(raw, content_start, segment.end)
    return _Report(
        segment_index=segment_index,
        provider=provider,
        predicate=predicate,
        content=content if content.start < content.end else None,
    )


def _find_instruction(
    raw: str,
    segment: _Span,
    segment_index: int,
) -> _Instruction | None:
    def consume_recipient(position: int) -> tuple[int, bool]:
        recipient_match = _starts_with_term(
            raw,
            _CLINICIAN_INSTRUCTION_RECIPIENTS,
            position=position,
            end=segment.end,
        )
        if recipient_match is None:
            return position, False
        return (
            _skip_spaces(raw, recipient_match[0].end, segment.end),
            True,
        )

    def instruction_content(
        position: int,
        *,
        require_action_root: bool,
    ) -> _Span | None:
        command_prefix = _starts_with_term(
            raw,
            CLINICIAN_STRICT_COMMAND_PREFIXES,
            position=position,
            end=segment.end,
        )
        if command_prefix is not None:
            position = _skip_spaces(
                raw,
                command_prefix[0].end,
                segment.end,
            )
        content = _trim(raw, position, segment.end)
        if (
            content.start >= content.end
            or not _content_is_substantive(raw, content)
        ):
            return None
        if require_action_root and _starts_with_term(
            raw,
            _DENY_ONLY_ACTION_ROOTS,
            position=content.start,
            end=content.end,
        ) is None:
            return None
        return content

    for provider, _ in _provider_matches(raw, segment):
        if not _provider_is_clause_head(
            raw,
            span=segment,
            provider=provider,
        ):
            continue
        position = _skip_spaces(raw, provider.end, segment.end)
        predicate_match = _starts_with_term(
            raw,
            _CLINICIAN_INSTRUCTION_PREDICATES,
            position=position,
            end=segment.end,
        )
        if predicate_match is not None:
            predicate, _ = predicate_match
            content_start = _skip_spaces(
                raw,
                predicate.end,
                segment.end,
            )
            content_start, has_recipient = consume_recipient(content_start)
            content = instruction_content(
                content_start,
                require_action_root=not has_recipient,
            )
            if content is None:
                continue
            return _Instruction(
                segment_index=segment_index,
                provider=provider,
                predicate=predicate,
                content=content,
            )

        bridge_match = _starts_with_term(
            raw,
            _CLINICIAN_INSTRUCTION_REPORT_BRIDGES,
            position=position,
            end=segment.end,
        )
        if bridge_match is None:
            continue
        bridge, _ = bridge_match
        content_start = _skip_spaces(raw, bridge.end, segment.end)
        content_start, has_outer_recipient = consume_recipient(content_start)
        nested_predicate_match = _starts_with_term(
            raw,
            _CLINICIAN_INSTRUCTION_PREDICATES,
            position=content_start,
            end=segment.end,
        )
        predicate = bridge
        require_action_root = True
        if nested_predicate_match is not None:
            predicate, _ = nested_predicate_match
            content_start = _skip_spaces(
                raw,
                predicate.end,
                segment.end,
            )
            content_start, has_inner_recipient = consume_recipient(
                content_start
            )
            require_action_root = not (
                has_outer_recipient or has_inner_recipient
            )
        content = instruction_content(
            content_start,
            require_action_root=require_action_root,
        )
        if content is None:
            continue
        return _Instruction(
            segment_index=segment_index,
            provider=provider,
            predicate=predicate,
            content=content,
        )
    return None


def _contains_question(raw: str) -> bool:
    compatible = unicodedata.normalize("NFKC", raw)
    return (
        any(signal in compatible for signal in _GUARD_QUESTION_SIGNALS)
        or any(_is_question_punctuation(char) for char in raw)
    )


def _span_is_question(raw: str, span: _Span) -> bool:
    text = raw[span.start : span.end]
    return (
        _contains_question(text)
        or span.end < len(raw)
        and _is_question_punctuation(raw[span.end])
    )


def _report_followup_kind(
    raw: str,
    report: _Report,
) -> Literal["soft", "coordinated"] | None:
    if report.content is None:
        return None
    return _second_action_kind(raw, report.content)


def _report_has_soft_followup(raw: str, report: _Report) -> bool:
    if report.content is None:
        return False
    for root in _DENY_ONLY_ACTION_ROOTS:
        position = raw.find(root, report.content.start, report.content.end)
        while position >= 0:
            if _second_action_prefix_kind(
                raw,
                span_start=report.content.start,
                action_start=position,
            ) == "soft":
                return True
            position = raw.find(
                root,
                position + len(root),
                report.content.end,
            )
    return False


def _segment_starts_with_action(raw: str, segment: _Span) -> bool:
    position = _skip_spaces(raw, segment.start, segment.end)
    while position < segment.end:
        wrapper = _starts_with_term(
            raw,
            _ACTION_PREFIX_WRAPPERS,
            position=position,
            end=segment.end,
        )
        if wrapper is None:
            break
        position = _skip_spaces(raw, wrapper[0].end, segment.end)
    return _starts_with_term(
        raw,
        _DENY_ONLY_ACTION_ROOTS,
        position=position,
        end=segment.end,
    ) is not None


def _report_has_prefix_action(
    raw: str,
    segment: _Span,
    report: _Report,
) -> bool:
    prefix = _trim(raw, segment.start, report.provider.start)
    return (
        prefix.start < prefix.end
        and (
            _segment_starts_with_action(raw, prefix)
            or _second_action_kind(raw, prefix) is not None
        )
    )


def _turn_has_extra_action(
    raw: str,
    segments: tuple[_Span, ...],
    reports: tuple[_Report, ...],
) -> bool:
    report_indexes = {report.segment_index for report in reports}
    if any(_report_followup_kind(raw, report) is not None for report in reports):
        return True
    if any(
        _report_has_prefix_action(
            raw,
            segments[report.segment_index],
            report,
        )
        for report in reports
    ):
        return True
    return any(
        index not in report_indexes
        and _segment_starts_with_action(raw, segment)
        for index, segment in enumerate(segments)
    )


def _prefix_is_legacy_record_operation(raw: str, prefix: _Span) -> bool:
    if prefix.start >= prefix.end:
        return True
    position = prefix.start
    while position < prefix.end:
        wrapper = _starts_with_term(
            raw,
            _ACTION_PREFIX_WRAPPERS,
            position=position,
            end=prefix.end,
        )
        if wrapper is None:
            break
        position = _skip_spaces(raw, wrapper[0].end, prefix.end)
    operation = _starts_with_term(
        raw,
        (*READ_ACTIONS, *MUTATE_ACTIONS["delete"]),
        position=position,
        end=prefix.end,
    )
    return (
        operation is not None
        and _skip_spaces(raw, operation[0].end, prefix.end) == prefix.end
    )


def _standalone_record_noun_shape(
    raw: str,
    segments: tuple[_Span, ...],
) -> tuple[_Span, bool] | None:
    if len(segments) != 1:
        return None
    segment = segments[0]
    provider_match = _first_provider(raw, segment)
    if provider_match is None:
        return None
    provider, _ = provider_match
    prefix = _trim(raw, segment.start, provider.start)
    if not _prefix_is_legacy_record_operation(raw, prefix):
        return None
    position = _skip_spaces(raw, provider.end, segment.end)
    if position < segment.end and raw[position] == "的":
        position = _skip_spaces(raw, position + 1, segment.end)
    object_match = _starts_with_term(
        raw,
        _LEGACY_CLINICIAN_OBJECT_SUFFIXES,
        position=position,
        end=segment.end,
    )
    if object_match is None:
        return None
    object_span, _ = object_match
    tail = _trim(raw, object_span.end, segment.end)
    if tail.start >= tail.end:
        return provider, False
    if _segment_starts_with_action(raw, tail):
        return provider, True
    if not _contains_question(raw):
        return None
    return provider, False


def _standalone_nonreport_record_noun_provider(
    raw: str,
    segments: tuple[_Span, ...],
) -> _Span | None:
    """Preserve narrow legacy noun shapes rejected by report parsing."""

    if len(segments) != 1:
        return None
    segment = segments[0]
    provider_match = _first_provider(raw, segment)
    if provider_match is None:
        return None
    provider, _ = provider_match
    prefix = _trim(raw, segment.start, provider.start)
    if not _prefix_is_legacy_record_operation(raw, prefix):
        return None

    position = _skip_spaces(raw, provider.end, segment.end)
    if position < segment.end and raw[position] == "的":
        position = _skip_spaces(raw, position + 1, segment.end)

    notification = _starts_with_term(
        raw,
        ("告知",),
        position=position,
        end=segment.end,
    )
    if notification is not None:
        noun_start = _skip_spaces(raw, notification[0].end, segment.end)
        if noun_start < segment.end and raw[noun_start] == "的":
            noun_start = _skip_spaces(raw, noun_start + 1, segment.end)
        noun = _starts_with_term(
            raw,
            _NOTIFICATION_NOUN_CONTINUATIONS,
            position=noun_start,
            end=segment.end,
        )
        if (
            noun is not None
            and _trim(raw, noun[0].end, segment.end).start >= segment.end
        ):
            return provider

    suffix = _starts_with_term(
        raw,
        _NONREPORT_RECORD_SUFFIXES,
        position=position,
        end=segment.end,
    )
    if (
        suffix is not None
        and _trim(raw, suffix[0].end, segment.end).start >= segment.end
    ):
        return provider
    return None


def _turn_contains_deny_only_action(raw: str) -> bool:
    return any(root in raw for root in _DENY_ONLY_ACTION_ROOTS)


def _canonical_clauses(
    raw: str,
    *,
    excluded_spans: tuple[_Span, ...] = (),
) -> tuple[_CanonicalClause, ...]:
    """Build clause-local NFKC views without crossing hard boundaries.

    Punctuation and format separators may split a sensitive token, so they are
    omitted inside a clause.  Hard sentence boundaries and explicitly excluded
    authorization envelopes flush the view instead of being omitted.
    """

    exclusions = tuple(sorted(excluded_spans, key=lambda span: span.start))
    clauses: list[_CanonicalClause] = []
    chars: list[str] = []
    positions: list[int] = []

    def flush() -> None:
        if chars:
            clauses.append(
                _CanonicalClause(
                    text="".join(chars),
                    raw_positions=tuple(positions),
                )
            )
            chars.clear()
            positions.clear()

    position = 0
    exclusion_index = 0
    while position < len(raw):
        while (
            exclusion_index < len(exclusions)
            and exclusions[exclusion_index].end <= position
        ):
            exclusion_index += 1
        if exclusion_index < len(exclusions):
            exclusion = exclusions[exclusion_index]
            if exclusion.start <= position < exclusion.end:
                flush()
                position = exclusion.end
                continue

        compatible = unicodedata.normalize("NFKC", raw[position])
        for char in compatible:
            category = unicodedata.category(char)
            if char in _HARD_BOUNDARIES or _is_question_punctuation(char):
                flush()
            elif (
                char.isspace()
                or category in {"Cf", "Zs"}
                or category.startswith("P")
            ):
                continue
            else:
                chars.append(char)
                positions.append(position)
        position += 1
    flush()
    return tuple(clauses)


def _canonical_term_occurrences(
    clause: _CanonicalClause,
    term: str,
) -> tuple[int, ...]:
    positions: list[int] = []
    start = clause.text.find(term)
    while start >= 0:
        positions.append(start)
        start = clause.text.find(term, start + 1)
    return tuple(positions)


def _term_at(
    text: str,
    position: int,
    terms: tuple[str, ...],
) -> str | None:
    return next(
        (term for term in terms if text.startswith(term, position)),
        None,
    )


def _next_mutation(
    text: str,
    position: int,
) -> tuple[int, str] | None:
    candidates = [
        (found, -len(root), root)
        for root in _MUTATION_ACTION_ROOTS
        if (found := text.find(root, position)) >= 0
    ]
    if not candidates:
        return None
    found, _negative_length, root = min(candidates)
    return found, root


def _basis_mutation_matches(
    raw: str,
    *,
    excluded_spans: tuple[_Span, ...] = (),
) -> tuple[_BasisMutationMatch, ...]:
    matches: list[_BasisMutationMatch] = []
    seen: set[tuple[tuple[int, ...], int, int]] = set()

    def add_match(
        clause: _CanonicalClause,
        *,
        basis_start: int,
        basis_end: int,
    ) -> None:
        mutation = _next_mutation(clause.text, basis_end)
        if mutation is None:
            return
        mutation_start, root = mutation
        key = (clause.raw_positions, basis_start, mutation_start)
        if key in seen:
            return
        seen.add(key)
        matches.append(
            _BasisMutationMatch(
                clause=clause,
                basis_start=basis_start,
                basis_end=basis_end,
                mutation_start=mutation_start,
                mutation_end=mutation_start + len(root),
            )
        )

    for clause in _canonical_clauses(raw, excluded_spans=excluded_spans):
        text = clause.text
        for relation in _PROVIDER_BASIS_RELATIONS:
            for start in _canonical_term_occurrences(clause, relation):
                position = start + len(relation)
                provider = _term_at(
                    text,
                    position,
                    CLINICIAN_PROVIDER_TERMS,
                )
                if provider is None:
                    continue
                position += len(provider)
                feedback_object = _term_at(
                    text,
                    position,
                    (*CLINICIAN_FEEDBACK_OBJECT_NOUNS, "建议"),
                )
                if feedback_object is None:
                    continue
                add_match(
                    clause,
                    basis_start=start,
                    basis_end=position + len(feedback_object),
                )

        for basis in CLINICIAN_BASIS_TERMS:
            for start in _canonical_term_occurrences(clause, basis):
                add_match(
                    clause,
                    basis_start=start,
                    basis_end=start + len(basis),
                )
    return tuple(matches)


def _canonical_term_is_obfuscated(
    raw: str,
    clause: _CanonicalClause,
    term: str,
) -> bool:
    for start in _canonical_term_occurrences(clause, term):
        raw_start = clause.raw_positions[start]
        raw_end = clause.raw_positions[start + len(term) - 1] + 1
        if raw[raw_start:raw_end] != term:
            return True
    return False


def _has_obfuscated_clinician_action(raw: str) -> bool:
    """Detect compact-sensitive signals within one hard-boundary clause."""

    for clause in _canonical_clauses(raw):
        canonical = clause.text
        if not any(term in canonical for term in CLINICIAN_PROVIDER_TERMS):
            continue
        if not any(root in canonical for root in _DENY_ONLY_ACTION_ROOTS):
            continue
        if any(
            term in canonical
            and _canonical_term_is_obfuscated(raw, clause, term)
            for term in _CANONICAL_SENSITIVE_TERMS
        ):
            return True
    return False


def _has_anchored_clinician_basis_mutation(
    raw: str,
    *,
    excluded_spans: tuple[_Span, ...] = (),
) -> bool:
    """Return whether one clause contains a clinician-basis mutation."""

    return bool(
        _basis_mutation_matches(raw, excluded_spans=excluded_spans)
    )


def _matched_quote_spans(raw: str) -> tuple[_Span, ...]:
    spans: list[_Span] = []
    for opener, closer in _QUOTE_PAIRS:
        if opener == closer:
            open_position: int | None = None
            for position, char in enumerate(raw):
                if char != opener:
                    continue
                if open_position is None:
                    open_position = position
                else:
                    spans.append(_Span(open_position, position + 1))
                    open_position = None
            continue

        open_positions: list[int] = []
        for position, char in enumerate(raw):
            if char == opener:
                open_positions.append(position)
            elif char == closer and open_positions:
                spans.append(_Span(open_positions.pop(), position + 1))
    return tuple(sorted(spans, key=lambda span: (span.start, span.end)))


def _basis_match_quote_span(
    raw: str,
    match: _BasisMutationMatch,
) -> _Span | None:
    raw_start = match.clause.raw_positions[match.basis_start]
    raw_end = match.clause.raw_positions[match.mutation_end - 1] + 1
    return next(
        (
            span
            for span in _matched_quote_spans(raw)
            if span.start < raw_start and raw_end < span.end
        ),
        None,
    )


def _canonical_mutation_starts(clause: _CanonicalClause) -> frozenset[int]:
    starts: set[int] = set()
    for root in _MUTATION_ACTION_ROOTS:
        starts.update(_canonical_term_occurrences(clause, root))
    return frozenset(starts)


def _canonical_action_starts(clause: _CanonicalClause) -> frozenset[int]:
    starts: set[int] = set()
    for root in _DENY_ONLY_ACTION_ROOTS:
        starts.update(_canonical_term_occurrences(clause, root))
    return frozenset(starts)


def _basis_match_uses_punctuation_gap(
    raw: str,
    match: _BasisMutationMatch,
) -> bool:
    raw_start = match.clause.raw_positions[match.basis_start]
    raw_end = match.clause.raw_positions[match.mutation_end - 1] + 1
    return any(
        unicodedata.category(char).startswith("P")
        for char in raw[raw_start:raw_end]
    )


def _basis_analysis_reason(
    raw: str,
    matches: tuple[_BasisMutationMatch, ...],
) -> Literal["clinician_question", "clinician_consultation"] | None:
    """Recognize narrow epistemic uses without releasing action questions."""

    if len(_segments(raw)) != 1:
        return None
    has_question = _contains_question(raw)
    for match in matches:
        text = match.clause.text
        prefix = text[: match.basis_start]
        suffix = text[match.mutation_end :]
        mutation_starts = _canonical_mutation_starts(match.clause)
        mutation_count = len(mutation_starts)
        extra_action_starts = (
            _canonical_action_starts(match.clause) - mutation_starts
        )
        if (
            mutation_count == 1
            and not extra_action_starts
            and has_question
            and any(term in suffix for term in _BASIS_RISK_ANALYSIS_TERMS)
        ):
            return "clinician_question"
        if (
            mutation_count == 1
            and not extra_action_starts
            and has_question
            and "为什么" in prefix
        ):
            return "clinician_question"
        if (
            mutation_count == 2
            and not extra_action_starts
            and "比较" in prefix
            and any(term in suffix for term in _BASIS_RISK_ANALYSIS_TERMS)
            and any(joiner in suffix for joiner in ("和", "与", "跟", "相比"))
        ):
            return (
                "clinician_question"
                if has_question
                else "clinician_consultation"
            )
        quote_span = _basis_match_quote_span(raw, match)
        if mutation_count != 1 or quote_span is None:
            continue
        if any(
            not (
                quote_span.start
                < match.clause.raw_positions[action_start]
                < quote_span.end
            )
            for action_start in _canonical_action_starts(match.clause)
        ):
            continue
        if has_question and any(
            term in suffix for term in _BASIS_MEANING_ANALYSIS_TERMS
        ):
            return "clinician_question"
        if "搜索" in prefix and any(
            term in suffix for term in _BASIS_MEANING_ANALYSIS_TERMS
        ):
            return "clinician_consultation"
    return None


def _local_basis_targets_action(
    raw: str,
    *,
    span: _Span,
    action_start: int,
    root: str,
) -> bool:
    if root not in MUTATE_ACTIONS["update"]:
        return False
    matches: list[tuple[int, int]] = []
    for match in _basis_mutation_matches(raw):
        basis_raw_start = match.clause.raw_positions[match.basis_start]
        mutation_raw_start = match.clause.raw_positions[match.mutation_start]
        mutation_raw_end = match.clause.raw_positions[match.mutation_end - 1] + 1
        if (
            span.start <= basis_raw_start
            and mutation_raw_end <= span.end
        ):
            matches.append((basis_raw_start, mutation_raw_start))
    if not matches:
        return False
    first_basis_start = min(basis_start for basis_start, _ in matches)
    return any(
        basis_start == first_basis_start and mutation_start == action_start
        for basis_start, mutation_start in matches
    )


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
    candidates = tuple(
        candidate
        for index, segment in enumerate(segments)
        if (candidate := _parse_write_segment(raw, segment, index))
        is not None
    )
    basis_exclusions = tuple(
        candidate.content
        for candidate in candidates
        if candidate.status == "valid" and candidate.content is not None
    )
    basis_matches = _basis_mutation_matches(
        raw,
        excluded_spans=basis_exclusions,
    )
    basis_analysis_reason = _basis_analysis_reason(raw, basis_matches)
    obfuscated_action = _has_obfuscated_clinician_action(raw)
    compact_basis_without_punctuation = any(
        not _basis_match_uses_punctuation_gap(raw, match)
        for match in basis_matches
    )
    if obfuscated_action and not compact_basis_without_punctuation:
        return _decision(
            raw,
            kind="ambiguous_clinician_action",
            reason_code="obfuscated_clinician_action",
        )
    if basis_matches and basis_analysis_reason is None:
        return _decision(
            raw,
            kind="ambiguous_clinician_action",
            reason_code=(
                "clinician_basis_action_requires_separate_command"
            ),
        )
    if obfuscated_action:
        return _decision(
            raw,
            kind="ambiguous_clinician_action",
            reason_code="obfuscated_clinician_action",
        )

    whole = _Span(0, len(raw))
    first_provider_match = _first_provider(raw, whole)
    if first_provider_match is None:
        if basis_analysis_reason is not None:
            return _decision(
                raw,
                kind="clinician_advice",
                reason_code=basis_analysis_reason,
            )
        return _decision(
            raw,
            kind="none",
            reason_code="no_clinician_signal",
        )
    first_provider, _ = first_provider_match

    instructions = tuple(
        instruction
        for index, segment in enumerate(segments)
        if (
            instruction := _find_instruction(raw, segment, index)
        )
        is not None
    )
    instruction_indexes = {
        instruction.segment_index for instruction in instructions
    }
    reports = tuple(
        report
        for index, segment in enumerate(segments)
        if index not in instruction_indexes
        if (report := _find_report(raw, segment, index)) is not None
    )

    if not candidates and not reports:
        record_noun_shape = _standalone_record_noun_shape(raw, segments)
        if record_noun_shape is not None:
            legacy_provider, has_extra_action = record_noun_shape
            return _decision(
                raw,
                kind=(
                    "ambiguous_clinician_action"
                    if has_extra_action
                    else "none"
                ),
                reason_code=(
                    "coordinated_clinician_action"
                    if has_extra_action
                    else "legacy_clinician_record_operation"
                ),
                provider=legacy_provider,
            )
        nonreport_record_provider = _standalone_nonreport_record_noun_provider(
            raw,
            segments,
        )
        if nonreport_record_provider is not None:
            return _decision(
                raw,
                kind="none",
                reason_code="no_clinician_report",
                provider=nonreport_record_provider,
            )

    if len(candidates) > 1:
        return _ambiguous_candidate(
            raw,
            candidates[0],
            reason_code="coordinated_clinician_action",
        )
    if candidates:
        candidate = candidates[0]
        if candidate.status == "negated":
            return _ambiguous_candidate(
                raw,
                candidate,
                reason_code="negated_clinician_action",
            )
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
            prefix_action = _report_has_prefix_action(
                raw,
                segments[preceding_report.segment_index],
                preceding_report,
            )
            if (
                _span_is_question(raw, segments[0])
                or followup_kind is not None
                or prefix_action
            ):
                return _ambiguous_candidate(
                    raw,
                    candidate,
                    reason_code=(
                        "soft_boundary_followup"
                        if followup_kind == "soft"
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

    if instructions:
        instruction = instructions[0]
        if (
            len(instructions) > 1
            or len(segments) > 1
            or reports
            or _second_action_kind(raw, instruction.content) is not None
        ):
            return _decision(
                raw,
                kind="ambiguous_clinician_action",
                reason_code="coordinated_clinician_action",
                provider=instruction.provider,
                content=instruction.content,
            )
        return _decision(
            raw,
            kind="clinician_advice",
            reason_code=(
                "clinician_question"
                if _contains_question(raw)
                else "clinician_instruction"
            ),
            provider=instruction.provider,
            content=instruction.content,
        )

    if reports:
        report = reports[0]
        if _turn_has_extra_action(raw, segments, reports):
            followup_kind = next(
                (
                    kind
                    for item in reports
                    if (kind := _report_followup_kind(raw, item)) is not None
                ),
                None,
            )
            has_soft_followup = any(
                _report_has_soft_followup(raw, item) for item in reports
            )
            return _decision(
                raw,
                kind="ambiguous_clinician_action",
                reason_code=(
                    "soft_boundary_followup"
                    if followup_kind == "soft" or has_soft_followup
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
    if _turn_contains_deny_only_action(raw):
        return _decision(
            raw,
            kind="ambiguous_clinician_action",
            reason_code="unresolved_clinician_action",
            provider=first_provider,
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
