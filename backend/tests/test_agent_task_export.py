"""Synthetic owner-isolation and honest-unknown exporter integration tests."""
from datetime import UTC, datetime, timedelta
import json

import pytest

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.agent_runtime import AgentRun
from app.models.client_event import ClientEvent
from app.models.llm_usage import LlmUsageLog
from app.models.user import User
from app.services.agent_task_evaluation import evaluate_tasks
from app.services.agent_task_export import export_agent_task_snapshots

NOW = datetime(2026, 9, 11, 8, tzinfo=UTC)
KEY = b'synthetic-key-never-used-in-production'
TURN = 'turn-42-1789099200000'


def _owner(db, name):
    user = User(username=name, email=f'{name}@example.test', hashed_password='x', name='synthetic')
    db.add(user)
    db.flush()
    return user


def _run(db, owner, label='a', turn=TURN, meta=None):
    conv = AgentConversation(user_id=owner.id, title='PRIVATE-TITLE')
    db.add(conv)
    db.flush()
    message = AgentMessage(conversation_id=conv.id, role='assistant', content='PRIVATE-HEALTH-TEXT',
                           meta=meta or {}, client_turn_id=turn)
    db.add(message)
    db.flush()
    run = AgentRun(run_id=f'run-PRIVATE-{label}', user_id=owner.id, conversation_id=conv.id,
                   assistant_message_id=message.id, client_turn_id=turn,
                   current_attempt_id=f'attempt-PRIVATE-{label}', status='succeeded',
                   created_at=NOW, finished_at=NOW + timedelta(seconds=2))
    db.add(run)
    db.flush()
    return run, message


def _event(db, owner, turn=TURN, **extra):
    db.add(ClientEvent(user_id=owner.id, event_name='agent_turn_milestone', created_at=NOW,
                       meta={'metric_version': 2, 'client_turn_id': turn,
                             'phase': 'first_key_content', 'duration_ms': 123,
                             'action_type': 'diet_record', 'has_image': False, **extra}))


def _usage(db, owner, run_id, **extra):
    row = LlmUsageLog(user_id=owner.id, run_id=run_id, provider='tokenplan', model='synthetic',
                      created_at=NOW, **extra)
    db.add(row)
    return row


def _export(db, owner, **kwargs):
    db.flush()
    return export_agent_task_snapshots(db, user_id=owner.id, hmac_key=KEY,
                                      since=NOW - timedelta(seconds=1),
                                      until=NOW + timedelta(minutes=1), **kwargs)


def test_owner_exact_join_anonymous_projection_and_evaluator_compile(db):
    owner, other = _owner(db, 'owner'), _owner(db, 'other')
    run, _ = _run(db, owner, meta={'perf': {'end_to_end_total_ms': 2500},
                                 'resolution_status': 'no_data', 'content': 'PRIVATE-META',
                                 'revision': 'b' * 40, 'task_outcome': 'satisfied'})
    _run(db, other, 'other', meta={'resolution_status': 'completed'})
    _event(db, owner)
    _event(db, other, duration_ms=999)
    _usage(db, owner, run.run_id, token_source='api', tokenplan_cost_cny=0.02,
           tokenplan_cost_estimated=1, tokenplan_cost_source='synthetic-price-source')
    _usage(db, other, run.run_id, token_source='api', tokenplan_cost_cny=999,
           tokenplan_cost_estimated=1, tokenplan_cost_source='synthetic-price-source')
    exported = _export(db, owner)
    assert len(exported['snapshots']) == 1
    row = exported['snapshots'][0]
    assert row['resolution_status'] == 'no_data'
    assert row['revision'] == 'unknown' and row['logical_task_id'] is None
    assert row['task_type'] == 'diet_record'
    assert row['task_outcome'] == 'unknown' and row['human_verified'] is False
    assert row['cost_cny'] == 0.02 and row['cost_source'] == 'estimate'
    assert row['task_elapsed_ms'] == 2500
    assert row['first_key_content_latency_ms'] == 123
    assert row['verified_content_latency_ms'] is None
    rendered = json.dumps(exported)
    assert 'PRIVATE' not in rendered and TURN not in rendered and 'synthetic-price-source' not in rendered
    group = evaluate_tasks(exported['snapshots'])['groups'][0]
    assert group['task_count'] == 1 and group['cost']['total_cny'] == 0.02
    assert group['verified_satisfaction_rate'] is None


def test_unmatched_alias_legacy_events_and_background_cost_are_separate(db):
    owner = _owner(db, 'owner')
    run, _ = _run(db, owner)
    _event(db, owner, turn='turn-43-1789099200000')
    _event(db, owner, metric_version=1)
    _event(db, owner, client_turn_id=None)
    _usage(db, owner, run.run_id)  # default zero has no provenance
    _usage(db, owner, None, token_source='api', tokenplan_cost_cny=5,
           tokenplan_cost_estimated=1, tokenplan_cost_source='synthetic')
    _usage(db, owner, 'unmatched-run', token_source='estimate')
    out = _export(db, owner)
    assert out['client_event_coverage'] == {
        'observed': 3, 'matched': 0, 'unmatched': 1, 'legacy': 1, 'invalid': 1,
        'ambiguous_phase_count': 0,
    }
    assert out['snapshots'][0]['cost_cny'] is None
    assert out['snapshots'][0]['cost_source'] == 'missing'
    assert out['usage_coverage']['linked_chat']['row_count'] == 1
    assert out['usage_coverage']['linked_chat']['token_sources'] == {'unknown': 1}
    assert out['usage_coverage']['without_run']['known_subtotal_cny'] == 5
    assert out['usage_coverage']['unmatched_run']['row_count'] == 1


def test_foreign_assistant_pointer_cannot_supply_metadata(db):
    owner, other = _owner(db, 'owner'), _owner(db, 'other')
    run, _ = _run(db, owner)
    _, foreign = _run(db, other, 'foreign', meta={'resolution_status': 'completed',
                                                'perf': {'end_to_end_total_ms': 99}})
    run.assistant_message_id = foreign.id
    out = _export(db, owner)
    row = out['snapshots'][0]
    assert row['resolution_status'] == 'unknown' and row['task_elapsed_ms'] is None
    assert out['assistant_metadata_coverage']['unmatched'] == 1


def test_incomplete_cost_and_conflicting_phase_do_not_manufacture_totals(db):
    owner = _owner(db, 'owner')
    run, _ = _run(db, owner)
    _usage(db, owner, run.run_id, token_source='api', tokenplan_cost_cny=0.3,
           tokenplan_cost_source='synthetic', tokenplan_cost_estimated=1)
    _usage(db, owner, run.run_id)
    _event(db, owner)
    _event(db, owner, duration_ms=456)
    out = _export(db, owner)
    assert out['snapshots'][0]['cost_cny'] is None
    assert out['snapshots'][0]['first_key_content_latency_ms'] is None
    assert out['usage_coverage']['linked_chat']['known_subtotal_cny'] == 0.3
    assert out['usage_coverage']['linked_chat']['missing_cost_count'] == 1
    assert out['client_event_coverage']['ambiguous_phase_count'] == 1


def test_time_range_and_hmac_key_are_explicit_and_owner_separated(db):
    owner, other = _owner(db, 'owner'), _owner(db, 'other')
    run, _ = _run(db, owner)
    _run(db, other, 'other')
    out = _export(db, owner)
    assert out['snapshots'][0]['scope_id'] != _export(db, other)['snapshots'][0]['scope_id']
    run.created_at = NOW - timedelta(days=2)
    assert _export(db, owner)['snapshots'] == []
    with pytest.raises(ValueError):
        export_agent_task_snapshots(db, user_id=owner.id, hmac_key=b'bad', since=NOW, until=NOW)
    with pytest.raises(ValueError):
        export_agent_task_snapshots(db, user_id=owner.id, hmac_key=KEY,
                                   since=NOW.replace(tzinfo=None), until=NOW + timedelta(days=1))


def test_output_budget_fails_without_silent_truncation(db):
    owner = _owner(db, 'owner')
    _run(db, owner)
    _run(db, owner, 'second', turn='turn-44-1789099200000')
    with pytest.raises(ValueError, match='budget'):
        _export(db, owner, max_rows=1)


def test_read_only_export_does_not_flush_caller_pending_changes(db):
    owner = _owner(db, 'owner')
    run, _ = _run(db, owner)
    db.autoflush = True
    run.status = 'failed'
    out = export_agent_task_snapshots(db, user_id=owner.id, hmac_key=KEY,
                                     since=NOW - timedelta(seconds=1), until=NOW + timedelta(minutes=1))
    assert out['snapshots'][0]['technical_status'] == 'succeeded'
    assert run in db.dirty


@pytest.mark.parametrize('source', ['', 'unknown', 'unpriced', 'missing'])
def test_unknown_price_provenance_never_makes_zero_known(db, source):
    owner = _owner(db, 'owner')
    run, _ = _run(db, owner)
    _usage(db, owner, run.run_id, token_source='api', tokenplan_cost_cny=0,
           tokenplan_cost_estimated=1, tokenplan_cost_source=source)
    assert _export(db, owner)['snapshots'][0]['cost_cny'] is None


@pytest.mark.parametrize(('outcome', 'resolution'), [
    ({'status': 'blocked', 'tool_failure_count': 2, 'capability_block_count': 3}, 'blocked'),
    ({'status': 'waiting_for_user', 'confirmation_required': True}, 'pending_confirmation'),
    ({'status': 'complete', 'refusal_detected': True, 'category': 'safety_boundary'}, 'unknown'),
    ({'status': 'waiting_for_user', 'confirmation_required': False}, 'unknown'),
])
def test_existing_execution_metadata_maps_only_explicit_resolution_facts(db, outcome, resolution):
    owner = _owner(db, 'owner')
    _run(db, owner, meta={'turn_outcome': outcome})
    row = _export(db, owner)['snapshots'][0]
    assert row['resolution_status'] == resolution
    assert row['tool_failures'] == outcome.get('tool_failure_count')
    assert row['unreviewed_blocks'] == outcome.get('capability_block_count')
    assert row['reviewed_appropriate_blocks'] is None
    assert row['task_outcome'] == 'unknown'
