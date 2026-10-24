import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('edu_operator', Path(__file__).with_name('trusted_edu_login.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_patch_preserves_unrelated_bytes():
    raw = b'# existing\r\nOTHER="a=b # private"\r\nEDU_SSO_ENABLED=false\r\n'
    result = m.patch_env(raw, {'EDU_SSO_ENABLED': 'true', 'EDU_SSO_OWNER_ID': '3'})
    assert result == b'# existing\r\nOTHER="a=b # private"\r\nEDU_SSO_ENABLED=true\nEDU_SSO_OWNER_ID=3\n'


@pytest.mark.parametrize('raw', [b'EDU_SSO_ENABLED=false\nEDU_SSO_ENABLED=false\n',
    b'export EDU_SSO_ENABLED=false\n', b' EDU_SSO_ENABLED = false\n',
    b'EDU_SSO_ENABLED="false"\n', b'EDU_SSO_ENABLED=false\\\n', b'edu_sso_enabled=true\n'])
def test_ambiguous_target_rejected(raw):
    with pytest.raises(m.ActivationError):
        m.patch_env(raw, {'EDU_SSO_ENABLED': 'true'})


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


def test_stat_identity_ignores_access_time_only():
    from types import SimpleNamespace
    fields = dict(st_dev=1, st_ino=2, st_mode=0o100640, st_nlink=1, st_uid=0, st_gid=10,
                  st_size=10, st_mtime_ns=100, st_ctime_ns=100)
    assert m.identity(SimpleNamespace(**fields, st_atime_ns=100)) == m.identity(SimpleNamespace(**fields, st_atime_ns=200))
    assert m.identity(SimpleNamespace(**fields)) != m.identity(SimpleNamespace(**{**fields, 'st_mtime_ns': 101}))


def test_proxy_jwt_never_sent_as_owner_proof(monkeypatch):
    monkeypatch.setattr(m, 'request', lambda *args, **kwargs: pytest.fail('unverified JWT must be rejected before request'))
    def reject(*args): raise m.ActivationError('not personal JWT')
    monkeypatch.setattr(m, 'personal_jwt_proof', reject)
    with pytest.raises(m.ActivationError):
        m.owner_proof('header.payload.signature', 3)


def test_unknown_pending_phase_rejected():
    with pytest.raises(m.ActivationError):
        m.advance({'done': [], 'pending': 'wrong'}, [('write', lambda: None)], lambda _: None)


@pytest.mark.parametrize('policies', [
    ["form-action 'self' https://edu.executor.life.evil"],
    ["form-action 'self' https://edu.executor.life *"],
    ["form-action 'self' https://edu.executor.life; form-action *"],
    ["form-action 'self' https://edu.executor.life", "form-action 'self'"], [],
])
def test_csp_rejects_inexact_form_destinations(policies):
    assert not m.exact_form_policy(policies)


def test_csp_accepts_only_fixed_destination():
    assert m.exact_form_policy(["default-src 'self'; form-action 'self' https://edu.executor.life; script-src 'self'"])


@pytest.mark.parametrize('scenario', ['optional-absent', 'optional-clean', 'optional-override', 'mandatory-absent', 'optional-dangling', 'optional-parent-unsafe'])
def test_health_service_environment_sources(tmp_path, monkeypatch, scenario):
    optional = tmp_path / 'enabled.env'
    required = tmp_path / 'model.env'
    required.write_bytes(b'MODEL=unchanged\n')
    if scenario in ('optional-clean', 'mandatory-absent'): optional.write_bytes(b'EVIDENCE_ENABLED=true\n')
    if scenario == 'optional-override': optional.write_bytes(b'EDU_SSO_ENABLED=true\n')
    if scenario == 'mandatory-absent': required.unlink()
    if scenario == 'optional-dangling': optional.symlink_to(tmp_path / 'missing')
    original_path = Path
    mapped = {'/var/lib/reva-health-evidence-runtime/enabled.env': optional,
              '/var/lib/reva-vision-model/model.env': required}
    monkeypatch.setattr(m, 'Path', lambda value: mapped.get(str(value), original_path(value)))
    checked = []
    def secure(path, directory=False):
        checked.append((path, directory))
        if scenario == 'optional-parent-unsafe' and path == tmp_path and directory:
            raise m.ActivationError('unsafe environment parent')
        if path.is_symlink(): raise m.ActivationError('unsafe environment source')
        return path.lstat()
    monkeypatch.setattr(m, 'secure', secure)
    read_bytes = Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda path: b'OTHER=unchanged\0' if str(path) == '/proc/123/environ' else read_bytes(path))
    monkeypatch.setattr(m, 'run', lambda *a, **kw: 'User=health-app\nActiveState=active\nMainPID=123\nEnvironmentFiles=/opt/health-app/backend/.env (ignore_errors=no) /var/lib/reva-health-evidence-runtime/enabled.env (ignore_errors=yes) /var/lib/reva-vision-model/model.env (ignore_errors=no)\nEnvironment=\nPassEnvironment=\nUnsetEnvironment=')
    if scenario in ('optional-override', 'optional-dangling', 'optional-parent-unsafe'):
        with pytest.raises(m.ActivationError): m.service('health')
    elif scenario == 'mandatory-absent':
        with pytest.raises(FileNotFoundError): m.service('health')
    else:
        assert m.service('health') == {}
        if scenario == 'optional-absent': assert (optional.parent, True) in checked


@pytest.mark.parametrize('values', [{'SECRET_KEY': 'other'}, {'EDU_SSO_EVIL': 'value'}, {'EDU_SSO_SECRET': 'unsafe value'}])
def test_only_fixed_edu_keys_can_be_patched(values):
    with pytest.raises(m.ActivationError): m.patch_env(b'OTHER=unchanged\n', values)


def test_secret_input_is_bounded_and_never_in_result():
    import json
    secret='a'*64
    assert m.parse_input(json.dumps({'owner_token':'opaque_owner_token','shared_secret':secret}).encode()) == ('opaque_owner_token',secret)
    assert m.parse_input(json.dumps({'owner_token':'header.payload.signature','shared_secret':secret}).encode()) == ('header.payload.signature',secret)
    for value in [{'owner_token':'jwt..dots','shared_secret':secret},
                  {'owner_token':'token','shared_secret':'short'},
                  {'owner_token':'token','shared_secret':secret,'destination':'https://attacker.test'}]:
        with pytest.raises(m.ActivationError): m.parse_input(json.dumps(value).encode())
    with pytest.raises(m.ActivationError): m.parse_input(b' '*8193)


@pytest.mark.parametrize('fault', ['write-health', 'restart-health', 'verify-health'])
def test_health_transaction_resumes_exact_secret_without_backups(tmp_path, monkeypatch, fault):
    import json
    from types import SimpleNamespace
    root, state, lease = tmp_path / 'operation', tmp_path / 'release', tmp_path / 'lease'
    state.mkdir(); (state / 'launcher.lock').write_bytes(b'')
    source = tmp_path / 'source'
    (source / 'scripts').mkdir(parents=True)
    (source / 'scripts/trusted_release_server.py').write_bytes(b'reviewed')
    installed = tmp_path / 'installed'; installed.write_bytes(b'reviewed')
    config = tmp_path / 'health.env'; config.write_bytes(b'OTHER=preserved\r\n'); config.chmod(0o640)
    for name, value in [('ROOT',root),('STATE',state),('LEASE',lease),('FILES',{'health':config})]: monkeypatch.setattr(m,name,value)
    monkeypatch.setattr(m,'secure',lambda path,directory=False:path.lstat())
    args=SimpleNamespace(publisher_sha='a'*40,production_sha='b'*40,owner_id=3,apply=True,resume=False)
    policy={'sha':args.publisher_sha,'executor_sha256':m.sha(b'reviewed')}
    bootstrap=SimpleNamespace(CONFIG=tmp_path,INSTALLED=installed,_read_json=lambda path:policy if path.name=='authorized-release.json' else {'sha':args.production_sha,'state':'SUCCEEDED'})
    server=SimpleNamespace(validate_policy=lambda value,now:value,assert_frontend_rebuild_history=lambda:None,assert_ota_history=lambda:None)
    helper=SimpleNamespace(_revision_proof=lambda *args:None,_validate_venv=lambda *args:None)
    gate=SimpleNamespace(verify_release=lambda *args:None)
    monkeypatch.setattr(m,'load',lambda _:(source,helper,bootstrap,server,gate))
    for name in ['owner_proof','owner_database','frontend_proof','installed_code','wait_ready']: monkeypatch.setattr(m,name,lambda *args:None)
    runtime={}
    monkeypatch.setattr(m,'service',lambda which,**kwargs:runtime)
    interrupted=False
    def interrupt(name):
        nonlocal interrupted
        if name==fault and not interrupted:
            interrupted=True
            raise m.ActivationError('injected unknown outcome')
    atomic=m.atomic
    def write(path,raw,expected=None):
        atomic(path,raw,expected)
        if path==config: interrupt('write-health')
    monkeypatch.setattr(m,'atomic',write)
    def run(*command):
        nonlocal runtime
        assert command==('/usr/bin/systemctl','restart','health-backend')
        runtime={}
        interrupt('restart-health')
        runtime=m.selected(config.read_bytes())
    monkeypatch.setattr(m,'run',run)
    def endpoints():
        if runtime: interrupt('verify-health')
    monkeypatch.setattr(m,'endpoint_proof',endpoints)
    secret='c'*64
    with pytest.raises(m.ActivationError): m.execute(args,'opaque',secret)
    assert lease.is_dir()
    assert json.loads((root/'journal.json').read_bytes())['state']=='NEEDS_OPERATOR'
    assert secret.encode() not in (root/'journal.json').read_bytes()
    args.resume=True
    with pytest.raises(m.ActivationError): m.execute(args,'opaque','d'*64)
    assert lease.is_dir()
    result=m.execute(args,'opaque',secret)
    assert result['state']=='CONFIGURATION_SUCCEEDED'
    assert result['edu_activation']=='separate'
    assert secret not in json.dumps(result)
    assert not lease.exists()
    assert config.read_bytes().startswith(b'OTHER=preserved\r\n')
    assert config.stat().st_mode & 0o777==0o640
    assert secret in config.read_text()
    assert {p.name for p in root.iterdir()}=={'journal.json'}


@pytest.mark.parametrize('token', ['', 'a.b', 'a..c', 'a.b.c.d', 'a.b.c\n', 'x'*4097, 'a b', 7])
def test_owner_credential_format_rejects_ambiguous_input(token):
    assert not m.credential_format(token)


def test_jwt_proof_passes_secret_only_via_stdin(monkeypatch):
    token='header.payload.signature'
    calls=[]
    monkeypatch.setattr(m.subprocess, 'run', lambda command, **kwargs: calls.append((command,kwargs)))
    m.personal_jwt_proof(token,3)
    command,kwargs=calls[0]
    assert token not in str(command) and token not in str(kwargs['env'])
    assert kwargs['input']==token.encode()
    assert kwargs['stdout']==m.subprocess.DEVNULL and kwargs['stderr']==m.subprocess.DEVNULL


def test_jwt_owner_proof_still_requires_live_account(monkeypatch):
    calls=[]
    monkeypatch.setattr(m,'personal_jwt_proof',lambda token,owner:calls.append(owner))
    monkeypatch.setattr(m,'request',lambda *args,**kwargs:(200,{},b'{"id":3,"is_active":true,"is_approved":true}'))
    m.owner_proof('header.payload.signature',3)
    assert calls==[3]
    monkeypatch.setattr(m,'request',lambda *args,**kwargs:(200,{},b'{"id":4,"is_active":true,"is_approved":true}'))
    with pytest.raises(m.ActivationError): m.owner_proof('header.payload.signature',3)
