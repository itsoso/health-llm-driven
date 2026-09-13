"""Frozen multi-domain reads cannot delegate broader reads or persisted analysis."""
from dataclasses import replace
from datetime import datetime
import json

import pytest

from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.tool_gateway import ToolGateway
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot
from tests.test_agent_longitudinal_read_regression import _decide
from tests.test_agent_read_repair_round_budget import (
    ANSWER, GOOD, QUERY, batch_trace, consume,
    _isolate_twin_cache as _isolate_twin_cache,
    clock as clock, four_domain_user as four_domain_user, owned_data as owned_data,
)


ANALYSIS_TYPES = ('comprehensive', 'sleep_insight', 'heart_rate_insight', 'recovery_status',
                  'risk_factors', 'trend', 'supplement_effectiveness', 'orchestrator')
EXPECTED_TOOLS = {'health_query', 'health_query_batch', 'knowledge_search'}


def snapshot():
    envelope = AgentEnvelope(user_id=41, channel='typed', text=QUERY)
    context = ExecutionContext(current_time=datetime.fromisoformat('2026-09-13T09:00:00+08:00'),
                               timezone='Asia/Shanghai', user_id=41, channel='typed')
    return TurnSnapshot(envelope, context, build_intent_frame(envelope, context))


@pytest.mark.parametrize('subtype', ANALYSIS_TYPES)
@pytest.mark.parametrize('days', [1, 365])
def test_broad_analysis_cannot_escape_frozen_multi_read(subtype, days):
    result = _decide(QUERY, 'health_analysis', {'analysis_type': subtype, 'days': days})
    assert result.action == 'block'
    assert result.reason == 'owned_read_tool_out_of_scope'


@pytest.mark.parametrize('tool,args', [
    ('health_manage', {'operation': 'list', 'record_type': 'mood'}),
    ('health_manage', {'operation': 'create', 'record_type': 'medication'}),
    ('health_manage', {'operation': 'delete', 'record_type': 'diet'}),
    ('web_search', {'query': 'synthetic'}),
])
def test_other_tools_cannot_widen_multi_read(tool, args):
    assert _decide(QUERY, tool, args).action == 'block'


@pytest.mark.parametrize('subtype', ANALYSIS_TYPES)
@pytest.mark.parametrize('mode', ['enforce', 'shadow'])
@pytest.mark.asyncio
async def test_gateway_denies_before_any_analysis_side_effect(db, subtype, mode):
    from app.models.health_analysis_cache import HealthAnalysisCache
    from app.models.action_card import ActionCard
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.models.memory_fact import MemoryFact
    from app.models.agent_audit_log import AgentAuditLog
    models = (HealthAnalysisCache, ActionCard, ClinicalJournalEntry, MemoryFact, AgentAuditLog)
    before = [db.query(model).count() for model in models]
    calls = []

    async def dispatch(request):
        calls.append(request)
        return '{"status":"success"}'

    result = await ToolGateway(replace(snapshot(), policy_mode=mode)).execute(
        ToolExecutionRequest('health_analysis', {'analysis_type': subtype, 'days': 365}), dispatch,
    )
    assert not calls
    assert json.loads(result.content)['dispatch_started'] is False
    assert [db.query(model).count() for model in models] == before


@pytest.mark.parametrize('panel', [False, True])
@pytest.mark.asyncio
async def test_multi_read_exposes_only_canonical_schemas(db, four_domain_user, monkeypatch, panel):
    trace = batch_trace(db, monkeypatch, [GOOD, ANSWER])
    done, _ = await consume(db, trace, four_domain_user, panel=panel)
    assert done['turn_outcome']['status'] == 'complete'
    assert {tool['function']['name'] for tool in trace.calls[0][1]} == EXPECTED_TOOLS


@pytest.mark.parametrize('panel', [False, True])
@pytest.mark.asyncio
async def test_broad_analysis_rejection_recovers_with_canonical_reads(db, four_domain_user, monkeypatch, panel):
    trace = batch_trace(db, monkeypatch, [
        [('health_analysis', {'analysis_type': 'orchestrator', 'days': 365})], GOOD, ANSWER,
    ])
    done, saved = await consume(db, trace, four_domain_user, panel=panel)
    assert done['completion_status'] == 'complete'
    assert done['turn_outcome']['status'] == 'complete'
    assert ANSWER in saved.content
    assert [r.tool_name for r in trace.dispatches] == ['health_query_batch']
    assert all(g['status'] == 'verified' for g in done['turn_outcome']['goals'])


def test_non_owned_analysis_retains_existing_capability():
    assert _decide('解释HRV的含义', 'health_analysis', {'analysis_type': 'comprehensive'}).action == 'allow'


@pytest.mark.parametrize('tool,args', [
    ('health_query', {'dimension': 'sleep', 'days': 30}),
    ('health_query_batch', {'queries': [{'dimension': 'sleep', 'days': 30}]}),
])
def test_allowed_tool_still_checks_frozen_window(tool, args):
    result = _decide(QUERY, tool, args)
    assert result.action == 'block'
    assert result.reason == 'health_query_calendar_window_conflict'


def test_schema_filter_uses_authorization_allowlist_without_adding_tools():
    from app.services.agent_input_tool_scope import scope_tools_for_owned_read
    from app.services.agent_kernel.read_task_scope import (
        OWNED_MULTI_READ_TOOL_NAMES, resolve_owned_read_scope, read_task_scope_contract_payload,
    )
    from app.services.tool_schema_registry import get_health_tools
    tools = get_health_tools()
    scope = resolve_owned_read_scope(snapshot())
    filtered = scope_tools_for_owned_read(tools, scope)
    assert {t['function']['name'] for t in filtered} == OWNED_MULTI_READ_TOOL_NAMES == EXPECTED_TOOLS
    assert read_task_scope_contract_payload()['multi_read_tool_names'] == sorted(EXPECTED_TOOLS)
    assert scope_tools_for_owned_read([], scope) == []
    knowledge_only = get_health_tools(subset=['knowledge_search'])
    assert scope_tools_for_owned_read(knowledge_only, scope) == knowledge_only
    assert scope_tools_for_owned_read(tools, None) is tools
    assert scope_tools_for_owned_read(tools, replace(scope, queries=scope.queries[:1])) is tools
