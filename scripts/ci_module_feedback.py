#!/usr/bin/env python3
"""Local module feedback, never CI admission or complete impact analysis.

Use --base origin/main while editing, or --module for an explicit local probe.
Unknown/cross-cutting changes require the regular full gate. These small declared
checks do not authorize skipping downstream consumers, PostgreSQL or release CI.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODULES = {
    'display-format': {
        'sources': ('backend/app/utils/number_format.py', 'backend/app/services/genui/table_builder.py'),
        'tests': ('tests/test_number_format.py', 'tests/test_genui_table.py',
                  'tests/test_calendar_query_presentation.py', 'tests/test_report_cards.py'),
    },
    'prompt-cache': {
        'sources': ('backend/app/services/llm/prompt_cache.py',),
        'tests': ('tests/test_prompt_cache.py', 'tests/test_openai_provider_prompt_cache.py'),
    },
}


def plan(paths):
    result = dict(mode='full_required', modules=[], tests=[], release_authority=False,
                  full_ci_required=True, impact_coverage='declared_local_checks_only')
    if not isinstance(paths, list) or not 0 < len(paths) <= 1000:
        return result
    selected = set()
    for path in paths:
        if (not isinstance(path, str) or not path or path.startswith('/')
                or any(part in ('', '.', '..') for part in path.split('/'))
                or '\\' in path or any(ord(c) < 32 or ord(c) == 127 for c in path)):
            return result
        if path.startswith('docs/') or path in {'README.md', 'AGENTS.md', 'CLAUDE.md'}:
            continue
        matches = {name for name, module in MODULES.items()
                   if path in module['sources'] or path in {'backend/'+p for p in module['tests']}}
        if not matches:
            return result
        selected.update(matches)
    if selected:
        result.update(mode='module_feedback', modules=sorted(selected),
                      tests=sorted({test for name in selected for test in MODULES[name]['tests']}))
    return result


def changed_paths(base):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./-]{0,200}', base):
        raise ValueError('invalid base revision')
    def git(*args):
        return subprocess.run(['git', '-C', str(ROOT), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15).stdout
    sha = git('rev-parse', '--verify', base+'^{commit}').decode().strip()
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('unresolved base revision')
    # Includes staged + unstaged changes; no-renames includes both old and new paths.
    raw = git('diff', '--no-ext-diff', '--no-textconv', '--no-renames', '--name-only', '-z', sha, '--')
    raw += git('ls-files', '--others', '--exclude-standard', '-z')
    if len(raw) > 1_000_000:
        raise ValueError('change inventory too large')
    return sorted(set(p.decode('utf-8') for p in raw.split(b'\0') if p))


def pytest_command(value):
    if value.get('mode') != 'module_feedback' or not value.get('tests'):
        raise ValueError('full regression required')
    allowed = {p for m in MODULES.values() for p in m['tests']}
    if any(p not in allowed for p in value['tests']):
        raise ValueError('unregistered feedback test')
    selected = value.get('modules', [])
    if not selected or any(name not in MODULES for name in selected):
        raise ValueError('unregistered feedback module')
    expected = sorted({test for name in selected for test in MODULES[name]['tests']})
    if value['tests'] != expected:
        raise ValueError('incomplete declared module checks')
    # Keep real conftest and fixtures. Measure >=80% for these declared modules;
    # a local module report is never presented as whole-application coverage.
    return [sys.executable, '-m', 'pytest', '-q', '--tb=short',
            '--cov-fail-under=80', *value['tests']]


def coverage_report_config(value, directory):
    pytest_command(value)  # Require the complete registered suite before filtering its report.
    paths = sorted({str(ROOT/source) for name in value['modules'] for source in MODULES[name]['sources']})
    if any('\n' in path or '\r' in path for path in paths):
        raise ValueError('unsupported coverage path')
    # Keep normal app instrumentation/import order. Named --cov modules eagerly
    # resolve package imports and can change SQLAlchemy initialization order.
    return '[report]\ninclude =\n' + ''.join('    '+p+'\n' for p in paths) + '\n[html]\ndirectory = '+str(directory/'html')+'\n'


def feedback_environment(source=None):
    env = dict(os.environ if source is None else source)
    for key in ('TEST_DATABASE_URL', 'TEST_LIVE_RUN_BROKER_URL', 'PYTEST_ADDOPTS',
                'PYTEST_PLUGINS', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD', 'PYTHONPATH',
                'COVERAGE_PROCESS_START', 'COVERAGE_FILE'):
        env.pop(key, None)
    env.update(APP_ENV='test', DATABASE_URL='sqlite:///:memory:', REDIS_URL='redis://127.0.0.1:1/0')
    return env


def execute(value):
    # Reuse existing process-family termination, with no retry or success masking.
    sys.path.insert(0, str(ROOT/'backend/scripts'))
    from run_ci_pytest_shard import _terminate_process_group
    with tempfile.TemporaryDirectory(prefix='reva-module-feedback-') as name:
        directory = Path(name)
        config = directory/'coverage.ini'
        config.write_text(coverage_report_config(value, directory))
        env = feedback_environment()
        env['COVERAGE_FILE'] = str(directory/'coverage-data')
        process = subprocess.Popen([*pytest_command(value), '--cov-config='+str(config)],
                                   cwd=ROOT/'backend', env=env, start_new_session=True)
        try:
            return process.wait(timeout=300)
        except subprocess.TimeoutExpired:
            _terminate_process_group(process)
            return 124
        except BaseException:
            _terminate_process_group(process)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--base', default=None)
    group.add_argument('--module', choices=sorted(MODULES))
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    try:
        paths = list(MODULES[args.module]['sources']) if args.module else changed_paths(args.base or 'origin/main')
        value = plan(paths)
        value['scope_source'] = 'explicit_module_probe' if args.module else 'tracked_and_untracked_git_changes'
        print(json.dumps(value, sort_keys=True), flush=True)
        if value['mode'] == 'full_required':
            return 2
        return execute(value) if args.run else 0
    except (OSError, ValueError, subprocess.SubprocessError):
        print('Module feedback unavailable; full regression required.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
