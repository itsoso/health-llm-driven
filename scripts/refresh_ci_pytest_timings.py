#!/usr/bin/env python3
"""Refresh placement timings from reviewed, successful CI process logs.

The caller must independently verify the supplied run ID and SHA against GitHub.
Only first-attempt passes are accepted. Test selection and execution policy stay
unchanged; failed/retried/incomplete runs cannot refresh scheduling telemetry.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import zipfile
from pathlib import Path


def refresh_catalog(catalog, logs, *, run_id, head_sha):
    if type(run_id) is not int or run_id <= 0:
        raise ValueError('run_id must be positive')
    if not isinstance(head_sha, str) or not re.fullmatch(r'[0-9a-f]{40}', head_sha):
        raise ValueError('head_sha must be a full commit SHA')
    labels = [row['label'] for row in catalog['shards']]
    if not labels or len(labels) != len(set(labels)):
        raise ValueError('catalog labels must be unique and nonempty')
    samples = {}
    for log in logs:
        pending = None
        for line in log.splitlines():
            if '[ci-worker] ' in line:
                if pending is not None:
                    raise ValueError('missing process timing')
                pending = json.loads(line.split('[ci-worker] ', 1)[1])['shard']
                if pending not in labels or pending in samples:
                    raise ValueError('unknown or duplicate shard')
            elif '[ci-shard-timing] ' in line:
                value = json.loads(line.split('[ci-shard-timing] ', 1)[1])
                if pending is None:
                    raise ValueError('orphan or duplicate timing')
                if (type(value.get('attempt')) is not int or value['attempt'] != 1
                        or value.get('outcome') != 'pass'
                        or type(value.get('return_code')) is not int
                        or value['return_code'] != 0):
                    raise ValueError('only first-attempt successful samples accepted')
                duration = value.get('duration_ms')
                if type(duration) is not int or duration <= 0:
                    raise ValueError('duration_ms must be a positive integer')
                samples[pending] = duration / 1000
                pending = None
        if pending is not None:
            raise ValueError('missing process timing')
    if set(samples) != set(labels):
        raise ValueError('timings must cover every shard exactly once')
    result = copy.deepcopy(catalog)
    for row in result['shards']:
        row['scheduling_seconds'] = samples[row['label']]
    result['timing_source'] = {
        'run_id': run_id, 'head_sha': head_sha,
        'measurement': 'successful_attempt_process_wall_seconds',
        'sample_count': len(samples), 'excluded_timeout_seconds': 0.0,
        'note': 'All shard timings are first-attempt successful process wall times from this run. Test selection, deadlines, attempts and process isolation are unchanged.',
    }
    return result


def archive_logs(archive):
    """Choose one complete log per worker; GitHub may omit per-step entries."""
    workers = {}
    for name in archive.namelist():
        aggregate = re.fullmatch(r'\d+_backend-test-(balanced-\d+)\.txt', name)
        step = re.fullmatch(r'backend-test-(balanced-\d+)/\d+_Run isolated shards \((balanced-\d+)\)\.txt', name)
        if not aggregate and not step:
            continue
        if step and step[1] != step[2]:
            raise ValueError('mismatched worker log identity')
        worker = (aggregate or step)[1]
        kind = 'aggregate' if aggregate else 'step'
        entries = workers.setdefault(worker, {})
        if kind in entries:
            raise ValueError('duplicate worker log')
        entries[kind] = archive.read(name).decode('utf-8')
    if not workers:
        raise ValueError('missing isolated-run logs')
    logs = []
    for worker in sorted(workers):
        entries = workers[worker]
        if len(entries) == 2:
            # Compare telemetry, ignoring timestamps and unrelated setup output.
            def telemetry(log):
                return [line.split(marker, 1)[1] for line in log.splitlines()
                        for marker in ('[ci-worker] ', '[ci-shard-timing] ') if marker in line]
            if telemetry(entries['aggregate']) != telemetry(entries['step']):
                raise ValueError('conflicting worker timing logs')
        logs.append(entries.get('aggregate', entries.get('step')))
    return logs


def combine_samples(samples):
    """Use conservative per-shard maxima across fully validated successful runs."""
    if len(samples) < 2:
        raise ValueError('at least two distinct runs required')
    def policy(sample):
        return (sample['worker_count'], [
            {k: v for k, v in row.items() if k != 'scheduling_seconds'}
            for row in sample['shards']])
    if (len({s['timing_source']['run_id'] for s in samples}) != len(samples)
            or any(policy(s) != policy(samples[0]) for s in samples)):
        raise ValueError('samples must be distinct runs with identical execution policies')
    result = copy.deepcopy(samples[-1])
    for i, row in enumerate(result['shards']):
        row['scheduling_seconds'] = max(s['shards'][i]['scheduling_seconds'] for s in samples)
    result['timing_source'].update(
        aggregation='maximum',
        runs=[copy.deepcopy(s['timing_source']) for s in samples],
        note='Per-shard maximum of the listed fully successful runs; placement only. Execution policies unchanged.',
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--logs-zip', type=Path, required=True)
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--head-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--additional-run', nargs=3, action='append', default=[],
                        metavar=('RUN_ID', 'HEAD_SHA', 'LOGS_ZIP'))
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())
    samples = []
    for run_id, head_sha, path in [(args.run_id, args.head_sha, args.logs_zip), *args.additional_run]:
        path = Path(path)
        with zipfile.ZipFile(path) as archive:
            logs = archive_logs(archive)
        sample = refresh_catalog(catalog, logs, run_id=int(run_id), head_sha=head_sha)
        sample['timing_source']['logs_zip_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        samples.append(sample)
    result = combine_samples(samples) if len(samples) > 1 else samples[0]
    # Preserve the existing one-shard-per-line catalog format for small diffs.
    compact = lambda value: json.dumps(value, separators=(',', ':'))
    text = '{\n  "worker_count": ' + str(result['worker_count']) + ',\n'
    text += '  "timing_source": ' + compact(result['timing_source']) + ',\n  "shards": [\n'
    text += ',\n'.join('    ' + compact(row) for row in result['shards']) + '\n  ]\n}\n'
    args.output.write_text(text)


if __name__ == '__main__':
    main()
