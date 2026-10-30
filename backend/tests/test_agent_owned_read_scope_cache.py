"""Turn-local owned-read parsing is reused without crossing snapshot boundaries."""

from dataclasses import replace
from datetime import timedelta

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel import read_task_scope
from tests.test_longitudinal_read_scope_policy import snapshot
from tests.test_running_analysis_read_scope import REQUEST


def test_executor_reuses_scope_only_for_the_same_immutable_snapshot(db, monkeypatch):
    executor = AgentExecutor(db)
    initial = snapshot(REQUEST)
    calls = []
    resolve = read_task_scope.resolve_owned_read_scope

    def counted(current):
        calls.append(current)
        return resolve(current)

    monkeypatch.setattr(read_task_scope, "resolve_owned_read_scope", counted)

    first = executor._owned_read_scope_for(initial)
    assert first is executor._owned_read_scope_for(initial)
    assert calls == [initial]

    next_day = replace(
        initial,
        context=replace(
            initial.context,
            current_time=initial.context.current_time + timedelta(days=1),
        ),
    )
    shifted = executor._owned_read_scope_for(next_day)
    assert shifted is not first
    assert shifted.queries[0]["end_date"] != first.queries[0]["end_date"]
    assert calls == [initial, next_day]

    foreign = replace(next_day, context=replace(next_day.context, user_id=42))
    assert executor._owned_read_scope_for(foreign) is None
    assert calls == [initial, next_day, foreign]


def test_executor_does_not_cache_a_scope_resolution_failure(db, monkeypatch):
    executor = AgentExecutor(db)
    turn = snapshot(REQUEST)
    expected = read_task_scope.resolve_owned_read_scope(turn)
    calls = 0

    def flaky(_current):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("synthetic scope failure")
        return expected

    monkeypatch.setattr(read_task_scope, "resolve_owned_read_scope", flaky)

    with pytest.raises(RuntimeError, match="synthetic scope failure"):
        executor._owned_read_scope_for(turn)
    assert executor._owned_read_scope_for(turn) == expected
    assert calls == 2
