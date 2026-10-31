"""The interrupted pre-revocation audit stays immutable; recovery is fail closed."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from test_bootstrap_trusted_release import (
    HOST, NEW_SHA, PUBLIC, SHA, successful_rotation_fixture,
)


def module():
    path = Path(__file__).with_name('successful_auth_abort.py')
    spec = importlib.util.spec_from_file_location('abort_fixture', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def interrupted(monkeypatch, tmp_path, *, build_lock=False):
    b, calls, receipt = successful_rotation_fixture(monkeypatch, tmp_path)
    if build_lock:
        (b.STATE / SHA / "build.lock").touch(mode=0o600)
    original_idle = b._assert_idle
    def competing_publisher(**kwargs):
        if (b.STATE / 'successful-auth-revocations' / SHA / 'intent.json').exists():
            raise b.BootstrapError('release process still present')
        return original_idle(**kwargs)
    monkeypatch.setattr(b, '_assert_idle', competing_publisher)
    with pytest.raises(b.BootstrapError, match='release process'):
        b.rotate(SHA, NEW_SHA, 0, PUBLIC, successful_workspace_sha256=receipt)
    monkeypatch.setattr(b, '_assert_idle', original_idle)
    m = module()
    record = b.STATE / 'successful-auth-revocations' / SHA
    monkeypatch.setattr(m, 'OLD', SHA)
    monkeypatch.setattr(m, 'FAILED', NEW_SHA)
    monkeypatch.setattr(m, 'ORIGINAL_INTENT', hashlib.sha256((record / 'intent.json').read_bytes()).hexdigest())
    monkeypatch.setattr(m, 'POLICY', hashlib.sha256((b.CONFIG / 'authorized-release.json').read_bytes()).hexdigest())
    monkeypatch.setattr(b, '_successful_abort_module', lambda: m)
    monkeypatch.setattr(b, '_recovery_production_proof', lambda *_: None)
    monkeypatch.setattr(b, '_recovery_process_proof', lambda *_: None)
    source, _ = b.reviewed_source('c' * 40)
    (source / 'scripts/successful_auth_abort.py').write_bytes(Path(m.__file__).read_bytes())
    return b, m, record, receipt


def close(b, m):
    inspected = m.abort(b, 'c' * 40)
    return m.abort(b, 'c' * 40, evidence_sha256=inspected['evidence_sha256'])


def test_original_failure_then_abort_then_fresh_rotation(monkeypatch, tmp_path):
    b, m, record, receipt = interrupted(monkeypatch, tmp_path)
    original = (record / 'intent.json').read_bytes()
    authorized = b.AUTHORIZED.read_bytes()
    key = (b.CONFIG / 'loopback.key').read_bytes()
    done = close(b, m)
    assert done['state'] == 'ABORTED_BEFORE_REVOCATION'
    assert b.AUTHORIZED.read_bytes() == authorized
    assert (b.CONFIG / 'loopback.key').read_bytes() == key
    assert b._retired_history() == {}
    assert (record / 'intent.json').read_bytes() == original
    with pytest.raises(b.BootstrapError):
        b.rotate(SHA, NEW_SHA, 0, PUBLIC, successful_workspace_sha256=receipt,
                 successful_abort_receipt=done['receipt'])
    with pytest.raises(b.BootstrapError):
        b.rotate(SHA, 'c' * 40, 0, PUBLIC, successful_workspace_sha256=receipt)
    assert b.rotate(SHA, 'c' * 40, 0, PUBLIC, successful_workspace_sha256=receipt,
                    successful_abort_receipt=done['receipt'])['state'] == 'INSTALLED'
    assert (record / 'intent.json').read_bytes() == original
    assert b._successful_auth_revocation_history()[SHA]['new_sha'] == 'c' * 40
    assert (record / 'successor' / 'completed.json').exists()
    with pytest.raises(b.BootstrapError):
        m.abort(b, 'c' * 40)


@pytest.mark.parametrize('fault', ['authorized', 'cloud-line', 'key-missing', 'derived-key',
    'policy', 'executor', 'workspace', 'intent', 'retirement', 'consumed', 'lease', 'process'])
def test_abort_refuses_unproved_pre_revocation(monkeypatch, tmp_path, fault):
    b, m, record, _ = interrupted(monkeypatch, tmp_path)
    if fault == 'authorized':
        b.AUTHORIZED.write_text(b.AUTHORIZED.read_text() + 'extra\n')
    elif fault == 'cloud-line':
        b.AUTHORIZED.write_text('\n'.join(x for x in b.AUTHORIZED.read_text().splitlines() if PUBLIC not in x))
    elif fault == 'key-missing':
        (b.CONFIG / 'loopback.key').unlink()
    elif fault == 'derived-key':
        original_run = b._run
        def run(args, **kwargs):
            if args[0] == '/usr/bin/ssh-keygen' and '-y' in args:
                from types import SimpleNamespace
                return SimpleNamespace(stdout=HOST)
            return original_run(args, **kwargs)
        monkeypatch.setattr(b, '_run', run)
    elif fault == 'policy':
        (b.CONFIG / 'authorized-release.json').write_text('{}')
    elif fault == 'executor':
        b.INSTALLED.write_text('drift')
    elif fault == 'workspace':
        (b.STATE / SHA / 'completed.json').write_text('{}')
    elif fault == 'intent':
        (record / 'intent.json').write_text('{}')
    elif fault == 'retirement':
        (b.STATE / 'retired' / SHA).mkdir(parents=True)
    elif fault == 'consumed':
        (b.STATE / NEW_SHA).mkdir()
    elif fault == 'lease':
        b.BUSINESS_LEASE.mkdir()
    else:
        monkeypatch.setattr(b, '_assert_idle', lambda **_: (_ for _ in ()).throw(b.BootstrapError('competing publisher')))
    with pytest.raises((b.BootstrapError, OSError, ValueError)):
        m.abort(b, 'c' * 40)
    assert not (record / 'abort-intent.json').exists()


def test_abort_inspect_apply_drift(monkeypatch, tmp_path):
    b, m, record, _ = interrupted(monkeypatch, tmp_path)
    inspected = m.abort(b, 'c' * 40)
    key = b.CONFIG / 'loopback.key'
    key.write_text(key.read_text() + '\n')
    with pytest.raises(b.BootstrapError):
        m.abort(b, 'c' * 40, evidence_sha256=inspected['evidence_sha256'])
    assert not (record / 'abort-intent.json').exists()


@pytest.mark.parametrize('fault', ['intent-write', 'completion-fsync', 'after-intent-drift', 'lock-replaced'])
def test_interrupted_abort_never_authorizes_successor(monkeypatch, tmp_path, fault):
    b, m, record, receipt = interrupted(monkeypatch, tmp_path)
    inspected = m.abort(b, 'c' * 40)
    original_write = b._write
    def write(path, data):
        if path.name == 'abort-intent.json' and fault == 'intent-write':
            path.write_text('{')
            raise OSError('interrupted')
        original_write(path, data)
        if path.name == 'abort-completed.json' and fault == 'completion-fsync':
            raise OSError('interrupted fsync')
        if path.name == 'abort-intent.json' and fault == 'after-intent-drift':
            b.AUTHORIZED.write_text('revoked')
        if path.name == 'abort-intent.json' and fault == 'lock-replaced':
            lock = b.STATE / 'launcher.lock'
            lock.unlink()
            lock.touch(mode=0o600)
    monkeypatch.setattr(b, '_write', write)
    with pytest.raises((b.BootstrapError, OSError)):
        m.abort(b, 'c' * 40, evidence_sha256=inspected['evidence_sha256'])
    monkeypatch.setattr(b, '_write', original_write)
    with pytest.raises(b.BootstrapError):
        b.rotate(SHA, 'c' * 40, 0, PUBLIC, successful_workspace_sha256=receipt)
    assert not (record / 'successor').exists()


@pytest.mark.parametrize('fault', ['fake-completion', 'missing-completion', 'extra', 'wrong-receipt', 'successor-incomplete'])
def test_aborted_history_remains_closed(monkeypatch, tmp_path, fault):
    b, m, record, receipt = interrupted(monkeypatch, tmp_path)
    done = close(b, m)
    if fault == 'fake-completion':
        (record / 'abort-completed.json').write_text('{}')
    elif fault == 'missing-completion':
        (record / 'abort-completed.json').unlink()
    elif fault == 'extra':
        (record / 'extra').touch()
    elif fault == 'successor-incomplete':
        (record / 'successor').mkdir(mode=0o700)
    else:
        done['receipt'] = '0' * 64
    with pytest.raises(b.BootstrapError):
        b.rotate(SHA, 'c' * 40, 0, PUBLIC, successful_workspace_sha256=receipt,
                 successful_abort_receipt=done['receipt'])


def test_unrelated_pending_attempt_is_not_exempted(monkeypatch, tmp_path):
    b, m, record, _ = interrupted(monkeypatch, tmp_path)
    unrelated = record.parent / ('d' * 40)
    unrelated.mkdir(mode=0o700)
    (unrelated / 'intent.json').write_text('{}')
    with pytest.raises(b.BootstrapError):
        m.abort(b, 'c' * 40)
    assert not (record / 'abort-intent.json').exists()


def test_new_competitor_after_abort_intent_blocks_terminal(monkeypatch, tmp_path):
    b, m, record, _ = interrupted(monkeypatch, tmp_path)
    inspected = m.abort(b, 'c' * 40)
    original_idle = b._assert_idle
    def check(**kwargs):
        if (record / 'abort-intent.json').exists():
            raise b.BootstrapError('competing publisher appeared')
        return original_idle(**kwargs)
    monkeypatch.setattr(b, '_assert_idle', check)
    with pytest.raises(b.BootstrapError, match='competing publisher'):
        m.abort(b, 'c' * 40, evidence_sha256=inspected['evidence_sha256'])
    assert not (record / 'abort-completed.json').exists()
    assert PUBLIC in b.AUTHORIZED.read_text()
    assert (b.CONFIG / 'loopback.key').exists()


def test_incomplete_successor_cannot_be_replayed(monkeypatch, tmp_path):
    b, m, record, receipt = interrupted(monkeypatch, tmp_path)
    done = close(b, m)
    original_idle = b._assert_idle
    def check(**kwargs):
        if (record / 'successor' / 'intent.json').exists():
            raise b.BootstrapError('competing publisher appeared')
        return original_idle(**kwargs)
    monkeypatch.setattr(b, '_assert_idle', check)
    with pytest.raises(b.BootstrapError, match='competing publisher'):
        b.rotate(SHA, 'c' * 40, 0, PUBLIC, successful_workspace_sha256=receipt,
                 successful_abort_receipt=done['receipt'])
    monkeypatch.setattr(b, '_assert_idle', original_idle)
    with pytest.raises(b.BootstrapError):
        b.rotate(SHA, 'd' * 40, 0, PUBLIC, successful_workspace_sha256=receipt,
                 successful_abort_receipt=done['receipt'])
    assert PUBLIC in b.AUTHORIZED.read_text()
    assert (b.CONFIG / 'loopback.key').exists()


def test_failed_production_sha_permanently_consumed(monkeypatch, tmp_path):
    b, _calls, _receipt = successful_rotation_fixture(monkeypatch, tmp_path)
    with pytest.raises(b.BootstrapError, match='aborted release SHA'):
        b._assert_fresh_sha('a030c61539c388e78a79fa6c6e01392310044d12', {})


def test_abort_inspect_apply_original_launcher_inode_bound(monkeypatch, tmp_path):
    b, m, record, _ = interrupted(monkeypatch, tmp_path)
    inspected = m.abort(b, 'c' * 40)
    lock = b.STATE / 'launcher.lock'
    prior = lock.with_name('test-retained-lock')
    lock.rename(prior)
    lock.touch(mode=0o600)
    with pytest.raises(b.BootstrapError, match='changed since inspection'):
        m.abort(b, 'c' * 40, evidence_sha256=inspected['evidence_sha256'])
    assert not (record / 'abort-intent.json').exists()


@pytest.mark.parametrize('existing', [False, True])
def test_abort_inspect_apply_build_lock_identity_bound(monkeypatch, tmp_path, existing):
    b, m, record, _ = interrupted(monkeypatch, tmp_path, build_lock=existing)
    inspected = m.abort(b, 'c' * 40)
    lock = b.STATE / SHA / 'build.lock'
    if existing:
        lock.rename(tmp_path / 'test-retained-build-lock')
    lock.touch(mode=0o600)
    with pytest.raises(b.BootstrapError):
        m.abort(b, 'c' * 40, evidence_sha256=inspected['evidence_sha256'])
    assert not (record / 'abort-intent.json').exists()
