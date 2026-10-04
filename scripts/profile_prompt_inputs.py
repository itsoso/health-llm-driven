#!/usr/bin/env python3
"""Content-free tokenizer diagnostics for registry and synthetic provider captures.

Requires optional tiktoken. Counts describe serialized JSON, not provider API
usage. Input captures use the existing REVA_ARCHITECTURE_PAYLOADS fixture format;
never pass real user transcripts. No model or database calls are made. The
tokenizer library may fetch its public encoding cache on first use.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def profile(encoding, captures):
    from app.services.tool_schema_registry import get_health_tools

    def tokens(value):
        serialized = json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
        return len(encoding.encode(serialized, disallowed_special=()))

    tools = get_health_tools()
    rows = []
    for tool in tools:
        function = tool['function']
        rows.append({'tool': function['name'], 'schema_json_tokens': tokens(tool),
                     'description_string_tokens': tokens(function.get('description', '')),
                     'parameters_json_tokens': tokens(function.get('parameters', {}))})
    report = {
        'status': 'offline_diagnostic', 'tokenizer': encoding.name,
        'api_usage': None,
        'source_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in ('backend/app/services/tool_schema_registry.py',
                         'backend/app/services/agent_executor.py',
                         'scripts/profile_prompt_inputs.py')},
        'limits': ['Serialized JSON tokenizer counts are not provider input tokens.',
                   'Per-component token counts are diagnostic and not strictly additive.',
                   'Captures contain fixed synthetic fixtures; providers are stubbed.',
                   'No quality, latency, billing or production savings are established.'],
        'registry_json_tokens': tokens(tools),
        'tools': sorted(rows, key=lambda row: row['schema_json_tokens'], reverse=True),
        'captures': [],
    }
    for label, path in captures:
        pairs = json.loads(path.read_text())
        for pair in pairs:
            calls = []
            for call in pair['calls']:
                messages = call['messages']
                call_tools = call.get('tools') or []
                calls.append({
                    'messages_json_tokens': tokens(messages),
                    'tools_json_tokens': tokens(call_tools) if call_tools else 0,
                    'payload_json_tokens': tokens({'messages': messages, 'tools': call_tools}),
                    'by_role_json_tokens': {role: tokens([m for m in messages if m.get('role') == role])
                        for role in ('system', 'user', 'assistant', 'tool')
                        if any(m.get('role') == role for m in messages)},
                    'tool_names': [(tool.get('function') or {}).get('name') for tool in call_tools],
                })
            report['captures'].append({'label': label, 'compared_variant_enabled': pair['enabled'],
                                       'provider_calls': len(calls), 'calls': calls})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', action='append', default=[], metavar='LABEL=PATH',
                        help='Explicitly synthetic provider capture exported by repository tests')
    parser.add_argument('--encoding', default='cl100k_base')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    captures = []
    for entry in args.capture:
        label, separator, path = entry.partition('=')
        if not separator or not re.fullmatch('[a-z0-9_-]{1,48}', label):
            parser.error('--capture requires a short LABEL=PATH')
        captures.append((label, Path(path)))
    try:
        import tiktoken
    except ImportError:
        parser.error('Optional dependency tiktoken is required; no character-count fallback is used')
    report = profile(tiktoken.get_encoding(args.encoding), captures)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'tokenizer': report['tokenizer'],
                      'registry_json_tokens': report['registry_json_tokens'],
                      'captures': len(report['captures'])}))


if __name__ == '__main__':
    main()
