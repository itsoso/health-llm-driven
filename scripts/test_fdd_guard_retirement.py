"""Fixed fdd restoration must bind both quiesce and canonical restore evidence."""
import copy
import importlib.util
from pathlib import Path
import pytest

PATH = Path(__file__).with_name('fdd_guard_retirement.py')

def module():
    spec = importlib.util.spec_from_file_location('fdd_retirement_test', PATH)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

def fixture(m):
    incident = {'lease': {}, 'workspace': {'deployment.log': {}, 'completed.json': {}},
                'terminal': {}, 'files': {}, 'static_units': {}, 'dependencies': {}}
    snapshot = {'incident': incident, 'config': {}, 'installed': {}}
    quiesce = {'failed_sha': m.FAILED, 'production_sha': m.PRODUCTION,
               'snapshot': snapshot, 'mixed': {'beat': 'running'}}
    quiesce['evidence_sha256'] = m.digest(quiesce)
    quiesce['state'] = 'QUIESCE_BEAT_FOR_ORIGINAL_RECOVERY'
    intent = {'recovery_sha': m.FAILED, 'failed_sha': m.FAILED,
              'production_sha': m.PRODUCTION, 'snapshot': snapshot}
    intent['evidence_sha256'] = m.digest(intent)
    identities = {'intent': {'sha256': 'a' * 64}, 'restore_intent': {'sha256': 'b' * 64}}
    continuation = {**intent, 'snapshot': {**snapshot, 'prior_consumed_intents': identities}}
    continuation['evidence_sha256'] = m.digest({k:v for k,v in continuation.items() if k != 'evidence_sha256'})
    done = {k: continuation[k] for k in ('recovery_sha', 'failed_sha', 'production_sha', 'evidence_sha256')}
    done.update(state='RESTORED_PREVIOUS_SERVICES', stable_services={}, original_release_and_lease_preserved=True)
    return quiesce, intent, continuation, done, identities

def test_binding_all_four_receipts():
    m = module(); q, i, c, d, ids = fixture(m)
    m.validate_restoration(q, i, c, d, ids)
    assert m.semantic_snapshot(i['snapshot'])['recovery_snapshot'] == i['snapshot']

@pytest.mark.parametrize('mutation', ['quiesce_digest', 'snapshot', 'failed_sha', 'completed_digest', 'extra_field'])
def test_reject_restoration_drift(mutation):
    m = module(); q, i, c, d, ids = copy.deepcopy(fixture(m))
    if mutation == 'quiesce_digest': q['evidence_sha256'] = '0' * 64
    if mutation == 'snapshot': q['snapshot']['extra'] = True
    if mutation == 'failed_sha': i['failed_sha'] = 'a' * 40
    if mutation == 'completed_digest': d['evidence_sha256'] = '0' * 64
    if mutation == 'extra_field': d['extra'] = True
    with pytest.raises(m.ClosureError): m.validate_restoration(q, i, c, d, ids)


def bootstrap():
    spec = importlib.util.spec_from_file_location('fdd_bootstrap_test', PATH.with_name('bootstrap_trusted_release.py'))
    value = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_bootstrap_fixed_profile_dispatch(monkeypatch):
    b = bootstrap(); fixed = object()
    monkeypatch.setattr(b, '_fdd_guard_module', lambda: fixed, raising=False)
    assert b._dinner_profile_module('fdd5659502888d44bf91c9b35a7368366932098f') is fixed


def test_bootstrap_fdd_historical_dispatch(tmp_path, monkeypatch):
    b = bootstrap(); sha = 'fdd5659502888d44bf91c9b35a7368366932098f'
    (tmp_path / 'fdd-guard-closures' / sha).mkdir(parents=True)
    monkeypatch.setattr(b, 'STATE', tmp_path)
    import types
    calls = []
    def closed(owner, candidate, receipt, *, historical):
        calls.append((candidate, receipt, historical)); return {'state': 'CLOSED_DINNER_GUARD_RELEASE'}
    monkeypatch.setattr(b, '_fdd_guard_module', lambda: types.SimpleNamespace(closed_evidence=closed), raising=False)
    assert b._workspace_evidence(sha, recovery_receipt='secret', historical=True)['state'] == 'CLOSED_DINNER_GUARD_RELEASE'
    assert calls == [(sha, 'secret', True)]


def test_bootstrap_fdd_old_profile_conflict(tmp_path, monkeypatch):
    b = bootstrap(); sha = 'fdd5659502888d44bf91c9b35a7368366932098f'
    for folder in ('fdd-guard-closures', 'dinner-guard-closures'):
        (tmp_path / folder / sha).mkdir(parents=True)
    monkeypatch.setattr(b, 'STATE', tmp_path)
    with pytest.raises(b.BootstrapError, match='conflicting'):
        b._workspace_evidence(sha, recovery_receipt='secret')


def test_normalization_preserves_config_installed_and_unknown_incident_fields():
    m = module(); q, i, c, d, ids = fixture(m)
    i['snapshot']['incident']['stage'] = {'staged.sha256': {'sha256': 'a' * 64}}
    i['snapshot']['config']['loopback.key'] = {'sha256': 'b' * 64}
    i['snapshot']['installed'] = {'sha256': 'c' * 64}
    normalized = m.semantic_snapshot(i['snapshot'])
    assert normalized['recovery_snapshot'] == i['snapshot']
    assert normalized['recovery_snapshot']['incident']['stage']['staged.sha256']['sha256'] == 'a' * 64


def test_restoration_requires_real_completed_pins(tmp_path, monkeypatch):
    m = module()
    root = tmp_path / 'contained-service-recoveries' / m.FAILED
    (root / 'restore').mkdir(parents=True)
    (root / m.CONTINUATION).mkdir()
    for path in (root / 'intent.json', root / 'restore/intent.json', root / m.CONTINUATION / 'intent.json', root / m.CONTINUATION / 'completed.json'):
        path.write_text('{}')
    import types
    b = types.SimpleNamespace(STATE=tmp_path)
    monkeypatch.setattr(m, 'private_directory', lambda *args: None)
    monkeypatch.setattr(m, 'load', lambda *args: types.SimpleNamespace(identity=lambda p: ({'sha256': 'a' * 64}, b'{}')))
    monkeypatch.setattr(m, 'QUIESCE_INTENT_PIN', '')
    with pytest.raises(m.ClosureError): m.restoration(b, tmp_path)


def test_historical_branch_does_not_inspect_current_installation():
    # Immutable recovery/workspace proof is before the explicit nonhistorical boundary.
    import inspect
    source = inspect.getsource(module().closed_evidence)
    prefix, live = source.split('    if not historical:', 1)
    assert '_installation_evidence' not in prefix
    assert '_installation_evidence' in live
    assert 'workspace(b, source)' in prefix and 'restoration(b, source)' in prefix

@pytest.mark.parametrize('mutation', ['prior_identity', 'child_snapshot', 'child_extra', 'child_digest', 'child_sha', 'original_completed_digest'])
def test_continuation_chain_rejects_drift(mutation):
    m = module(); q, i, c, d, ids = copy.deepcopy(fixture(m))
    if mutation == 'prior_identity': c['snapshot']['prior_consumed_intents'] = {'wrong': True}
    if mutation == 'child_snapshot': c['snapshot'] = {**c['snapshot'], 'installed': {'drift': True}}
    if mutation == 'child_extra': c['snapshot']['unknown'] = True
    if mutation == 'child_digest': c['evidence_sha256'] = '0' * 64
    if mutation == 'child_sha': c['recovery_sha'] = 'c' * 40
    if mutation == 'original_completed_digest': d['evidence_sha256'] = i['evidence_sha256']
    with pytest.raises(m.ClosureError): m.validate_restoration(q, i, c, d, ids)

@pytest.mark.parametrize('extra', ['original_completed', 'root_extra', 'child_extra', 'missing_completed', None])
def test_exact_consumed_and_success_audit_tree(tmp_path, monkeypatch, extra):
    import json, hashlib, types
    m = module(); q, i, c, d, ids = fixture(m)
    root = tmp_path / 'contained-service-recoveries' / m.FAILED
    original = root / 'restore'; child = root / m.CONTINUATION
    original.mkdir(parents=True); child.mkdir()
    def ident(path):
        raw = path.read_bytes(); st = path.stat()
        return {'sha256': hashlib.sha256(raw).hexdigest(), 'st_ino': st.st_ino}, raw
    for path, value in ((root/'intent.json',q),(original/'intent.json',i)):
        path.write_text(json.dumps(value))
    ids = {'intent': ident(root/'intent.json')[0], 'restore_intent': ident(original/'intent.json')[0]}
    c['snapshot']['prior_consumed_intents'] = ids
    c['evidence_sha256'] = m.digest({k:v for k,v in c.items() if k!='evidence_sha256'})
    d['evidence_sha256'] = c['evidence_sha256']
    for path, value in ((child/'intent.json',c),(child/'completed.json',d)):
        path.write_text(json.dumps(value))
    for name, path in (('QUIESCE_INTENT_PIN',root/'intent.json'),('RESTORE_INTENT_PIN',original/'intent.json'),('CONTINUATION_INTENT_PIN',child/'intent.json'),('CONTINUATION_COMPLETED_PIN',child/'completed.json')):
        monkeypatch.setattr(m,name,ident(path)[0]['sha256'])
    monkeypatch.setattr(m, 'private_directory', lambda *args: None)
    monkeypatch.setattr(m, 'load', lambda *args: types.SimpleNamespace(identity=ident))
    if extra=='original_completed': (original/'completed.json').write_text('{}')
    if extra=='root_extra': (root/'other').write_text('{}')
    if extra=='child_extra': (child/'other').write_text('{}')
    if extra=='missing_completed': (child/'completed.json').unlink()
    b=types.SimpleNamespace(STATE=tmp_path)
    if extra:
        with pytest.raises(m.ClosureError): m.restoration(b,tmp_path)
    else:
        got,completed,audit=m.restoration(b,tmp_path)
        assert got==i and completed==d
        assert set(audit)=={'quiesce_intent','restore_intent','continuation_intent','continuation_completed','root','restore','continuation'}

@pytest.mark.parametrize('change', ['known_hosts', 'loopback.conf', 'directory_identity', 'installed_metadata', None])
def test_live_installation_bound_to_recovery_real_files(tmp_path, monkeypatch, change):
    import hashlib, os, types
    m = module(); b = bootstrap()
    config = tmp_path / 'config'; config.mkdir(mode=0o700)
    for name in ('known_hosts','loopback.conf','authorized-release.json','loopback.pub','cloud.pub','loopback.key'):
        p = config / name; p.write_text(name); p.chmod(0o600)
    installed = tmp_path / 'executor'; installed.write_text('canonical'); installed.chmod(0o600)
    monkeypatch.setattr(b, 'CONFIG', config); monkeypatch.setattr(b, 'INSTALLED', installed)
    # Only root ownership/ancestors are simulated; real inventory, mode, inode,
    # file hashes and installed timestamps are used throughout.
    monkeypatch.setattr(b, 'secure', lambda *args, **kwargs: None)
    def identity(p):
        s = p.stat(); raw = p.read_bytes()
        return {'inode':s.st_ino,'mtime_ns':s.st_mtime_ns,'sha256':hashlib.sha256(raw).hexdigest()},raw
    helper = types.SimpleNamespace(identity=identity)
    snapshot = {'config':b._inventory(config,{p.name for p in config.iterdir()}), 'installed':identity(installed)[0]}
    if change in ('known_hosts','loopback.conf'): (config/change).write_text('drift')
    if change=='directory_identity':
        previous=tmp_path/'previous';config.rename(previous);config.mkdir(mode=0o700)
        for path in previous.iterdir():path.rename(config/path.name)
    if change=='installed_metadata':
        st=installed.stat();os.utime(installed,ns=(st.st_atime_ns,st.st_mtime_ns+1000000))
    if change:
        with pytest.raises(m.ClosureError):m.assert_recovery_installation(b,helper,snapshot)
    else:m.assert_recovery_installation(b,helper,snapshot)
