"""Measurement must retain failures and distinguish content from status events."""
import asyncio
from contextlib import nullcontext
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


async def test_stream_records_first_content_and_preserves_tool_proposals():
    from eval.prompt_benchmark_metrics import measure_response

    class Provider:
        async def chat_stream(self, **kwargs):
            yield {'type': 'reasoning', 'text': 'not public content'}
            yield {'type': 'content', 'text': ' '}
            yield {'type': 'content', 'text': 'answer'}
            yield {'type': 'tool_calls', 'tool_calls': [{'id': 'unexpected'}]}
            yield {'type': 'finish', 'finish_reason': 'tool_calls'}

    metrics = {}
    response = await measure_response(Provider(), [], streaming=True, timeout_seconds=1, metrics=metrics)
    assert response == {'content': ' answer', 'tool_calls': [{'id': 'unexpected'}], 'finish_reason': 'tool_calls'}
    assert 0 <= metrics['first_content_seconds'] <= metrics['wall_seconds']


async def test_nonstream_has_no_fabricated_first_token_time():
    from eval.prompt_benchmark_metrics import measure_response

    class Provider:
        async def chat(self, **kwargs):
            return {'content': 'answer', 'finish_reason': 'stop'}

    metrics = {}
    await measure_response(Provider(), [], streaming=False, timeout_seconds=1, metrics=metrics)
    assert metrics['first_content_seconds'] is None
    assert metrics['wall_seconds'] >= 0


@pytest.mark.parametrize('failure', ['timeout', 'truncated', 'error'])
async def test_failure_retains_elapsed_and_closes_generator(failure):
    from eval.prompt_benchmark_metrics import measure_response

    closed = []
    class Provider:
        async def chat_stream(self, **kwargs):
            try:
                yield {'type': 'content', 'text': 'partial'}
                if failure == 'timeout':
                    await asyncio.Event().wait()
                elif failure == 'error':
                    raise RuntimeError('fixture')
            finally:
                closed.append(True)

    metrics = {}
    with pytest.raises((TimeoutError, RuntimeError)):
        await measure_response(Provider(), [], streaming=True, timeout_seconds=.01, metrics=metrics)
    assert closed == [True]
    assert metrics['wall_seconds'] >= metrics['first_content_seconds'] >= 0


def test_summary_preserves_failures_and_missing_api_usage():
    from eval.prompt_benchmark_metrics import summarize_comparisons

    rows = [{'model': 'synthetic', 'variants': [
        {'variant': 'baseline', 'wall_seconds': 1, 'input_tokens': 10, 'output_tokens': 2,
         'token_source': 'api', 'quality': {'deterministic_status': 'pass'}},
        {'variant': 'baseline', 'wall_seconds': 20, 'error_type': 'TimeoutError'},
        {'variant': 'candidate', 'wall_seconds': .5, 'input_tokens': 9, 'output_tokens': 2,
         'token_source': 'api', 'quality': {'deterministic_status': 'fail'}},
    ]}]
    baseline, candidate = summarize_comparisons(rows)
    assert baseline['attempts'] == 2 and baseline['failed_attempts'] == 1
    assert baseline['wall_seconds_all_attempts']['p95'] == 20
    assert baseline['api_input_tokens_known'] == 10
    assert baseline['usage_unknown_attempts'] == 1
    assert baseline['input_tokens_per_passing_contract'] is None
    assert candidate['contract_failures'] == 1
    assert candidate['passing_contracts'] == 0
    assert candidate['input_tokens_per_passing_contract'] is None
    assert candidate['first_content_seconds']['n'] == 0


def test_dry_diagnostics_are_not_latency_samples():
    from eval.prompt_benchmark_metrics import summarize_comparisons

    assert summarize_comparisons([{'model': 'm', 'variants': [{'variant': 'baseline'}]}]) == []


def benchmark_module():
    path = Path(__file__).resolve().parents[2] / 'scripts/benchmark_argument_transport.py'
    spec = importlib.util.spec_from_file_location('benchmark_metrics_test_runner', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_dry_run_reverses_pairs_and_reuses_frozen_payloads(tmp_path):
    benchmark = benchmark_module()
    args = SimpleNamespace(include_live_llm=False, model=['synthetic'], repetitions=2,
                           stream=True, output=tmp_path/'report.json')
    assert await benchmark.run(args) == 0
    report = json.loads(args.output.read_text())
    assert report['planned_calls'] == 16 and report['measurements'] == []
    first, second = report['comparisons'][:2]
    assert [r['variant'] for r in first['variants']] == ['baseline', 'candidate']
    assert [r['variant'] for r in second['variants']] == ['candidate', 'baseline']
    assert first['variants'][0]['payload_sha256'] == second['variants'][1]['payload_sha256']
    indices = [row['call_index'] for comp in report['comparisons'] for row in comp['variants']]
    assert indices == list(range(16))


async def test_budget_is_checked_before_entering_live_environment(tmp_path):
    benchmark = benchmark_module()
    args = SimpleNamespace(include_live_llm=True, model=['synthetic'], repetitions=2,
                           max_api_calls=1, output=tmp_path/'report.json')
    with pytest.raises(ValueError, match='planned_calls_exceed_budget'):
        await benchmark.run(args)
    assert not args.output.exists()


async def test_explicit_usage_failure_does_not_retry_stream_creation(monkeypatch):
    from eval.prompt_benchmark_metrics import measure_response
    from app.services.llm.providers import openai_provider as op

    calls = []
    async def fail_create(**kwargs):
        calls.append(kwargs)
        raise RuntimeError('fixture_stream_options_failure')

    provider = object.__new__(op.OpenAIProvider)
    provider.base_url, provider.model = 'https://synthetic.example.test/v1', 'synthetic'
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail_create)))
    monkeypatch.setattr(provider, '_get_async_client', lambda: client)
    monkeypatch.setattr(op, 'require_ai_consent', lambda **_: None)
    with pytest.raises(RuntimeError, match='fixture_stream_options_failure'):
        await measure_response(provider, [], streaming=True, timeout_seconds=1, metrics={})
    assert len(calls) == 1
    assert calls[0]['stream_options'] == {'include_usage': True}


@pytest.mark.parametrize('cancel', [False, True])
async def test_runner_saves_error_and_restores_retry_configuration(monkeypatch, tmp_path, cancel):
    benchmark = benchmark_module()
    import harness_llm_regression_gate
    import app.database
    from app.config import settings
    from app.models.llm_usage import LlmUsageLog
    from app.services.llm import factory, usage_tracker
    from app.services.llm.providers import openai_provider as op

    monkeypatch.setattr(settings, 'llm_auto_recovery_enabled', True)
    old_retries = op._DEFAULT_MAX_RETRIES
    monkeypatch.setattr(harness_llm_regression_gate, '_live_llm_eval_consent_scope', lambda _: nullcontext())
    monkeypatch.setattr(LlmUsageLog.__table__, 'create', lambda *a, **k: None)
    fake_db = SimpleNamespace(query=lambda _: SimpleNamespace(one=lambda: SimpleNamespace(id=1)))
    monkeypatch.setattr(app.database, 'SessionLocal', lambda: nullcontext(fake_db))
    monkeypatch.setattr(usage_tracker, 'set_caller', lambda *a, **k: None)
    monkeypatch.setattr(usage_tracker, 'summarize_usage_capture', lambda: None)
    async def fail_measure(*a, **kw):
        assert settings.llm_auto_recovery_enabled is False
        assert op._DEFAULT_MAX_RETRIES == 0
        if cancel:
            raise asyncio.CancelledError()
        raise TimeoutError()
    monkeypatch.setattr(factory, 'create_provider_for_model_id', lambda _: object())
    monkeypatch.setattr(benchmark, 'measure_response', fail_measure)
    args = SimpleNamespace(include_live_llm=True, model=['synthetic'], output=tmp_path/'failed.json')
    with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
        await benchmark.run(args)
    report = json.loads(args.output.read_text())
    assert report['status'] == ('cancelled' if cancel else 'failed')
    row = report['comparisons'][0]['variants'][0]
    assert row['error_type'] == ('CancelledError' if cancel else 'TimeoutError')
    assert row['wall_seconds'] >= 0
    assert report['measurements'][0]['failed_attempts'] == 1
    assert settings.llm_auto_recovery_enabled is True and op._DEFAULT_MAX_RETRIES == old_retries
