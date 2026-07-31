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
_ACTION_VOCABULARY: tuple[tuple[str, ActionKind], ...] = tuple(
    sorted(
        (
            ("存下来", "save"),
            ("记一下", "save"),
            ("记录", "save"),
            ("记下", "save"),
            ("录入", "save"),
            ("保存", "save"),
            ("写入", "save"),
            ("查看", "read"),
            ("删除", "delete"),
            ("调整", "update"),
            ("更新", "update"),
            ("同步", "sync"),
            ("分析", "advice"),
            ("生成", "media"),
            ("创建", "reminder"),
            ("制定", "plan"),
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
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
    "\n",
)
_NEGATIVE_MARKERS = (
    "没有必要",
    "不要",
    "不用",
    "无需",
    "先别",
    "不想",
    "别",
)
_QUESTION_MARKERS = ("要不要", "是否需要", "是否")
_USER_AUTHORITY_CUES = (
    "我想",
    "我要",
    "请",
    "帮我",
)
_HARD_SPEECH_RESETS = ("。", "；", ";", "\n", "！", "!", "？", "?")
_RECORD_NOUN_TERMS = (
    "医生诊断记录",
    "诊断记录",
    "用药记录",
    "健康记录",
    "病历记录",
    "检查记录",
    "昨天记录",
)
_TARGET_TERMS: tuple[tuple[str, TargetKind], ...] = (
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
    ("体重71kg", "weight"),
    ("体重", "weight"),
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
    ("昨天记录", "health_record"),
    ("医生诊断记录", "clinician_record"),
    ("诊断记录", "clinician_record"),
    ("医生说的内容", "clinician_content"),
    ("检查结果", "clinician_content"),
    ("诊断", "clinician_content"),
)


@dataclass(frozen=True)
class _ActionCandidate:
    start: int
    end: int
    action: ActionKind
    verb: str


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
                (verb, action)
                for verb, action in _ACTION_VOCABULARY
                if text.startswith(verb, cursor)
            ),
            None,
        )
        if match is None:
            cursor += 1
            continue

        verb, action = match
        end = cursor + len(verb)
        candidates.append(
            _ActionCandidate(
                start=cursor,
                end=end,
                action=action,
                verb=verb,
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


def _target_match(
    text: str,
    *,
    start: int,
    end: int,
    exclude_clinician: bool = False,
) -> tuple[TargetKind, int, int] | None:
    for term, target in _TARGET_TERMS:
        if exclude_clinician and target in {
            "clinician_content",
            "clinician_record",
        }:
            continue
        index = text.find(term, start, end)
        if index >= 0:
            return target, index, index + len(term)
    return None


def _is_record_noun(
    text: str,
    candidate: _ActionCandidate,
    raw_candidates: tuple[_ActionCandidate, ...],
) -> bool:
    if candidate.verb != "记录":
        return False

    noun_start = next(
        (
            candidate.end - len(term)
            for term in _RECORD_NOUN_TERMS
            if candidate.end >= len(term)
            and text.startswith(
                term,
                candidate.end - len(term),
                candidate.end,
            )
        ),
        None,
    )
    if noun_start is None:
        return False

    region_start = _region_start(text, candidate.start)
    region_end = _region_end(text, candidate.end)
    after = text[candidate.end : region_end].lstrip()

    prior_targeting_action = any(
        other.end <= noun_start
        and other.start >= region_start
        and other.action in {"read", "update", "delete", "sync", "advice"}
        for other in raw_candidates
    )
    if prior_targeting_action:
        return True

    specific_object = _target_match(
        text,
        start=candidate.end,
        end=region_end,
        exclude_clinician=True,
    )
    if specific_object is not None and after:
        return False
    return True


def _is_attributive_creation(
    text: str,
    candidate: _ActionCandidate,
) -> bool:
    return (
        candidate.action in {"media", "reminder", "plan"}
        and text.startswith("的", candidate.end)
    )


def _scan_action_candidates(
    text: str,
) -> tuple[_ActionCandidate, ...]:
    raw_candidates = _scan_raw_action_candidates(text)
    return tuple(
        candidate
        for candidate in raw_candidates
        if not _is_record_noun(text, candidate, raw_candidates)
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


def _last_user_cue_start(text: str, *, start: int, end: int) -> int:
    latest = -1
    for cue in _USER_AUTHORITY_CUES:
        cursor = text.find(cue, start, end)
        while cursor >= 0:
            latest = max(latest, cursor)
            cursor = text.find(cue, cursor + len(cue), end)
    return latest


def _has_hard_speech_reset(text: str, *, start: int, end: int) -> bool:
    return any(
        text.find(boundary, start, end) >= 0
        for boundary in _HARD_SPEECH_RESETS
    )


def _resolve_actor(
    text: str,
    candidate: _ActionCandidate,
    providers: tuple[ProviderEvidence, ...],
    candidates: tuple[_ActionCandidate, ...],
) -> ActorKind:
    provider = _nearest_provider_before(candidate, providers)
    previous_action_end = max(
        (
            other.end
            for other in candidates
            if other.end <= candidate.start
        ),
        default=0,
    )
    cue_floor = max(
        previous_action_end,
        provider.end if provider is not None else 0,
    )
    cue_start = _last_user_cue_start(
        text,
        start=cue_floor,
        end=candidate.start,
    )
    if provider is None:
        return "user"
    if provider.relation == "basis":
        return "user"
    if cue_start >= 0 and (
        previous_action_end > provider.end
        or _has_hard_speech_reset(
            text,
            start=provider.end,
            end=cue_start,
        )
    ):
        return "user"
    if provider.relation == "report":
        return "clinician"
    return "ambiguous"


def _resolve_target(
    text: str,
    candidate: _ActionCandidate,
    candidates: tuple[_ActionCandidate, ...],
) -> tuple[TargetKind, int, int]:
    index = candidates.index(candidate)
    next_start = (
        candidates[index + 1].start
        if index + 1 < len(candidates)
        else len(text)
    )
    forward_end = min(next_start, _region_end(text, candidate.end))
    forward = _target_match(
        text,
        start=candidate.end,
        end=forward_end,
    )
    if forward is not None:
        return forward

    previous_end = candidates[index - 1].end if index > 0 else 0
    backward_start = max(
        previous_end,
        _region_start(text, candidate.start),
    )
    backward = _target_match(
        text,
        start=backward_start,
        end=candidate.start,
    )
    if backward is not None:
        return backward
    return "unknown", candidate.end, candidate.end


def _local_prefix(text: str, candidate: _ActionCandidate) -> str:
    return text[_region_start(text, candidate.start) : candidate.start].rstrip()


def _resolve_polarity(
    text: str,
    candidate: _ActionCandidate,
) -> PolarityKind:
    prefix = _local_prefix(text, candidate)
    if any(prefix.endswith(marker) for marker in _QUESTION_MARKERS):
        return "positive"
    if any(prefix.endswith(marker) for marker in _NEGATIVE_MARKERS):
        return "negative"
    return "positive"


def _resolve_modality(
    text: str,
    candidate: _ActionCandidate,
) -> ModalityKind:
    prefix = _local_prefix(text, candidate)
    if any(prefix.endswith(marker) for marker in _QUESTION_MARKERS):
        return "question"
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


def _scan_actions(
    text: str,
    providers: tuple[ProviderEvidence, ...],
) -> tuple[ActionEvidence, ...]:
    candidates = _scan_action_candidates(text)
    actions: list[ActionEvidence] = []
    for candidate in candidates:
        actor = _resolve_actor(
            text,
            candidate,
            providers,
            candidates,
        )
        target, target_start, target_end = _resolve_target(
            text,
            candidate,
            candidates,
        )
        actions.append(
            ActionEvidence(
                start=candidate.start,
                end=candidate.end,
                action=candidate.action,
                actor=actor,
                target=target,
                target_start=target_start,
                target_end=target_end,
                polarity=_resolve_polarity(text, candidate),
                modality=_resolve_modality(text, candidate),
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
