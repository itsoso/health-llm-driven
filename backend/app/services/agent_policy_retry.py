"""Turn-local retry policy for decisions that need new user facts or authority."""
from typing import Any, Iterable

# Closed authority failures cannot become a parameter-repair loop. A new user
# instruction may authorize a new turn; changing model arguments cannot.
_PERMISSION_NOTICES = {
    'health_query_subject_not_current_user': '这次查询未执行。只能查询当前登录用户本人的记录。',
    'health_query_not_requested': '这次查询未执行。当前请求没有授权读取这些个人记录。',
    'recipe_replay_tool_not_allowed': '本次调用未执行。已确认的配方不允许调用这项工具。',
    'recipe_replay_record_type_not_allowed': '本次调用未执行。已确认的配方不允许记录这类数据。',
    'telegram_directive_tool_not_allowed': '本次调用未执行。当前指令入口没有授权这项工具。',
}
_CANCELLATION_NOTICES = {
    'health_query_cancelled_by_user': '已停止这次查询。',
    'explicit_write_cancellation': '已停止被取消的写入操作，没有执行这次变更。',
    'explicit_aigc_media_provider_veto': '已停止使用被你拒绝的生成服务，本次调用未执行。',
}
# Parameter/model repair failures intentionally do not appear here.
_TERMINAL_NOTICES = {
    **_PERMISSION_NOTICES, **_CANCELLATION_NOTICES,
    'longitudinal_read_scope_unresolved': '这次查询未执行。你的范围限制尚不能完整解析；请明确要查询的日期或日期范围。',
    'supplement_dosage_requires_clarification': '这项补剂尚未写入。请确认本次服用的时间和数量。',
}


def is_terminal_policy_reason(reason: str) -> bool:
    return reason in _TERMINAL_NOTICES


def terminal_policy_notice(reasons: Iterable[str], *, has_verified_writes: bool = False) -> str | None:
    for reason in reasons:
        if reason in _TERMINAL_NOTICES:
            prefix = '其他已核实保存的记录仍然保留；请勿重复提交。\n\n' if has_verified_writes else ''
            return prefix + _TERMINAL_NOTICES[reason]
    return None


READ_REPAIR_REASONS = frozenset({
    'health_query_semantics_unresolved', 'health_query_calendar_window_unsupported',
    'health_query_calendar_window_conflict', 'health_query_dimension_conflict',
    'owned_read_tool_out_of_scope',
})
MAX_READ_REPAIR_FAILURES = 2


def is_repairable_read_reason(reason: str) -> bool:
    return reason in READ_REPAIR_REASONS


def is_repairable_read_failure(reason: str, tool_name: str, args: Any) -> bool:
    """Only a rejected known read may advertise automatic parameter repair."""
    if not is_repairable_read_reason(reason):
        return False
    if reason == 'owned_read_tool_out_of_scope' and tool_name == 'health_analysis':
        # Recover by choosing the bounded read adapters, never by replaying
        # the rejected analysis (which can read broadly or persist artifacts).
        return True
    return tool_name in {'health_query', 'health_query_batch'} or (
        tool_name == 'health_manage' and isinstance(args, dict) and args.get('operation') == 'list'
    )


def policy_failure_category(reason: str) -> str:
    if reason in _CANCELLATION_NOTICES:
        return 'cancelled'
    if reason in _PERMISSION_NOTICES:
        return 'permission_denied'
    if is_repairable_read_reason(reason):
        return 'read_parameters'
    return 'clarification_required'
