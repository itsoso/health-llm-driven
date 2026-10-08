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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--logs-zip', type=Path, required=True)
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--head-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with zipfile.ZipFile(args.logs_zip) as archive:
        # GitHub also includes aggregate logs: select only the isolated-run step.
        names = sorted(name for name in archive.namelist() if re.fullmatch(
            r'backend-test-balanced-\d+/\d+_Run isolated shards \(balanced-\d+\)\.txt', name))
        if not names or len(names) != len(set(names)):
            raise ValueError('missing or duplicate isolated-run logs')
        logs = [archive.read(name).decode('utf-8') for name in names]
    result = refresh_catalog(json.loads(args.catalog.read_text()), logs,
                             run_id=args.run_id, head_sha=args.head_sha)
    result['timing_source']['logs_zip_sha256'] = hashlib.sha256(args.logs_zip.read_bytes()).hexdigest()
    # Preserve the existing one-shard-per-line catalog format for small diffs.
    compact = lambda value: json.dumps(value, separators=(',', ':'))
    text = '{\n  "worker_count": ' + str(result['worker_count']) + ',\n'
    text += '  "timing_source": ' + compact(result['timing_source']) + ',\n  "shards": [\n'
    text += ',\n'.join('    ' + compact(row) for row in result['shards']) + '\n  ]\n}\n'
    args.output.write_text(text)


if __name__ == '__main__':
    main()
