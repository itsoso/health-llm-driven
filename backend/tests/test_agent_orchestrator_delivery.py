"""Internal attestations, never tool JSON, can supply Pi's final answer."""
import json
from app.services.agent_kernel.types import CapabilityDecision
from unittest.mock import Mock

import pytest

from app.config import settings
from app.models.agent_conversation import AgentMessage
from app.orchestrator.schema import Intent, OrchestratorResponse
from app.services.episode.validator import TextValidationResult
from app.services.orchestrator_delivery import current_report_capture
from tests.test_agent_executor_synthesis_passthrough import _make_executor, _ORCH_SYNTH, _RESYNTH

QUERY = '综合分析一下我的恢复'


@pytest.mark.asyncio
@pytest.mark.parametrize('denial', [None, 'real_gateway', 'delivery_guard', 'off', 'shadow', 'metadata', 'length', 'validation', 'query', 'multi', 'history', 'error', 'cards', 'owner', 'turn', 'nonce', 'cancel'])
async def test_actual_pi_delivery_requires_current_internal_receipt(db, auth_user_and_headers, monkeypatch, denial):
    user, _ = auth_user_and_headers
    monkeypatch.setattr(settings, 'domain_prompt_optimization', True)
    monkeypatch.setattr(settings, 'orchestrator_synthesis_passthrough', denial if denial in ('off', 'shadow') else 'on')
    executor, rounds = _make_executor(db, extra_tool=denial == 'multi')
    orch_db = Mock()

    async def orchestrator(_db, uid, req):
        capture = current_report_capture()
        if capture:
            capture.record_generation({'content': _ORCH_SYNTH, 'finish_reason': 'length' if denial == 'length' else 'stop'}, 'inner-report-model')
            capture.record_validation(_ORCH_SYNTH, None if denial == 'validation' else TextValidationResult(ok=True, action='pass', safe_text=_ORCH_SYNTH))
            capture.seal(req.query, _ORCH_SYNTH, evidence_complete=True, mode='off', persisted_card_ids=[123] if denial == 'cards' else [])
        if denial == 'error':
            raise RuntimeError('synthetic failure')
        if denial == 'cancel':
            import asyncio
            raise asyncio.CancelledError()
        return OrchestratorResponse(query=req.query, intent=Intent(raw_query=req.query), synthesis=_ORCH_SYNTH, safety_action='pass')

    monkeypatch.setattr('app.orchestrator.run_orchestrator', orchestrator)
    async def execute(name, args, token):
        if name != 'health_analysis':
            return '{}'
        # Exercise the actual in-process boundary and fresh DB lifecycle.
        executor._agent_kernel_last_decision = CapabilityDecision(action='allow', reason='test', normalized_tool_name='health_analysis')
        with monkeypatch.context() as local_patch:
            local_patch.setattr('app.database.SessionLocal', lambda: orch_db)
            if denial == 'real_gateway':
                from app.services.agent_executor import AgentExecutor
                executor._agent_kernel_last_decision = None
                result = await AgentExecutor._execute_tool(executor, name, args, token)
            else:
                result = await executor._run_orchestrator_in_process(json.loads(args)['question'])
        receipt = getattr(executor, '_completed_orchestrator_delivery', None)
        if receipt and denial in ('owner', 'turn', 'nonce'):
            from dataclasses import replace
            key, value = {'owner': ('user_id', uid_bad), 'turn': ('turn_id', 'other'), 'nonce': ('tool_call_id', 'other')}[denial]
            executor._completed_orchestrator_delivery = replace(receipt, **{key: value})
        return result
    uid_bad = user.id + 100
    executor._execute_tool = execute
    conversation_id = None
    if denial == 'history':
        from app.services.agent_conversation_service import AgentConversationService
        svc = AgentConversationService(db)
        conv = svc.get_or_create_conversation(user.id, None)
        svc.save_message(conv.id, 'user', '前面的事还没完成')
        svc.save_message(conv.id, 'assistant', '请确认。')
        conversation_id = conv.id
    if denial == 'delivery_guard':
        from app.services import agent_executor as ae
        original_guard = ae.enforce_medical_evidence_boundaries
        def guard(text, **kwargs):
            result = original_guard(text, **kwargs)
            if text == _ORCH_SYNTH:
                result.text = '公共医疗护栏已替换候选回复。'
                result.flagged = True
                result.violations = ['synthetic_delivery_guard']
            return result
        monkeypatch.setattr(ae, 'enforce_medical_evidence_boundaries', guard)
        async def no_repair(**kwargs):
            return None, None
        monkeypatch.setattr(executor, '_repair_incidental_medical_boundary', no_repair)
    kwargs = dict(user_id=user.id, message='顺便' + QUERY if denial == 'query' else QUERY,
                  user_auth_token='test-token', run_id='test-report-run', conversation_id=conversation_id)
    if denial == 'metadata':
        kwargs['extra_context'] = '{"model_id":"other-model"}'
    if denial == 'cancel':
        import asyncio
        with pytest.raises(asyncio.CancelledError):
            _ = [e async for e in executor.run_stream(**kwargs)]
        assert getattr(executor, '_completed_orchestrator_delivery', None) is None
        assert current_report_capture() is None
        orch_db.close.assert_called_once()
        return
    events = [e async for e in executor.run_stream(**kwargs)]
    done = next(e['data'] for e in events if e.get('event') == 'done')
    saved = db.query(AgentMessage).filter_by(role='assistant').order_by(AgentMessage.id.desc()).first()
    chunks = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert chunks == saved.content
    if denial in (None, 'real_gateway', 'delivery_guard'):
        assert len(rounds) == 1
        if denial == 'delivery_guard':
            assert saved.content == '公共医疗护栏已替换候选回复。'
            assert done['medical_boundary_flags'] == ['synthetic_delivery_guard']
        else:
            assert _ORCH_SYNTH in saved.content
        assert _RESYNTH not in saved.content
        assert done['orchestrator_delivery']['outer_model_calls_avoided'] == 1
        assert done['orchestrator_delivery']['model'] == 'inner-report-model'
        assert done['model'] == 'inner-report-model'
        assert saved.meta['model'] == 'inner-report-model'
        assert saved.meta['orchestrator_delivery'] == done['orchestrator_delivery']
        assert done['completion_status'] == ('error' if denial == 'delivery_guard' else 'complete')
    else:
        assert len(rounds) == 2
        assert _RESYNTH in saved.content
        assert 'orchestrator_delivery' not in done
    assert getattr(executor, '_completed_orchestrator_delivery', None) is None
    assert current_report_capture() is None
    orch_db.close.assert_called_once()
