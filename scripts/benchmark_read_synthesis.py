#!/usr/bin/env python3
"""Paired answer-stage experiment with full application static rules.

Synthetic evidence only, opt-in API calls, no tool execution. Write-answer
controls retain full prompts. Production has no experiment import or flag.
"""
import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))

from benchmark_argument_transport import run, add_run_options
from eval.experimental_read_synthesis import build_read_synthesis_parts
from eval.prompt_projection_quality import build_case_messages
from app.services.llm.prompt_transport import compact_tool_json

SOURCES = (
    'backend/app/services/agent_executor.py',
    'backend/app/services/agent_prompt_sections.py',
    'backend/eval/experimental_read_synthesis.py',
    'backend/eval/prompt_projection_quality.py',
    'backend/eval/prompt_benchmark_metrics.py',
    'scripts/benchmark_argument_transport.py',
    'scripts/benchmark_read_synthesis.py',
)


def variants(case):
    from app.config import settings
    from app.services.agent_executor import AgentExecutor

    read_only = bool(case.evidence) and all(
        entry['name'] in {'health_query', 'health_query_batch'} for entry in case.evidence)
    executor = AgentExecutor(None)
    kwargs = dict(intent_query=case.query, static_rules_only=True, synthesis_only=read_only)
    with patch.object(settings, 'domain_prompt_optimization', True):
        original = executor._build_system_prompt(1, 1, None, **kwargs)
        with patch('app.services.agent_prompt_sections.build_base_prompt_parts', build_read_synthesis_parts):
            projected = executor._build_system_prompt(1, 1, None, **kwargs)
    baseline = compact_tool_json(build_case_messages(case, original))
    candidate = deepcopy(baseline)
    candidate[0]['content'] = projected + '\n\n' + case.frozen_context
    return {'baseline': baseline, 'candidate': candidate}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_run_options(parser)
    args = parser.parse_args()
    args.model = args.model or ['qwen3.8-flash', 'qwen3.8-max']
    try:
        return asyncio.run(run(args, variant_builder=variants, source_paths=SOURCES,
                               caller='eval.read_synthesis'))
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
