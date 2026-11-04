"""Native continuation evidence tests use synthetic vendors and temporary sources."""
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def load():
    path = Path(__file__).with_name('successful_native_continuation.py')
    spec = importlib.util.spec_from_file_location('successful_native_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def evidence(monkeypatch, tmp_path):
    m = load()
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'producer.py').write_bytes(b'reviewed synthetic producer')
    profile = {
        'workspace_kind': 'successful-backend', 'run_attempt': 1,
        'run_id': 123, 'build_id': 'synthetic-build', 'submission_id': 'synthetic-upload',
        'log_sha256': 'a' * 64, 'jobs_sha256': 'b' * 64,
        'canonical_hashes': {'producer.py': hashlib.sha256((source / 'producer.py').read_bytes()).hexdigest()},
    }
    native = SimpleNamespace(WORKFLOW_ID=456, profile_for=lambda sha: profile)
    b = SimpleNamespace(secure=lambda *_: None, canonical_source=lambda sha: source)
    monkeypatch.setattr(m, 'load', lambda _b, name: native if name == 'native_release_retirement'
                        else SimpleNamespace(_CREDENTIAL_PATH='/fixed/synthetic', _read_credential_file=lambda _: 'synthetic-secret'))
    workspace = {'state': 'SUCCEEDED', 'inventory': ['build-started.json', 'native-started.json']}
    _, proof = m.expected(b, 'c' * 40)
    calls = []
    def vendor(token, *, native_sha):
        calls.append((token, native_sha))
        return proof['vendor']
    native.vendor_evidence = vendor
    return m, b, profile, native, workspace, proof, calls, source


def test_completed_native_continuation_is_live_verified_and_secret_free(evidence):
    m, b, _, _, workspace, proof, calls, _ = evidence
    assert m.inspect(b, 'c' * 40, workspace) == proof
    assert calls == [('synthetic-secret', 'c' * 40)]
    assert 'synthetic-secret' not in repr(proof)
    assert m.validate_saved(b, 'c' * 40, proof) == proof


def test_rerun_continuation_binds_reviewed_prior_attempts(evidence):
    m, b, profile, _, _, _, _, _ = evidence
    profile.update(run_attempt=3, prior_jobs_sha256='c' * 64)
    _, proof = m.expected(b, 'c' * 40)
    assert proof['vendor']['run_attempt'] == 3
    assert proof['vendor']['prior_jobs_sha256'] == 'c' * 64


def test_terminal_upload_failure_is_preserved_in_continuation(evidence):
    m, b, profile, _, _, _, _, _ = evidence
    profile['vendor_state'] = 'VENDOR_UPLOAD_FAILED_UNCERTAIN'
    _, proof = m.expected(b, 'c' * 40)
    assert proof['vendor']['state'] == 'VENDOR_UPLOAD_FAILED_UNCERTAIN'


def test_prior_backend_link_is_preserved_in_continuation(evidence):
    m, b, profile, native, workspace, _, _, _ = evidence
    profile['backend_link'] = {
        'run_id': 789, 'run_attempt': 1,
        'job_ids': {'backend': 999},
        'jobs_sha256': 'c' * 64,
    }
    _, proof = m.expected(b, 'c' * 40)
    assert proof['backend_link'] == {
        'state': 'PRIOR_BACKEND_SUCCEEDED',
        'run_id': 789,
        'run_attempt': 1,
        'workflow_id': 456,
        'jobs_sha256': 'c' * 64,
    }
    observed = {**proof['vendor'], 'backend_link': proof['backend_link']}
    native.vendor_evidence = lambda *args, **kwargs: observed
    assert m.inspect(b, 'c' * 40, workspace) == proof
    assert observed['backend_link'] == proof['backend_link']


@pytest.mark.parametrize('damage', ['missing-upload', 'wrong-kind', 'wrong-producer', 'vendor-differs'])
def test_incomplete_or_mismatched_continuation_fails_closed(evidence, damage):
    m, b, profile, native, workspace, proof, _, source = evidence
    if damage == 'missing-upload': workspace['inventory'].remove('native-started.json')
    if damage == 'wrong-kind': profile['workspace_kind'] = 'native-only'
    if damage == 'wrong-producer': (source / 'producer.py').write_bytes(b'changed')
    if damage == 'vendor-differs': native.vendor_evidence = lambda *a, **k: {**proof['vendor'], 'build_id': 'other'}
    with pytest.raises(m.ContinuationError):
        m.inspect(b, 'c' * 40, workspace)


@pytest.mark.parametrize('damage', ['sha', 'build', 'log', 'jobs', 'extra'])
def test_historical_proof_remains_bound_to_exact_native_terminal(evidence, damage):
    m, b, _, _, _, proof, _, _ = evidence
    import copy
    changed = copy.deepcopy(proof)
    if damage == 'sha': changed['native_sha'] = 'd' * 40
    if damage == 'build': changed['vendor']['build_id'] = 'other'
    if damage == 'log': changed['vendor']['log_sha256'] = 'd' * 64
    if damage == 'jobs': changed['vendor']['jobs_sha256'] = 'd' * 64
    if damage == 'extra': changed['unknown'] = True
    with pytest.raises(m.ContinuationError):
        m.validate_saved(b, 'c' * 40, changed)


def test_backend_without_native_claim_does_not_read_vendor(evidence):
    m, b, _, _, _, _, calls, _ = evidence
    assert m.inspect(b, 'c' * 40, {'state': 'SUCCEEDED', 'inventory': []}) is None
    assert calls == []


def test_consumed_backend_rejection_digest_survives_saved_proof(evidence):
    m, b, profile, _, _, _, _, _ = evidence
    profile.update(terminal_mode='backend-already-consumed', backend_log_sha256='e' * 64)
    _, proof = m.expected(b, 'c' * 40)
    assert proof['vendor']['backend_log_sha256'] == 'e' * 64
    assert m.validate_saved(b, 'c' * 40, proof) == proof
    proof['vendor']['backend_log_sha256'] = 'f' * 64
    with pytest.raises(m.ContinuationError):
        m.validate_saved(b, 'c' * 40, proof)


@pytest.fixture
def legacy_audit(evidence, monkeypatch, tmp_path):
    import json
    import stat
    m, b, profile, native, workspace, _, _, source = evidence
    old = 'ad8949e7eeb4abc73968b0c83ebdb38b64a6cae1'
    successor = '1423dd5d5af378abe679b2aba7ef03761ca5f42a'
    profile['backend_link'] = {'run_id': 789, 'run_attempt': 1, 'jobs_sha256': 'c' * 64}
    _, proof = m.expected(b, old)
    legacy = {k: v for k, v in proof.items() if k != 'backend_link'}
    intent = {'old_sha': old, 'new_sha': successor, 'native_continuation': legacy}
    done = {'old_sha': old, 'new_sha': successor, 'state': 'SUCCESSFUL_IDENTITY_REVOKED',
            'installation_sha256': 'f' * 64}
    retired = {'old_sha': old, 'new_sha': successor, 'state': 'RETIRED'}
    b.STATE = tmp_path / 'state'
    payloads = {'successful-auth-revocations/' + old + '/intent.json': intent,
                'successful-auth-revocations/' + old + '/completed.json': done,
                'retired/' + old + '/completed.json': retired}
    digests = {}
    for name, value in payloads.items():
        path = b.STATE / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True))
        path.chmod(0o600)
        digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    def secure(path, *, private=False):
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('unsafe fixture audit')
    b.secure = lambda path, **kw: secure(path, **kw) if path.is_relative_to(b.STATE) else None
    monkeypatch.setattr(m, 'LEGACY_AUDIT_DIGESTS', digests, raising=False)
    monkeypatch.setattr(m, 'LEGACY_PROOF_SHA256', hashlib.sha256(
        json.dumps(legacy, sort_keys=True, separators=(',', ':')).encode()).hexdigest(), raising=False)
    return m, b, old, legacy, proof, native, workspace, payloads


def test_completed_legacy_audit_is_read_without_upgrade_or_mutation(legacy_audit):
    m, b, old, legacy, _, _, _, payloads = legacy_audit
    before = {name: (b.STATE / name).read_bytes() for name in payloads}
    assert m.validate_saved(b, old, legacy) == legacy
    assert {name: (b.STATE / name).read_bytes() for name in payloads} == before


@pytest.mark.parametrize('damage', ['sha', 'proof', 'intent', 'successor', 'revocation',
                                    'retirement', 'missing', 'symlink', 'mode'])
def test_legacy_audit_fails_closed(legacy_audit, damage):
    import json
    m, b, old, legacy, _, _, _, _ = legacy_audit
    root = b.STATE / 'successful-auth-revocations' / old
    if damage == 'sha': old = 'd' * 40
    elif damage == 'proof': legacy['vendor']['build_id'] = 'changed'
    elif damage == 'missing': (root / 'completed.json').unlink()
    elif damage == 'mode': (root / 'completed.json').chmod(0o644)
    elif damage == 'symlink':
        path = root / 'completed.json'
        path.rename(root / 'other.json')
        path.symlink_to(root / 'other.json')
    else:
        path = root / ('intent.json' if damage in ('intent', 'successor') else 'completed.json')
        if damage == 'retirement': path = b.STATE / 'retired' / old / 'completed.json'
        value = json.loads(path.read_text())
        value['new_sha' if damage == 'successor' else 'changed'] = 'e' * 40
        path.write_text(json.dumps(value))
    with pytest.raises((m.ContinuationError, ValueError, OSError)):
        m.validate_saved(b, old, legacy)


def test_fresh_inspect_cannot_use_legacy_compatibility(legacy_audit):
    m, b, old, legacy, _, native, workspace, _ = legacy_audit
    native.vendor_evidence = lambda *args, **kwargs: legacy['vendor']
    with pytest.raises(m.ContinuationError, match='vendor terminal differs'):
        m.inspect(b, old, workspace)


@pytest.mark.parametrize('damage', ['successor', 'intent-proof', 'unfinished'])
def test_legacy_semantics_fail_even_with_matching_fixture_digest(legacy_audit, monkeypatch, damage):
    import json
    m, b, old, legacy, _, _, _, _ = legacy_audit
    name = f'successful-auth-revocations/{old}/' + ('completed.json' if damage == 'unfinished' else 'intent.json')
    path = b.STATE / name
    value = json.loads(path.read_text())
    if damage == 'successor': value['new_sha'] = 'e' * 40
    elif damage == 'intent-proof': value['native_continuation'] = {}
    else: value['state'] = 'INTENT'
    path.write_text(json.dumps(value))
    monkeypatch.setitem(m.LEGACY_AUDIT_DIGESTS, name, hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(m.ContinuationError, match='completion differs'):
        m.validate_saved(b, old, legacy)


def test_legacy_audit_replacement_during_read_fails(legacy_audit):
    m, b, old, legacy, _, _, _, _ = legacy_audit
    original_secure = b.secure
    path = b.STATE / f'successful-auth-revocations/{old}/intent.json'
    calls = []
    def secure(item, **kwargs):
        original_secure(item, **kwargs)
        if item == path:
            calls.append(item)
            if len(calls) == 2:
                replacement = path.with_suffix('.replacement')
                replacement.write_bytes(path.read_bytes())
                replacement.chmod(0o600)
                replacement.replace(path)
    b.secure = secure
    with pytest.raises(m.ContinuationError, match='audit differs'):
        m.validate_saved(b, old, legacy)
