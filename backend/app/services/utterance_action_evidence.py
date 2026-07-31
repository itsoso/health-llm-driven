"""Typed primitives for deterministic action-evidence extraction.

This module preserves raw spans and clinician provenance per action
occurrence.  Authorization reduction and public intent mapping happen in
later integration layers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from app.services.utterance_intent_lexicon import (
    EVIDENCE_ACTION_LEXICON,
    EVIDENCE_ACTOR_TRANSITION_CUES,
    EVIDENCE_HARD_BOUNDARIES,
    EVIDENCE_NEGATION_CUES,
    EVIDENCE_NEGATION_EXCEPTION_CUES,
    EVIDENCE_QUESTION_CUES,
    EVIDENCE_QUOTE_PAIRS,
    EVIDENCE_STRICT_USER_COMMAND_CUES,
    EVIDENCE_USER_SUBJECT_CUES,
    MEDIA_TERMS,
    PLAN_TERMS,
    REMINDER_TERMS,
)

__all__ = (
    "ActionEvidence",
    "EvidenceParse",
    "ProviderEvidence",
    "parse_action_evidence",
)

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
CandidateActionKind: TypeAlias = ActionKind
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
_ACTION_VOCABULARY: tuple[
    tuple[str, frozenset[CandidateActionKind]], ...
] = tuple(
    (row.surface, row.allowed_families)
    for row in EVIDENCE_ACTION_LEXICON
)
_ACTION_SEPARATORS = (
    "然后",
    "随后",
    "接着",
    "但是",
    "不过",
    "可是",
    "并且",
    "同时",
    "但",
    "而",
    "后",
    "并",
    "，",
    ",",
    "。",
    "；",
    ";",
    "！",
    "!",
    "？",
    "?",
    "\n",
)
_NEGATIVE_MARKERS = tuple(cue.surface for cue in EVIDENCE_NEGATION_CUES)
_NEGATIVE_EXCEPTIONS = tuple(
    cue.surface for cue in EVIDENCE_NEGATION_EXCEPTION_CUES
)
_QUESTION_PREFIX_MARKERS = tuple(
    cue.surface
    for cue in EVIDENCE_QUESTION_CUES
    if cue.placement == "prefix"
)
_QUESTION_TERMINAL_MARKERS = tuple(
    cue.surface
    for cue in EVIDENCE_QUESTION_CUES
    if cue.placement == "terminal"
)
_STRICT_USER_AUTHORITY_CUES = tuple(
    cue.surface for cue in EVIDENCE_STRICT_USER_COMMAND_CUES
)
_EXPLICIT_USER_SUBJECT_CUES = tuple(
    cue.surface for cue in EVIDENCE_USER_SUBJECT_CUES
)
_USER_AUTHORITY_CUES = (
    *_EXPLICIT_USER_SUBJECT_CUES,
    *_STRICT_USER_AUTHORITY_CUES,
)
_ACTOR_TRANSITIONS = tuple(
    cue.surface for cue in EVIDENCE_ACTOR_TRANSITION_CUES
)
_ACTOR_HARD_BOUNDARIES = tuple(
    cue.surface for cue in EVIDENCE_HARD_BOUNDARIES
)
_HARD_SPEECH_RESETS = (*_ACTOR_HARD_BOUNDARIES, "？", "?")
_QUOTE_PAIRS = tuple(
    (pair.opener, pair.closer) for pair in EVIDENCE_QUOTE_PAIRS
)
_NESTED_REPORT_MARKERS = ("告诉", "表示", "要求", "让我", "称")
_NOMINAL_SPEECH_SUFFIXES = ("的内容", "的建议", "的话")
_BASE_TARGET_TERMS: tuple[tuple[str, TargetKind], ...] = (
    ("用药剂量", "medication"),
    ("用药记录", "medication"),
    ("药物", "medication"),
    ("用药", "medication"),
    ("每天腰痛情况", "symptom"),
    ("今天腰痛6分", "symptom"),
    ("今天腰痛", "symptom"),
    ("每天疼痛", "symptom"),
    ("每天腰痛", "symptom"),
    ("腰痛", "symptom"),
    ("疼痛", "symptom"),
    ("疼痛记录", "symptom"),
    ("体重71kg", "weight"),
    ("体重记录", "weight"),
    ("体重", "weight"),
    ("饮食记录", "diet"),
    ("饮食", "diet"),
    ("午餐", "diet"),
    ("康复图片", "media"),
    ("图片", "media"),
    ("复查提醒", "reminder"),
    ("提醒", "reminder"),
    ("康复计划", "plan"),
    ("计划", "plan"),
    ("健康数据", "health_record"),
    ("健康记录", "health_record"),
    ("运动记录", "health_record"),
    ("旧记录", "health_record"),
    ("昨天记录", "health_record"),
    ("医生诊断记录", "clinician_record"),
    ("诊断记录", "clinician_record"),
    ("医生说的内容", "clinician_content"),
    ("检查结果", "clinician_content"),
    ("诊断", "clinician_content"),
)
_TARGET_KIND_BY_TERM = dict(_BASE_TARGET_TERMS)
for _term in MEDIA_TERMS:
    _TARGET_KIND_BY_TERM.setdefault(_term, "media")
for _term in PLAN_TERMS:
    _TARGET_KIND_BY_TERM.setdefault(_term, "plan")
for _term in REMINDER_TERMS:
    _TARGET_KIND_BY_TERM.setdefault(_term, "reminder")
_TARGET_TERMS: tuple[tuple[str, TargetKind], ...] = tuple(
    sorted(
        _TARGET_KIND_BY_TERM.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )
)
_CREATE_FAMILIES = frozenset({"media", "plan", "reminder"})
_CLAUSE_SCOPE_BOUNDARIES = (
    *_HARD_SPEECH_RESETS,
    "，",
    ",",
    "然后",
    "随后",
    "接着",
    "但是",
    "不过",
    "可是",
    "现在",
    "但",
)
_COORDINATION_MARKERS = ("或者", "以及", "并且", "或", "和", "与", "及", "并", "、")
_COMPLETED_PREFIX_MARKERS = (
    "已经",
    "刚刚",
    "刚才",
    "早就",
    "之前",
    "曾经",
    "已",
    "刚",
)
_COMPLETED_SUFFIX_MARKERS = ("后的", "过的", "了的", "了", "过")
_RELATIVE_ACTION_SUFFIXES = ("后的", "过的", "了的", "的")
_BASIS_MODIFIER_END_MARKERS = (
    "生成的",
    "形成的",
    "提到的",
    "给出的",
    "提出的",
    "作出的",
)


@dataclass(frozen=True)
class _ActionCandidate:
    start: int
    end: int
    verb: str
    allowed_families: frozenset[CandidateActionKind]


@dataclass(frozen=True)
class _ResolvedActionCandidate:
    candidate: _ActionCandidate
    action: ActionKind
    target: TargetKind
    target_start: int
    target_end: int


@dataclass(frozen=True)
class _TargetMatch:
    target: TargetKind
    start: int
    end: int


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
    previous_end = 0
    for item in evidence:
        if item.start < previous_end:
            raise ValueError(
                f"{label} must be ordered and non-overlapping by raw span"
            )
        previous_end = item.end


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
    noun_start = content_start
    if text.startswith("的", noun_start):
        noun_start = _skip_whitespace_right(text, noun_start + len("的"))
    return not any(
        text.startswith(noun, noun_start)
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


def _scan_raw_action_candidates(
    text: str,
) -> tuple[_ActionCandidate, ...]:
    candidates: list[_ActionCandidate] = []
    cursor = 0
    while cursor < len(text):
        match = next(
            (
                (verb, allowed_families)
                for verb, allowed_families in _ACTION_VOCABULARY
                if text.startswith(verb, cursor)
            ),
            None,
        )
        if match is None:
            cursor += 1
            continue

        verb, allowed_families = match
        end = cursor + len(verb)
        candidates.append(
            _ActionCandidate(
                start=cursor,
                end=end,
                verb=verb,
                allowed_families=allowed_families,
            )
        )
        cursor = end
    return tuple(candidates)


def _region_start(text: str, position: int) -> int:
    start = 0
    for separator in _ACTION_SEPARATORS:
        index = text.rfind(separator, 0, position)
        if index >= 0:
            start = max(start, index + len(separator))
    return start


def _region_end(text: str, position: int) -> int:
    end = len(text)
    for separator in _ACTION_SEPARATORS:
        index = text.find(separator, position)
        if index >= 0:
            end = min(end, index)
    return end


def _scan_target_matches(
    text: str,
    *,
    start: int,
    end: int,
) -> tuple[_TargetMatch, ...]:
    matches: list[_TargetMatch] = []
    cursor = start
    while cursor < end:
        choices = tuple(
            (term, target)
            for term, target in _TARGET_TERMS
            if text.startswith(term, cursor, end)
        )
        if not choices:
            cursor += 1
            continue
        term, target = max(choices, key=lambda item: len(item[0]))
        target_end = cursor + len(term)
        matches.append(_TargetMatch(target, cursor, target_end))
        cursor = target_end
    return tuple(matches)


def _has_specific_target_after(
    text: str,
    candidate: _ActionCandidate,
    end: int,
) -> bool:
    return any(
        match.target not in {"clinician_content", "clinician_record"}
        for match in _scan_target_matches(
            text,
            start=candidate.end,
            end=end,
        )
    )


def _is_record_noun(
    text: str,
    candidate: _ActionCandidate,
    raw_candidates: tuple[_ActionCandidate, ...],
) -> bool:
    if candidate.verb != "记录":
        return False

    region_start = _region_start(text, candidate.start)
    region_end = _region_end(text, candidate.end)
    leading_text = text[region_start : candidate.start].strip()
    after = text[candidate.end : region_end].lstrip()

    targeting_action = any(
        other != candidate
        and other.start >= region_start
        and other.end <= region_end
        and bool(
            other.allowed_families
            & {"read", "save", "update", "delete", "sync", "advice"}
        )
        for other in raw_candidates
    )
    if targeting_action and leading_text:
        return True

    if after and _has_specific_target_after(text, candidate, region_end):
        return False
    explicit_leads = (
        _USER_AUTHORITY_CUES
        + _NEGATIVE_MARKERS
        + _QUESTION_PREFIX_MARKERS
        + ("让我", "叫我", "要求我", "希望我")
    )
    if any(leading_text.endswith(cue) for cue in explicit_leads):
        return False
    return bool(leading_text and not after)


def _is_attributive_creation(
    text: str,
    candidate: _ActionCandidate,
) -> bool:
    return (
        candidate.allowed_families <= _CREATE_FAMILIES
        and text.startswith("的", candidate.end)
    )


def _is_reminder_target_noun(
    text: str,
    candidate: _ActionCandidate,
    raw_candidates: tuple[_ActionCandidate, ...],
) -> bool:
    if candidate.verb not in REMINDER_TERMS:
        return False

    region_start = _region_start(text, candidate.start)
    region_end = _region_end(text, candidate.end)
    containing_target = next(
        (
            match
            for match in _scan_target_matches(
                text,
                start=region_start,
                end=region_end,
            )
            if match.target == "reminder"
            and match.start <= candidate.start
            and candidate.end <= match.end
        ),
        None,
    )
    if containing_target is None:
        return False
    return any(
        other != candidate
        and other.end <= containing_target.start
        and other.start >= region_start
        for other in raw_candidates
    )


def _scan_action_candidates(
    text: str,
) -> tuple[_ActionCandidate, ...]:
    raw_candidates = _scan_raw_action_candidates(text)
    return tuple(
        candidate
        for candidate in raw_candidates
        if not _is_record_noun(text, candidate, raw_candidates)
        and not _is_reminder_target_noun(text, candidate, raw_candidates)
        and not _is_attributive_creation(text, candidate)
    )


def _nearest_provider_before(
    candidate: _ActionCandidate,
    providers: tuple[ProviderEvidence, ...],
) -> ProviderEvidence | None:
    preceding = tuple(
        provider
        for provider in providers
        if provider.end <= candidate.start
    )
    return preceding[-1] if preceding else None


def _has_hard_speech_reset(text: str, *, start: int, end: int) -> bool:
    return any(
        text.find(boundary, start, end) >= 0
        for boundary in _HARD_SPEECH_RESETS
    )


def _quote_span_containing(text: str, position: int) -> tuple[int, int] | None:
    for opener, closer in _QUOTE_PAIRS:
        cursor = 0
        while cursor < len(text):
            quote_start = text.find(opener, cursor)
            if quote_start < 0:
                break
            quote_end = text.find(closer, quote_start + len(opener))
            if quote_end < 0:
                quote_end = len(text)
            if quote_start < position < quote_end:
                return quote_start, quote_end
            cursor = quote_end + len(closer)
    return None


def _has_nested_report_marker(text: str, *, start: int, end: int) -> bool:
    if any(
        text.find(marker, start, end) >= 0
        for marker in _NESTED_REPORT_MARKERS
    ):
        return True
    speech_start = text.find("说", start, end)
    while speech_start >= 0:
        suffix_start = _skip_whitespace_right(text, speech_start + len("说"))
        if not any(
            text.startswith(suffix, suffix_start, end)
            for suffix in _NOMINAL_SPEECH_SUFFIXES
        ):
            return True
        speech_start = text.find("说", speech_start + len("说"), end)
    return False


def _has_quoted_report_marker(text: str, *, start: int, end: int) -> bool:
    return any(
        text.find(marker, start, end) >= 0
        for marker in _REPORT_MARKERS
    )


def _provider_owns_quote(
    text: str,
    quote_span: tuple[int, int],
    providers: tuple[ProviderEvidence, ...],
) -> bool:
    quote_start, _quote_end = quote_span
    provider = next(
        (
            item
            for item in reversed(providers)
            if item.end <= quote_start
        ),
        None,
    )
    return provider is not None and (
        provider.relation == "report"
        or _has_quoted_report_marker(
            text,
            start=provider.end,
            end=quote_start,
        )
    )


def _latest_top_level_transition_end(
    text: str,
    *,
    start: int,
    end: int,
) -> int:
    latest = -1
    for marker in (*_ACTOR_TRANSITIONS, *_ACTOR_HARD_BOUNDARIES):
        cursor = text.find(marker, start, end)
        while cursor >= 0:
            if _quote_span_containing(text, cursor) is None:
                latest = max(latest, cursor + len(marker))
            cursor = text.find(marker, cursor + len(marker), end)
    return latest


def _has_user_cue_after_transition(
    text: str,
    *,
    start: int,
    end: int,
) -> bool:
    transition_end = _latest_top_level_transition_end(
        text,
        start=start,
        end=end,
    )
    if transition_end < 0:
        return False
    return any(
        text.find(cue, transition_end, end) >= 0
        for cue in (
            *_STRICT_USER_AUTHORITY_CUES,
            *_EXPLICIT_USER_SUBJECT_CUES,
        )
    )


def _assign_actors(
    text: str,
    providers: tuple[ProviderEvidence, ...],
    candidates: tuple[_ActionCandidate, ...],
) -> tuple[ActorKind, ...]:
    actors: list[ActorKind] = []
    active_provider: ProviderEvidence | None = None
    report_scope_active = False
    report_action_count = 0
    previous_report_action_end = 0
    provider_index = 0
    provider: ProviderEvidence | None = None

    for candidate in candidates:
        while (
            provider_index < len(providers)
            and providers[provider_index].end <= candidate.start
        ):
            provider = providers[provider_index]
            provider_index += 1
        if provider != active_provider:
            active_provider = provider
            report_scope_active = bool(
                provider is not None and provider.relation == "report"
            )
            report_action_count = 0
            previous_report_action_end = provider.end if provider else 0

        quote_span = _quote_span_containing(text, candidate.start)
        if quote_span is not None and _provider_owns_quote(
            text,
            quote_span,
            providers,
        ):
            actor: ActorKind = "clinician"
            if report_scope_active:
                report_action_count += 1
                previous_report_action_end = candidate.end
            actors.append(actor)
            continue

        if provider is None:
            actors.append("user")
            continue

        if provider.relation == "basis":
            actor = (
                "clinician"
                if _has_nested_report_marker(
                    text,
                    start=provider.end,
                    end=candidate.start,
                )
                else "user"
            )
            actors.append(actor)
            continue

        if report_scope_active:
            may_switch = (
                report_action_count > 0
                and _has_user_cue_after_transition(
                    text,
                    start=previous_report_action_end,
                    end=candidate.start,
                )
            )
            if may_switch:
                report_scope_active = False
                actors.append("user")
                continue
            actors.append("clinician")
            report_action_count += 1
            previous_report_action_end = candidate.end
            continue

        actors.append("ambiguous" if provider.relation == "unresolved" else "user")

    return tuple(actors)


def _resolve_target(
    text: str,
    candidate: _ActionCandidate,
    candidate_index: int,
    candidates: tuple[_ActionCandidate, ...],
    providers: tuple[ProviderEvidence, ...],
) -> tuple[TargetKind, int, int]:
    next_candidate = (
        candidates[candidate_index + 1]
        if candidate_index + 1 < len(candidates)
        else None
    )
    next_is_relative = (
        next_candidate is not None
        and any(
            text.startswith(marker, next_candidate.end)
            for marker in _RELATIVE_ACTION_SUFFIXES
        )
    )
    next_start = (
        len(text)
        if next_candidate is None or next_is_relative
        else next_candidate.start
    )
    forward_end = min(next_start, _region_end(text, candidate.end))
    forward = _scan_target_matches(
        text,
        start=candidate.end,
        end=forward_end,
    )
    if forward:
        return _resolve_target_matches(
            text,
            candidate,
            forward,
            providers,
        )

    previous_end = (
        candidates[candidate_index - 1].end
        if candidate_index > 0
        else 0
    )
    backward_start = max(
        previous_end,
        _region_start(text, candidate.start),
    )
    backward = _scan_target_matches(
        text,
        start=backward_start,
        end=candidate.start,
    )
    if backward:
        return _resolve_target_matches(
            text,
            candidate,
            backward,
            providers,
        )
    return "unknown", candidate.end, candidate.end


def _is_provider_modifier_target(
    text: str,
    match: _TargetMatch,
    providers: tuple[ProviderEvidence, ...],
) -> bool:
    if match.target not in {"clinician_content", "clinician_record"}:
        return False
    for provider in providers:
        if provider.relation == "unresolved":
            continue
        if provider.start > match.start or provider.end > match.end:
            continue
        if not _has_hard_speech_reset(
            text,
            start=provider.end,
            end=match.end,
        ):
            return True
    return False


def _basis_modifier_spans(
    text: str,
    providers: tuple[ProviderEvidence, ...],
) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    for provider in providers:
        if provider.relation != "basis":
            continue
        before_provider = _skip_whitespace_left(text, provider.start)
        span_start = next(
            (
                before_provider - len(marker)
                for marker in _BASIS_MARKERS
                if before_provider >= len(marker)
                and text.startswith(
                    marker,
                    before_provider - len(marker),
                    before_provider,
                )
            ),
            provider.start,
        )
        scope_end = _clause_scope_end(text, provider.end)
        terminal_matches = tuple(
            (text.find(marker, provider.end, scope_end), marker)
            for marker in _BASIS_MODIFIER_END_MARKERS
        )
        valid_matches = tuple(
            item for item in terminal_matches if item[0] >= 0
        )
        if not valid_matches:
            continue
        terminal_start, terminal = min(
            valid_matches,
            key=lambda item: item[0],
        )
        spans.append(
            (span_start, terminal_start + len(terminal))
        )
    return tuple(spans)


def _inside_any_span(
    match: _TargetMatch,
    spans: tuple[tuple[int, int], ...],
) -> bool:
    return any(
        start <= match.start and match.end <= end
        for start, end in spans
    )


def _resolve_target_matches(
    text: str,
    candidate: _ActionCandidate,
    matches: tuple[_TargetMatch, ...],
    providers: tuple[ProviderEvidence, ...],
) -> tuple[TargetKind, int, int]:
    modifier_spans = _basis_modifier_spans(text, providers)
    scoped_matches = tuple(
        match
        for match in matches
        if not _inside_any_span(match, modifier_spans)
    )
    has_actual_target = any(
        match.target not in {"clinician_content", "clinician_record"}
        for match in scoped_matches
    )
    filtered = tuple(
        match
        for match in scoped_matches
        if not (
            has_actual_target
            and _is_provider_modifier_target(text, match, providers)
        )
    )
    if not filtered:
        return "unknown", candidate.end, candidate.end
    target_kinds = {match.target for match in filtered}
    if len(target_kinds) != 1:
        return "unknown", candidate.end, candidate.end

    if candidate.end <= filtered[0].start:
        chosen = min(
            filtered,
            key=lambda match: (match.start - candidate.end, -match.end),
        )
    else:
        chosen = min(
            filtered,
            key=lambda match: (candidate.start - match.end, match.start),
        )
    return chosen.target, chosen.start, chosen.end


def _hard_scope_start(text: str, position: int) -> int:
    start = 0
    for boundary in _HARD_SPEECH_RESETS:
        index = text.rfind(boundary, 0, position)
        if index >= 0:
            start = max(start, index + len(boundary))
    return start


def _hard_scope_end(text: str, position: int) -> int:
    end = len(text)
    for boundary in _HARD_SPEECH_RESETS:
        index = text.find(boundary, position)
        if index >= 0:
            end = min(end, index + len(boundary))
    return end


def _clause_scope_start(text: str, position: int) -> int:
    start = 0
    for boundary in _CLAUSE_SCOPE_BOUNDARIES:
        index = text.rfind(boundary, 0, position)
        if index >= 0:
            start = max(start, index + len(boundary))
    return start


def _clause_scope_end(text: str, position: int) -> int:
    end = len(text)
    for boundary in _CLAUSE_SCOPE_BOUNDARIES:
        index = text.find(boundary, position)
        if index >= 0:
            end = min(end, index + len(boundary))
    return end


def _is_question_scope(text: str, candidate: _ActionCandidate) -> bool:
    start = _clause_scope_start(text, candidate.start)
    end = _clause_scope_end(text, candidate.end)
    scope = text[start:end]
    prefix = text[start : candidate.start]
    normalized_scope = scope.rstrip("？?")
    return (
        any(marker in prefix for marker in _QUESTION_PREFIX_MARKERS)
        or any(
            normalized_scope.endswith(marker)
            for marker in _QUESTION_TERMINAL_MARKERS
            if marker not in {"？", "?"}
        )
        or scope.endswith(("？", "?"))
    )


def _is_coordinated_with_previous(
    text: str,
    candidate_index: int,
    candidates: tuple[_ActionCandidate, ...],
) -> bool:
    if candidate_index == 0:
        return False
    previous = candidates[candidate_index - 1]
    candidate = candidates[candidate_index]
    bridge = text[previous.end : candidate.start]
    if any(boundary in bridge for boundary in _CLAUSE_SCOPE_BOUNDARIES):
        return False
    return any(marker in bridge for marker in _COORDINATION_MARKERS)


def _occurrence_prefix_start(
    text: str,
    candidate: _ActionCandidate,
    candidate_index: int,
    candidates: tuple[_ActionCandidate, ...],
) -> int:
    previous_end = (
        candidates[candidate_index - 1].end
        if candidate_index > 0
        else 0
    )
    clause_start = _clause_scope_start(text, candidate.start)
    if _is_coordinated_with_previous(text, candidate_index, candidates):
        return clause_start
    return max(previous_end, clause_start)


def _resolve_polarity(
    text: str,
    candidate: _ActionCandidate,
    candidate_index: int,
    candidates: tuple[_ActionCandidate, ...],
) -> PolarityKind:
    prefix_start = _occurrence_prefix_start(
        text,
        candidate,
        candidate_index,
        candidates,
    )
    if _has_negative_evidence(
        text,
        start=prefix_start,
        end=candidate.start,
    ):
        return "negative"
    return "positive"


def _has_negative_evidence(text: str, *, start: int, end: int) -> bool:
    exception_spans: list[tuple[int, int]] = []
    for exception in _NEGATIVE_EXCEPTIONS:
        exception_start = text.find(exception, start, end)
        while exception_start >= 0:
            exception_spans.append(
                (exception_start, exception_start + len(exception))
            )
            exception_start = text.find(
                exception,
                exception_start + len(exception),
                end,
            )

    for marker in _NEGATIVE_MARKERS:
        cursor = text.find(marker, start, end)
        while cursor >= 0:
            is_question_compound = (
                marker.startswith("不要")
                and cursor > start
                and text[cursor - 1] == "要"
            )
            is_exception = any(
                exception_start <= cursor < exception_end
                for exception_start, exception_end in exception_spans
            )
            if not is_question_compound and not is_exception:
                return True
            cursor = text.find(marker, cursor + len(marker), end)
    return False


def _resolve_modality(
    text: str,
    candidate: _ActionCandidate,
    candidate_index: int,
    candidates: tuple[_ActionCandidate, ...],
) -> ModalityKind:
    if _is_question_scope(text, candidate):
        return "question"
    scope_start = _clause_scope_start(text, candidate.start)
    scope_end = _clause_scope_end(text, candidate.end)
    prefix = text[scope_start : candidate.start]
    suffix_end = (
        candidates[candidate_index + 1].start
        if candidate_index + 1 < len(candidates)
        else scope_end
    )
    suffix = text[candidate.end:suffix_end]
    if any(
        text.startswith(marker, candidate.end)
        for marker in _RELATIVE_ACTION_SUFFIXES
    ):
        return "statement"
    if any(
        text.startswith(marker, candidate.end)
        for marker in _COMPLETED_SUFFIX_MARKERS
    ):
        return "statement"
    if any(marker in prefix for marker in _COMPLETED_PREFIX_MARKERS):
        return "statement"
    if "昨天" in prefix and ("过" in suffix or "了" in suffix):
        return "statement"
    return "command"


def _provenance(
    actor: ActorKind,
    candidate: _ActionCandidate,
    providers: tuple[ProviderEvidence, ...],
) -> str:
    if actor == "clinician":
        return "clinician_reported_action"
    if actor == "ambiguous":
        return "ambiguous_clinician_context"
    provider = _nearest_provider_before(candidate, providers)
    if provider is not None and provider.relation == "basis":
        return "clinician_basis_user_action"
    return "explicit_user_action"


def _resolve_action_kind(
    candidate: _ActionCandidate,
    target: TargetKind,
) -> ActionKind | None:
    create_families = candidate.allowed_families & _CREATE_FAMILIES
    if target in _CREATE_FAMILIES:
        if target in create_families:
            return target
        if create_families:
            return None

    non_create_families = candidate.allowed_families - _CREATE_FAMILIES
    if len(non_create_families) == 1:
        return next(iter(non_create_families))
    return None


def _scan_actions(
    text: str,
    providers: tuple[ProviderEvidence, ...],
) -> tuple[ActionEvidence, ...]:
    raw_candidates = _scan_action_candidates(text)
    resolved_candidates: list[_ResolvedActionCandidate] = []
    for candidate_index, candidate in enumerate(raw_candidates):
        target, target_start, target_end = _resolve_target(
            text,
            candidate,
            candidate_index,
            raw_candidates,
            providers,
        )
        action_kind = _resolve_action_kind(candidate, target)
        if action_kind is None:
            continue
        resolved_candidates.append(
            _ResolvedActionCandidate(
                candidate=candidate,
                action=action_kind,
                target=target,
                target_start=target_start,
                target_end=target_end,
            )
        )

    candidates = tuple(item.candidate for item in resolved_candidates)
    actors = _assign_actors(text, providers, candidates)
    actions: list[ActionEvidence] = []
    for candidate_index, resolved in enumerate(resolved_candidates):
        candidate = resolved.candidate
        actor = actors[candidate_index]
        actions.append(
            ActionEvidence(
                start=candidate.start,
                end=candidate.end,
                action=resolved.action,
                actor=actor,
                target=resolved.target,
                target_start=resolved.target_start,
                target_end=resolved.target_end,
                polarity=_resolve_polarity(
                    text,
                    candidate,
                    candidate_index,
                    candidates,
                ),
                modality=_resolve_modality(
                    text,
                    candidate,
                    candidate_index,
                    candidates,
                ),
                provenance=_provenance(actor, candidate, providers),
            )
        )
    return tuple(actions)


def parse_action_evidence(text: str) -> EvidenceParse:
    """Return ordered raw evidence without reducing authorization state."""

    providers = _scan_providers(text)
    return EvidenceParse(
        text=text,
        clinician_bearing=bool(providers),
        providers=providers,
        actions=_scan_actions(text, providers),
    )
