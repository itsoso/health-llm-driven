"""Explicit, candidate-bound simulator risk acceptance; never physical-test proof."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


def validate_simulator_acceptance(path: Path, *, required_checks: tuple[str, ...],
        expected_build_id: str, expected_app_version: str, expected_eas_build_id: str,
        expected_git_commit_hash: str, accept_risk: bool) -> list[str]:
    failures = []
    if not accept_risk:
        failures.append('simulator acceptance requires explicit --accept-simulator-risk')
    try:
        evidence = json.loads(path.read_text())
    except (OSError, ValueError):
        return failures + ['simulator acceptance evidence missing or invalid JSON']
    if not isinstance(evidence, dict):
        return failures + ['simulator evidence must be an object']
    candidate = evidence.get('candidate')
    simulator = evidence.get('simulator')
    approval = evidence.get('risk_acceptance')
    checks = evidence.get('checks')
    if not all(isinstance(value, dict) for value in (candidate, simulator, approval, checks)):
        return failures + ['simulator evidence requires candidate, simulator, risk_acceptance and checks objects']
    expected = dict(build_id=expected_build_id, app_version=expected_app_version,
                    eas_build_id=expected_eas_build_id, git_commit_hash=expected_git_commit_hash,
                    build_profile='production')
    for field, value in expected.items():
        if not value or candidate.get(field) != value:
            failures.append(f'simulator candidate mismatch: {field}')
    xcode = candidate.get('dtxcode')
    sdk = candidate.get('dtplatform_version')
    if not isinstance(xcode, str) or not xcode.isdigit() or int(xcode) < 2600:
        failures.append('candidate IPA dtxcode must be at least 2600')
    if not isinstance(sdk, str) or not re.fullmatch(r'\d+(?:\.\d+)*', sdk) or int(sdk.split('.')[0]) < 26:
        failures.append('candidate IPA dtplatform_version major must be at least 26')
    if not re.fullmatch(r'[0-9a-f]{40}', expected_git_commit_hash):
        failures.append('simulator candidate source must be a full SHA')
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', expected_eas_build_id):
        failures.append('simulator candidate EAS ID must be a UUID')
    if simulator.get('source_sha') != expected_git_commit_hash or simulator.get('configuration') != 'Release':
        failures.append('simulator must be Release from exact candidate source')
    for field in ('build_id', 'device', 'ios_version'):
        if not isinstance(simulator.get(field), str) or not simulator[field].strip():
            failures.append(f'simulator missing {field}')
    if approval.get('accepted') is not True:
        failures.append('simulator risk acceptance is not explicit')
    for field in ('accepted_by', 'reference'):
        if not isinstance(approval.get(field), str) or not approval[field].strip():
            failures.append(f'simulator risk acceptance missing {field}')
    if not isinstance(evidence.get('tester'), str) or not evidence['tester'].strip():
        failures.append('simulator evidence missing tester')
    try:
        stamp = datetime.fromisoformat(evidence.get('tested_at', '').replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            failures.append('simulator timestamp must include timezone')
    except (ValueError, TypeError, AttributeError):
        failures.append('simulator evidence requires an ISO timestamp')
    if set(checks) != set(required_checks):
        failures.append('simulator checks must enumerate the full acceptance inventory')
    unverified = set()
    core = {'demo_account_login', 'today_context_open_dismiss', 'personal_center_privacy_policy'}
    for name in required_checks:
        result = checks.get(name)
        if not isinstance(result, dict):
            failures.append(f'simulator missing structured result: {name}')
            continue
        status = result.get('status')
        if status not in {'passed', 'unverified'}:
            failures.append(f'simulator failed or invalid check: {name}')
            continue
        field = 'evidence' if status == 'passed' else 'reason'
        if not isinstance(result.get(field), str) or not result[field].strip():
            failures.append(f'simulator check missing {field}: {name}')
        if status == 'unverified':
            unverified.add(name)
            if name in core:
                failures.append(f'simulator core check must pass: {name}')
    accepted = evidence.get('accepted_unverified_checks')
    if not isinstance(accepted, list) or not all(isinstance(item, str) for item in accepted):
        failures.append('simulator requires explicit accepted_unverified_checks list')
    elif set(accepted) != unverified or len(accepted) != len(set(accepted)):
        failures.append('simulator risk acceptance must exactly enumerate unverified checks')
    return failures
