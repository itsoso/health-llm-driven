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
    r"[，,。.!！；;：:]|但是|不过|然而|然后|接着|随后"
)
_CAPABILITY_INQUIRY_PREFIXES = (
    "我想问一下",
    "我想问",
    "想问一下",
    "想问",
    "请问一下",
    "请问",
)
_CAPABILITY_SUBJECTS = ("这个功能", "该功能", "系统", "小巴")
_CAPABILITY_MODALS = ("可不可以", "能不能", "可以", "能否", "可否", "能")
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
_HISTORY_TERMS = ("历史", "列表", "汇总", "以前", "上一次", "既往", "曾经")
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
    return tuple(clause for clause in _CLAUSE_BOUNDARY_RE.split(text) if clause)


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
    if not any(signal.lower() in text for signal in QUESTION_SIGNALS):
        return False

    had_inquiry_prefix = False
    for prefix in _CAPABILITY_INQUIRY_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
            had_inquiry_prefix = True
            break
    subject = next(
        (candidate for candidate in _CAPABILITY_SUBJECTS if text.startswith(candidate)),
        None,
    )
    if subject is None:
        return False
    after_subject = text[len(subject):]
    if after_subject.startswith(("，", ",", "：", ":")):
        if not had_inquiry_prefix:
            return False
        after_subject = after_subject[1:]

    action_position = min(
        (
            position
            for action in _ORDERED_WRITE_ACTIONS
            if (position := after_subject.find(action)) >= 0
        ),
        default=-1,
    )
    if action_position < 0:
        return False
    before_action = after_subject[:action_position]
    return any(modal in before_action for modal in _CAPABILITY_MODALS)


def is_historical_write_reference(value: str) -> bool:
    """Recognize completed actions and historical/list noun frames."""
    for clause in split_write_clauses(value):
        for action in _ORDERED_WRITE_ACTIONS:
            start = clause.find(action)
            while start >= 0:
                after = clause[start + len(action):]
                if after.startswith(("过", "了")):
                    return True
                if any(term in clause for term in _HISTORY_TERMS):
                    return True
                start = clause.find(action, start + len(action))
    return False
