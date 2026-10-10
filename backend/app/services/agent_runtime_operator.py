"""Root-only server recovery; preserve unresolved Runs and acknowledge admission."""
from __future__ import annotations
import hashlib
import json
import os
import re
import socket
import sys

from sqlalchemy import func
from app.models.agent_runtime import AgentRun, AgentRunEvent, AgentRuntimeRolloutEvent, AgentRuntimeRolloutState
from app.services.agent_runtime_rollout import RolloutTransition


def require_server_operator() -> None:
    # The CLI is available only through the existing authenticated server access
    # plane. No HTTP route accepts this authority or a caller-supplied actor.
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise PermissionError('authenticated_server_root_required')


class ServerRuntimeRecovery:
    def __init__(self, db):
        self.db = db

    def _state(self, *, lock=False):
        query = self.db.query(AgentRuntimeRolloutState).filter_by(id=1).populate_existing()
        if lock:
            query = query.with_for_update()
        state = query.one_or_none()
        if state is None:
            raise ValueError('runtime_control_missing')
        return state

    def _manifest(self, state):
        event_count = self.db.query(func.count(AgentRunEvent.id)).filter(
            AgentRunEvent.event_name == 'run.reconciliation_required'
        ).scalar()
        if int(event_count or 0) != int(state.reconciliation_generation):
            raise ValueError('runtime_generation_ledger_mismatch')
        rows = self.db.query(AgentRun.run_id).filter_by(status='reconciliation_required').order_by(AgentRun.run_id).limit(1001).all()
        if len(rows) > 1000:
            raise ValueError('operator_review_scope_exceeded')
        digest = hashlib.sha256(json.dumps([row[0] for row in rows], separators=(',', ':')).encode()).hexdigest()
        return {
            'version': int(state.version),
            'generation': int(state.reconciliation_generation),
            'acknowledged_generation': int(state.reconciliation_acknowledged_generation),
            'unresolved_count': len(rows),
            'unresolved_sha256': digest,
            'operator_uid': 0,
            'operator_host_sha256': hashlib.sha256(socket.gethostname().encode()).hexdigest(),
            'decision': 'resume_future_admission_preserve_unknown',
        }

    def review(self):
        require_server_operator()
        state = self._state()
        if state.status != 'paused' or state.reason_code != 'reconciliation_detected':
            raise ValueError('operator_recovery_requires_reconciliation_pause')
        return self._manifest(state)

    def resume(self, reviewed):
        require_server_operator()
        if (type(reviewed) is not dict
                or set(reviewed) != {'version', 'generation', 'acknowledged_generation', 'unresolved_count', 'unresolved_sha256', 'operator_uid', 'operator_host_sha256', 'decision'}
                or any(type(reviewed.get(key)) is not int or reviewed[key] < 0 for key in ('version', 'generation', 'acknowledged_generation', 'unresolved_count', 'operator_uid'))
                or reviewed['operator_uid'] != 0
                or reviewed['decision'] != 'resume_future_admission_preserve_unknown'
                or any(type(reviewed.get(key)) is not str or not re.fullmatch('[0-9a-f]{64}', reviewed[key]) for key in ('unresolved_sha256', 'operator_host_sha256'))):
            raise ValueError('invalid_operator_review')
        try:
            state = self._state(lock=True)
            if state.status == 'active':
                event = self.db.query(AgentRuntimeRolloutEvent).order_by(AgentRuntimeRolloutEvent.id.desc()).first()
                if (event and event.actor_kind == 'operator' and event.operator_review == reviewed
                        and state.reconciliation_generation == reviewed.get('generation')
                        and state.reconciliation_acknowledged_generation == reviewed.get('generation')
                        and state.version == reviewed.get('version', -2) + 1):
                    self.db.commit()
                    return RolloutTransition(False, 'active', None)
                raise ValueError('operator_review_changed')
            if state.reason_code != 'reconciliation_detected' or reviewed != self._manifest(state):
                raise ValueError('operator_review_changed')
            # Never modify Run/Attempt/tool/receipt records and never dispatch.
            state.status = 'active'
            state.reason_code = None
            state.version += 1
            state.updated_by_user_id = None
            state.reconciliation_acknowledged_generation = state.reconciliation_generation
            self.db.add(AgentRuntimeRolloutEvent(
                action='resume', actor_kind='operator', reason_code='manual_resume',
                actor_user_id=None, operator_review=dict(reviewed),
                reconciliation_runs=reviewed['unresolved_count'],
            ))
            self.db.commit()
            return RolloutTransition(True, 'active', None)
        except Exception:
            self.db.rollback()
            raise
