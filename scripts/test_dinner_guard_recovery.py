"""Synthetic tests only; no SSH, model, application or real database calls."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import pytest

PATH = Path(__file__).with_name('dinner_guard_recovery.py')
SPEC = importlib.util.spec_from_file_location('tested_dinner_recovery', PATH)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def test_fixed_failure_binding():
    assert m.FAILED == 'ae49cf1fc53c567b305c2a9f6cfff5c3257e7309'
    assert m.PRODUCTION == 'f42bb4c6d1c962453a6eadd1318ca6b663174b80'
    assert set(m.LEASE_PINS) == {'token', 'label', 'stage', 'started_at'}
    assert len(m.UNIT_CONFIG_PINS) == 4
    assert all(len(v) == 64 for v in m.FILE_PINS.values())


@pytest.mark.parametrize('unit,state,result', [
    ('health-backend.service', 'inactive', 'success'),
    ('celery-worker.service', 'failed', 'timeout'),
    ('celery-worker.service', 'inactive', 'success'),
])
def test_exact_stopped_states(unit, state, result):
    m.stopped_unit_allowed(unit, {'MainPID': '0', 'ActiveState': state,
        'SubState': 'failed' if state == 'failed' else 'dead', 'Result': result}, [])


@pytest.mark.parametrize('change,pids', [({'MainPID': '24'}, []), ({}, ['24']),
    ({'Result': 'exit-code'}, []), ({'ActiveState': 'active'}, []),
    ({'SubState': 'running'}, [])])
def test_failed_worker_must_be_empty_and_exact(change, pids):
    fields = {'MainPID': '0', 'ActiveState': 'failed', 'SubState': 'failed', 'Result': 'timeout'}
    fields.update(change)
    with pytest.raises(m.RecoveryError):
        m.stopped_unit_allowed('celery-worker.service', fields, pids)


def test_failed_other_service_is_not_special_cased():
    with pytest.raises(m.RecoveryError):
        m.stopped_unit_allowed('health-backend.service', {
            'MainPID': '0', 'ActiveState': 'failed', 'SubState': 'failed', 'Result': 'timeout'}, [])


def test_log_rejects_changed_content_even_if_markers_remain():
    with pytest.raises(m.RecoveryError):
        m.validate_log(b'phase=remote_guard_started phase=remote_pi_install_started pi-runtime/install.sh: No such file or directory')


@pytest.mark.parametrize('marker', [b'command=prepare-code', b'command=install',
    b'phase=remote_writers_stopped', b'phase=remote_checkout_completed'])
def test_log_rejects_later_phase_even_with_rebound_hash(monkeypatch, marker):
    raw = b'phase=remote_guard_started\nphase=remote_pi_install_started\npi-runtime/install.sh: No such file or directory\n' + marker
    monkeypatch.setattr(m, 'LOG_PIN', hashlib.sha256(raw).hexdigest())
    with pytest.raises(m.RecoveryError):
        m.validate_log(raw)


def test_dependency_rejects_any_post_lease_non_bytecode(tmp_path, monkeypatch):
    (tmp_path / 'package.py').write_text('x = 1')
    monkeypatch.setattr(m, 'secure', lambda *a: None)
    monkeypatch.setattr(m, 'LEASE_NS', 1)
    with pytest.raises(m.RecoveryError):
        m.dependency_metadata(tmp_path)


def test_dependency_snapshot_is_deterministic_and_tracks_metadata(tmp_path, monkeypatch):
    (tmp_path / 'package.py').write_text('x = 1')
    monkeypatch.setattr(m, 'secure', lambda *a: None)
    monkeypatch.setattr(m, 'LEASE_NS', 2**63 - 1)
    first = m.dependency_metadata(tmp_path)
    assert first == m.dependency_metadata(tmp_path)
    (tmp_path / 'package.py').write_text('x = 2')
    assert first != m.dependency_metadata(tmp_path)


def core_module():
    path = PATH.with_name('recover_contained_services.py')
    spec = importlib.util.spec_from_file_location('dinner_core_test', path)
    core = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = core
    spec.loader.exec_module(core)
    return core


@pytest.mark.parametrize('health_failure', [False, True])
def test_reused_core_preserves_evidence_and_contains_failed_start(tmp_path, monkeypatch, health_failure):
    core = core_module()
    monkeypatch.setattr(core, 'STATE', tmp_path)
    monkeypatch.setattr(core, '_application_probes', lambda *a: None)
    monkeypatch.setattr(core, '_wait_ready', lambda *a: {'stable': True})
    calls = []
    monkeypatch.setattr(core, '_systemctl', lambda action, unit: calls.append((action, unit)))
    def health():
        if health_failure:
            raise core.RecoveryError('synthetic failure')
    monkeypatch.setattr(core, '_http_probes', health)
    class Proof:
        failed_sha = m.FAILED
        production_sha = m.PRODUCTION
        def snapshot(self): return {'lease': 'unchanged', 'production': m.PRODUCTION}
        def stopped(self): pass
    proof = Proof()
    audit = tmp_path / 'once'
    inspect = core.recover_services(proof, audit, 'a'*40)
    assert calls == [] and not audit.exists()
    if health_failure:
        with pytest.raises(core.RecoveryError):
            core.recover_services(proof, audit, 'a'*40, inspect['evidence_sha256'])
        assert {u for a,u in calls if a == 'stop'} == set(core.UNITS)
        assert not (audit / 'completed.json').exists()
    else:
        result = core.recover_services(proof, audit, 'a'*40, inspect['evidence_sha256'])
        assert result['state'] == 'RESTORED_PREVIOUS_SERVICES'
        assert result['original_release_and_lease_preserved'] is True
    assert (audit / 'intent.json').exists()
    with pytest.raises(core.RecoveryError):
        core.recover_services(proof, audit, 'a'*40, inspect['evidence_sha256'])


@pytest.mark.parametrize('mode,uid,gid,path,allowed', [
    (0o41777, 0, 0, '/run/lock', True),
    (0o40777, 0, 0, '/run/lock', False),
    (0o41777, 1, 0, '/run/lock', False),
    (0o41777, 0, 1, '/run/lock', False),
    (0o41777, 0, 0, '/tmp', False),
    (0o120777, 0, 0, '/run/lock', False),
])
def test_only_exact_sticky_lease_parent_exception(monkeypatch, mode, uid, gid, path, allowed):
    from types import SimpleNamespace
    info = SimpleNamespace(st_mode=mode, st_uid=uid, st_gid=gid)
    monkeypatch.setattr(Path, 'lstat', lambda self: info)
    if allowed:
        assert m.secure(Path(path), True, lease_parent=True) is info
    else:
        with pytest.raises(m.RecoveryError):
            m.secure(Path(path), True, lease_parent=True)


@pytest.mark.parametrize('kind', ['empty_directory', 'directory_symlink'])
def test_dependency_rejects_post_lease_directory_entries(tmp_path, monkeypatch, kind):
    from types import SimpleNamespace
    package = tmp_path / 'package.py'
    package.write_text('x = 1')
    if kind == 'empty_directory':
        (tmp_path / 'new_package').mkdir()
    else:
        outside = tmp_path.parent / (tmp_path.name + '-outside')
        outside.mkdir()
        (tmp_path / 'new_package').symlink_to(outside, target_is_directory=True)
    original = Path.lstat
    def observed(path):
        info = original(path)
        if path == package:
            fields = {key: getattr(info, key) for key in m.FIELDS}
            fields.update(st_ctime_ns=0, st_mtime_ns=0)
            return SimpleNamespace(**fields)
        return info
    monkeypatch.setattr(Path, 'lstat', observed)
    monkeypatch.setattr(m, 'secure', lambda *a: None)
    monkeypatch.setattr(m, 'LEASE_NS', 1)
    with pytest.raises(m.RecoveryError):
        m.dependency_metadata(tmp_path)


def test_dependency_walk_error_is_not_silently_skipped(tmp_path, monkeypatch):
    (tmp_path / 'package.py').write_text('x = 1')
    monkeypatch.setattr(m, 'secure', lambda *a: None)
    monkeypatch.setattr(m, 'LEASE_NS', 2**63 - 1)
    def failed_walk(root, **kwargs):
        yield str(root), [], ['package.py']
        if kwargs.get('onerror'):
            kwargs['onerror'](PermissionError('synthetic inaccessible subdirectory'))
    monkeypatch.setattr(m.os, 'walk', failed_walk)
    with pytest.raises(m.RecoveryError):
        m.dependency_metadata(tmp_path)
