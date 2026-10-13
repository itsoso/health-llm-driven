#!/usr/bin/env python3
"""Bounded read-only observation of one GitHub run, never release authority.

Each invocation takes at most three 12-second reads and six seconds of backoff.
Exit 0: observed success; 1: observed unsuccessful terminal; 2: unknown;
3: still pending. A success observation does not prove production delivery.
"""
import argparse
import json
import re
import subprocess
import time

REPOSITORY = 'itsoso/health-llm-driven'
FIELDS = '{id,head_sha,run_attempt,name,status,conclusion}'
WORKFLOWS = {'CI', 'Trusted release', 'Trusted OTA'}
TERMINALS = {'success', 'failure', 'cancelled', 'skipped', 'timed_out',
             'action_required', 'neutral', 'stale', 'startup_failure'}
PENDING = {'queued', 'in_progress', 'requested', 'waiting', 'pending'}


def read_run(run_id):
    result = subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/actions/runs/{run_id}', '--jq', FIELDS],
                            capture_output=True, text=True, check=True, timeout=12)
    if len(result.stdout) > 4096:
        raise ValueError('oversized metadata')
    return json.loads(result.stdout)


def observe(run_id, sha, attempt, *, read=read_run, sleep=time.sleep):
    result = {'run_id':run_id, 'sha':sha, 'attempt':attempt,
              'release_authority':False, 'status':'unknown'}
    if (type(run_id) is not int or run_id <= 0 or type(attempt) is not int or attempt <= 0
            or not isinstance(sha, str) or re.fullmatch('[0-9a-f]{40}', sha) is None):
        return result, 2
    for retry in range(3):
        try:
            value = read(run_id)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
            if retry < 2:
                sleep(2 ** (retry + 1))
                continue
            return {**result, 'reason':'metadata_unavailable'}, 2
        except (ValueError, UnicodeError):
            return {**result, 'reason':'invalid_metadata'}, 2
        if (not isinstance(value, dict) or type(value.get('id')) is not int or value['id'] != run_id
                or value.get('head_sha') != sha or type(value.get('run_attempt')) is not int
                or value['run_attempt'] != attempt or not isinstance(value.get('name'), str)
                or (value['name'] not in WORKFLOWS and re.fullmatch(
                    r'(?:Trusted release|Trusted OTA) · [a-z][a-z0-9-]{0,31} · ' + sha,
                    value['name']) is None)):
            return {**result, 'reason':'identity_mismatch'}, 2
        status, conclusion = value.get('status'), value.get('conclusion')
        if not isinstance(status, str) or (conclusion is not None and not isinstance(conclusion, str)):
            return {**result, 'reason':'invalid_state'}, 2
        if status == 'completed' and conclusion in TERMINALS:
            return {**result, 'status':status, 'conclusion':conclusion}, 0 if conclusion == 'success' else 1
        if status in PENDING and conclusion is None:
            return {**result, 'status':status, 'conclusion':None}, 3
        return {**result, 'reason':'invalid_state'}, 2
    raise AssertionError('unreachable')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--attempt', type=int, default=1)
    args = parser.parse_args(argv)
    result, code = observe(args.run_id, args.sha, args.attempt)
    print(json.dumps(result))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
