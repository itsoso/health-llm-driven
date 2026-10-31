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
