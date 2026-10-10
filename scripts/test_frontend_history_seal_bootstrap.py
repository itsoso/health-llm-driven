"""Operator history-seal boundaries, isolated from hosts and business releases."""
import fcntl
import json

import pytest

from test_bootstrap_trusted_release import (
    SHA, NEW_SHA, PUBLIC, HOST, fixture, rotation_fixture, lifecycle_snapshot,
)

LIVE = 'c' * 64
CHECKPOINT = 'd' * 64


def seal_fixture(monkeypatch, tmp_path):
    bootstrap, calls = fixture(monkeypatch, tmp_path)
    bootstrap.install(SHA, 200, PUBLIC)
    monkeypatch.setattr(bootstrap, 'BUSINESS_LEASE', tmp_path / 'business-lease')
    monkeypatch.setattr(bootstrap, '_recovery_process_proof', lambda: None)
    monkeypatch.setattr(bootstrap, 'assert_ota_history', lambda: None)
    source, server = bootstrap.reviewed_source(SHA)
    events = []
    server.validate_policy = lambda *args, **kw: events.append(('policy', kw))
    server.assert_frontend_rebuild_history = lambda *args, **kw: events.append(('history', kw))
    server._frontend_history_seal = lambda *args, **kw: {'payload': {'records': ['old']}}
    server.inspect_frontend_history_seal = lambda *args: {'state': 'INSPECTED'}
    server.seal_frontend_publication_history = lambda *args, **kw: events.append(('seal', kw)) or {'state': 'SEALED'}
    server.finish_frontend_history_seal = lambda *args, **kw: events.append(('finish', kw)) or {'state': 'FINISHED'}
    monkeypatch.setattr(bootstrap, '_frontend_live_seal_binding', lambda *args, **kw: ('live-operation', LIVE))
    calls.clear()
    return bootstrap, source, server, events


def test_inspect_is_read_only_and_never_resolves_or_creates_seal(monkeypatch, tmp_path):
    bootstrap, _, server, events = seal_fixture(monkeypatch, tmp_path)
    before = lifecycle_snapshot(bootstrap)
    monkeypatch.setattr(bootstrap, '_frontend_live_seal_binding', lambda *a, **k: pytest.fail('inspect resolved live binding'))
    assert bootstrap.frontend_history_seal(SHA, inspect=True) == {'state': 'INSPECTED'}
    assert lifecycle_snapshot(bootstrap) == before
    assert [name for name, _ in events] == ['policy']


def test_finish_uses_original_checkpoint_and_recovery_snapshot(monkeypatch, tmp_path):
    bootstrap, _, server, events = seal_fixture(monkeypatch, tmp_path)
    snapshots = []
    def read_snapshot(*args, **kwargs):
        snapshots.append(kwargs)
        return {'checkpoint': CHECKPOINT}
    server._frontend_history_seal = read_snapshot
    assert bootstrap.frontend_history_seal(SHA, checkpoint_sha256=CHECKPOINT) == {'state': 'FINISHED'}
    assert snapshots == [{'recovery': True}]
    assert ('history', {'_seal_snapshot': {'checkpoint': CHECKPOINT}}) in events
    assert events[-1] == ('finish', {'checkpoint_sha256': CHECKPOINT, 'live_digest': LIVE})
    assert not any(name == 'seal' for name, _ in events)


@pytest.mark.parametrize('blocker', ['lease', 'process', 'launcher', 'build'])
def test_operator_refuses_activity_without_mutating_history(monkeypatch, tmp_path, blocker):
    bootstrap, _, _, events = seal_fixture(monkeypatch, tmp_path)
    held = None
    if blocker == 'lease':
        bootstrap.BUSINESS_LEASE.mkdir()
    elif blocker == 'process':
        def reject():
            raise bootstrap.BootstrapError('release process present')
        monkeypatch.setattr(bootstrap, '_recovery_process_proof', reject)
    else:
        path = bootstrap.STATE / 'launcher.lock'
        if blocker == 'build':
            path = bootstrap.STATE / SHA / 'build.lock'
            path.parent.mkdir(mode=0o700)
            path.write_text('')
            path.chmod(0o600)
        held = path.open('r+')
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    before = lifecycle_snapshot(bootstrap)
    try:
        with pytest.raises((bootstrap.BootstrapError, BlockingIOError)):
            bootstrap.frontend_history_seal(SHA)
    finally:
        if held:
            held.close()
    assert lifecycle_snapshot(bootstrap) == before
    assert not any(name in {'seal', 'finish'} for name, _ in events)


@pytest.mark.parametrize('race', ['lease', 'launcher', 'build'])
def test_operator_rechecks_locks_and_lease_after_live_validation(monkeypatch, tmp_path, race):
    bootstrap, _, _, events = seal_fixture(monkeypatch, tmp_path)
    def binding(*args, **kwargs):
        if race == 'lease':
            bootstrap.BUSINESS_LEASE.mkdir()
        else:
            path = bootstrap.STATE / 'launcher.lock' if race == 'launcher' else bootstrap.STATE / SHA / 'build.lock'
            path.parent.mkdir(exist_ok=True)
            if path.exists():
                path.unlink()
            path.write_text('changed')
        return 'live-operation', LIVE
    monkeypatch.setattr(bootstrap, '_frontend_live_seal_binding', binding)
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.frontend_history_seal(SHA)
    assert not any(name in {'seal', 'finish'} for name, _ in events)


@pytest.mark.parametrize('matches,explicit,valid', [
    ([], None, False), (['one'], None, True), (['one', 'two'], None, False),
    (['one', 'two'], 'two', True), (['one'], 'other', False),
])
def test_binding_requires_live_match_or_explicit_disambiguation(monkeypatch, tmp_path, matches, explicit, valid):
    bootstrap, source, server, _ = seal_fixture(monkeypatch, tmp_path)
    # Exercise the real loader and selector with isolated reviewed module code.
    from test_bootstrap_trusted_release import load_bootstrap
    real_bootstrap = load_bootstrap()
    binding = real_bootstrap._frontend_live_seal_binding
    binding.__globals__['STATE'] = bootstrap.STATE
    binding.__globals__['secure'] = lambda *a, **k: None
    (source / 'scripts/trusted_frontend_rebuild.py').write_text('# fixture\n')
    (source / 'scripts/trusted_frontend_publish.py').write_text('def bundle_digest(frontend, rebuild):\n    return "' + LIVE + '"\n')
    publications = bootstrap.STATE / 'frontend-publications'
    publications.mkdir()
    for operation, digest in [(name, LIVE) for name in matches] + [('stale', 'e' * 64)]:
        directory = publications / operation
        directory.mkdir()
        (directory / 'completed.json').write_text(json.dumps({'artifact_digest': digest}))
    server.PRODUCTION = tmp_path / 'production'
    validated = []
    server._frontend_publication_backup_digest = lambda path, **kw: validated.append((path.name, kw))
    server._read_private = lambda path: path.read_bytes()
    server._json = json.loads
    if valid:
        assert binding(source, server, active_operation=explicit) == (explicit or matches[0], LIVE)
    else:
        with pytest.raises(real_bootstrap.BootstrapError, match='live artifact|absent or ambiguous'):
            binding(source, server, active_operation=explicit)
    assert validated == [('.next', {'live': True}), ('node_modules', {'live': True})]


@pytest.mark.parametrize('changed', [False, True])
def test_rotate_refreshes_only_new_validated_records_before_business_retirement(monkeypatch, tmp_path, changed):
    bootstrap, _ = rotation_fixture(monkeypatch, tmp_path)
    source, server = bootstrap.reviewed_source(NEW_SHA)
    (bootstrap.STATE / 'frontend-history-seal').mkdir()
    events = []
    server._frontend_history_seal = lambda *a: {'payload': {'records': ['old']}}
    server.assert_frontend_publication_history = lambda *a, **k: ['old', 'new'] if changed else ['old']
    server.seal_frontend_publication_history = lambda *a, **k: events.append(('refresh', k))
    monkeypatch.setattr(bootstrap, '_recovery_process_proof', lambda: events.append(('process', {})))
    monkeypatch.setattr(bootstrap, '_frontend_live_seal_binding', lambda *a: ('new', LIVE))
    idle_calls = []
    def stop_before_business(**kwargs):
        idle_calls.append(kwargs)
        # A new publication first requires the full idle gate; stop only at
        # the next pre-intent gate so no business retirement can begin.
        if changed and len(idle_calls) == 1:
            return
        raise bootstrap.BootstrapError('stop-before-business')
    monkeypatch.setattr(bootstrap, '_assert_idle', stop_before_business)
    before = lifecycle_snapshot(bootstrap)
    with pytest.raises(bootstrap.BootstrapError, match='stop-before-business'):
        bootstrap.rotate(SHA, NEW_SHA, 200, HOST)
    assert lifecycle_snapshot(bootstrap) == before
    assert len(idle_calls) == (2 if changed else 1)
    assert all('backup_memo' in call for call in idle_calls)
    assert [name for name, _ in events] == (['process', 'process', 'refresh'] if changed else [])
    if changed:
        assert events[-1][1]['sealed_by_sha'] == NEW_SHA
        assert events[-1][1]['active_operation'] == 'new'


def test_rotate_refuses_lease_appearing_during_refresh_validation(monkeypatch, tmp_path):
    bootstrap, _ = rotation_fixture(monkeypatch, tmp_path)
    _, server = bootstrap.reviewed_source(NEW_SHA)
    (bootstrap.STATE / 'frontend-history-seal').mkdir()
    server._frontend_history_seal = lambda *a: {'payload': {'records': ['old']}}
    server.assert_frontend_publication_history = lambda *a, **k: ['old', 'new']
    monkeypatch.setattr(bootstrap, '_recovery_process_proof', lambda: None)
    def binding(*args):
        bootstrap.BUSINESS_LEASE.mkdir()
        return 'new', LIVE
    monkeypatch.setattr(bootstrap, '_frontend_live_seal_binding', binding)
    writes = []
    server.seal_frontend_publication_history = lambda *a, **k: writes.append(k)
    # The full pre-refresh gate already has separate coverage. Permit it here
    # so this case reaches the late lease introduced by live validation.
    monkeypatch.setattr(bootstrap, '_assert_idle', lambda **kw: None)
    with pytest.raises(bootstrap.BootstrapError, match='business release appeared during history refresh'):
        bootstrap.rotate(SHA, NEW_SHA, 200, HOST)
    assert bootstrap.BUSINESS_LEASE.exists()
    assert writes == [], 'refresh must recheck the lease after live validation'


@pytest.mark.parametrize('proof', ['process', 'ota'])
def test_operator_rechecks_process_and_ota_after_live_validation(monkeypatch, tmp_path, proof):
    bootstrap, _, _, events = seal_fixture(monkeypatch, tmp_path)
    calls = []
    def check():
        calls.append(proof)
        if len(calls) == 2:
            raise bootstrap.BootstrapError('late-' + proof)
    monkeypatch.setattr(bootstrap, '_recovery_process_proof' if proof == 'process' else 'assert_ota_history', check)
    with pytest.raises(bootstrap.BootstrapError, match='late-' + proof):
        bootstrap.frontend_history_seal(SHA)
    assert not any(name in {'seal', 'finish'} for name, _ in events)


@pytest.mark.parametrize('proof', ['process', 'ota'])
def test_rotate_rechecks_process_and_ota_before_refresh_write(monkeypatch, tmp_path, proof):
    bootstrap, _ = rotation_fixture(monkeypatch, tmp_path)
    # Isolate the late proof from the separately tested full idle gate.
    monkeypatch.setattr(bootstrap, '_assert_idle', lambda **kw: None)
    _, server = bootstrap.reviewed_source(NEW_SHA)
    (bootstrap.STATE / 'frontend-history-seal').mkdir()
    server._frontend_history_seal = lambda *a: {'payload': {'records': ['old']}}
    server.assert_frontend_publication_history = lambda *a, **k: ['old', 'new']
    monkeypatch.setattr(bootstrap, '_frontend_live_seal_binding', lambda *a: ('new', LIVE))
    writes = []
    server.seal_frontend_publication_history = lambda *a, **k: writes.append(k)
    monkeypatch.setattr(bootstrap, '_recovery_process_proof', lambda: None)
    calls = []
    def reject():
        calls.append(proof)
        if proof == 'ota' or len(calls) == 2:
            raise bootstrap.BootstrapError('late-' + proof)
    monkeypatch.setattr(bootstrap, '_recovery_process_proof' if proof == 'process' else 'assert_ota_history', reject)
    before = lifecycle_snapshot(bootstrap)
    with pytest.raises(bootstrap.BootstrapError, match='late-' + proof):
        bootstrap.rotate(SHA, NEW_SHA, 200, HOST)
    assert writes == []
    assert calls == ([proof, proof] if proof == 'process' else [proof])
    assert lifecycle_snapshot(bootstrap) == before


def test_rotate_validates_new_admission_before_refreshing_seal(monkeypatch, tmp_path):
    bootstrap, _ = rotation_fixture(monkeypatch, tmp_path)
    _, server = bootstrap.reviewed_source(NEW_SHA)
    (bootstrap.STATE / 'frontend-history-seal').mkdir()
    server._frontend_history_seal = lambda *a: pytest.fail('seal read before admission')
    def reject(*args):
        raise bootstrap.BootstrapError('admission rejected')
    monkeypatch.setattr(bootstrap, '_installation_inputs', reject)
    before = lifecycle_snapshot(bootstrap)
    with pytest.raises(bootstrap.BootstrapError, match='admission rejected'):
        bootstrap.rotate(SHA, NEW_SHA, 200, HOST)
    assert lifecycle_snapshot(bootstrap) == before


def test_finish_failure_keeps_original_checkpoint_and_business_evidence(monkeypatch, tmp_path):
    bootstrap, _, server, _ = seal_fixture(monkeypatch, tmp_path)
    seal = bootstrap.STATE / 'frontend-history-seal'
    seal.mkdir()
    (seal / 'checkpoint.json').write_text(json.dumps({'sha256': CHECKPOINT}))
    def reject(*args, **kwargs):
        assert kwargs['checkpoint_sha256'] == CHECKPOINT
        raise bootstrap.BootstrapError('checkpoint binding rejected')
    server.finish_frontend_history_seal = reject
    before = lifecycle_snapshot(bootstrap)
    with pytest.raises(bootstrap.BootstrapError, match='checkpoint binding rejected'):
        bootstrap.frontend_history_seal(SHA, checkpoint_sha256=CHECKPOINT)
    assert lifecycle_snapshot(bootstrap) == before


def test_rotate_checks_full_idle_gate_before_new_record_seal_write(monkeypatch, tmp_path):
    bootstrap, _ = rotation_fixture(monkeypatch, tmp_path)
    _, server = bootstrap.reviewed_source(NEW_SHA)
    (bootstrap.STATE / 'frontend-history-seal').mkdir()
    server._frontend_history_seal = lambda *a: {'payload': {'records': ['old']}}
    server.assert_frontend_publication_history = lambda *a, **k: ['old', 'new']
    monkeypatch.setattr(bootstrap, '_recovery_process_proof', lambda: None)
    monkeypatch.setattr(bootstrap, '_frontend_live_seal_binding', lambda *a: ('new', LIVE))
    writes = []
    server.seal_frontend_publication_history = lambda *a, **k: writes.append(k)
    # An otherwise valid new publication cannot authorize rewriting a seal
    # while any unrelated history/activity is still rejected by the full gate.
    def reject_full_idle(**kwargs):
        assert 'backup_memo' in kwargs
        raise bootstrap.BootstrapError('unrelated history blocks full idle')
    monkeypatch.setattr(bootstrap, '_assert_idle', reject_full_idle)
    before = lifecycle_snapshot(bootstrap)
    with pytest.raises(bootstrap.BootstrapError, match='unrelated history blocks full idle'):
        bootstrap.rotate(SHA, NEW_SHA, 200, HOST)
    assert writes == [], 'full idle validation must precede every new-record seal write'
    assert lifecycle_snapshot(bootstrap) == before
