#!/usr/bin/env python3
"""Compare frozen synthetic provider inputs; live API evaluation is opt-in.

Replays a rejected candidate isolated in backend/eval, never runtime-enabled.
Requires disposable test configuration for live consent. Never executes model
proposed tools. Output contains synthetic fixtures/replies, not user records.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from eval.prompt_projection_quality import (  # noqa: E402
    build_case_messages, evaluate_projection_response, synthetic_projection_cases,
)

SOURCES = (
    'backend/app/services/agent_executor.py',
    'backend/app/services/agent_tool_prompt_projection.py',
    'backend/eval/experimental_record_projection.py',
    'backend/app/services/tool_schema_registry.py',
    'backend/eval/prompt_projection_quality.py',
    'scripts/benchmark_record_prompt_projection.py',
)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class _CaptureProvider:
    model = 'synthetic-input-capture'

    def __init__(self):
        self.calls = []

    async def chat(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        return {'content': 'synthetic capture only', 'finish_reason': 'stop'}


async def capture_payload(case, *, enabled: bool, user_id: int):
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.goal_spec import compile_goal_spec
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, TurnSnapshot
    from app.services.health_worldview import worldview_prompt_blob
    from app.services.tool_schema_registry import get_health_tools

    envelope = AgentEnvelope(user_id=user_id, channel='typed', text=case.query)
    context = ExecutionContext(current_time=datetime.fromisoformat('2026-10-04T10:00:00+08:00'),
                               timezone='Asia/Shanghai', user_id=user_id, channel='typed')
    intent = build_intent_frame(envelope, context)
    goal = compile_goal_spec(envelope=envelope, context=context, intent=intent)
    executor = AgentExecutor(None)
    executor._current_user_id = user_id
    executor._current_turn_user_message = case.query
    executor._agent_kernel_snapshot = TurnSnapshot(envelope, context, intent, goal=goal)
    if enabled:
        from eval.experimental_record_projection import project_owned_record_data_descriptions

        # Benchmark-local injection only. The rejected candidate has no runtime
        # switch or import; the application always retains full record prose.
        original_projection = executor._model_tools_for_turn
        def experimental_projection(tools):
            return project_owned_record_data_descriptions(
                original_projection(tools), executor._agent_kernel_snapshot,
                user_id=user_id, current_message=case.query,
            )
        executor._model_tools_for_turn = experimental_projection
    capture = _CaptureProvider()
    executor._resolve_chat_provider = lambda tools: (capture, tools)
    system = (
        '按用户本轮要求完成任务。需要操作或查询时使用工具，不能以文字冒充执行。'
        '缺少必要信息先澄清；明确不要记录时禁止写入；复合请求保留全部目标。'
        '只有合成工具结果证明成功才可以说已完成；不把未记录当作没有发生。\n'
        + worldview_prompt_blob(include_triage=True)
    )
    messages = build_case_messages(case, system)
    tools = get_health_tools() if case.stage == 'tool_decision' else []
    await executor._call_llm(messages, tools)
    if len(capture.calls) != 1:
        raise RuntimeError('capture_count_invalid')
    call = capture.calls[0]
    return {'messages': call['messages'], **({'tools': call['tools']} if call.get('tools') else {})}


def require_description_only_difference(before, after):
    restored = deepcopy(after)
    original = next((t for t in before.get('tools', []) if t['function']['name'] == 'health_record'), None)
    if original:
        for tool in restored.get('tools', []):
            if tool['function']['name'] == 'health_record':
                tool['function']['parameters']['properties']['data']['description'] = original['function']['parameters']['properties']['data']['description']
    if restored != before:
        raise ValueError('projection_changed_more_than_record_data_description')


async def evaluate(args):
    from app.config import settings
    from app.database import engine, SessionLocal
    from app.models.llm_usage import LlmUsageLog
    from app.models.user import User
    from app.services.llm.factory import create_provider_for_model_id
    from app.services.llm.usage_tracker import begin_usage_capture, end_usage_capture, summarize_usage_capture, set_caller
    from harness_llm_regression_gate import _live_llm_eval_consent_scope
    from app.services.llm.providers import openai_provider

    openai_provider._DEFAULT_MAX_RETRIES = 0

    # Benchmark only. Other projection behavior remains identical in both arms.
    settings.domain_prompt_optimization = True
    settings.agent_base_url = None
    settings.agent_api_key = None
    cases = [c for c in synthetic_projection_cases() if not args.case or c.id in args.case]
    if not cases or (args.case and set(args.case) - {c.id for c in cases}):
        raise ValueError('unknown_or_empty_case_selection')
    report = {
        'status': 'running' if args.include_live_llm else 'dry_run',
        'candidate_disposition': 'rejected_experiment_not_in_application_runtime',
        'model_id': args.model, 'temperature': 0, 'max_tokens': args.max_tokens,
        'source_sha256': {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in SOURCES},
        'comparisons': [],
        'limits': [
            'Fixed synthetic provider boundary replay; not whole-agent execution or production sampling.',
            'Only data.description differs; all other prompt projection features stay enabled in both arms.',
            'No proposed tool is executed; no persistence or clinical efficacy is established.',
            'Deterministic contract checks do not prove general semantic or clinical quality; unknowns are retained.',
            'Single bounded sample per arm cannot establish production P95, billing savings or noninferiority.',
        ],
    }
    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')

    with _live_llm_eval_consent_scope(args.include_live_llm):
        user_id = 1
        if args.include_live_llm:
            LlmUsageLog.__table__.create(engine, checkfirst=True)
            with SessionLocal() as db:
                user_id = db.query(User).one().id
        for index, case in enumerate(cases):
            variants = {name: await capture_payload(case, enabled=enabled, user_id=user_id)
                        for name, enabled in (('baseline', False), ('candidate', True))}
            require_description_only_difference(variants['baseline'], variants['candidate'])
            comparison = {'case': case.id, 'query': case.query,
                          'payload_changed': variants['baseline'] != variants['candidate'], 'variants': []}
            report['comparisons'].append(comparison)
            # Alternate order across cases; do not report noisy latency as a win.
            order = ('baseline', 'candidate') if index % 2 == 0 else ('candidate', 'baseline')
            for name in order:
                payload = variants[name]
                row = {'variant': name, 'payload_sha256': digest(payload),
                       'schema_chars': len(json.dumps(payload.get('tools', []), ensure_ascii=False))}
                comparison['variants'].append(row)
                if args.include_live_llm:
                    set_caller('eval.record_prompt_projection', user_id=user_id)
                    provider = create_provider_for_model_id(args.model)
                    capture_token = begin_usage_capture()
                    started = perf_counter()
                    try:
                        response = await provider.chat(**payload, temperature=0, max_tokens=args.max_tokens, return_metadata=True)
                        usage = summarize_usage_capture()
                        if not usage or usage['calls'] != 1 or usage.get('failed_calls') or any(item['token_source'] != 'api' for item in usage['items']):
                            raise RuntimeError('non_single_api_usage')
                        row.update(input_tokens=usage['prompt_tokens'], output_tokens=usage['completion_tokens'],
                                   cached_tokens=[item.get('cached_tokens') for item in usage['items']],
                                   wall_seconds=round(perf_counter() - started, 2), token_source='api',
                                   response={k: response[k] for k in ('content', 'tool_calls', 'finish_reason') if k in response})
                        row['quality'] = evaluate_projection_response(case, response,
                            authorized_tool_names={t['function']['name'] for t in payload.get('tools', [])},
                            tool_schemas=payload.get('tools', [])).to_dict()
                    except Exception as exc:
                        row['error_type'] = type(exc).__name__
                        report['status'] = 'failed'
                        save()
                        raise
                    finally:
                        end_usage_capture(capture_token)
                save()
                print(json.dumps({'case': case.id, 'variant': name, 'input_tokens': row.get('input_tokens'),
                                  'quality': row.get('quality', {}).get('deterministic_status')}), flush=True)
            if args.include_live_llm:
                rows = {r['variant']: r for r in comparison['variants']}
                comparison['observed_contract_drop'] = (rows['baseline']['quality']['deterministic_status'] == 'pass'
                    and rows['candidate']['quality']['deterministic_status'] != 'pass')
                comparison['regressed'] = comparison['payload_changed'] and comparison['observed_contract_drop']
                comparison['attribution'] = 'changed_projection' if comparison['payload_changed'] else 'unchanged_control'
                comparison['input_token_reduction_percent'] = round(100 * (1 - rows['candidate']['input_tokens'] / rows['baseline']['input_tokens']), 2)
        if args.include_live_llm:
            report['status'] = 'passed_contracts' if all(
                row['quality']['deterministic_status'] == 'pass'
                for comparison in report['comparisons'] for row in comparison['variants']
            ) else 'failed_contracts'
        save()
    return 0 if report['status'] in ('dry_run', 'passed_contracts') else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-live-llm', action='store_true')
    parser.add_argument('--model', default='qwen3.8-max')
    parser.add_argument('--case', action='append')
    parser.add_argument('--max-tokens', type=int, default=1200)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 256 <= args.max_tokens <= 4096:
        parser.error('--max-tokens must be between 256 and 4096')
    try:
        return asyncio.run(evaluate(args))
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
