"""No-backup publication must fail closed without retaining old artifacts."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

import pytest

from test_trusted_frontend_publish import execution_fixture
from test_trusted_frontend_publish_history import evidence  # noqa: F401


def load():
    spec = importlib.util.spec_from_file_location('no_backup_test', Path(__file__).with_name('trusted_frontend_no_backup.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def test_mount_namespace(tmp_path, monkeypatch):
    # Ordinary tests run on macOS too. The native test below uses real procfs.
    mountinfo = tmp_path / 'mountinfo'
    mountinfo.write_text('1 0 0:1 / / rw - rootfs rootfs rw\n')
    original = load
    def configured():
        module = original()
        monkeypatch.setattr(module, 'MOUNTINFO', mountinfo, raising=False)
        return module
    monkeypatch.setitem(globals(), 'load', configured)


def setup(tmp_path, monkeypatch):
    publisher, plan, helper, server, build, events = execution_fixture(tmp_path, monkeypatch)
    module = load()
    monkeypatch.setattr(module, 'OWNER', os.getuid())
    stage = publisher.BUILDS / plan['operation_id'] / 'frontend'
    stage.mkdir(parents=True)
    for name in ('.next', 'node_modules'):
        (stage / name).mkdir()
        (stage / name / 'new').write_text('candidate')
    binding = dict(schema_version=1, publisher_sha=plan['publisher_sha'], frontend_tree=plan['frontend_tree'],
                   artifact_id=plan['operation_id'], package_lock_sha256='a' * 64,
                   recipe_sha256='b' * 64, public_build_env={}, toolchain={})
    artifact = p_artifact = publisher.STATE / 'frontend-artifacts'
    artifact.mkdir(mode=0o700)
    artifact = p_artifact / plan['operation_id']; artifact.mkdir(mode=0o700)
    def write(name, value): (artifact / name).write_text(json.dumps(value))
    write('intent.json', dict(binding=binding, state='FRONTEND_ARTIFACT_PREPARING'))
    (artifact / 'prepare.lock').write_bytes(b'')
    (artifact / 'build.log').write_text('verified prepared build')
    manifest = dict(binding=binding, state='FRONTEND_ARTIFACT_READY', artifact_digest='e' * 64,
                    intent_sha256=hashlib.sha256((artifact / 'intent.json').read_bytes()).hexdigest(),
                    build_log_sha256=hashlib.sha256((artifact / 'build.log').read_bytes()).hexdigest())
    write('ready.json', manifest)
    proof = dict(artifact_id=plan['operation_id'], manifest_sha256=hashlib.sha256((artifact / 'ready.json').read_bytes()).hexdigest(), manifest=manifest)
    plan.update(publication_policy='no-backup-v1', prepared_artifact=proof)
    def consume(*args):
        (args[-1] / 'build.log').write_text('verified prepared build')
        write('claim.json', dict(schema_version=1, artifact_id=plan['operation_id'], operation_id=plan['operation_id'],
                                production_sha=plan['production_sha'], manifest_sha256=proof['manifest_sha256']))
        events.append(('consume',))
        return 'e' * 64
    monkeypatch.setattr(publisher, 'load_artifact', lambda *a: SimpleNamespace(consume=consume))
    monkeypatch.setattr(module, 'assert_stopped', lambda *a: events.append(('stopped',)))
    monkeypatch.setattr(module, 'assert_installed_consumer', lambda *a: None)
    monkeypatch.setattr(publisher, 'assert_preserved', lambda *a: None)
    return module, publisher, plan, helper, server, build, events


def execute(values):
    m, p, plan, helper, server, build, events = values
    return m.execute(plan, Path('/canonical'), helper, None, server, build, p, lambda: events.append(('locks',)))


def test_promotes_prepared_artifact_without_old_copies(tmp_path, monkeypatch):
    values = setup(tmp_path, monkeypatch)
    m, p, plan, _, server, _, events = values
    result = execute(values)
    assert result['state'] == 'FRONTEND_SUCCEEDED'
    assert result['publication_policy'] == 'no-backup-v1'
    assert result['backups_digest'] == {}
    audit = p.STATE / 'frontend-publications' / plan['operation_id']
    assert not any(path.name.startswith('previous-') for path in audit.iterdir())
    for name in ('.next', 'node_modules'):
        assert (p.PRODUCTION / 'frontend' / name / 'new').read_text() == 'candidate'
        assert not (p.PRODUCTION / 'frontend' / name / 'old').exists()
    assert not p.LEASE.exists()
    assert events.index(('consume',)) < events.index(('/usr/bin/systemctl', 'stop', 'health-frontend'))
    # The same consumer used by bootstrap/release must understand this receipt.
    spec = importlib.util.spec_from_file_location('server_consumer', Path(__file__).with_name('trusted_release_server.py'))
    consumer = importlib.util.module_from_spec(spec); spec.loader.exec_module(consumer)
    monkeypatch.setattr(consumer, 'secure_path', lambda *a, **kw: None)
    monkeypatch.setattr(consumer, '_read_private', lambda path: path.read_bytes())
    monkeypatch.setattr(consumer, 'validate_metadata', lambda *a, **kw: None)
    assert plan['operation_id'] in consumer.assert_frontend_publication_history(p.STATE)


@pytest.mark.parametrize('failure', ['delete', 'rename', 'start', 'readback'])
def test_failure_retains_lease_and_blocks_history(tmp_path, monkeypatch, failure):
    values = setup(tmp_path, monkeypatch)
    m, p, plan, _, _, build, events = values
    def fail(*a, **kw):
        raise OSError('synthetic failure')
    if failure == 'delete': monkeypatch.setattr(m, 'remove_live', fail)
    if failure == 'rename': monkeypatch.setattr(Path, 'rename', fail)
    if failure == 'start':
        original = build.run
        def run(args):
            if 'start' in args: fail()
            return original(args)
        build.run = run
    if failure == 'readback': monkeypatch.setattr(p, 'verify_pages', fail)
    with pytest.raises(m.PublicationError, match='no retry'): execute(values)
    audit = p.STATE / 'frontend-publications' / plan['operation_id']
    assert p.LEASE.exists()
    assert json.loads((audit / 'failed.json').read_text())['state'] == 'FRONTEND_NEEDS_OPERATOR'
    assert not (audit / 'completed.json').exists()
    assert not any(path.name.startswith('previous-') for path in audit.iterdir())
    assert events.count(('/usr/bin/systemctl', 'start', 'health-frontend')) <= 1


@pytest.mark.parametrize('invalid', ['policy', 'unprepared', 'link', 'consumer'])
def test_rejects_before_intent_or_live_changes(tmp_path, monkeypatch, invalid):
    values = setup(tmp_path, monkeypatch)
    m, p, plan, _, _, _, events = values
    if invalid == 'policy': plan['publication_policy'] = 'unknown'
    if invalid == 'unprepared': plan.pop('prepared_artifact')
    if invalid == 'link':
        root = p.PRODUCTION / 'frontend/.next'
        root.rename(root.with_name('untouched'))
        root.symlink_to(root.with_name('untouched'), target_is_directory=True)
    if invalid == 'consumer':
        def reject(*args): raise m.PublicationError('installed consumer differs')
        monkeypatch.setattr(m, 'assert_installed_consumer', reject)
    with pytest.raises(m.PublicationError): execute(values)
    assert not p.LEASE.exists()
    assert not (p.STATE / 'frontend-publications').exists()
    assert not events


@pytest.mark.parametrize('mutation', ['policy', 'phase', 'backup', 'claim', 'ready', 'build-log', 'missing-proof', 'recovery'])
def test_history_rejects_tampered_no_backup_provenance(tmp_path, monkeypatch, mutation):
    values = setup(tmp_path, monkeypatch)
    _, p, plan, _, _, _, _ = values
    execute(values)
    audit = p.STATE / 'frontend-publications' / plan['operation_id']
    artifact = p.STATE / 'frontend-artifacts' / plan['operation_id']
    if mutation == 'policy':
        path = audit / 'intent.json'
        value = json.loads(path.read_text()); value['publication_policy'] = 'unknown'; path.write_text(json.dumps(value))
    elif mutation == 'phase': (audit / 'verified.json').write_text('{}')
    elif mutation == 'backup': (audit / 'previous-next').mkdir()
    elif mutation == 'claim': (artifact / 'claim.json').write_text('{}')
    elif mutation == 'ready': (artifact / 'ready.json').write_text('{}')
    elif mutation == 'build-log': (artifact / 'build.log').write_text('changed')
    elif mutation == 'missing-proof': (artifact / 'intent.json').unlink()
    else: (audit / 'recovery-completed.json').write_text('{}')
    spec = importlib.util.spec_from_file_location('tampered_consumer', Path(__file__).with_name('trusted_release_server.py'))
    consumer = importlib.util.module_from_spec(spec); spec.loader.exec_module(consumer)
    monkeypatch.setattr(consumer, 'secure_path', lambda *a, **kw: None)
    monkeypatch.setattr(consumer, '_read_private', lambda path: path.read_bytes())
    monkeypatch.setattr(consumer, 'validate_metadata', lambda *a, **kw: None)
    with pytest.raises(consumer.LaunchError): consumer.assert_frontend_publication_history(p.STATE)


def test_no_backup_record_cannot_claim_recovery_verification(tmp_path, monkeypatch):
    values = setup(tmp_path, monkeypatch)
    _, p, plan, _, _, _, _ = values
    execute(values)
    spec = importlib.util.spec_from_file_location('recovery_consumer', Path(__file__).with_name('trusted_release_server.py'))
    consumer = importlib.util.module_from_spec(spec); spec.loader.exec_module(consumer)
    monkeypatch.setattr(consumer, 'secure_path', lambda *a, **kw: None)
    monkeypatch.setattr(consumer, '_read_private', lambda path: path.read_bytes())
    monkeypatch.setattr(consumer, 'validate_metadata', lambda *a, **kw: None)
    with pytest.raises(consumer.LaunchError, match='no recovery set'):
        consumer.assert_frontend_publication_history(p.STATE, verify_backups=True, _force_operations=(plan['operation_id'],))


def test_fixed_deletion_never_follows_child_symlinks(tmp_path, monkeypatch):
    m = load(); monkeypatch.setattr(m, 'OWNER', os.getuid())
    frontend = tmp_path / 'frontend'; frontend.mkdir()
    live = frontend / '.next'; live.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir(); (outside / 'keep').write_text('user-data')
    (live / 'escape').symlink_to(outside, target_is_directory=True)
    m.remove_live(frontend, '.next', m.identity(frontend), m.identity(live))
    assert not live.exists() and (outside / 'keep').read_text() == 'user-data'


@pytest.mark.parametrize('change', ['mount', 'device', 'parent', 'root'])
def test_removal_rejects_boundary_drift_without_deleting(tmp_path, monkeypatch, change):
    m = load(); monkeypatch.setattr(m, 'OWNER', os.getuid())
    front = tmp_path / 'front'; front.mkdir(); live = front / '.next'; live.mkdir()
    nested = live / 'nested'; nested.mkdir(); (nested / 'keep').write_text('keep')
    parent, root = m.identity(front), m.identity(live)
    if change == 'mount':
        original = Path.is_mount
        monkeypatch.setattr(Path, 'is_mount', lambda p: p == nested or original(p))
    elif change == 'device':
        original = Path.lstat
        def lstat(p):
            info = original(p)
            return SimpleNamespace(st_mode=info.st_mode, st_dev=info.st_dev + 1) if p == nested else info
        monkeypatch.setattr(Path, 'lstat', lstat)
    elif change == 'parent': parent = (parent[0], parent[1] + 1, *parent[2:])
    else: root = (root[0], root[1] + 1, *root[2:])
    with pytest.raises(m.PublicationError): m.remove_live(front, '.next', parent, root)
    assert (nested / 'keep').read_text() == 'keep'


def test_stopped_requires_contained_service_and_no_descendants(tmp_path, monkeypatch):
    m = load(); p = SimpleNamespace(stopped_runtime=lambda _: None)
    with pytest.raises(m.PublicationError, match='containment'):
        m.assert_stopped(p, SimpleNamespace(run=lambda _: 'process'))


@pytest.mark.parametrize('record', [
    '2 1 0:1 /external {path} rw - ext4 /dev/root rw\n',
    '2 1 0:1 /external {path}/child rw - ext4 /dev/root rw\n',
])
def test_same_device_bind_mount_blocks_without_is_mount_hint(tmp_path, monkeypatch, record):
    m = load(); monkeypatch.setattr(m, 'OWNER', os.getuid())
    front = tmp_path / 'front space'; front.mkdir(); live = front / '.next'; live.mkdir()
    (live / 'child').mkdir(); (live / 'child/keep').write_text('outside')
    # Linux bind mounts can share st_dev and return false from is_mount().
    monkeypatch.setattr(Path, 'is_mount', lambda _: False)
    escaped = str(live).replace(' ', '\\040')
    m.MOUNTINFO.write_text(record.format(path=escaped))
    with pytest.raises(m.PublicationError, match='mount'):
        m.remove_live(front, '.next', m.identity(front), m.identity(live))
    assert (live / 'child/keep').read_text() == 'outside'


@pytest.mark.parametrize('raw', ['', 'broken', '1 0 0:1 / relative rw - ext4 dev rw\n',
                                  '1 0 0:1 / /bad\\999 rw - ext4 dev rw\n'])
def test_unknown_mount_inventory_fails_closed(raw):
    m = load(); m.MOUNTINFO.write_text(raw)
    with pytest.raises(m.PublicationError): m.mount_points()


def test_missing_mount_inventory_fails_closed():
    m = load(); m.MOUNTINFO.unlink()
    with pytest.raises(m.PublicationError): m.mount_points()


def test_mount_inventory_is_rechecked_at_deletion_boundary(tmp_path, monkeypatch):
    m = load(); monkeypatch.setattr(m, 'OWNER', os.getuid())
    front = tmp_path / 'front'; front.mkdir(); live = front / '.next'; live.mkdir()
    (live / 'keep').write_text('untouched')
    scans = iter([[Path('/')], [Path('/'), live]])
    monkeypatch.setattr(m, 'mount_points', lambda: next(scans))
    with pytest.raises(m.PublicationError, match='mount'):
        m.remove_live(front, '.next', m.identity(front), m.identity(live))
    assert (live / 'keep').read_text() == 'untouched'


@pytest.mark.skipif(os.environ.get('REVA_TEST_FRONTEND_MOUNT') != '1', reason='requires disposable Linux root mount namespace')
def test_real_linux_same_device_bind_mount_is_not_deleted(tmp_path):
    assert sys.platform == 'linux' and os.geteuid() == 0
    script = '''
import importlib.util, pathlib, subprocess, sys
entry, root = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
spec = importlib.util.spec_from_file_location('native_no_backup', entry)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
front = root / 'frontend'; front.mkdir()
live = front / '.next'; live.mkdir()
nested = live / 'bind'; nested.mkdir()
outside = root / 'outside'; outside.mkdir(); (outside / 'keep').write_text('untouched')
subprocess.run(['/usr/bin/mount', '--bind', str(outside), str(nested)], check=True)
try:
    assert nested.stat().st_dev == live.stat().st_dev
    try:
        m.remove_live(front, '.next', m.identity(front), m.identity(live))
    except m.PublicationError as exc:
        assert 'mount' in str(exc)
    else:
        raise AssertionError('same-device bind mount was not blocked')
    assert (outside / 'keep').read_text() == 'untouched'
finally:
    subprocess.run(['/usr/bin/umount', str(nested)], check=True)
'''
    subprocess.run(['/usr/bin/unshare', '--mount', '--propagation', 'private', '--fork', sys.executable,
                    '-I', '-B', '-c', script, str(Path(__file__).with_name('trusted_frontend_no_backup.py')), str(tmp_path)],
                   check=True, timeout=30)


def test_legacy_seal_accepts_new_policy_then_binds_it(tmp_path, monkeypatch, evidence):
    # Real seal/canonical catalog implementation, with only host ownership mocked.
    server, state, old, _ = evidence
    server.seal_frontend_publication_history(state, active_operation=old.name, live_digest='e' * 64)
    values = setup(tmp_path, monkeypatch)
    _, p, plan, _, _, _, _ = values
    execute(values)
    import shutil
    shutil.copytree(p.STATE / 'frontend-publications' / plan['operation_id'], state / 'frontend-publications' / plan['operation_id'])
    shutil.copytree(p.STATE / 'frontend-artifacts', state / 'frontend-artifacts')
    catalog = server.assert_frontend_publication_history(state)
    assert set(catalog) == {old.name, plan['operation_id']}
    server.seal_frontend_publication_history(state, active_operation=plan['operation_id'], live_digest='e' * 64)
    assert set(server.assert_frontend_publication_history(state)) == set(catalog)
    (state / 'frontend-artifacts' / plan['operation_id'] / 'claim.json').write_text('{}')
    with pytest.raises(server.LaunchError): server.assert_frontend_publication_history(state)
