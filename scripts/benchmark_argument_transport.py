#!/usr/bin/env python3
"""Frozen synthetic A/B; dry-run by default; never executes proposed tools.

The candidate lives exclusively in eval. Tokenizer counts are diagnostic,
not Qwen API billing. Live quality failures produce a nonzero exit code.
"""
import argparse
import asyncio
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))

from eval.experimental_argument_transport import compact_call_arguments
from eval.prompt_projection_quality import build_case_messages, evaluate_projection_response, synthetic_projection_cases
from app.services.llm.prompt_transport import compact_tool_json
from eval.prompt_benchmark_metrics import measure_response, summarize_comparisons


def variants(case):
    baseline = compact_tool_json(build_case_messages(case,
        '只根据合成工具回执回答；失败不能声称成功，缺失不等于正常。'
        '保留日期、来源和限制；不得诊断或推算未验证的ODI。'))
    candidate = compact_call_arguments(baseline)
    return {'baseline': baseline, 'candidate': candidate}


async def run(args, *, variant_builder=variants, source_paths=None,
              caller='eval.argument_transport'):
    repetitions = getattr(args, 'repetitions', 1)
    streaming = getattr(args, 'stream', False)
    timeout_seconds = getattr(args, 'timeout_seconds', 90)
    max_api_calls = getattr(args, 'max_api_calls', 64)
    cases = [c for c in synthetic_projection_cases() if c.stage == 'answer']
    planned_calls = len(cases) * len(args.model) * 2 * repetitions
    if not 1 <= repetitions <= 10 or not 0 < timeout_seconds <= 300 or max_api_calls < 1:
        raise ValueError('invalid_benchmark_budget')
    if args.include_live_llm and planned_calls > max_api_calls:
        raise ValueError('planned_calls_exceed_budget')
    report = {'status': 'running' if args.include_live_llm else 'dry_run',
              'candidate_disposition': 'experimental_not_runtime',
              'batch_id': uuid4().hex, 'phase': 'answer', 'stream': streaming,
              'repetitions': repetitions, 'planned_calls': planned_calls,
              'max_api_calls': max_api_calls, 'timeout_seconds_per_call': timeout_seconds,
              'max_output_tokens_per_call': 1200,
              'order': 'Paired baseline/candidate; reverse order on alternating repetitions and cases.',
              'models': args.model, 'comparisons': [],
              'source_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                  for path in (source_paths or ('backend/eval/experimental_argument_transport.py',
                               'backend/eval/prompt_projection_quality.py',
                               'backend/app/services/llm/prompt_transport.py',
                               'backend/eval/prompt_benchmark_metrics.py',
                               'scripts/benchmark_argument_transport.py'))},
              'limits': ['Fixed synthetic answer-stage replay; no tools executed.',
                         'Tokenizer diagnostics are not API usage or whole-task savings.',
                         'Semantic noninferiority, persistence and production latency remain unknown.',
                         'No cold-cache or warm-cache claim; cached tokens only from API usage.',
                         'Fail fast on call/usage errors; unattempted samples remain missing.']}
    def save():
        report['measurements'] = summarize_comparisons(report['comparisons'])
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    save()
    try:
        import tiktoken
        encoding = tiktoken.get_encoding('cl100k_base')
    except ImportError:
        encoding = None
    from harness_llm_regression_gate import _live_llm_eval_consent_scope
    with ExitStack() as stack:
        stack.enter_context(_live_llm_eval_consent_scope(args.include_live_llm))
        if args.include_live_llm:
            from app.config import settings
            from app.database import engine, SessionLocal
            from app.models.llm_usage import LlmUsageLog
            from app.models.user import User
            from app.services.llm.factory import create_provider_for_model_id
            from app.services.llm.usage_tracker import begin_usage_capture, end_usage_capture, summarize_usage_capture, set_caller
            from app.services.llm.providers import openai_provider
            stack.enter_context(patch.object(openai_provider, '_DEFAULT_MAX_RETRIES', 0))
            stack.enter_context(patch.object(settings, 'llm_auto_recovery_enabled', False))
            LlmUsageLog.__table__.create(engine, checkfirst=True)
            with SessionLocal() as db:
                user_id = db.query(User).one().id
        for index, case in enumerate(cases):
            payloads = variant_builder(case)
            for model, repeat in ((model, repeat) for model in args.model for repeat in range(repetitions)):
                comparison = {'case': case.id, 'model': model, 'repeat': repeat, 'variants': []}
                report['comparisons'].append(comparison)
                order = ('baseline', 'candidate') if (index + repeat) % 2 == 0 else ('candidate', 'baseline')
                for name in order:
                    messages = payloads[name]
                    row = {'variant': name, 'sample_id': f'{case.id}:{model}:{repeat}:{name}',
                           'call_index': sum(len(c['variants']) for c in report['comparisons']),
                           'payload_sha256': hashlib.sha256(
                        json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}
                    comparison['variants'].append(row)
                    if encoding is not None:
                        row['diagnostic_tokenizer'] = 'cl100k_base'
                        row['diagnostic_message_json_tokens'] = len(encoding.encode(
                            json.dumps(messages, ensure_ascii=False, separators=(',', ':')),
                            disallowed_special=()))
                    if args.include_live_llm:
                        set_caller(caller, user_id=user_id)
                        capture = begin_usage_capture()
                        started = perf_counter()
                        try:
                            response = await measure_response(create_provider_for_model_id(model), messages,
                                streaming=streaming, timeout_seconds=timeout_seconds, metrics=row)
                            usage = summarize_usage_capture()
                            if not usage or usage['calls'] != 1 or usage.get('failed_calls') or any(
                                item['token_source'] != 'api' for item in usage['items']):
                                raise RuntimeError('non_single_api_usage')
                            row.update(input_tokens=usage['prompt_tokens'], output_tokens=usage['completion_tokens'],
                                cached_tokens=[item.get('cached_tokens') for item in usage['items']],
                                provider_calls=usage['calls'], token_source='api',
                                actual_models=usage.get('models'),
                                response={k: response[k] for k in ('content', 'tool_calls', 'finish_reason') if k in response},
                                quality=evaluate_projection_response(case, response, authorized_tool_names=set()).to_dict())
                        except (Exception, asyncio.CancelledError) as exc:
                            row['error_type'] = type(exc).__name__
                            row.setdefault('wall_seconds', perf_counter() - started)
                            row.setdefault('first_content_seconds', None)
                            usage = summarize_usage_capture()
                            row['provider_calls'] = usage['calls'] if usage else 0
                            if usage and all(item['token_source'] == 'api' for item in usage['items']):
                                row.update(input_tokens=usage['prompt_tokens'], output_tokens=usage['completion_tokens'],
                                    cached_tokens=[item.get('cached_tokens') for item in usage['items']], token_source='api')
                            report['status'] = 'cancelled' if isinstance(exc, asyncio.CancelledError) else 'failed'
                            save()
                            raise
                        finally:
                            end_usage_capture(capture)
                    save()
        if args.include_live_llm:
            report['status'] = 'passed_contracts' if all(row['quality']['deterministic_status'] == 'pass'
                for comparison in report['comparisons'] for row in comparison['variants']) else 'failed_contracts'
        save()
    return 0 if report['status'] in ('dry_run', 'passed_contracts') else 1


def add_run_options(parser):
    parser.add_argument('--include-live-llm', action='store_true')
    parser.add_argument('--model', action='append', default=None)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=1)
    parser.add_argument('--stream', action='store_true', help='Measure first content via provider streaming')
    parser.add_argument('--max-api-calls', type=int, default=64)
    parser.add_argument('--timeout-seconds', type=float, default=90)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_run_options(parser)
    args = parser.parse_args()
    args.model = args.model or ['qwen3.8-flash', 'qwen3.8-max']
    try:
        return asyncio.run(run(args))
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
