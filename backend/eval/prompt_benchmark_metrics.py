"""Offline/API benchmark accounting, never imported by application runtime."""
import asyncio
from contextlib import aclosing
import math
from time import perf_counter


async def measure_response(provider, messages, *, streaming, timeout_seconds, metrics):
    started = perf_counter()
    metrics['first_content_seconds'] = None
    try:
        async with asyncio.timeout(timeout_seconds):
            kwargs = dict(messages=messages, temperature=0, max_tokens=1200, return_metadata=True)
            if not streaming:
                return await provider.chat(**kwargs)
            # Explicit usage is required. Do not permit the provider's automatic
            # compatibility retry without usage to create an unbudgeted call.
            kwargs['stream_options'] = {'include_usage': True}
            content, calls, finish = [], [], None
            async with aclosing(provider.chat_stream(**kwargs)) as stream:
                async for event in stream:
                    if event.get('type') == 'content':
                        chunk = event.get('text') or ''
                        content.append(chunk)
                        if chunk.strip() and metrics['first_content_seconds'] is None:
                            metrics['first_content_seconds'] = perf_counter() - started
                    elif event.get('type') == 'tool_calls':
                        calls.extend(event.get('tool_calls') or [])
                    elif event.get('type') == 'finish':
                        finish = event.get('finish_reason')
            if finish is None:
                raise RuntimeError('stream_missing_finish')
            return {'content': ''.join(content), 'tool_calls': calls, 'finish_reason': finish}
    finally:
        metrics['wall_seconds'] = perf_counter() - started


def _distribution(values):
    values = sorted(values)
    return {'n': len(values), **{f'p{p}': values[math.ceil(len(values)*p/100)-1] if values else None
                               for p in (50, 95, 99)}}


def summarize_comparisons(comparisons):
    groups = {}
    for comparison in comparisons:
        for row in comparison['variants']:
            if 'wall_seconds' in row:
                groups.setdefault((comparison['model'], row['variant']), []).append(row)
    summaries = []
    for (model, variant), rows in sorted(groups.items()):
        known = [r for r in rows if r.get('token_source') == 'api']
        passing = sum(r.get('quality', {}).get('deterministic_status') == 'pass' for r in rows)
        known_input = sum(r['input_tokens'] for r in known)
        summaries.append({
            'model': model, 'variant': variant, 'attempts': len(rows),
            'failed_attempts': sum('error_type' in r for r in rows),
            'contract_failures': sum(r.get('quality', {}).get('deterministic_status') == 'fail' for r in rows),
            'passing_contracts': passing,
            'api_input_tokens_known': known_input,
            'api_output_tokens_known': sum(r['output_tokens'] for r in known),
            'usage_unknown_attempts': len(rows)-len(known),
            # Unknown failed-call usage must not create artificially cheap successes.
            'input_tokens_per_passing_contract': known_input/passing if passing and len(known) == len(rows) else None,
            'wall_seconds_all_attempts': _distribution([r['wall_seconds'] for r in rows]),
            'first_content_seconds': _distribution([r['first_content_seconds'] for r in rows
                                                    if r.get('first_content_seconds') is not None]),
            'limits': ['Answer-stage measurements only; not whole tasks or production latency.',
                       'Nearest-rank percentiles; small samples do not prove tail improvement.',
                       'First content is not first useful/safety-verified UI output.',
                       'Passing deterministic contracts does not establish semantic noninferiority.'],
        })
    return summaries
