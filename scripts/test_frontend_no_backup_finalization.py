"""Installed-only closure preserves the failure, and partial closure blocks."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_frontend_no_backup import setup, execute, test_mount_namespace  # noqa: F401
from test_trusted_frontend_publish_history import load


@pytest.fixture
def installed(tmp_path, monkeypatch):
    values = setup(tmp_path, monkeypatch)
    _, publisher, plan, _, _, _, events = values
    def fail(): raise RuntimeError('CSR readback false negative')
    monkeypatch.setattr(publisher, 'verify_pages', fail)
    with pytest.raises(Exception): execute(values)
    server = load('trusted_release_server')
    monkeypatch.setattr(server, 'secure_path', lambda *a, **kw: None)
    monkeypatch.setattr(server, 'validate_metadata', lambda *a, **kw: None)
    monkeypatch.setattr(server, '_read_private', lambda p: p.read_bytes())
    binding = {k: plan[k] for k in ('publisher_sha', 'production_sha', 'frontend_tree', 'operation_id')}
    binding['artifact_digest'] = 'e' * 64
    monkeypatch.setattr(server, 'NO_BACKUP_FINALIZATION_BINDING', binding)
    monkeypatch.setattr(server, 'NO_BACKUP_FINALIZATION_OPERATION', plan['operation_id'])
    spec = importlib.util.spec_from_file_location('closure', Path(__file__).with_name('frontend_no_backup_finalization.py'))
    finalizer = importlib.util.module_from_spec(spec); spec.loader.exec_module(finalizer)
    monkeypatch.setattr(finalizer, 'STATE', publisher.STATE)
    monkeypatch.setattr(finalizer, 'LEASE', publisher.LEASE)
    operation = publisher.STATE / 'frontend-publications' / plan['operation_id']
    lease = finalizer.lease_evidence(server, operation)
    original = server.no_backup_finalization_original(publisher.STATE, plan['operation_id'])
    closure_plan = {'schema_version': 1, 'profile': 'csr-login-readback-v1', 'finalizer_sha': 'f' * 40,
                    'original': original, 'lease': lease, 'process': {'MainPID': '123'}}
    writes = []
    def write(path, raw):
        with path.open('xb') as stream: stream.write(raw)
        writes.append(path.name)
    bootstrap = SimpleNamespace(_write=write)
    return finalizer, server, closure_plan, bootstrap, operation, events, writes


def finish(values):
    f, s, plan, b, *_ = values
    return f.finalize(plan, lambda: plan, s, b, lambda: None)


def test_finalization_preserves_original_evidence_and_never_mutates_service(installed):
    f, s, plan, _, operation, events, writes = installed
    before = {p.name: s._finalization_file_evidence(p) for p in operation.iterdir()}
    service_events = list(events)
    result = finish(installed)
    assert result['state'] == 'FINALIZED_NO_BACKUP_PUBLICATION'
    assert not f.LEASE.exists()
    assert {p.name: s._finalization_file_evidence(p) for p in operation.iterdir()} == before
    assert events == service_events
    assert writes == ['intent.json', 'verified.json', 'completed.json']
    catalog = s.assert_frontend_publication_history(f.STATE)
    assert set(catalog) == {operation.name}
    assert s.frontend_publication_completion(f.STATE, operation.name) == result
    with pytest.raises(Exception): finish(installed)


@pytest.mark.parametrize('mutation', ['failed', 'claim', 'ready', 'build-log', 'original-inode', 'orphan', 'missing-terminal', 'intent', 'verified', 'completed'])
def test_history_rejects_changed_original_or_partial_finalization(installed, mutation):
    f, s, plan, _, operation, *_ = installed
    finish(installed)
    audit = f.STATE / 'frontend-publication-finalizations' / operation.name
    artifact = f.STATE / 'frontend-artifacts' / operation.name
    if mutation == 'failed': (operation / 'failed.json').write_text('{}')
    elif mutation == 'claim': (artifact / 'claim.json').write_text('{}')
    elif mutation == 'ready': (artifact / 'ready.json').write_text('{}')
    elif mutation == 'build-log': (operation / 'build.log').write_text('changed')
    elif mutation == 'original-inode':
        p = operation / 'failed.json'; raw = p.read_bytes(); p.unlink(); p.write_bytes(raw)
    elif mutation == 'orphan': (audit.parent / ('0' * 32)).mkdir()
    elif mutation == 'missing-terminal': (audit / 'completed.json').unlink()
    else: (audit / (mutation + '.json')).write_text('{}')
    with pytest.raises(s.LaunchError): s.assert_frontend_publication_history(f.STATE)


@pytest.mark.parametrize('step', ['intent.json', 'verified.json', 'completed.json'])
def test_write_failure_never_becomes_success(installed, step):
    f, s, plan, b, operation, *_ = installed
    original = b._write
    def fail(path, raw):
        if path.name == step: raise OSError('fsync failure')
        original(path, raw)
    b._write = fail
    with pytest.raises(OSError): finish(installed)
    with pytest.raises(s.LaunchError): s.assert_frontend_publication_history(f.STATE)
    assert (operation / 'failed.json').exists()
    if step != 'completed.json': assert f.LEASE.exists()


@pytest.mark.parametrize('step', ['root-parent', 'audit-parent', 'lease-parent', 'label', 'stage', 'started_at', 'token', 'lease-directory'])
def test_partial_release_and_fsync_failure_remain_blocked(installed, monkeypatch, step):
    f, s, plan, _, operation, *_ = installed
    sync = s._sync_directory
    def sync_failure(path):
        targets = {'root-parent': f.STATE, 'audit-parent': f.STATE / 'frontend-publication-finalizations', 'lease-parent': f.LEASE.parent}
        if path == targets.get(step): raise OSError('fsync failure')
        return sync(path)
    monkeypatch.setattr(s, '_sync_directory', sync_failure)
    unlink = Path.unlink; rmdir = Path.rmdir
    def unlink_failure(path, *args, **kwargs):
        if path.parent == f.LEASE and path.name == step: raise OSError('unlink failure')
        return unlink(path, *args, **kwargs)
    def rmdir_failure(path):
        if path == f.LEASE and step == 'lease-directory': raise OSError('rmdir failure')
        return rmdir(path)
    monkeypatch.setattr(Path, 'unlink', unlink_failure); monkeypatch.setattr(Path, 'rmdir', rmdir_failure)
    with pytest.raises(OSError): finish(installed)
    with pytest.raises(s.LaunchError): s.assert_frontend_publication_history(f.STATE)
    assert (operation / 'failed.json').exists()


@pytest.mark.parametrize('field', ['token', 'stage', 'label', 'directory'])
def test_rebound_lease_is_never_released(installed, field):
    f, s, plan, _, operation, *_ = installed
    if field == 'directory':
        old = f.LEASE.with_name('original'); f.LEASE.rename(old); f.LEASE.mkdir(mode=0o700)
        for p in old.iterdir(): (f.LEASE / p.name).write_bytes(p.read_bytes())
    else:
        (f.LEASE / field).write_text(('a' * 64 if field == 'token' else 'wrong') + '\n')
    with pytest.raises(f.FinalizationError): finish(installed)
    assert f.LEASE.exists()
    assert not (f.STATE / 'frontend-publication-finalizations' / operation.name / 'completed.json').exists()


def test_pending_exception_is_only_the_bound_profile_and_other_failures_block(installed):
    f, s, plan, _, operation, *_ = installed
    s.assert_frontend_publication_history(f.STATE, pending_no_backup_finalization=operation.name)
    with pytest.raises(s.LaunchError): s.assert_frontend_publication_history(f.STATE, pending_no_backup_finalization='0' * 32)
    (operation.parent / ('1' * 32)).mkdir(mode=0o700)
    with pytest.raises(s.LaunchError): s.assert_frontend_publication_history(f.STATE, pending_no_backup_finalization=operation.name)
