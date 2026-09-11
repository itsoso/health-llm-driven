"""Read-only, owner-scoped local export of anonymous run snapshots.

The caller supplies an authorized owner, bounded UTC-aware window and secret
HMAC key. No API, credentials, production connection or scheduler is created.
Worker attempts cannot be attributed from current usage rows, so each snapshot
represents a whole Run, with no inferred cross-Run logical task identity.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import hmac
import json
import math
import re

from sqlalchemy.orm import Session

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.agent_runtime import AgentRun
from app.models.client_event import ClientEvent
from app.models.llm_usage import LlmUsageLog
from app.services.agent_conversation_service import AgentConversationService
from app.services.agent_task_evaluation import RESOLUTION_STATUSES, TECHNICAL_STATUSES, TASK_TYPES

_TURN_ID = re.compile(r'turn-[0-9]{1,12}-[0-9]{10,16}\Z')
_PHASES = frozenset({
    'local_feedback', 'server_accepted', 'first_useful', 'first_semantic_progress',
    'first_content_painted', 'first_key_content', 'first_interactive',
    'citations_received', 'citations_painted', 'citations_visible', 'write_verified',
})
_ACTIONS = frozenset({'generic', 'diet_record', 'diet_photo', 'medication_record', 'supplement_record'})


def _number(value):
    if type(value) not in (int, float) or value < 0:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _cost(row):
    # cost_usd's historical default zero has no persisted price provenance.
    # Only explicit sourced TokenPlan capacity estimates can be exported today.
    if (row.token_source not in ('api', 'estimate')
            or row.tokenplan_cost_estimated != 1
            or not isinstance(row.tokenplan_cost_source, str)
            or not row.tokenplan_cost_source.strip()
            or row.tokenplan_cost_source.strip().lower() in {'unknown', 'unpriced', 'missing'}
            or not _number(row.tokenplan_cost_cny)):
        return None
    return row.tokenplan_cost_cny


def _sum_cost(values):
    value = float(sum((Decimal(str(item)) for item in values), Decimal(0)))
    if not math.isfinite(value):
        raise ValueError('cost aggregate exceeds numeric range')
    return value


def _usage_stats(rows):
    costs = [cost for row in rows if (cost := _cost(row)) is not None]
    return {
        'row_count': len(rows),
        'known_cost_count': len(costs),
        'missing_cost_count': len(rows) - len(costs),
        'known_subtotal_cny': _sum_cost(costs) if costs else None,
        'total_cny': _sum_cost(costs) if rows and len(costs) == len(rows) else None,
        'cost_sources': dict(Counter('tokenplan_estimate' if _cost(row) is not None else 'unknown'
                                     for row in rows)),
        'token_sources': dict(Counter(row.token_source if row.token_source in ('api', 'estimate')
                                      else 'unknown' for row in rows)),
    }


def export_agent_task_snapshots(
    db: Session, *, user_id: int, hmac_key: bytes,
    since: datetime, until: datetime, max_rows: int = 2000,
) -> dict:
    """Project one owner's exact associations; missing evidence stays unknown.

    All queries have an explicit owner predicate and share the supplied Session.
    For a consistent multi-query export, the caller must provide a read-only
    repeatable-read transaction. This function does not commit or change RLS.
    Window is [since, until), at most 31 days. Each source query is bounded.
    """
    if (type(user_id) is not int or user_id <= 0
            or not isinstance(hmac_key, bytes) or len(hmac_key) < 32
            or type(max_rows) is not int or not 1 <= max_rows <= 10000
            or not isinstance(since, datetime) or not isinstance(until, datetime)
            or since.utcoffset() is None or until.utcoffset() is None
            or not timedelta(0) < until - since <= timedelta(days=31)):
        raise ValueError('invalid export scope, window, key or budget')

    def bounded(query):
        rows = query.execution_options(autoflush=False).limit(max_rows + 1).all()
        if len(rows) > max_rows:
            raise ValueError('export row budget exceeded; narrow the date range')
        return rows

    def opaque(kind, identifier):
        payload = json.dumps([kind, user_id, identifier], separators=(',', ':')).encode()
        return hmac.new(hmac_key, payload, hashlib.sha256).hexdigest()

    # Project metadata columns only; never select conversation or message text.
    runs = bounded(db.query(
        AgentRun.run_id, AgentRun.client_turn_id, AgentRun.status,
        AgentRun.conversation_id, AgentRun.assistant_message_id,
    ).filter(AgentRun.user_id == user_id, AgentRun.created_at >= since, AgentRun.created_at < until)
                   .order_by(AgentRun.run_id))
    run_ids = {run.run_id for run in runs}
    assistants = bounded(db.query(
        AgentMessage.id, AgentMessage.conversation_id, AgentMessage.client_turn_id, AgentMessage.meta,
    ).join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id).filter(
        AgentConversation.user_id == user_id, AgentMessage.role == 'assistant',
        AgentMessage.id.in_([run.assistant_message_id for run in runs if run.assistant_message_id]),
    )) if runs else []
    assistant_by_id = {row.id: row for row in assistants}
    usages = bounded(db.query(
        LlmUsageLog.run_id, LlmUsageLog.token_source, LlmUsageLog.tokenplan_cost_cny,
        LlmUsageLog.tokenplan_cost_estimated, LlmUsageLog.tokenplan_cost_source,
    ).filter(LlmUsageLog.user_id == user_id, LlmUsageLog.created_at >= since,
             LlmUsageLog.created_at < until))
    usage_groups = {'linked_chat': [], 'without_run': [], 'unmatched_run': []}
    usage_by_run = defaultdict(list)
    for row in usages:
        bucket = 'linked_chat' if row.run_id in run_ids else ('without_run' if not row.run_id else 'unmatched_run')
        usage_groups[bucket].append(row)
        if bucket == 'linked_chat':
            usage_by_run[row.run_id].append(row)

    events = bounded(db.query(ClientEvent.meta).filter(
        ClientEvent.user_id == user_id, ClientEvent.event_name == 'agent_turn_milestone',
        ClientEvent.created_at >= since, ClientEvent.created_at < until,
    ))
    event_coverage = dict.fromkeys(('observed', 'matched', 'unmatched', 'legacy', 'invalid', 'ambiguous_phase_count'), 0)
    event_coverage['observed'] = len(events)
    turns = {run.client_turn_id: run.run_id for run in runs if run.client_turn_id}
    events_by_run = defaultdict(list)
    for event in events:
        meta = event.meta if isinstance(event.meta, dict) else {}
        version = meta.get('metric_version', 1)
        if type(version) is int and version == 1:
            event_coverage['legacy'] += 1
            continue
        turn = meta.get('client_turn_id')
        phase = meta.get('phase')
        action = meta.get('action_type')
        duration = meta.get('duration_ms')
        if (type(version) is not int or version != 2
                or not isinstance(turn, str) or not _TURN_ID.fullmatch(turn)
                or not isinstance(phase, str) or phase not in _PHASES
                or not isinstance(action, str) or action not in _ACTIONS
                or type(meta.get('has_image')) is not bool
                or type(duration) is not int or not 0 <= duration <= 300000):
            event_coverage['invalid'] += 1
            continue
        run_id = turns.get(turn)
        if run_id is None:
            event_coverage['unmatched'] += 1
            continue
        event_coverage['matched'] += 1
        events_by_run[run_id].append((phase, duration, action))

    snapshots = []
    assistant_coverage = {'matched': 0, 'unmatched': 0}
    for run in runs:
        assistant = assistant_by_id.get(run.assistant_message_id)
        owned = (
            assistant is not None and assistant.conversation_id == run.conversation_id
            and bool(run.client_turn_id)
            and (
                assistant.client_turn_id == AgentConversationService._client_turn_storage_key(user_id, run.client_turn_id)
                or (_TURN_ID.fullmatch(run.client_turn_id) is not None
                    and assistant.client_turn_id == run.client_turn_id)
            )
        )
        assistant_coverage['matched' if owned else 'unmatched'] += 1
        meta = assistant.meta if owned and isinstance(assistant.meta, dict) else {}
        phases = defaultdict(set)
        actions = set()
        for phase, duration, action in events_by_run[run.run_id]:
            phases[phase].add(duration)
            actions.add(action)
        event_coverage['ambiguous_phase_count'] += sum(len(values) > 1 for values in phases.values())
        key_times = phases['first_key_content']
        task_type = next(iter(actions)) if len(actions) == 1 else 'other'
        if task_type not in TASK_TYPES:
            task_type = 'other'
        perf = meta.get('perf') if isinstance(meta.get('perf'), dict) else {}
        elapsed = perf.get('end_to_end_total_ms')
        resolution = meta.get('resolution_status', 'unknown')
        outcome = meta.get('turn_outcome') if isinstance(meta.get('turn_outcome'), dict) else {}
        if resolution == 'unknown':
            if outcome.get('status') == 'blocked':
                resolution = 'blocked'
            elif outcome.get('status') == 'waiting_for_user' and outcome.get('confirmation_required') is True:
                resolution = 'pending_confirmation'

        def observed_count(field):
            value = outcome.get(field)
            return value if type(value) is int and value >= 0 else None

        cost = _usage_stats(usage_by_run[run.run_id])['total_cny']
        snapshots.append({
            'scope_id': opaque('owner', None),
            'attempt_id': opaque('run-snapshot', run.run_id),
            'logical_task_id': None,
            'attempt_index': 1,
            'revision': 'unknown',
            'task_type': task_type,
            'technical_status': run.status if run.status in TECHNICAL_STATUSES else 'unknown',
            'resolution_status': resolution if resolution in RESOLUTION_STATUSES else 'unknown',
            'human_verified': False,
            'task_outcome': 'unknown',
            'task_elapsed_ms': elapsed if _number(elapsed) else None,
            'first_key_content_latency_ms': next(iter(key_times)) if len(key_times) == 1 else None,
            'verified_content_latency_ms': None,
            'tool_failures': observed_count('tool_failure_count'),
            'unreviewed_blocks': observed_count('capability_block_count'),
            'reviewed_appropriate_blocks': None,
            'cost_cny': cost,
            'cost_source': 'estimate' if cost is not None else 'missing',
        })
    return {
        'schema_version': 'agent-task-export.v1',
        'snapshots': snapshots,
        'client_event_coverage': event_coverage,
        'assistant_metadata_coverage': assistant_coverage,
        'usage_coverage': {name: _usage_stats(rows) for name, rows in usage_groups.items()},
        'limitations': [
            'Local Session export only; no production scheduling or deployed-version attribution.',
            'One whole-Run snapshot, not worker-attempt attribution; logical IDs and revisions remain unknown.',
            'Exact owner and turn/run joins only; semantic aliases and legacy events remain unmatched.',
            'Client key-content paint is not verified content or a human/clinical outcome.',
            'Costs cover only observed, explicitly sourced TokenPlan estimates; USD defaults are not priced evidence.',
            'Usage without a run is separate and may include background or unattributed calls; never allocated to chat.',
            'Run creation, events and usage use a half-open window; Run state and linked metadata are current snapshots, not historical state at the cutoff.',
            'Caller supplies a read-only repeatable-read transaction for snapshot consistency and protects the HMAC key.',
        ],
    }
