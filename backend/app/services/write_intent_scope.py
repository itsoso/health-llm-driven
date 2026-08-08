"""Shared clause/scope parser for deterministic health-write authorization."""
from __future__ import annotations

import re
import unicodedata

from app.services.utterance_intent_lexicon import (
    QUESTION_SIGNALS,
    STRUCTURAL_WRITE_NEGATIONS,
    WRITE_COMMAND_ACTIONS,
    WRITE_NEGATION_EXCEPTIONS,
)

_CLAUSE_BOUNDARY_RE = re.compile(
    r"[，,。.!！；;]|但是|但|不过|然而|却|而是|然后|接着|随后"
)
_CAPABILITY_INQUIRY_PREFIXES = (
    "我想问一下",
    "我想问",
    "想问一下",
    "想问",
    "请问一下",
    "请问",
    "我想知道",
    "想知道",
    "请告诉我",
    "告诉我",
    "我想了解",
    "想了解",
    "我想确认",
    "想确认",
)
_CAPABILITY_SUBJECTS = ("这个功能", "该功能", "系统", "小巴")
_CAPABILITY_MODALS = (
    "可不可以",
    "能不能",
    "会不会",
    "是否会",
    "有没有",
    "可以",
    "能否",
    "可否",
    "支持",
    "会",
    "能",
)
_NON_NEGATING_MODALS = (
    "可不可以",
    "能不能",
    "该不该",
    "要不要",
    "不得不",
    "不能不",
    "不妨",
)
_NEGATION_LEXICAL_CONTAINERS = (
    "分别",
    "区别",
    "性别",
    "个别",
    "特别",
    "类别",
    "级别",
    "识别",
    "鉴别",
    "告别",
)
_POSITIVE_REMINDER_RE = re.compile(r"(?:不要|别|勿|甭)(?:忘记|忘了|忘)")
_HISTORY_NOUN_TERMS = ("历史", "列表", "汇总")
_PAST_TIME_TERMS = (
    "以前",
    "上一次",
    "上次",
    "上回",
    "之前",
    "刚才",
    "既往",
    "曾经",
)
_HISTORY_TERMS = (*_HISTORY_NOUN_TERMS, *_PAST_TIME_TERMS)
_COMPLETED_QUESTION_SUFFIXES = ("了吗", "了没", "了没有", "过吗", "过没", "过没有")
_BACKFILL_DATE_SIGNALS = (
    "发作日期",
    "开始日期",
    "起病日期",
    "发生日期",
    "日期是",
    "日期为",
    "时间是",
    "时间为",
)
_BACKFILL_REQUEST_MARKERS = ("请", "帮我", "把", "麻烦", "替我", "给我", "为我")
_DENIAL_SCOPE_INTRO_ENDINGS = (
    "执行",
    "执行以下操作",
    "执行如下操作",
    "以下操作",
    "如下操作",
    "这些操作",
    "这项操作",
)
_DIRECT_DENIAL_PREDICATES = (
    "禁止",
    "严禁",
    "拒绝",
    "避免",
    "停止",
    "暂停",
    "终止",
    "取消",
    "撤销",
    "放弃",
    "谢绝",
)
_ORDERED_WRITE_ACTIONS = tuple(sorted(WRITE_COMMAND_ACTIONS, key=len, reverse=True))
_ORDERED_NEGATIONS = tuple(sorted(STRUCTURAL_WRITE_NEGATIONS, key=len, reverse=True))
_ORDERED_NON_NEGATING_MODALS = tuple(
    sorted(_NON_NEGATING_MODALS, key=len, reverse=True)
)


def normalize_write_scope_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return "".join(normalized.split()).lower()


def split_write_clauses(value: str) -> tuple[str, ...]:
    text = normalize_write_scope_text(value)
    colon_scoped: list[str] = []
    current = ""
    for character in text:
        if character not in ("：", ":"):
            current += character
            continue
        if _colon_extends_denial_scope(current):
            continue
        if current:
            colon_scoped.append(current)
        current = ""
    if current:
        colon_scoped.append(current)
    return tuple(
        clause
        for segment in colon_scoped
        for clause in _CLAUSE_BOUNDARY_RE.split(segment)
        if clause
    )


def _colon_extends_denial_scope(left: str) -> bool:
    if not any(negation in left for negation in _ORDERED_NEGATIONS):
        return False
    return left.endswith(_DENIAL_SCOPE_INTRO_ENDINGS) or left.endswith(
        _DIRECT_DENIAL_PREDICATES
    )


def has_negated_write_scope(value: str) -> bool:
    """Return true when a negation precedes a write action in one clause."""
    text = normalize_write_scope_text(value)
    if not text:
        return False
    if re.search(r"(?:取消|撤销)(?:这次|本次|该次)?(?:记录|保存|录入|写入)", text):
        return True
    if re.search(r"(?:记录|保存|录入|写入)(?:这次|本次|该次)?(?:取消|撤销|算了)", text):
        return True

    for raw_clause in split_write_clauses(text):
        clause = raw_clause
        for exception in WRITE_NEGATION_EXCEPTIONS:
            clause = clause.replace(exception, "")
        clause = _POSITIVE_REMINDER_RE.sub("", clause)
        for container in _NEGATION_LEXICAL_CONTAINERS:
            clause = clause.replace(container, "")
        for modal in _ORDERED_NON_NEGATING_MODALS:
            clause = clause.replace(modal, "")
        action_positions = [
            position
            for action in _ORDERED_WRITE_ACTIONS
            if (position := clause.find(action)) >= 0
        ]
        if not action_positions:
            continue
        first_action = min(action_positions)
        if any(clause.find(negation, 0, first_action) >= 0 for negation in _ORDERED_NEGATIONS):
            return True
    return False


def is_write_capability_question(value: str) -> bool:
    """Recognize product-capability questions without treating them as requests."""
    text = normalize_write_scope_text(value)
    action_position = min(
        (
            position
            for action in _ORDERED_WRITE_ACTIONS
            if (position := text.find(action)) >= 0
        ),
        default=-1,
    )
    if action_position < 0:
        return False
    before_action = text[:action_position]
    has_inquiry_cue = any(
        cue in before_action for cue in _CAPABILITY_INQUIRY_PREFIXES
    )
    subject_match = min(
        (
            (position, candidate)
            for candidate in _CAPABILITY_SUBJECTS
            if (position := before_action.find(candidate)) >= 0
        ),
        default=None,
    )
    if subject_match is None:
        return has_inquiry_cue and (
            any(signal.lower() in text for signal in QUESTION_SIGNALS)
            or any(modal in before_action for modal in _CAPABILITY_MODALS)
        )
    subject_position, subject = subject_match
    after_subject = text[subject_position + len(subject):]
    if after_subject.startswith(("，", ",", "：", ":")):
        if subject_position == 0 and not has_inquiry_cue:
            return False
        after_subject = after_subject[1:]

    subject_action_position = min(
        (
            position
            for action in _ORDERED_WRITE_ACTIONS
            if (position := after_subject.find(action)) >= 0
        ),
        default=-1,
    )
    if subject_action_position < 0:
        return False
    before_subject_action = after_subject[:subject_action_position]
    return has_inquiry_cue or any(
        modal in before_subject_action for modal in _CAPABILITY_MODALS
    )


def _is_explicit_dated_backfill(value: str) -> bool:
    text = normalize_write_scope_text(value)
    if not any(term in text for term in _HISTORY_TERMS):
        return False
    if not any(signal in text for signal in _BACKFILL_DATE_SIGNALS):
        return False
    if any(signal in text for signal in QUESTION_SIGNALS):
        return False
    action_position = min(
        (
            position
            for action in _ORDERED_WRITE_ACTIONS
            if (position := text.find(action)) >= 0
        ),
        default=-1,
    )
    if action_position < 0:
        return False
    before_action = text[:action_position]
    after_action = text[action_position:]
    return (
        action_position == 0
        or before_action.startswith(_BACKFILL_REQUEST_MARKERS)
        or after_action.startswith(("记录下来", "记下来", "存下来"))
    )


def is_historical_write_reference(value: str) -> bool:
    """Recognize completed actions and historical/list noun frames."""
    if _is_explicit_dated_backfill(value):
        return False
    for clause in split_write_clauses(value):
        for action in _ORDERED_WRITE_ACTIONS:
            start = clause.find(action)
            while start >= 0:
                after = clause[start + len(action):]
                if after.startswith(("过", "了")):
                    return True
                completed_tail = after.rstrip("?？")
                if completed_tail.endswith(_COMPLETED_QUESTION_SUFFIXES):
                    return True
                if any(term in clause for term in _HISTORY_NOUN_TERMS):
                    return True
                has_question = any(
                    signal.lower() in clause for signal in QUESTION_SIGNALS
                )
                if any(
                    (term_position := clause.find(term)) >= 0
                    and (term_position < start or has_question)
                    for term in _PAST_TIME_TERMS
                ):
                    return True
                start = clause.find(action, start + len(action))
    return False
