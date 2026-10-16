import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('kbase_operator', Path(__file__).with_name('trusted_kbase_login.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_patch_preserves_unrelated_bytes():
    raw = b'# existing\r\nOTHER="a=b # private"\r\nKBASE_SSO_ENABLED=false\r\n'
    result = m.patch_env(raw, {'KBASE_SSO_ENABLED': 'true', 'KBASE_SSO_OWNER_ID': '3'})
    assert result == b'# existing\r\nOTHER="a=b # private"\r\nKBASE_SSO_ENABLED=true\nKBASE_SSO_OWNER_ID=3\n'


@pytest.mark.parametrize('raw', [b'KBASE_SSO_ENABLED=false\nKBASE_SSO_ENABLED=false\n',
    b'export KBASE_SSO_ENABLED=false\n', b' KBASE_SSO_ENABLED = false\n',
    b'KBASE_SSO_ENABLED="false"\n', b'KBASE_SSO_ENABLED=false\\\n', b'kbase_sso_enabled=true\n'])
def test_ambiguous_target_rejected(raw):
    with pytest.raises(m.ActivationError):
        m.patch_env(raw, {'KBASE_SSO_ENABLED': 'true'})


@pytest.mark.parametrize('user', [dict(id=3, is_active=False, is_approved=True),
    dict(id=4, is_active=True, is_approved=True), dict(id=3, is_active=True, is_approved=True, is_managed=True),
    dict(id=True, is_active=True, is_approved=True)])
def test_owner_is_exact_active_unmanaged(user):
    with pytest.raises(m.ActivationError):
        m.check_owner(user, 3)


def test_owner_from_authenticated_identity():
    m.check_owner(dict(id=3, is_active=True, is_approved=True, is_managed=False), 3)


def test_missing_managed_evidence_is_not_accepted():
    with pytest.raises(m.ActivationError):
        m.check_owner(dict(id=3, is_active=True, is_approved=True), 3)


@pytest.mark.parametrize('failure', range(6))
def test_each_interrupted_action_resumes_same_intent(failure):
    journal, performed, secret = {'done': []}, [], 'same-generated-secret'
    def save(value):
        assert value is journal
    def actions(crash):
        result = []
        for index in range(6):
            def action(index=index):
                if index not in performed:
                    performed.append(index)
                if crash and index == failure:
                    raise m.ActivationError('interrupted after effect')
            result.append((str(index), action))
        return result
    with pytest.raises(m.ActivationError):
        m.advance(journal, actions(True), save)
    m.advance(journal, actions(False), save)
    assert performed == list(range(6))
    assert journal['done'] == [str(i) for i in range(6)]
    assert secret == 'same-generated-secret'


def test_unknown_phase_rejected():
    with pytest.raises(m.ActivationError):
        m.advance({'done': ['unexpected']}, [('write', lambda: None)], lambda _: None)


@pytest.mark.parametrize('fault', ['write-kbase', 'restart-kbase', 'verify-kbase', 'write-health', 'restart-health', 'verify-health'])
def test_real_file_transaction_resumes_without_rotating_secret(tmp_path, monkeypatch, fault):
    import json
    from types import SimpleNamespace
    root, state, lease = tmp_path / 'operation', tmp_path / 'release', tmp_path / 'lease'
    state.mkdir()
    (state / 'launcher.lock').write_bytes(b'')
    source = tmp_path / 'source'
    (source / 'scripts').mkdir(parents=True)
    (source / 'scripts/trusted_release_server.py').write_bytes(b'reviewed')
    installed = tmp_path / 'installed'
    installed.write_bytes(b'reviewed')
    files = {'health': tmp_path / 'health.env', 'kbase': tmp_path / 'kbase.env'}
    for path in files.values():
        path.write_bytes(b'OTHER=preserved\r\n')
        path.chmod(0o640)
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'STATE', state)
    monkeypatch.setattr(m, 'LEASE', lease)
    monkeypatch.setattr(m, 'FILES', files)
    monkeypatch.setattr(m, 'secure', lambda path, directory=False: path.lstat())
    args = SimpleNamespace(publisher_sha='a' * 40, production_sha='b' * 40, kbase_sha='c' * 40,
                           owner_id=3, apply=True, resume=False)
    policy = {'sha': args.publisher_sha, 'executor_sha256': m.sha(b'reviewed')}
    bootstrap = SimpleNamespace(CONFIG=tmp_path, INSTALLED=installed,
        _read_json=lambda path: policy if path.name == 'authorized-release.json' else {'sha': args.production_sha, 'state': 'SUCCEEDED'})
    server = SimpleNamespace(validate_policy=lambda value, now: value, assert_frontend_rebuild_history=lambda: None, assert_ota_history=lambda: None)
    helper = SimpleNamespace(_revision_proof=lambda *args: None, _validate_venv=lambda *args: None)
    gate = SimpleNamespace(verify_release=lambda *args: None)
    monkeypatch.setattr(m, 'load', lambda _: (source, helper, bootstrap, server, gate))
    monkeypatch.setattr(m, 'owner_proof', lambda *args: None)
    monkeypatch.setattr(m, 'owner_database', lambda *args: None)
    monkeypatch.setattr(m, 'frontend_proof', lambda: None)
    def revision_proof(_):
        if args.resume and not runtime['kbase']:
            raise m.ActivationError('service is down before continuation')
    monkeypatch.setattr(m, 'runtime_revision', revision_proof)
    monkeypatch.setattr(m, 'wait_ready', lambda _: None)
    runtime = {'health': {}, 'kbase': {}}
    monkeypatch.setattr(m, 'service', lambda which, **kwargs: runtime[which])
    interrupted = False
    def interrupt(name):
        nonlocal interrupted
        if name == fault and not interrupted:
            interrupted = True
            raise m.ActivationError('injected interruption')
    atomic = m.atomic
    def write(path, raw, expected=None):
        atomic(path, raw, expected)
        for which, target_path in files.items():
            if path == target_path:
                interrupt('write-' + which)
    monkeypatch.setattr(m, 'atomic', write)
    def run(*command):
        which = next(key for key, value in m.SERVICES.items() if value == command[-1])
        runtime[which] = {}
        interrupt('restart-' + which)
        runtime[which] = m.selected(files[which].read_bytes())
    monkeypatch.setattr(m, 'run', run)
    def request(url, **kwargs):
        if url.endswith('/browser/health/config'):
            if runtime['kbase']:
                interrupt('verify-kbase')
            return 200, {}, json.dumps({'enabled': bool(runtime['kbase'])}).encode()
        interrupt('verify-health')
        return 401, {}, b''
    monkeypatch.setattr(m, 'request', request)
    with pytest.raises(m.ActivationError):
        m.execute(args, 'token')
    assert lease.is_dir()
    original_secret = (root / 'secret').read_bytes()
    assert json.loads((root / 'journal.json').read_bytes())['state'] == 'NEEDS_OPERATOR'
    args.resume = True
    result = m.execute(args, 'token')
    assert result['state'] == 'CONFIGURATION_SUCCEEDED'
    assert not lease.exists()
    assert (root / 'secret').read_bytes() == original_secret
    for which, path in files.items():
        assert path.read_bytes().startswith(b'OTHER=preserved\r\n')
        assert path.stat().st_mode & 0o777 == 0o640
        assert original_secret.decode() in path.read_text()
    assert original_secret not in (root / 'journal.json').read_bytes()


def test_stat_identity_ignores_access_time_only():
    from types import SimpleNamespace
    fields = dict(st_dev=1, st_ino=2, st_mode=0o100640, st_nlink=1, st_uid=0, st_gid=10,
                  st_size=10, st_mtime_ns=100, st_ctime_ns=100)
    assert m.identity(SimpleNamespace(**fields, st_atime_ns=100)) == m.identity(SimpleNamespace(**fields, st_atime_ns=200))
    assert m.identity(SimpleNamespace(**fields)) != m.identity(SimpleNamespace(**{**fields, 'st_mtime_ns': 101}))


def test_proxy_jwt_never_sent_as_owner_proof(monkeypatch):
    monkeypatch.setattr(m, 'request', lambda *args, **kwargs: pytest.fail('JWT must be rejected before request'))
    with pytest.raises(m.ActivationError):
        m.owner_proof('header.payload.signature', 3)


def test_unknown_pending_phase_rejected():
    with pytest.raises(m.ActivationError):
        m.advance({'done': [], 'pending': 'wrong'}, [('write', lambda: None)], lambda _: None)
