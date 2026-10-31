"""Bind native upload completion to retirement of an already successful backend.

The exact reviewed vendor profile is source-owned. No caller-selected workflow,
artifact, token argument or synthetic backend completion is accepted.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path


class ContinuationError(ValueError):
    """Secret-free continuation diagnostics."""


def load(b, name):
    path = Path(__file__).with_name(name + '.py')
    b.secure(path)
    if (path.parent / '__pycache__').exists():
        raise ContinuationError('cached native continuation code forbidden')
    spec = importlib.util.spec_from_file_location('continuation_' + name, path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(), str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def requires_proof(b, sha):
    native = load(b, 'native_release_retirement')
    return native.PROFILES.get(sha, {}).get('workspace_kind') == 'successful-backend'


def expected(b, sha):
    native = load(b, 'native_release_retirement')
    profile = native.profile_for(sha)
    if profile.get('workspace_kind') != 'successful-backend' or profile['run_attempt'] != 1:
        raise ContinuationError('reviewed successful-backend native continuation required')
    source = b.canonical_source(sha)
    for name, digest in profile['canonical_hashes'].items():
        path = source / name
        b.secure(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ContinuationError('native continuation producer differs')
    vendor = {
        'state': 'VENDOR_UPLOAD_SUCCEEDED', 'run_id': profile['run_id'],
        'run_attempt': 1, 'workflow_id': native.WORKFLOW_ID,
        'build_id': profile['build_id'], 'submission_id': profile['submission_id'],
        'log_sha256': profile['log_sha256'], 'jobs_sha256': profile['jobs_sha256'],
        'prior_jobs_sha256': None, 'canonical_hashes': profile['canonical_hashes'],
    }
    return native, {'kind': 'successful-backend-native-continuation', 'native_sha': sha,
                    'vendor': vendor}


def validate_saved(b, sha, value):
    _, proof = expected(b, sha)
    if value != proof:
        raise ContinuationError('native continuation terminal proof differs')
    return proof


def inspect(b, sha, workspace):
    claims = {'build-started.json', 'native-started.json'}
    present = claims & set(workspace.get('inventory') or [])
    if not present:
        return None
    if present != claims or workspace.get('state') != 'SUCCEEDED':
        raise ContinuationError('native continuation is incomplete')
    native, proof = expected(b, sha)
    gate = load(b, 'trusted_release_gate')
    token = gate._read_credential_file(gate._CREDENTIAL_PATH)
    if not token:
        raise ContinuationError('native continuation read credential unavailable')
    observed = native.vendor_evidence(token, native_sha=sha)
    if observed != proof['vendor']:
        raise ContinuationError('native continuation vendor terminal differs')
    return proof
