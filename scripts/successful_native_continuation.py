"""Bind a native vendor terminal to retirement of an already successful backend.

The exact reviewed vendor profile is source-owned. No caller-selected workflow,
artifact, token argument or synthetic backend completion is accepted.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
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
    if profile.get('workspace_kind') != 'successful-backend' or profile['run_attempt'] < 1:
        raise ContinuationError('reviewed successful-backend native continuation required')
    source = b.canonical_source(sha)
    for name, digest in profile['canonical_hashes'].items():
        path = source / name
        b.secure(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ContinuationError('native continuation producer differs')
    vendor = {
        'state': profile.get('vendor_state', 'VENDOR_UPLOAD_SUCCEEDED'),
        'run_id': profile['run_id'],
        'run_attempt': profile['run_attempt'], 'workflow_id': native.WORKFLOW_ID,
        'build_id': profile['build_id'], 'submission_id': profile['submission_id'],
        'log_sha256': profile['log_sha256'], 'jobs_sha256': profile['jobs_sha256'],
        'prior_jobs_sha256': profile.get('prior_jobs_sha256'),
        'canonical_hashes': profile['canonical_hashes'],
    }
    if profile.get('terminal_mode') == 'backend-already-consumed':
        vendor['backend_log_sha256'] = profile['backend_log_sha256']
    proof = {'kind': 'successful-backend-native-continuation', 'native_sha': sha,
             'vendor': vendor}
    link = profile.get('backend_link')
    if link is not None:
        proof['backend_link'] = {
            'state': 'PRIOR_BACKEND_SUCCEEDED',
            'run_id': link['run_id'], 'run_attempt': link['run_attempt'],
            'workflow_id': native.WORKFLOW_ID,
            'jobs_sha256': link['jobs_sha256'],
        }
    return native, proof


# Immutable audit issued before backend_link became part of the proof schema.
# This is historical read compatibility only; new inspect() never uses it.
LEGACY_SHA = 'ad8949e7eeb4abc73968b0c83ebdb38b64a6cae1'
LEGACY_SUCCESSOR = '1423dd5d5af378abe679b2aba7ef03761ca5f42a'
LEGACY_PROOF_SHA256 = 'd08d026f6bf8cd342517284e8561d74f4de2db8311e74c101ffa61ecf8aeb655'
LEGACY_AUDIT_DIGESTS = {
    f'successful-auth-revocations/{LEGACY_SHA}/intent.json':
        '59b7d4c57929eb84dbb3c02696904a2012c0bf1bf0af92d45829beb20e060c91',
    f'successful-auth-revocations/{LEGACY_SHA}/completed.json':
        'f8a42a9eb2eab12f800e9abffa683f180483c0d9a1fb2485e4ec64c077e5eae9',
    f'retired/{LEGACY_SHA}/completed.json':
        '8336ec1ea3f6258e0bbe2c45b686eb59e9b9a3d190c02e817eaf392dadd8577c',
}


def _legacy_audit(b, relative, digest):
    path = b.STATE / relative
    b.secure(path, private=True)
    before = path.lstat()
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read()
        after = os.fstat(stream.fileno())
    b.secure(path, private=True)
    if (not identity(before) == identity(opened) == identity(after) == identity(path.lstat())
            or hashlib.sha256(raw).hexdigest() != digest):
        raise ContinuationError('historical native audit differs')
    return json.loads(raw)


def validate_saved(b, sha, value):
    _, proof = expected(b, sha)
    if value == proof:
        return proof
    legacy = {key: item for key, item in proof.items() if key != 'backend_link'}
    digest = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if sha != LEGACY_SHA or value != legacy or digest != LEGACY_PROOF_SHA256:
        raise ContinuationError('native continuation terminal proof differs')
    records = {name: _legacy_audit(b, name, digest)
               for name, digest in LEGACY_AUDIT_DIGESTS.items()}
    intent = records[f'successful-auth-revocations/{sha}/intent.json']
    done = records[f'successful-auth-revocations/{sha}/completed.json']
    retired = records[f'retired/{sha}/completed.json']
    if (any(record.get('old_sha') != sha or record.get('new_sha') != LEGACY_SUCCESSOR
            for record in (intent, done, retired))
            or intent.get('native_continuation') != value
            or done.get('state') != 'SUCCESSFUL_IDENTITY_REVOKED'
            or retired.get('state') != 'RETIRED'):
        raise ContinuationError('historical native completion differs')
    return value


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
    observed_link = observed.get('backend_link')
    observed_vendor = {key: value for key, value in observed.items() if key != 'backend_link'}
    if observed_vendor != proof['vendor'] or observed_link != proof.get('backend_link'):
        raise ContinuationError('native continuation vendor terminal differs')
    return proof
