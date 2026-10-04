"""The comparison must isolate one provider-only description change."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('record_prompt_benchmark', Path(__file__).resolve().parents[2] / 'scripts/benchmark_record_prompt_projection.py')
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def payload():
    return {'messages': [{'role': 'user', 'content': 'synthetic'}], 'tools': [{'function': {
        'name': 'health_record', 'parameters': {'required': ['record_type', 'data'], 'properties': {
            'record_type': {'enum': ['water', 'diet']}, 'data': {'description': 'all examples', 'type': 'object'},
        }},
    }}]}


def test_same_payload_and_description_only_are_valid_controls():
    before = payload()
    after = deepcopy(before)
    benchmark.require_description_only_difference(before, after)
    after['tools'][0]['function']['parameters']['properties']['data']['description'] = 'water example'
    benchmark.require_description_only_difference(before, after)
    assert before['tools'][0]['function']['parameters']['properties']['data']['description'] == 'all examples'


@pytest.mark.parametrize('change', ['messages', 'required', 'enum', 'tools', 'data_type'])
def test_benchmark_cannot_credit_other_changes_to_description_projection(change):
    before = payload()
    after = deepcopy(before)
    params = after['tools'][0]['function']['parameters']
    if change == 'messages':
        after['messages'] = []
    elif change == 'required':
        params['required'] = []
    elif change == 'enum':
        params['properties']['record_type']['enum'] = ['water']
    elif change == 'tools':
        after['tools'] = []
    else:
        params['properties']['data']['type'] = 'string'
    with pytest.raises(ValueError, match='more_than'):
        benchmark.require_description_only_difference(before, after)


async def test_candidate_is_opt_in_and_does_not_mutate_application(monkeypatch):
    from app.config import settings
    from app.services.agent_executor import AgentExecutor

    monkeypatch.setattr(settings, 'domain_prompt_optimization', True)
    monkeypatch.setattr(settings, 'agent_base_url', None)
    monkeypatch.setattr(settings, 'agent_api_key', None)
    case = next(c for c in benchmark.synthetic_projection_cases() if c.id == 'water_typed_milliliter')
    original_method = AgentExecutor._model_tools_for_turn
    before = await benchmark.capture_payload(case, enabled=False, user_id=41)
    candidate = await benchmark.capture_payload(case, enabled=True, user_id=41)
    after = await benchmark.capture_payload(case, enabled=False, user_id=41)
    assert before == after
    assert candidate != before
    benchmark.require_description_only_difference(before, candidate)
    assert AgentExecutor._model_tools_for_turn is original_method
