from types import SimpleNamespace

import pytest

from tests.test_agent_write_retry_recovery import _mixed_retry_fixture


@pytest.mark.parametrize('state', ['proven', 'in_flight', 'uncertain', 'missing_proof', 'extra_unknown'])
def test_settlement_requires_exhaustive_durable_no_effect_proof(state):
    from app.services.agent_executor import _settled_intake_failure_tools
    from app.services.agent_turn_outcome import classify_agent_turn_outcome

    kw = _mixed_retry_fixture()
    meta = kw['meta']
    if state in {'in_flight', 'uncertain'}:
        meta['write_operations']['b']['status'] = state
    elif state == 'missing_proof':
        meta['write_operations']['b'].pop('no_side_effect')
    elif state == 'extra_unknown':
        meta['write_operations']['c'] = {'status': 'in_flight'}
    source = SimpleNamespace(content=kw['source_text'], id=3, conversation_id=2, meta=meta)
    settled = _settled_intake_failure_tools(
        source, owner_id=1, now=kw['now'], failed_tools=['health_record'],
    )
    assert settled == (('health_record',) if state == 'proven' else ())
    outcome = classify_agent_turn_outcome(
        completion_status='error', final_text='部分项目未完成。',
        tool_failure_tools=['health_record'], settled_write_failure_tools=settled,
        dispatch_started=True, write_receipts=meta['write_receipts'],
        action_outcomes=[{'action_id': 'b', 'status': 'failed'}],
    )
    assert outcome['status'] == ('partial' if state == 'proven' else 'reconciliation_required')
