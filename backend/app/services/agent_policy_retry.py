"""Turn-local retry policy for decisions that need new user facts or authority."""
from typing import Iterable

# Parameter/model repair failures intentionally do not appear here.
_TERMINAL_NOTICES = {
    'supplement_dosage_requires_clarification': '这项补剂尚未写入。请确认本次服用的时间和数量。',
    'health_query_subject_not_current_user': '这次查询未执行。只能查询当前登录用户本人的记录。',
    'health_query_semantics_unresolved': '这次查询未执行。请明确要查询哪类记录以及日期。',
    'health_query_calendar_window_unsupported': '这次查询未执行。请给出明确的起止日期，并一次查询一种记录。',
    'health_query_cancelled_by_user': '已停止这次查询。',
}


def is_terminal_policy_reason(reason: str) -> bool:
    return reason in _TERMINAL_NOTICES


def terminal_policy_notice(reasons: Iterable[str], *, has_verified_writes: bool = False) -> str | None:
    for reason in reasons:
        if reason in _TERMINAL_NOTICES:
            prefix = '其他已核实保存的记录仍然保留；请勿重复提交。\n\n' if has_verified_writes else ''
            return prefix + _TERMINAL_NOTICES[reason]
    return None
