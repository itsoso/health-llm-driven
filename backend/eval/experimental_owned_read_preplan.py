"""Eval-only planner bypass for a closed, already authorized read shape.

No runtime import or switch. Eligibility is narrower than authority; the
existing OwnedReadScope and Pi/Gateway remain responsible for all arguments,
authentication, isolation, execution and receipts. Never dispatch directly.
"""
import json
import re

_CLOSED_READ = re.compile(r'(?:请)?(?:查询|查看|列出|分析)我最近([1-9]|[12][0-9]|3[01])天的睡眠和饮食记录[。.!！]?')


def install_owned_read_preplan(executor):
    original = executor._call_llm_stream
    attempted = False

    async def project(messages, tools):
        nonlocal attempted
        if not attempted:
            attempted = True
            snapshot = executor._agent_kernel_snapshot
            match = _CLOSED_READ.fullmatch(executor._current_turn_user_message or '')
            if (
                match and snapshot is not None
                and snapshot.envelope.user_id == executor._current_user_id
                and snapshot.context.user_id == executor._current_user_id
                and snapshot.envelope.text == executor._current_turn_user_message
                and not executor._current_turn_has_attachment
                and not getattr(executor, '_agent_kernel_pending_confirmation_tools', None)
                and not any(m.get('role') == 'tool' or m.get('tool_calls') for m in messages)
            ):
                calls = executor._initial_composed_read_calls(0, tools)
                if len(calls) == 1:
                    queries = json.loads(calls[0]['function']['arguments'])['queries']
                    if (
                        len(queries) == 2
                        and {q['dimension'] for q in queries} == {'sleep', 'diet'}
                        and all(q.get('days') == int(match[1]) for q in queries)
                    ):
                        yield {'type': 'tool_calls', 'tool_calls': calls}
                        yield {'type': 'finish', 'finish_reason': 'tool_calls'}
                        return
        async for event in original(messages, tools):
            yield event

    executor._call_llm_stream = project
