"""Lossless argument transport experiment must not enter application runtime."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from eval.experimental_argument_transport import compact_call_arguments


def call(arguments):
    return {'role': 'assistant', 'content': '保留原话', 'tool_calls': [{
        'id': 'synthetic-call', 'type': 'function', 'function': {
            'name': 'health_record', 'arguments': arguments,
        }, 'extension': {'keep': True},
    }]}


def test_compacts_only_argument_whitespace_without_reserializing():
    raw = r'{ "amount": 0.50000000000000001, "amount": 500, "text": "两  格\n\u4e2d", "n": 1e-20 }'
    messages = [call(raw), {'role': 'user', 'content': raw},
                {'role': 'tool', 'content': raw}]
    before = deepcopy(messages)
    result = compact_call_arguments(messages)
    assert messages == before
    assert result[0]['tool_calls'][0]['function']['arguments'] == r'{"amount":0.50000000000000001,"amount":500,"text":"两  格\n\u4e2d","n":1e-20}'
    assert result[0]['content'] == before[0]['content']
    assert result[0]['tool_calls'][0]['extension'] == {'keep': True}
    assert result[1:] == before[1:]
    assert compact_call_arguments(result) == result


@pytest.mark.parametrize('arguments', ['{ "x": NaN }', '{ "x": Infinity }',
    '{ "x": 01 }', '{ "x":', 'opaque failure', '{' * 1500, None, {},
    '{ "text": "raw\nline" }'])
def test_invalid_arguments_are_not_repaired(arguments):
    messages = [call(arguments)]
    assert compact_call_arguments(messages) == messages


def test_non_assistant_and_specialized_calls_remain_opaque():
    messages = [dict(call('{ "x": 1 }'), role='user'),
                {'role': 'assistant', 'tool_calls': [{'type': 'custom', 'input': '{ "x": 1 }'}]},
                {'role': 'assistant', 'content': [{'type': 'text', 'text': '{ "x": 1 }'}]}]
    assert compact_call_arguments(messages) == messages


def test_frozen_benchmark_changes_only_argument_whitespace():
    from eval.prompt_projection_quality import synthetic_projection_cases

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('argument_benchmark', root / 'scripts/benchmark_argument_transport.py')
    benchmark = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(benchmark)
    for case in synthetic_projection_cases():
        if case.stage != 'answer':
            continue
        payloads = benchmark.variants(case)
        baseline, restored = payloads['baseline'], deepcopy(payloads['candidate'])
        assert restored != baseline
        for old, new in zip(baseline, restored):
            for old_call, new_call in zip(old.get('tool_calls', []), new.get('tool_calls', [])):
                old_args = old_call['function']['arguments']
                new_args = new_call['function']['arguments']
                assert json.loads(old_args) == json.loads(new_args)
                new_call['function']['arguments'] = old_args
        assert restored == baseline


def test_experiment_has_no_application_import():
    root = Path(__file__).resolve().parents[1] / 'app'
    assert not any('experimental_argument_transport' in path.read_text()
                   for path in root.rglob('*.py'))
