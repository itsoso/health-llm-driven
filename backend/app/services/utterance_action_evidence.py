"""Authorization-grade action evidence extracted from one lexical scan.

The parser is intentionally deterministic and fail closed.  It preserves raw
offsets, represents ownership and command proof separately, and never treats
an unrecognised prefix as an imperative.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Literal, TypeAlias

from app.services.utterance_intent_lexicon import (
    EVIDENCE_ACTION_LEXICON,
    EVIDENCE_ACTOR_TRANSITION_CUES,
    EVIDENCE_BA_PARTICLE_CHARS,
    EVIDENCE_GROUP_BOUNDARIES,
    EVIDENCE_HARD_BOUNDARIES,
    EVIDENCE_PROVIDER_LEXICON,
    EVIDENCE_QUOTE_PAIRS,
    EVIDENCE_RELATION_LEXICON,
    EVIDENCE_REPORT_FILLER_CHARS,
    EVIDENCE_REPORT_NOUN_CONTINUATIONS,
    EVIDENCE_SOFT_CONJUNCTIONS,
    EVIDENCE_STANCE_LEXICON,
    EVIDENCE_TARGET_LEXICON,
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
ActorKind: TypeAlias = Literal["user", "clinician", "ambiguous"]
PolarityKind: TypeAlias = Literal["positive", "negative"]
ModalityKind: TypeAlias = Literal[
    "command",
    "question",
    "statement",
    "unknown",
]
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
_EventKind: TypeAlias = Literal[
    "action",
    "provider",
    "relation",
    "target",
    "stance",
    "boundary",
    "conjunction",
    "quote_open",
    "quote_close",
    "quote_toggle",
    "structure",
]
_ActionRole: TypeAlias = Literal[
    "governor",
    "coordinated",
    "embedded",
    "noun",
]


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
            raise ValueError("clinician_bearing must equal bool(providers)")
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


@dataclass(frozen=True)
class _Lexeme:
    surface: str
    kind: _EventKind
    value: str
    allowed_families: frozenset[ActionKind] = frozenset()


@dataclass(frozen=True)
class _LexEvent:
    start: int
    end: int
    kind: _EventKind
    surface: str
    value: str
    allowed_families: frozenset[ActionKind] = frozenset()


@dataclass(frozen=True)
class _LexicalIndex:
    text: str
    events: tuple[_LexEvent, ...]
    actions: tuple[_LexEvent, ...]
    providers: tuple[_LexEvent, ...]
    relations: tuple[_LexEvent, ...]
    targets: tuple[_LexEvent, ...]
    stances: tuple[_LexEvent, ...]
    boundaries: tuple[_LexEvent, ...]
    conjunctions: tuple[_LexEvent, ...]
    quotes: tuple[_LexEvent, ...]
    structures: tuple[_LexEvent, ...]
    scanner_runs: int
    lexical_work_units: int
    work_units: int


@dataclass
class _WorkMeter:
    units: int


_ACTIVE_WORK_METER: ContextVar[_WorkMeter | None] = ContextVar(
    "utterance_action_evidence_work_meter",
    default=None,
)


def _work(units: int = 1) -> None:
    meter = _ACTIVE_WORK_METER.get()
    if meter is not None:
        meter.units += units


@dataclass(frozen=True)
class _QuoteScope:
    scope_id: int
    start: int
    content_start: int
    content_end: int
    end: int
    depth: int
    closed: bool


@dataclass(frozen=True)
class _ReportScope:
    scope_id: int
    provider_index: int
    start: int
    end: int


@dataclass(frozen=True)
class _ActionDraft:
    event: _LexEvent
    role: _ActionRole
    group: int
    ordinal: int = 0
    group_start: int = 0
    group_end: int = 0
    group_first_ordinal: int = 0
    group_end_ordinal: int = 0
    previous_top_level_ordinal: int | None = None
    next_top_level_ordinal: int | None = None


@dataclass(frozen=True)
class _CommandProof:
    shape: str
    start: int
    end: int
    complete: bool


@dataclass(frozen=True)
class _TargetResolution:
    target: TargetKind
    start: int
    end: int
    observed_targets: frozenset[TargetKind]
    conflicted: bool


@dataclass(frozen=True)
class _ResolvedDraft:
    draft: _ActionDraft
    action: ActionKind
    target: _TargetResolution
    proof: _CommandProof


_ACTION_VOCABULARY = tuple(
    (row.surface, row.allowed_families)
    for row in EVIDENCE_ACTION_LEXICON
)
_CREATE_FAMILIES = frozenset({"media", "plan", "reminder"})
_HARD_BOUNDARY_SURFACES = frozenset(
    cue.surface for cue in EVIDENCE_HARD_BOUNDARIES
)
_ACTOR_TRANSITION_SURFACES = frozenset(
    cue.surface for cue in EVIDENCE_ACTOR_TRANSITION_CUES
)
_GROUP_BOUNDARY_SURFACES = frozenset(EVIDENCE_GROUP_BOUNDARIES)
_COORDINATION_SURFACES = frozenset(EVIDENCE_SOFT_CONJUNCTIONS)
_MAX_PROVIDER_SURFACE_LENGTH = max(
    len(row.surface) for row in EVIDENCE_PROVIDER_LEXICON
)
_MAX_TARGET_SURFACE_LENGTH = max(
    len(row.surface) for row in EVIDENCE_TARGET_LEXICON
)


def _all_lexemes() -> tuple[_Lexeme, ...]:
    lexemes: list[_Lexeme] = []
    lexemes.extend(
        _Lexeme(
            row.surface,
            "action",
            row.surface,
            row.allowed_families,
        )
        for row in EVIDENCE_ACTION_LEXICON
    )
    lexemes.extend(
        _Lexeme(row.surface, "provider", row.surface)
        for row in EVIDENCE_PROVIDER_LEXICON
    )
    lexemes.extend(
        _Lexeme(row.surface, "relation", row.relation)
        for row in EVIDENCE_RELATION_LEXICON
    )
    lexemes.extend(
        _Lexeme(row.surface, "target", row.target)
        for row in EVIDENCE_TARGET_LEXICON
    )
    lexemes.extend(
        _Lexeme(row.surface, "stance", row.kind)
        for row in EVIDENCE_STANCE_LEXICON
    )
    lexemes.extend(
        _Lexeme(surface, "boundary", surface)
        for surface in EVIDENCE_GROUP_BOUNDARIES
    )
    lexemes.extend(
        _Lexeme(surface, "conjunction", surface)
        for surface in EVIDENCE_SOFT_CONJUNCTIONS
    )
    for pair_index, pair in enumerate(EVIDENCE_QUOTE_PAIRS):
        if pair.opener == pair.closer:
            lexemes.append(
                _Lexeme(pair.opener, "quote_toggle", str(pair_index))
            )
        else:
            lexemes.append(
                _Lexeme(pair.opener, "quote_open", str(pair_index))
            )
            lexemes.append(
                _Lexeme(pair.closer, "quote_close", str(pair_index))
            )
    lexemes.extend(
        _Lexeme(surface, "structure", surface)
        for surface in ("把", "的", "前", "以前", "之前", "任何")
    )
    unique: dict[tuple[str, _EventKind, str], _Lexeme] = {}
    for lexeme in lexemes:
        key = (lexeme.surface, lexeme.kind, lexeme.value)
        unique[key] = lexeme
    return tuple(unique.values())


_LEXEMES = _all_lexemes()
_LEXEMES_BY_FIRST: dict[str, tuple[_Lexeme, ...]] = {}
for _lexeme in _LEXEMES:
    _LEXEMES_BY_FIRST.setdefault(_lexeme.surface[0], ())
    _LEXEMES_BY_FIRST[_lexeme.surface[0]] += (_lexeme,)
for _first, _rows in tuple(_LEXEMES_BY_FIRST.items()):
    _LEXEMES_BY_FIRST[_first] = tuple(
        sorted(_rows, key=lambda row: (-len(row.surface), row.kind, row.value))
    )


def _lexical_scan(text: str) -> _LexicalIndex:
    events: list[_LexEvent] = []
    work_units = 0
    for cursor, char in enumerate(text):
        rows = _LEXEMES_BY_FIRST.get(char, ())
        longest_by_kind: dict[_EventKind, _Lexeme] = {}
        for row in rows:
            work_units += 1
            if not text.startswith(row.surface, cursor):
                continue
            existing = longest_by_kind.get(row.kind)
            if existing is None or len(row.surface) > len(existing.surface):
                longest_by_kind[row.kind] = row
        for row in longest_by_kind.values():
            events.append(
                _LexEvent(
                    start=cursor,
                    end=cursor + len(row.surface),
                    kind=row.kind,
                    surface=row.surface,
                    value=row.value,
                    allowed_families=row.allowed_families,
                )
            )
    ordered = tuple(
        sorted(events, key=lambda event: (event.start, event.end, event.kind))
    )

    def select(kind: _EventKind) -> tuple[_LexEvent, ...]:
        return tuple(event for event in ordered if event.kind == kind)

    quote_kinds = {"quote_open", "quote_close", "quote_toggle"}
    return _LexicalIndex(
        text=text,
        events=ordered,
        actions=_prune_overlapping_events(select("action")),
        providers=_prune_overlapping_events(select("provider")),
        relations=select("relation"),
        targets=_prune_contained_targets(select("target")),
        stances=_prune_shadowed_stances(select("stance")),
        boundaries=select("boundary"),
        conjunctions=select("conjunction"),
        quotes=tuple(event for event in ordered if event.kind in quote_kinds),
        structures=select("structure"),
        scanner_runs=1,
        lexical_work_units=work_units + len(ordered),
        work_units=work_units + len(ordered),
    )


def _prune_overlapping_events(
    events: tuple[_LexEvent, ...],
) -> tuple[_LexEvent, ...]:
    kept: list[_LexEvent] = []
    for event in events:
        if kept and event.start < kept[-1].end:
            previous = kept[-1]
            if event.start == previous.start and event.end > previous.end:
                kept[-1] = event
            continue
        kept.append(event)
    return tuple(kept)


def _prune_contained_targets(
    targets: tuple[_LexEvent, ...],
) -> tuple[_LexEvent, ...]:
    kept: list[_LexEvent] = []
    furthest_end = -1
    for target in sorted(targets, key=lambda item: (item.start, -item.end)):
        if target.end <= furthest_end:
            continue
        kept.append(target)
        furthest_end = target.end
    return tuple(sorted(kept, key=lambda item: (item.start, item.end)))


def _prune_shadowed_stances(
    stances: tuple[_LexEvent, ...],
) -> tuple[_LexEvent, ...]:
    shields = tuple(
        event
        for event in stances
        if event.value.startswith("question")
        or event.value in {"negative_exception", "negative_command"}
    )
    return tuple(
        event
        for event in stances
        if not (
            (
                (
                    event.value.startswith("negative")
                    and event.value != "negative_exception"
                )
                or event.value == "strict_command"
            )
            and any(
                shield != event
                and shield.start <= event.start < shield.end
                for shield in shields
            )
        )
    )


def _build_quote_scopes(index: _LexicalIndex) -> tuple[_QuoteScope, ...]:
    stacks: dict[str, list[tuple[int, int]]] = {}
    open_scopes: list[tuple[str, int, int, int]] = []
    completed: list[_QuoteScope] = []
    next_scope_id = 0
    for event in index.quotes:
        _work()
        pair = event.value
        stack = stacks.setdefault(pair, [])
        if event.kind == "quote_toggle" and stack:
            scope_id, start = stack.pop()
            depth = next(
                item[3]
                for item in reversed(open_scopes)
                if item[0] == pair and item[1] == scope_id
            )
            open_scopes = [
                item for item in open_scopes if item[1] != scope_id
            ]
            completed.append(
                _QuoteScope(
                    scope_id,
                    start,
                    start + len(event.surface),
                    event.start,
                    event.end,
                    depth,
                    True,
                )
            )
            continue
        if event.kind in {"quote_open", "quote_toggle"}:
            depth = len(open_scopes)
            stack.append((next_scope_id, event.start))
            open_scopes.append((pair, next_scope_id, event.start, depth))
            next_scope_id += 1
            continue
        if event.kind == "quote_close" and stack:
            scope_id, start = stack.pop()
            depth = next(
                item[3]
                for item in reversed(open_scopes)
                if item[0] == pair and item[1] == scope_id
            )
            open_scopes = [
                item for item in open_scopes if item[1] != scope_id
            ]
            completed.append(
                _QuoteScope(
                    scope_id,
                    start,
                    start + 1,
                    event.start,
                    event.end,
                    depth,
                    True,
                )
            )
    for _pair, scope_id, start, depth in open_scopes:
        completed.append(
            _QuoteScope(
                scope_id,
                start,
                start + 1,
                len(index.text),
                len(index.text),
                depth,
                False,
            )
        )
    return tuple(sorted(completed, key=lambda item: (item.start, item.end)))


def _innermost_quote(
    position: int,
    quotes: tuple[_QuoteScope, ...],
) -> _QuoteScope | None:
    # Count the indexed lookup once, then count only scopes actually inspected.
    # Binary-search comparisons are an implementation detail rather than a
    # candidate-sized scan; the backward cursor below exposes any real fan-out.
    _work()
    low = 0
    high = len(quotes)
    while low < high:
        middle = (low + high) // 2
        if quotes[middle].content_start <= position:
            low = middle + 1
        else:
            high = middle
    cursor = low - 1
    while cursor >= 0:
        _work()
        quote = quotes[cursor]
        if quote.content_start <= position < quote.content_end:
            return quote
        if quote.depth == 0 and quote.content_end <= position:
            return None
        cursor -= 1
    return None


def _events_between(
    events: tuple[_LexEvent, ...],
    start: int,
    end: int,
) -> tuple[_LexEvent, ...]:
    # This is an indexed range lookup.  Work accounting includes the lookup and
    # every returned event, while deliberately not pretending binary search is
    # a scan of the prefix that it skips.
    _work()
    low = 0
    high = len(events)
    while low < high:
        middle = (low + high) // 2
        if events[middle].start < start:
            low = middle + 1
        else:
            high = middle
    selected: list[_LexEvent] = []
    cursor = low
    while cursor < len(events) and events[cursor].start < end:
        _work()
        event = events[cursor]
        if event.end <= end:
            selected.append(event)
        cursor += 1
    return tuple(selected)


def _first_hard_boundary_after(
    index: _LexicalIndex,
    position: int,
) -> int:
    # Do not materialize every remaining boundary for every provider.  Find the
    # first possible boundary and stop as soon as the hard boundary is known.
    _work()
    low = 0
    high = len(index.boundaries)
    while low < high:
        middle = (low + high) // 2
        if index.boundaries[middle].start < position:
            low = middle + 1
        else:
            high = middle
    cursor = low
    while cursor < len(index.boundaries):
        _work()
        event = index.boundaries[cursor]
        if event.surface in _HARD_BOUNDARY_SURFACES:
            return event.start
        cursor += 1
    return len(index.text)


def _relation_after_provider(
    index: _LexicalIndex,
    provider: _LexEvent,
) -> _LexEvent | None:
    for relation in _events_between(
        index.relations,
        provider.end,
        min(len(index.text), provider.end + 12),
    ):
        if relation.value != "report":
            continue
        if any(
            boundary.start < relation.start
            for boundary in _events_between(
                index.boundaries,
                provider.end,
                relation.start,
            )
        ):
            return None
        if _events_between(
            index.actions,
            provider.end,
            relation.start,
        ):
            return None
        return relation
    return None


def _basis_before_provider(
    index: _LexicalIndex,
    provider: _LexEvent,
) -> _LexEvent | None:
    preceding: _LexEvent | None = None
    for relation in _events_between(
        index.relations,
        max(0, provider.start - 3),
        provider.start,
    ):
        if relation.value != "basis":
            continue
        if provider.start - relation.end <= 1:
            preceding = relation
    return preceding


def _is_nominal_report(index: _LexicalIndex, report: _LexEvent) -> bool:
    cursor = report.end
    while cursor < len(index.text) and index.text[cursor].isspace():
        cursor += 1
    suffix = index.text[cursor:]
    if suffix.startswith("的"):
        suffix = suffix[1:]
    if not suffix:
        return True
    return any(
        suffix.startswith(continuation.removeprefix("的"))
        for continuation in EVIDENCE_REPORT_NOUN_CONTINUATIONS.get(
            report.surface,
            (),
        )
    )


def _build_provider_evidence(
    index: _LexicalIndex,
) -> tuple[ProviderEvidence, ...]:
    evidence: list[ProviderEvidence] = []
    for provider in index.providers:
        _work()
        basis = _basis_before_provider(index, provider)
        report = _relation_after_provider(index, provider)
        if basis is not None:
            relation: ProviderRelationKind = "basis"
        elif report is not None and not _is_nominal_report(index, report):
            relation = "report"
        else:
            cursor = provider.end
            while cursor < len(index.text) and index.text[cursor].isspace():
                cursor += 1
            relation = (
                "report"
                if cursor < len(index.text)
                and index.text[cursor] in "：:"
                and cursor + 1 < len(index.text)
                else "unresolved"
            )
        evidence.append(
            ProviderEvidence(
                provider.start,
                provider.end,
                provider.surface,
                relation,
            )
        )
    return tuple(evidence)


def _build_report_scopes(
    index: _LexicalIndex,
    providers: tuple[ProviderEvidence, ...],
) -> tuple[_ReportScope, ...]:
    scopes: list[_ReportScope] = []
    for provider_index, provider in enumerate(providers):
        _work()
        if provider.relation != "report":
            continue
        scopes.append(
            _ReportScope(
                len(scopes),
                provider_index,
                provider.start,
                _first_hard_boundary_after(index, provider.end),
            )
        )
    return tuple(scopes)


def _action_is_report_predicate(
    action: _LexEvent,
    index: _LexicalIndex,
) -> bool:
    if action.surface != "告诉我":
        return False
    local_providers = _events_between(
        index.providers,
        max(0, action.start - _MAX_PROVIDER_SURFACE_LENGTH),
        action.start + 1,
    )
    return any(
        provider.end == action.start
        for provider in local_providers
    )


def _action_is_inside_target_noun(
    action: _LexEvent,
    index: _LexicalIndex,
    previous: _LexEvent | None,
) -> bool:
    local_targets = _events_between(
        index.targets,
        max(0, action.start - _MAX_TARGET_SURFACE_LENGTH),
        min(
            len(index.text),
            action.end + 3 + _MAX_TARGET_SURFACE_LENGTH,
        ),
    )
    following_object = any(
        target.start >= action.end
        and target.start - action.end <= 3
        and target.value != "health_record"
        and not _events_between(index.actions, action.end, target.start)
        and not _events_between(index.conjunctions, action.end, target.start)
        for target in local_targets
    )
    if following_object:
        return False
    strictly_contained = any(
        target.start <= action.start
        and action.end <= target.end
        and (target.start < action.start or action.end < target.end)
        for target in local_targets
    )
    exact_record_target = (
        action.surface == "记录"
        and previous is not None
        and any(
            target.start == action.start
            and target.end == action.end
            and target.value == "health_record"
            for target in local_targets
        )
    )
    return strictly_contained or exact_record_target


def _top_level_bridge_event(
    event: _LexEvent,
    quotes: tuple[_QuoteScope, ...],
) -> bool:
    return _innermost_quote(event.start, quotes) is None


def _build_action_drafts(
    index: _LexicalIndex,
    quotes: tuple[_QuoteScope, ...],
) -> tuple[_ActionDraft, ...]:
    preliminary: list[_ActionDraft] = []
    group = 0
    previous: _LexEvent | None = None
    for action in index.actions:
        _work()
        if _action_is_report_predicate(action, index):
            continue
        if _action_is_inside_target_noun(action, index, previous):
            preliminary.append(_ActionDraft(action, "noun", group))
            continue
        if previous is None:
            role: _ActionRole = "governor"
        else:
            bridge_boundaries = tuple(
                event
                for event in _events_between(
                    index.boundaries,
                    previous.end,
                    action.start,
                )
                if _top_level_bridge_event(event, quotes)
            )
            bridge_conjunctions = _events_between(
                index.conjunctions,
                previous.end,
                action.start,
            )
            if any(
                event.surface in _GROUP_BOUNDARY_SURFACES
                for event in bridge_boundaries
            ):
                group += 1
                role = "governor"
            elif bridge_conjunctions:
                role = "coordinated"
            else:
                role = "embedded"
        preliminary.append(_ActionDraft(action, role, group))
        previous = action
    return tuple(preliminary)


def _group_window(
    draft: _ActionDraft,
    drafts: tuple[_ActionDraft, ...],
    text_length: int,
) -> tuple[int, int]:
    del drafts, text_length
    return draft.group_start, draft.group_end


def _finalize_drafts(
    drafts: tuple[_ActionDraft, ...],
    index: _LexicalIndex,
) -> tuple[_ActionDraft, ...]:
    if not drafts:
        return ()
    group_indices: dict[int, list[int]] = {}
    for ordinal, draft in enumerate(drafts):
        _work()
        group_indices.setdefault(draft.group, []).append(ordinal)
    finalized: list[_ActionDraft] = []
    previous_top_level_by_group: dict[int, int | None] = {}
    next_top_level_by_ordinal: dict[int, int | None] = {}
    next_top_level_by_group: dict[int, int | None] = {}
    for ordinal in range(len(drafts) - 1, -1, -1):
        _work()
        reverse_draft = drafts[ordinal]
        next_top_level_by_ordinal[ordinal] = next_top_level_by_group.get(
            reverse_draft.group
        )
        if reverse_draft.role in {"governor", "coordinated"}:
            next_top_level_by_group[reverse_draft.group] = ordinal
    group_windows: dict[int, tuple[int, int]] = {}
    ordered_groups = tuple(group_indices)
    for group_offset, group in enumerate(ordered_groups):
        _work()
        indices = group_indices[group]
        previous_group_indices = (
            group_indices[ordered_groups[group_offset - 1]]
            if group_offset > 0
            else []
        )
        next_group_indices = (
            group_indices[ordered_groups[group_offset + 1]]
            if group_offset + 1 < len(ordered_groups)
            else []
        )
        search_start = (
            drafts[previous_group_indices[0]].event.end
            if previous_group_indices
            else 0
        )
        preceding_boundaries = _events_between(
            index.boundaries,
            search_start,
            drafts[indices[0]].event.start,
        )
        group_start = (
            preceding_boundaries[-1].end
            if preceding_boundaries
            else search_start
        )
        group_end = (
            drafts[next_group_indices[0]].event.start
            if next_group_indices
            else len(index.text)
        )
        group_windows[group] = (group_start, group_end)
    for ordinal, draft in enumerate(drafts):
        _work()
        indices = group_indices[draft.group]
        group_start, group_end = group_windows[draft.group]
        previous_top_level = previous_top_level_by_group.get(draft.group)
        finalized.append(
            _ActionDraft(
                event=draft.event,
                role=draft.role,
                group=draft.group,
                ordinal=ordinal,
                group_start=group_start,
                group_end=group_end,
                group_first_ordinal=indices[0],
                group_end_ordinal=indices[-1] + 1,
                previous_top_level_ordinal=previous_top_level,
                next_top_level_ordinal=next_top_level_by_ordinal[ordinal],
            )
        )
        if draft.role in {"governor", "coordinated"}:
            previous_top_level_by_group[draft.group] = ordinal
    return tuple(finalized)


def _head_targets(
    index: _LexicalIndex,
    start: int,
    end: int,
) -> tuple[_LexEvent, ...]:
    targets = _events_between(index.targets, start, end)
    if not targets:
        return ()
    last_de: _LexEvent | None = None
    for node in _events_between(index.structures, start, end):
        if node.surface == "的":
            last_de = node
    if last_de is None:
        return targets
    heads = tuple(
        target
        for target in targets
        if target.start >= last_de.end
        or target.start <= last_de.start < target.end
    )
    return heads or targets


def _action_target_window(
    draft: _ActionDraft,
    drafts: tuple[_ActionDraft, ...],
    index: _LexicalIndex,
) -> tuple[int, int]:
    group_start, group_end = _group_window(draft, drafts, len(index.text))
    if draft.role == "embedded":
        governor = drafts[draft.group_first_ordinal]
        return governor.event.start, group_end
    following = (
        drafts[draft.next_top_level_ordinal]
        if draft.next_top_level_ordinal is not None
        else None
    )
    local_end = following.event.start if following is not None else group_end
    contained_or_forward = _head_targets(
        index,
        draft.event.start,
        local_end,
    )
    if contained_or_forward:
        return draft.event.start, local_end
    if draft.role == "coordinated":
        return draft.event.start, group_end
    shared_forward = _head_targets(index, draft.event.start, group_end)
    if shared_forward:
        return draft.event.start, group_end
    return group_start, group_end


def _resolve_target(
    draft: _ActionDraft,
    drafts: tuple[_ActionDraft, ...],
    index: _LexicalIndex,
) -> _TargetResolution:
    _work()
    start, end = _action_target_window(draft, drafts, index)
    targets = tuple(
        target
        for target in _head_targets(index, start, end)
        if not (
            target.start == draft.event.start
            and target.end == draft.event.end
            and target.value not in _CREATE_FAMILIES
        )
    )
    if not targets:
        return _TargetResolution(
            "unknown",
            draft.event.end,
            draft.event.end,
            frozenset(),
            False,
        )
    kinds = frozenset(target.value for target in targets)
    if len(kinds) != 1:
        return _TargetResolution(
            "unknown",
            draft.event.end,
            draft.event.end,
            kinds,
            True,
        )
    chosen = min(
        targets,
        key=lambda target: (
            0 if target.start >= draft.event.end else 1,
            abs(target.start - draft.event.end),
            -len(target.surface),
        ),
    )
    return _TargetResolution(
        chosen.value,  # type: ignore[arg-type]
        chosen.start,
        chosen.end,
        kinds,  # type: ignore[arg-type]
        False,
    )


def _resolve_action_kind(
    draft: _ActionDraft,
    target: _TargetResolution,
) -> ActionKind | None:
    _work()
    if draft.role == "noun":
        return None
    create_families = draft.event.allowed_families & _CREATE_FAMILIES
    if draft.role == "embedded" and target.target in _CREATE_FAMILIES:
        return None
    if target.conflicted and (
        create_families or "save" in draft.event.allowed_families
    ):
        return None
    if target.target in _CREATE_FAMILIES:
        return (
            target.target  # type: ignore[return-value]
            if target.target in create_families
            else None
        )
    non_create = draft.event.allowed_families - _CREATE_FAMILIES
    if len(non_create) == 1:
        return next(iter(non_create))
    return None


def _group_stances(
    draft: _ActionDraft,
    drafts: tuple[_ActionDraft, ...],
    index: _LexicalIndex,
) -> tuple[_LexEvent, ...]:
    start, end = _group_window(draft, drafts, len(index.text))
    return _events_between(index.stances, start, end)


def _has_completed_evidence(
    draft: _ActionDraft,
    drafts: tuple[_ActionDraft, ...],
    index: _LexicalIndex,
) -> bool:
    stances = _group_stances(draft, drafts, index)
    return any(
        (
            stance.value == "completed_prefix"
            and stance.end <= draft.event.start
            and not _events_between(
                index.actions,
                stance.end,
                draft.event.start,
            )
        )
        or (
            stance.value == "completed_suffix"
            and stance.start >= draft.event.end
            and not _events_between(
                index.actions,
                draft.event.end,
                stance.start,
            )
        )
        for stance in stances
    )


def _has_conditional_evidence(
    draft: _ActionDraft,
    drafts: tuple[_ActionDraft, ...],
    index: _LexicalIndex,
) -> bool:
    return any(
        stance.value == "conditional" and stance.end <= draft.event.start
        for stance in _group_stances(draft, drafts, index)
    )


def _has_question_evidence(
    draft: _ActionDraft,
    drafts: tuple[_ActionDraft, ...],
    index: _LexicalIndex,
) -> bool:
    stances = _group_stances(draft, drafts, index)
    for stance in stances:
        if stance.value == "question_prefix" and stance.end <= draft.event.start:
            return True
        if stance.value == "question_terminal" and stance.start >= draft.event.end:
            trailing = index.text[stance.end : _group_window(
                draft,
                drafts,
                len(index.text),
            )[1]].strip("？?。！! ")
            if not trailing:
                return True
    return False


def _negative_stance(
    draft: _ActionDraft,
    drafts: tuple[_ActionDraft, ...],
    index: _LexicalIndex,
) -> _LexEvent | None:
    previous = (
        drafts[draft.previous_top_level_ordinal]
        if draft.previous_top_level_ordinal is not None
        else None
    )
    group_start, _group_end = _group_window(
        draft,
        drafts,
        len(index.text),
    )
    local_start = previous.event.end if previous is not None else group_start
    local = tuple(
        stance
        for stance in _group_stances(draft, drafts, index)
        if local_start <= stance.start < draft.event.start
    )
    if any(
        stance.value in {"strict_command", "user_subject"}
        for stance in local
    ):
        return next(
            (
                stance
                for stance in reversed(local)
                if stance.value.startswith("negative")
                and stance.value != "negative_exception"
                and not any(
                    reset.start > stance.start
                    for reset in local
                    if reset.value in {"strict_command", "user_subject"}
                )
            ),
            None,
        )
    direct = next(
        (
            stance
            for stance in reversed(local)
            if stance.value.startswith("negative")
            and stance.value != "negative_exception"
        ),
        None,
    )
    if direct is not None:
        return direct
    if draft.role == "coordinated" and previous is not None:
        return _negative_stance(previous, drafts, index)
    return None


def _span_covered(
    start: int,
    end: int,
    spans: tuple[tuple[int, int], ...],
    text: str,
) -> bool:
    ordered_spans = tuple(sorted(spans))
    span_cursor = 0
    for cursor in range(start, end):
        _work()
        if text[cursor].isspace() or text[cursor] in (
            "，,：:。；;！!?？“”‘’「」\""
        ):
            continue
        while (
            span_cursor < len(ordered_spans)
            and ordered_spans[span_cursor][1] <= cursor
        ):
            _work()
            span_cursor += 1
        if (
            span_cursor < len(ordered_spans)
            and ordered_spans[span_cursor][0]
            <= cursor
            < ordered_spans[span_cursor][1]
        ):
            continue
        return False
    return True


def _basis_command_proof(
    draft: _ActionDraft,
    index: _LexicalIndex,
    prefix_start: int,
) -> _CommandProof | None:
    basis = next(
        (
            relation
            for relation in _events_between(
                index.relations,
                prefix_start,
                draft.event.start,
            )
            if relation.value == "basis"
        ),
        None,
    )
    if basis is None:
        return None
    provider = next(
        (
            event
            for event in _events_between(
                index.providers,
                basis.end,
                draft.event.start,
            )
        ),
        None,
    )
    if provider is None:
        return None
    spans: list[tuple[int, int]] = [
        (basis.start, basis.end),
        (provider.start, provider.end),
    ]
    report_relations = tuple(
        event
        for event in _events_between(
            index.relations,
            provider.end,
            draft.event.start,
        )
        if event.value == "report"
    )
    spans.extend((event.start, event.end) for event in report_relations)
    for report in report_relations:
        continuation_start = report.end
        if (
            continuation_start < draft.event.start
            and index.text[continuation_start] == "的"
        ):
            continuation_start += 1
        for continuation in EVIDENCE_REPORT_NOUN_CONTINUATIONS.get(
            report.surface,
            (),
        ):
            if index.text.startswith(continuation, continuation_start):
                spans.append(
                    (
                        continuation_start,
                        continuation_start + len(continuation),
                    )
                )
                break
    spans.extend(
        (event.start, event.end)
        for event in _events_between(
            index.stances,
            prefix_start,
            basis.start,
        )
        if event.value in {"negative_command", "strict_command"}
    )
    for cursor in range(provider.end, draft.event.start):
        if index.text[cursor] in EVIDENCE_REPORT_FILLER_CHARS:
            spans.append((cursor, cursor + 1))
    complete = _span_covered(
        prefix_start,
        draft.event.start,
        tuple(spans),
        index.text,
    )
    return _CommandProof(
        "clinician_basis",
        prefix_start,
        draft.event.start,
        complete,
    )


def _ordinary_command_proof(
    draft: _ActionDraft,
    drafts: tuple[_ActionDraft, ...],
    index: _LexicalIndex,
    prior_proofs: dict[int, _CommandProof],
) -> _CommandProof:
    group_start, _group_end = _group_window(
        draft,
        drafts,
        len(index.text),
    )
    previous = (
        drafts[draft.previous_top_level_ordinal]
        if draft.previous_top_level_ordinal is not None
        else None
    )
    if draft.role == "coordinated" and previous is not None:
        previous_proof = prior_proofs.get(previous.event.start)
        if previous_proof is not None and previous_proof.complete:
            return _CommandProof(
                "coordinated_command",
                previous.event.end,
                draft.event.start,
                True,
            )
    prefix_start = group_start
    stances = tuple(
        stance
        for stance in _events_between(
            index.stances,
            prefix_start,
            draft.event.start,
        )
        if stance.value in {
            "negative_command",
            "strict_command",
            "user_subject",
        }
    )
    if stances:
        prefix_start = stances[-1].start
    basis = _basis_command_proof(draft, index, prefix_start)
    if basis is not None:
        return basis
    targets = _events_between(index.targets, prefix_start, draft.event.start)
    structures = tuple(
        event
        for event in _events_between(
            index.structures,
            prefix_start,
            draft.event.start,
        )
        if event.surface == "把"
    )
    spans = tuple((event.start, event.end) for event in stances)
    if structures:
        spans += tuple(
            (event.start, event.end)
            for event in (*targets, *structures)
        )
        spans += tuple(
            (cursor, cursor + 1)
            for cursor in range(prefix_start, draft.event.start)
            if index.text[cursor] in EVIDENCE_BA_PARTICLE_CHARS
        )
    complete = _span_covered(
        prefix_start,
        draft.event.start,
        spans,
        index.text,
    )
    if stances:
        shape = stances[-1].value
    elif structures and targets:
        shape = "ba_object"
    else:
        shape = "bare_action"
    return _CommandProof(shape, prefix_start, draft.event.start, complete)


def _owned_basis_quote_ids(
    index: _LexicalIndex,
    quotes: tuple[_QuoteScope, ...],
    providers: tuple[ProviderEvidence, ...],
) -> frozenset[int]:
    owned: set[int] = set()
    provider_cursor = 0
    provider_index = -1
    for quote in quotes:
        while (
            provider_cursor < len(providers)
            and providers[provider_cursor].end <= quote.start
        ):
            provider_index = provider_cursor
            provider_cursor += 1
        if provider_index < 0:
            continue
        provider = providers[provider_index]
        if provider.relation != "basis":
            continue
        report = next(
            (
                relation
                for relation in _events_between(
                    index.relations,
                    provider.end,
                    quote.start,
                )
                if relation.value == "report"
                and not _is_nominal_report(index, relation)
            ),
            None,
        )
        if report is not None:
            owned.add(quote.scope_id)
    return frozenset(owned)


def _actor_reset_between(
    previous_end: int,
    current: _ResolvedDraft,
    index: _LexicalIndex,
    quotes: tuple[_QuoteScope, ...],
) -> bool:
    transitions = tuple(
        event
        for event in _events_between(
            index.boundaries,
            previous_end,
            current.draft.event.start,
        )
        if event.surface in _ACTOR_TRANSITION_SURFACES
        or event.surface in _HARD_BOUNDARY_SURFACES
    )
    for transition in transitions:
        if _innermost_quote(transition.start, quotes) is not None:
            continue
        for stance in _events_between(
            index.stances,
            transition.end,
            current.draft.event.start,
        ):
            if stance.value not in {
                "negative_command",
                "strict_command",
                "user_subject",
            }:
                continue
            if _innermost_quote(stance.start, quotes) is None:
                return True
    return False


def _assign_actors(
    resolved: tuple[_ResolvedDraft, ...],
    index: _LexicalIndex,
    quotes: tuple[_QuoteScope, ...],
    providers: tuple[ProviderEvidence, ...],
    report_scopes: tuple[_ReportScope, ...],
) -> tuple[ActorKind, ...]:
    basis_owned_quotes = _owned_basis_quote_ids(index, quotes, providers)
    reset_scopes: set[int] = set()
    last_report_action_end: dict[int, int] = {}
    actors: list[ActorKind] = []
    report_cursor = 0
    active_reports: list[_ReportScope] = []
    provider_cursor = 0
    latest_basis: ProviderEvidence | None = None
    latest_unresolved: ProviderEvidence | None = None
    for item in resolved:
        _work()
        position = item.draft.event.start
        quote = _innermost_quote(position, quotes)
        while (
            report_cursor < len(report_scopes)
            and report_scopes[report_cursor].start <= position
        ):
            _work()
            active_reports.append(report_scopes[report_cursor])
            report_cursor += 1
        active_reports = [
            scope for scope in active_reports if position < scope.end
        ]
        while (
            provider_cursor < len(providers)
            and providers[provider_cursor].end <= position
        ):
            _work()
            provider = providers[provider_cursor]
            if provider.relation == "basis":
                latest_basis = provider
            elif provider.relation == "unresolved":
                latest_unresolved = provider
            provider_cursor += 1
        if quote is not None and quote.scope_id in basis_owned_quotes:
            actors.append("clinician")
            continue
        active = next(
            (
                scope
                for scope in active_reports
                if scope.scope_id not in reset_scopes
            ),
            None,
        )
        while active is not None:
            previous_end = last_report_action_end.get(
                active.scope_id,
                active.start,
            )
            if _actor_reset_between(
                previous_end,
                item,
                index,
                quotes,
            ):
                reset_scopes.add(active.scope_id)
                active = next(
                    (
                        scope
                        for scope in active_reports
                        if scope.scope_id not in reset_scopes
                    ),
                    None,
                )
                continue
            actors.append("clinician")
            last_report_action_end[active.scope_id] = item.draft.event.end
            break
        if active is not None and active.scope_id not in reset_scopes:
            continue
        if quote is not None:
            user_proof_before_quote = (
                item.proof.complete
                and item.proof.shape
                in {"negative_command", "strict_command", "user_subject"}
                and item.proof.start < quote.start
            )
            actors.append("user" if user_proof_before_quote else "ambiguous")
            continue
        basis = latest_basis
        if basis is not None and (
            _first_hard_boundary_after(index, basis.end) < position
        ):
            basis = None
        unresolved = latest_unresolved
        if unresolved is not None and (
            _first_hard_boundary_after(index, unresolved.end) < position
        ):
            unresolved = None
        if unresolved is not None:
            actors.append("ambiguous")
        elif basis is not None and item.proof.complete:
            actors.append("user")
        elif basis is not None:
            actors.append("ambiguous")
        elif item.proof.complete:
            actors.append("user")
        else:
            actors.append("ambiguous")
    return tuple(actors)


def _resolve_stance(
    item: _ResolvedDraft,
    drafts: tuple[_ActionDraft, ...],
    index: _LexicalIndex,
) -> tuple[PolarityKind, ModalityKind]:
    _work()
    negative = _negative_stance(item.draft, drafts, index)
    polarity: PolarityKind = "negative" if negative is not None else "positive"
    if item.draft.role == "embedded":
        return polarity, "statement"
    if _has_conditional_evidence(item.draft, drafts, index):
        return polarity, "unknown"
    if _has_question_evidence(item.draft, drafts, index):
        return polarity, "question"
    if _has_completed_evidence(item.draft, drafts, index):
        return polarity, "statement"
    if negative is not None and negative.value == "negative_statement":
        return polarity, "unknown"
    if negative is not None and negative.value == "negative_command":
        return polarity, "command"
    return polarity, "command" if item.proof.complete else "unknown"


def _provenance(
    actor: ActorKind,
    target: _TargetResolution,
    providers: tuple[ProviderEvidence, ...],
) -> str:
    if actor == "clinician":
        return "clinician_reported_action"
    if actor == "ambiguous":
        return "ambiguous_clinician_context"
    if providers and any(provider.relation == "basis" for provider in providers):
        return "clinician_basis_user_action"
    if target.target == "clinician_record":
        return "explicit_user_clinician_record_action"
    return "explicit_user_action"


def _scan_actions(
    index: _LexicalIndex,
    providers: tuple[ProviderEvidence, ...],
    quotes: tuple[_QuoteScope, ...],
) -> tuple[ActionEvidence, ...]:
    all_drafts = _build_action_drafts(index, quotes)
    drafts = _finalize_drafts(
        tuple(draft for draft in all_drafts if draft.role != "noun"),
        index,
    )
    prior_proofs: dict[int, _CommandProof] = {}
    resolved: list[_ResolvedDraft] = []
    for draft in drafts:
        _work()
        target = _resolve_target(draft, drafts, index)
        action = _resolve_action_kind(draft, target)
        if action is None:
            continue
        proof = _ordinary_command_proof(
            draft,
            drafts,
            index,
            prior_proofs,
        )
        prior_proofs[draft.event.start] = proof
        resolved.append(_ResolvedDraft(draft, action, target, proof))
    resolved_tuple = tuple(resolved)
    report_scopes = _build_report_scopes(index, providers)
    actors = _assign_actors(
        resolved_tuple,
        index,
        quotes,
        providers,
        report_scopes,
    )
    actions: list[ActionEvidence] = []
    for item, actor in zip(resolved_tuple, actors):
        _work()
        polarity, modality = _resolve_stance(item, drafts, index)
        actions.append(
            ActionEvidence(
                start=item.draft.event.start,
                end=item.draft.event.end,
                action=item.action,
                actor=actor,
                target=item.target.target,
                target_start=item.target.start,
                target_end=item.target.end,
                polarity=polarity,
                modality=modality,
                provenance=_provenance(actor, item.target, providers),
            )
        )
    return tuple(actions)


def _parse_action_evidence_with_index(
    text: str,
) -> tuple[EvidenceParse, _LexicalIndex]:
    index = _lexical_scan(text)
    meter = _WorkMeter(index.lexical_work_units)
    token = _ACTIVE_WORK_METER.set(meter)
    try:
        providers = _build_provider_evidence(index)
        quotes = _build_quote_scopes(index)
        parsed = EvidenceParse(
            text=text,
            clinician_bearing=bool(providers),
            providers=providers,
            actions=_scan_actions(index, providers, quotes),
        )
    finally:
        _ACTIVE_WORK_METER.reset(token)
    index = replace(index, work_units=meter.units)
    return parsed, index


def parse_action_evidence(text: str) -> EvidenceParse:
    """Return ordered raw evidence without reducing authorization state."""

    parsed, _index = _parse_action_evidence_with_index(text)
    return parsed
