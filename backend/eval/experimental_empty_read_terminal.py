"""Eval-only terminal for a closed read with verified empty results.

The normal Pi/Gateway executes every query first. This only replaces the final
provider call; the existing fact summary, output guards and persistence remain.
"""
import re

from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope

_CLOSED_READ = re.compile(
    r"(?:请)?(?:查询|查看|列出|分析)我最近([1-9]|[12][0-9]|3[01])天的睡眠和饮食记录[。.!！]?"
)


def empty_read_answer(executor):
    snapshot = executor._agent_kernel_snapshot
    message = executor._current_turn_user_message or ""
    match = _CLOSED_READ.fullmatch(message)
    if (
        not match or snapshot is None or snapshot.intent.is_write
        or snapshot.envelope.user_id != executor._current_user_id
        or snapshot.context.user_id != executor._current_user_id
        or snapshot.envelope.text != message
        or executor._current_turn_has_attachment
        or getattr(executor, "_agent_kernel_pending_confirmation_tools", None)
        or executor._turn_sync_attempted
        or executor._turn_daily_read_plan is not None
        or executor._force_no_tools_synthesis
    ):
        return None
    scope = resolve_owned_read_scope(snapshot)
    if (
        scope is None or len(scope.queries) != 2
        or {q["dimension"] for q in scope.queries} != {"sleep", "diet"}
        or any(q.get("days") != int(match[1]) for q in scope.queries)
    ):
        return None
    completion = executor._composed_read_completion()
    if (
        completion is None or not completion.complete or completion.missing_dimensions
        or not completion.verified_evidence or executor._unresolved_read_failure_notice()
    ):
        return None
    queries = completion.verified_evidence.get("queries", [])
    if (
        len(queries) != 2
        or [q["query"] for q in queries] != list(scope.queries)
        or any(q.get("availability") != "no_data" or q.get("records") != []
               or q.get("record_count") != 0 for q in queries)
    ):
        return None
    return "本轮各项查询均未返回记录，暂无可供分析的样本，无法判断健康状态。"


def install_empty_read_terminal(executor):
    original = executor._call_llm_stream

    async def project(messages, tools):
        answer = empty_read_answer(executor) if not tools else None
        if answer is not None:
            yield {"type": "content", "text": answer}
            yield {"type": "finish", "finish_reason": "stop"}
            return
        async for event in original(messages, tools):
            yield event

    executor._call_llm_stream = project
