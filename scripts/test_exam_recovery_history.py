"""Persistent incident evidence blocks ordinary publishers even after reboot."""
import importlib.util
import json
from pathlib import Path

import pytest


FAILED = 'a8cd1e7635eb697c0f0bc528382c98b3602893c3'
COMPETING = (
    'exam-service-recovery-' + FAILED,
    'exam-attempts-migrations/recovery-' + FAILED,
    'exam-recovery-lease-retirement-' + FAILED,
    'retained-candidate-closures/' + FAILED,
    'retired/' + FAILED,
)


def competing_fixture(monkeypatch, tmp_path):
    from types import SimpleNamespace
    path = Path(__file__).with_name('trusted_release_server.py')
    spec = importlib.util.spec_from_file_location('exam_competing_server', path)
    server = importlib.util.module_from_spec(spec); spec.loader.exec_module(server)
    state = tmp_path / 'state'; state.mkdir()
    refresh = tmp_path / 'provider' / 'refresh'
    credential = tmp_path / 'credential'
    monkeypatch.setattr(server, 'EXAM_PROVIDER_REFRESH_ROOT', refresh, raising=False)
    monkeypatch.setattr(server, 'EXAM_CREDENTIAL_ROOT', credential, raising=False)
    monkeypatch.setattr(server, 'EXAM_RETIRED_INSTALLATIONS', (
        tmp_path/'etc'/('reva-release.retired-'+FAILED),
        tmp_path/'library'/('reva-release.retired-'+FAILED),
    ), raising=False)
    # Keep real type/mode/link checks; only synthetic fixture ownership and its
    # unrelated host ancestors differ from the production root-owned contract.
    def secure(path, *, directory=False, private=False):
        if path != tmp_path and tmp_path not in path.parents:
            return
        info = path.lstat()
        server.validate_metadata(SimpleNamespace(st_uid=0, st_mode=info.st_mode,
            st_nlink=info.st_nlink), directory=directory, private=private)
    monkeypatch.setattr(server, 'secure_path', secure)
    return server, state, refresh, credential


@pytest.mark.parametrize('relative', COMPETING)
@pytest.mark.parametrize('kind', ['directory', 'file', 'broken_link'])
def test_competing_recovery_presence_blocks_all_outcomes(monkeypatch, tmp_path, relative, kind):
    server, state, _, _ = competing_fixture(monkeypatch, tmp_path)
    path = state / relative; path.parent.mkdir(parents=True, exist_ok=True)
    if kind == 'directory':
        path.mkdir(); (path / 'completed.json').write_text('{"state":"SUCCESS"}')
    elif kind == 'file': path.write_text('unknown')
    else: path.symlink_to(tmp_path / 'absent')
    with pytest.raises(server.LaunchError, match='competing exam recovery'):
        server.assert_no_competing_exam_recovery(state)


@pytest.mark.parametrize('provider', ['refresh', 'credential', 'credential_malformed'])
@pytest.mark.parametrize('kind', ['directory', 'file', 'broken_link'])
def test_provider_prefix_inventory_blocks_without_reading_secret(monkeypatch, tmp_path, provider, kind):
    server, state, refresh, credential = competing_fixture(monkeypatch, tmp_path)
    root = refresh if provider == 'refresh' else credential
    root.mkdir(parents=True)
    name = {'refresh':'exam-external', 'credential':'credential.exam-external.tmp',
            'credential_malformed':'credential.exam-external.unknown'}[provider]
    path = root / name
    if kind == 'directory': path.mkdir()
    elif kind == 'file': path.write_text('must not be read')
    else: path.symlink_to(tmp_path / 'absent')
    monkeypatch.setattr(Path, 'read_bytes', lambda _: (_ for _ in ()).throw(AssertionError('secret read')))
    with pytest.raises(server.LaunchError, match='competing exam recovery'):
        server.assert_no_competing_exam_recovery(state)


@pytest.mark.parametrize('root_name', ['migration_parent', 'provider_parent', 'credential_parent'])
@pytest.mark.parametrize('kind', ['file', 'broken_link', 'writable'])
def test_competing_inventory_rejects_unsafe_or_unexpected_parents(monkeypatch, tmp_path, root_name, kind):
    server, state, refresh, credential = competing_fixture(monkeypatch, tmp_path)
    path = {'migration_parent': state/'exam-attempts-migrations',
            'provider_parent': refresh.parent, 'credential_parent': credential}[root_name]
    if kind == 'file': path.write_text('unexpected')
    elif kind == 'broken_link': path.symlink_to(tmp_path/'absent')
    else: path.mkdir(); path.chmod(0o777)
    with pytest.raises(server.LaunchError): server.assert_no_competing_exam_recovery(state)


def test_no_competing_history_allows_unrelated_provider_records_and_never_reads_them(monkeypatch, tmp_path):
    server, state, refresh, credential = competing_fixture(monkeypatch, tmp_path)
    server.assert_no_competing_exam_recovery(state)
    refresh.mkdir(parents=True); credential.mkdir()
    (refresh/'other-release').mkdir()
    (credential/'credential.json').write_text('unread secret')
    (refresh.parent/'provider-refresh.lock').touch()
    monkeypatch.setattr(Path, 'read_bytes', lambda _: (_ for _ in ()).throw(AssertionError('secret read')))
    server.assert_no_competing_exam_recovery(state)


@pytest.mark.parametrize('index', [0, 1])
@pytest.mark.parametrize('kind', ['directory', 'file', 'broken_link'])
def test_competing_legacy_installation_blocks(monkeypatch, tmp_path, index, kind):
    server, state, _, _ = competing_fixture(monkeypatch, tmp_path)
    path = server.EXAM_RETIRED_INSTALLATIONS[index]; path.parent.mkdir()
    if kind == 'directory': path.mkdir()
    elif kind == 'file': path.write_text('old configuration')
    else: path.symlink_to(tmp_path/'absent')
    with pytest.raises(server.LaunchError, match='competing exam recovery'):
        server.assert_no_competing_exam_recovery(state)


def test_competing_provider_added_during_inventory_cannot_escape_scan(monkeypatch, tmp_path):
    server, state, refresh, _ = competing_fixture(monkeypatch, tmp_path)
    refresh.mkdir(parents=True)
    original = server.os.scandir
    class ChangedInventory:
        def __enter__(self): return iter(())
        def __exit__(self, *args): (refresh/'exam-racing').mkdir()
    expected = refresh.stat()
    def scan(fd):
        current = server.os.fstat(fd)
        if (current.st_dev,current.st_ino) == (expected.st_dev,expected.st_ino):
            return ChangedInventory()
        return original(fd)
    monkeypatch.setattr(server.os, 'scandir', scan)
    with pytest.raises(server.LaunchError, match='inventory.*changed'):
        server.assert_no_competing_exam_recovery(state)


@pytest.mark.parametrize('module_name', ['trusted_release_server', 'bootstrap_trusted_release'])
def test_ordinary_history_calls_shared_competing_checker(monkeypatch, tmp_path, module_name):
    from types import SimpleNamespace
    path = Path(__file__).with_name(module_name + '.py')
    spec = importlib.util.spec_from_file_location('exam_shared_' + module_name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    monkeypatch.setattr(m, 'STATE', tmp_path)
    calls = []
    def reject(state):
        calls.append(state)
        raise RuntimeError('competing exam recovery')
    if module_name == 'trusted_release_server':
        monkeypatch.setattr(m, 'assert_no_competing_exam_recovery', reject, raising=False)
    else:
        monkeypatch.setattr(m, '_exam_history_server', lambda: SimpleNamespace(
            assert_no_competing_exam_recovery=reject, LaunchError=RuntimeError), raising=False)
    with pytest.raises((RuntimeError, getattr(m, 'BootstrapError', RuntimeError))):
        m.assert_exam_recovery_history()
    assert calls == [tmp_path]


@pytest.mark.parametrize('cached', [False, True])
def test_shared_history_loader_never_creates_or_accepts_bytecode_cache(monkeypatch, tmp_path, cached):
    path = Path(__file__).with_name('bootstrap_trusted_release.py')
    spec = importlib.util.spec_from_file_location('exam_loader_bootstrap', path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    monkeypatch.setattr(m, '__file__', str(tmp_path/'bootstrap_trusted_release.py'))
    monkeypatch.setattr(m, 'secure', lambda *args, **kwargs: None)
    monkeypatch.setattr(m.sys, 'dont_write_bytecode', False)
    (tmp_path/'trusted_release_server.py').write_text('MARKER = "reviewed"\n')
    cache = tmp_path/'__pycache__'
    if cached:
        cache.symlink_to(tmp_path/'absent')
        with pytest.raises(m.BootstrapError, match='cached exam history'): m._exam_history_server()
    else:
        assert m._exam_history_server().MARKER == 'reviewed'
        assert not cache.exists()


@pytest.mark.parametrize('module_name,entry', [
    ('bootstrap_trusted_release', '_assert_known_activity'),
    ('bootstrap_trusted_release', '_assert_idle'),
    ('bootstrap_trusted_release', 'assert_frontend_rebuild_history'),
    ('bootstrap_trusted_release', 'assert_ota_history'),
    ('trusted_release_server', 'assert_frontend_rebuild_history'),
    ('trusted_release_server', 'assert_ota_history'),
])
@pytest.mark.parametrize('attempt', ['exam-a8-forward-acl-v1', 'exam-a8-read-credential-v1'])
@pytest.mark.parametrize('state', ['intent', 'failure', 'completed', 'file', 'dangling_symlink'])
def test_all_incident_states_block_without_volatile_lease(monkeypatch, tmp_path, module_name, entry, attempt, state):
    path = Path(__file__).with_name(module_name + '.py')
    spec = importlib.util.spec_from_file_location(module_name + '_exam_history', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'STATE', tmp_path)
    if module_name == 'bootstrap_trusted_release':
        monkeypatch.setattr(module, 'BUSINESS_LEASE', tmp_path / 'absent-lease')
    record = tmp_path / attempt
    if state == 'file':
        record.write_text('unknown')
    elif state == 'dangling_symlink':
        record.symlink_to(tmp_path / 'absent-target')
    else:
        record.mkdir()
        (record / (state + '.json')).write_text(json.dumps({'state': 'FORWARD_RECOVERED'}))
    error = module.BootstrapError if module_name == 'bootstrap_trusted_release' else module.LaunchError
    with pytest.raises(error, match='exam recovery requires independent closure'):
        getattr(module, entry)(*([{}] if entry == '_assert_known_activity' else []))
    assert not (tmp_path / 'absent-lease').exists()
