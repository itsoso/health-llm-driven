"""A meal update requires a fresh owned row and an independently derived patch."""
from dataclasses import replace

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.types import ActionableReference, ToolExecutionRequest
from app.services.agent_executor import _parse_explicit_diet_correction, _diet_correction_update_data
from tests.test_longitudinal_read_scope_policy import snapshot

TEXT = '修改今天午餐记录，我只吃了五分之一'
ROW = {'id': 1040, 'record_date': '2026-09-13', 'meal_type': 'lunch',
       'food_items': '合成餐', 'calories': 900, 'protein': 40}


def turn(text=TEXT, rows=None):
    state = snapshot(text)
    return replace(state, actionable_references=(ActionableReference(
        kind='owner_scoped_health_manage_list', data={'record_type': 'diet',
        'records': tuple(rows if rows is not None else [ROW])}),))


def args():
    correction = _parse_explicit_diet_correction(TEXT, reference_now=snapshot().context.current_time)
    return {'record_type': 'diet', 'operation': 'update', 'record_id': ROW['id'],
            'data': _diet_correction_update_data(correction, ROW)}


def decision(state, arguments=None):
    return decide_tool_capability(state, ToolExecutionRequest('health_manage', arguments or args()))


def test_fresh_owned_row_authorizes_only_derived_absolute_portion():
    result = decision(turn())
    assert result.action == 'allow', result.reason
    assert result.normalized_args == args()


@pytest.mark.parametrize('rows', [[], [{**ROW, 'record_date': '2026-09-12'}],
                                  [{**ROW, 'meal_type': 'dinner'}],
                                  [ROW, {**ROW, 'id': 1041}]])
def test_missing_wrong_date_meal_or_ambiguous_record_denies_patch(rows):
    assert decision(turn(rows=rows)).action == 'block'


@pytest.mark.parametrize('patch', [{'record_id': 1041}, {'owner_id': 42},
    {'data': {'meal_type': 'lunch', 'calories': 1}},
    {'data': {**args()['data'], 'calories': 1}},
    {'data': {**args()['data'], 'protein': True}},
])
def test_model_patch_and_identity_cannot_be_substituted(patch):
    assert decision(turn(), {**args(), **patch}).action == 'block'


@pytest.mark.parametrize('text', ['不要' + TEXT, '假如' + TEXT, '解释例句：“' + TEXT + '”'])
def test_non_authorizing_text_cannot_use_valid_row_and_patch(text):
    assert decision(turn(text)).action == 'block'


def test_latest_meal_uses_same_ordering_and_freshness_evidence_as_normalizer():
    text = '修改上一餐，只吃了五分之一'
    row = {**ROW, 'created_at': '2026-09-13T08:00:00+08:00'}
    state = turn(text, [row])
    correction = _parse_explicit_diet_correction(text, reference_now=state.context.current_time)
    arguments = {**args(), 'data': _diet_correction_update_data(correction, row)}
    assert decision(state, arguments).action == 'allow'
    for records in ([row, {**row, 'id': 1041}],
                    [{**row, 'record_date': '2026-09-10'}],
                    [{**row, 'created_at': '2026-09-14T08:00:00+08:00'}]):
        assert decision(turn(text, records), arguments).action == 'block'
def test_portion_receipt_grammar_changes_capability_contract(monkeypatch):
    import re
    from app.services import agent_diet_continuation
    from app.services.agent_kernel.capability_policy import capability_policy_contract_payload

    original = capability_policy_contract_payload()
    monkeypatch.setattr(agent_diet_continuation, "_BARE_PORTION", re.compile(r"synthetic-changed-grammar"))
    assert capability_policy_contract_payload() != original
