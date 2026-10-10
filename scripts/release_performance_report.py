#!/usr/bin/env python3
"""Offline, non-authorizing timing report from bounded GitHub run/job metadata.

Export runs with gh run list --json databaseId,workflowName,headSha,createdAt,status,conclusion
and save each complete jobs API response as <run-id>.json. No credentials,
logs, environment values, vendor calls or publication mutations are consumed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import re
from statistics import median
import sys

WORKFLOWS = {'CI', 'Trusted release', 'Trusted OTA'}
STATES = {'success', 'failure', 'cancelled', 'skipped', 'timed_out', 'action_required', 'neutral', 'stale', 'startup_failure'}
JOBS = {'preflight', 'build-permission', 'backend', 'ios-build', 'testflight', 'retained-testflight',
        'ota', 'release-result', 'classify-changes', 'backend-tests', 'backend-release-ready-v1',
        'release-tests', 'agent-runtime-postgres', 'backend-quality', 'release-invariants',
        'docs-quality', 'frontend-build', 'mobile-typecheck', 'mac-build', 'type-drift',
        'frontend-artifact-integration', 'retained-runner-startup', 'ota-runner-startup'}
STEP_CATEGORIES = {
    'Install dependencies': 'dependency_install',
    'Install locked CLI and app dependencies without lifecycle scripts or shared cache': 'dependency_install',
    'Claim one build in this job before every vendor create attempt': 'native_build_claim',
    'Build once without uploading to Apple': 'native_build_vendor_combined',
    'Claim one-time TestFlight upload permission before exposing vendor credentials': 'native_upload_claim',
    'Revalidate and upload the exact finished build': 'native_upload_vendor_combined',
    'Start the fixed server-side release capability': 'backend_operation_combined',
    'Prepare exact OTA artifact without consuming a publication claim': 'ota_prepare',
    'Read-only vendor admission after source and CI gates': 'ota_admission',
    'Publish one bound iOS artifact and verify server receipt': 'ota_publish_combined',
}


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError('invalid timing timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timezone required')
    return parsed


def duration(start, end):
    value = (timestamp(end) - timestamp(start)).total_seconds()
    if value < 0:
        raise ValueError('negative duration')
    return round(value, 2)


def positive(value):
    return type(value) is int and value > 0


def safe_job(name):
    if isinstance(name, str) and (name in JOBS or re.fullmatch(r'backend-test-balanced-[0-9]{2}', name)):
        return name
    return 'other'


def observation(run, inventory):
    rid, sha = run.get('databaseId'), run.get('headSha')
    if not positive(rid) or not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('invalid run identity')
    workflow = run.get('workflowName')
    if workflow not in WORKFLOWS:
        raise ValueError('unsupported workflow')
    jobs = inventory.get('jobs')
    if not isinstance(jobs, list) or not 0 < len(jobs) <= 1000 or inventory.get('total_count') != len(jobs):
        raise ValueError('incomplete job inventory; paginate before reporting')
    attempts, ids, active, phases = set(), set(), [], []
    for job in jobs:
        if (job.get('run_id') != rid or job.get('head_sha') != sha or not positive(job.get('id'))
                or job['id'] in ids or not positive(job.get('run_attempt'))):
            raise ValueError('unbound job metadata')
        ids.add(job['id']); attempts.add(job['run_attempt'])
        if job.get('conclusion') == 'skipped':
            continue
        active.append(job)
        for step in job.get('steps', []):
            category = STEP_CATEGORIES.get(step.get('name'))
            if category and step.get('conclusion') != 'skipped':
                phases.append({'phase': category, 'job': safe_job(job.get('name')),
                               'conclusion': step.get('conclusion') if step.get('conclusion') in STATES else 'pending',
                               'seconds': duration(step['started_at'], step['completed_at'])
                               if step.get('started_at') and step.get('completed_at') else None})
    if len(attempts) != 1:
        raise ValueError('mixed attempt evidence')
    completed = [j for j in active if j.get('started_at') and j.get('completed_at')]
    for job in completed:
        duration(run['createdAt'], job['started_at'])
        duration(job['started_at'], job['completed_at'])
    finished = bool(active) and len(completed) == len(active) and run.get('status') == 'completed'
    names = {safe_job(j.get('name')) for j in active}
    workers = sum(name.startswith('backend-test-balanced-') for name in names)
    kinds = {p['phase'] for p in phases}
    if workflow == 'CI':
        kind = f'ci-backend-{workers}-workers' if workers else 'ci-other'
    elif workflow == 'Trusted OTA':
        kind = ('ota-publish-path' if 'ota_publish_combined' in kinds else 'ota-prepare' if 'ota_prepare' in kinds
                else 'ota-admission' if 'ota_admission' in kinds else 'ota-preflight-or-legacy')
    else:
        kind = ('native-upload-path' if names & {'ios-build', 'testflight', 'retained-testflight'}
                else 'backend-path' if names & {'backend', 'build-permission'} else 'preflight-only')
    last = max(completed, key=lambda j: timestamp(j['completed_at'])) if completed else None
    work = [j for j in completed if j['name'] not in {'backend-tests', 'backend-release-ready-v1', 'release-tests', 'release-result'}]
    critical = max(work, key=lambda j: timestamp(j['completed_at'])) if work else last
    return {
        'run_id': rid, 'sha': sha, 'workflow': workflow, 'kind': kind, 'attempt': next(iter(attempts)),
        'conclusion': run.get('conclusion') if run.get('conclusion') in STATES else 'pending',
        'all_active_jobs_succeeded': finished and all(j.get('conclusion') == 'success' for j in active),
        'wall_seconds': duration(run['createdAt'], last['completed_at']) if finished else None,
        'attempt_execution_span_seconds': duration(min(j['started_at'] for j in completed), last['completed_at']) if finished else None,
        'runner_seconds': round(sum(duration(j['started_at'], j['completed_at']) for j in completed), 2) if finished else None,
        'critical_job': safe_job(critical['name']) if critical else None, 'phases': phases,
        'production_state': 'unverified', 'apple_processing_seconds': None, 'tester_availability': 'unverified',
    }


def summarize(runs, inventories):
    if not isinstance(runs, list) or not 0 < len(runs) <= 1000:
        raise ValueError('bounded nonempty run list required')
    ids = [r.get('databaseId') for r in runs]
    if any(not positive(rid) for rid in ids) or len(set(ids)) != len(ids):
        raise ValueError('invalid or duplicate runs')
    rows = [observation(r, inventories[r['databaseId']]) for r in runs]
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['kind']].append(row)
    cohorts = []
    for kind, values in sorted(grouped.items()):
        good = [v for v in values if v['attempt'] == 1 and v['conclusion'] == 'success' and v['all_active_jobs_succeeded']]
        times = [v['wall_seconds'] for v in good]
        cohorts.append({'kind': kind, 'observed_runs': len(values), 'outcomes': dict(Counter(v['conclusion'] for v in values)),
                        'retry_runs': sum(v['attempt'] > 1 for v in values),
                        'first_attempt_success': {'sample_count': len(times),
                            'min_seconds': min(times) if times else None,
                            'median_seconds': round(median(times), 2) if times else None,
                            'max_seconds': max(times) if times else None}})
    return {'schema_version': 'release_performance.v1', 'release_authority': False,
            'limitations': ['observed sample; not a stable latency guarantee',
                            'job metadata does not prove vendor, server receipt, Apple processing or user acceptance',
                            'wall includes initial scheduling and prior attempts; retry runs excluded from first-attempt summaries',
                            'native vendor steps combine queue, execution and polling; no invented subphase timings'],
            'cohorts': cohorts, 'runs': rows}


def read_json(path):
    with path.open('rb') as stream:
        raw = stream.read(16_000_001)
    if len(raw) > 16_000_000:
        raise ValueError('metadata file exceeds bound')
    return json.loads(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, required=True)
    parser.add_argument('--jobs-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        runs = read_json(args.runs)
        if not isinstance(runs, list) or not 0 < len(runs) <= 1000 or any(not isinstance(r, dict) or not positive(r.get('databaseId')) for r in runs):
            raise ValueError('invalid run inventory')
        inventories = {r['databaseId']: read_json(args.jobs_dir / f"{r['databaseId']}.json") for r in runs}
        result = summarize(runs, inventories)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        print('Performance metadata rejected; supply complete bound run/job inventories.', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
