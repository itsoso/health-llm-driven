"""The operator changes one fixed admission policy, never arbitrary configuration."""
import importlib.util
from pathlib import Path

import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load('public_registration_activation')


def old_env():
    return b'# retained\r\nOTHER="private=value"\r\n' + b''.join(f'{k}={v}\n'.encode() for k, v in m.OLD.items())


def test_exact_one_way_transition_preserves_unrelated_bytes():
    raw = old_env()
    changed = m.patch_env(raw)
    assert changed.startswith(b'# retained\r\nOTHER="private=value"\r\n')
    assert m.selected(changed) == m.NEW
    assert m.patch_env(changed) == changed


@pytest.mark.parametrize('raw', [
    b'AUTH_PHONE_SELF_REGISTRATION_ENABLED=true\n',
    old_env() + b'AUTH_PHONE_SELF_REGISTRATION_ENABLED=false\n',
    old_env().replace(b'=false', b'=$(command)'),
    old_env().replace(b'AUTH_PHONE_SELF_REGISTRATION_ENABLED=', b'export AUTH_PHONE_SELF_REGISTRATION_ENABLED='),
    old_env().replace(b'AUTH_PHONE_SELF_REGISTRATION_ENABLED=', b'auth_phone_self_registration_enabled='),
    old_env().replace(b'AUTH_PHONE_SELF_REGISTRATION_ENABLED=false', b'AUTH_PHONE_SELF_REGISTRATION_ENABLED=true'),
])
def test_ambiguous_partial_or_nonliteral_configuration_rejected(raw):
    with pytest.raises(m.ActivationError):
        m.patch_env(raw)


@pytest.mark.parametrize('bad', [dict(m.NEW, HEALTH_EVIDENCE_RUNTIME_ENABLED='true'),
    dict(m.NEW, REGISTRATION_INVITATION_ROLLOUT_ENABLED='true')])
def test_no_arbitrary_target_is_accepted(bad):
    with pytest.raises(m.ActivationError):
        m.validate_policy(bad)


@pytest.mark.parametrize('failure', range(5))
def test_resume_only_repeats_original_pending_idempotent_action(failure):
    journal = {'done': [], 'pending': None}
    calls = []
    def actions(crash):
        def action(index):
            calls.append(index)
            if index == crash:
                raise RuntimeError('interrupted')
        return [(str(i), lambda i=i: action(i)) for i in range(5)]
    with pytest.raises(RuntimeError):
        m.advance(journal, actions(failure), lambda _: None)
    assert journal['done'] == [str(i) for i in range(failure)]
    assert journal['pending'] == str(failure)
    m.advance(journal, actions(None), lambda _: None)
    assert journal['done'] == [str(i) for i in range(5)]
    assert calls == list(range(failure + 1)) + list(range(failure, 5))


@pytest.mark.parametrize('value', [dict(done=['unknown'],pending=None), dict(done=[],pending='wrong')])
def test_unknown_journal_phase_rejected(value):
    with pytest.raises(m.ActivationError):
        m.advance(value, [('write', lambda: None)], lambda _: None)


def test_deployment_validator_accepts_complete_old_and_new_only():
    server = load('trusted_release_server')
    for policy in (m.OLD, m.NEW):
        raw = ''.join(f'{k}={v}\n' for k,v in policy.items()) + 'HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n'
        server.validate_live_deployment_config(raw)
    partial = dict(m.OLD, AUTH_PHONE_SELF_REGISTRATION_ENABLED='true')
    with pytest.raises(server.LaunchError):
        server.validate_live_deployment_config(''.join(f'{k}={v}\n' for k,v in partial.items()) + 'HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n')


def fake_runtime(tmp_path, monkeypatch):
    from types import SimpleNamespace
    state, root, lease = tmp_path/'state', tmp_path/'registration', tmp_path/'lease'
    state.mkdir(); (state/'launcher.lock').touch()
    env = tmp_path/'production.env';env.write_bytes(old_env() + b'HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n')
    source = state/'source';(source/'scripts').mkdir(parents=True)
    (source/'scripts/trusted_release_server.py').write_bytes(b'reviewed')
    installed=tmp_path/'installed';installed.write_bytes(b'reviewed')
    publisher='a'*40
    policy={'sha':publisher,'executor_sha256':m.digest(b'reviewed')}
    calls=[]
    def atomic(path,raw,expected=None):
        if expected is not None:
            assert m.digest(path.read_bytes()) == expected
        path.write_bytes(raw)
    io=SimpleNamespace(secure=lambda *a,**k:None,read=lambda p:p.read_bytes(),sync=lambda p:None,
        atomic=atomic,identity=lambda s:(s.st_dev,s.st_ino),wait_ready=lambda _:calls.append('healthy'))
    helper=SimpleNamespace(_revision_proof=lambda *a:calls.append('revision'),_validate_venv=lambda *a:None)
    bootstrap=SimpleNamespace(CONFIG=tmp_path,INSTALLED=installed,_read_json=lambda p:policy if p.name=='authorized-release.json' else {'sha':publisher,'state':'SUCCEEDED'})
    server=SimpleNamespace(validate_policy=lambda value,**k:value,assert_frontend_rebuild_history=lambda:None,
        assert_ota_history=lambda:None,validate_live_deployment_config=lambda value:None,
        read_production_env=lambda:env.read_bytes().decode(),_json=__import__('json').loads)
    gate=SimpleNamespace(verify_release=lambda *a:calls.append('ci'))
    policies={name:dict(m.OLD) for name in m.SERVICES}
    def run(*args):
        assert args[:2]==('/usr/bin/systemctl','restart')
        policies[args[2]]=dict(m.NEW);calls.append(args[2]);return ''
    io.run=run
    monkeypatch.setattr(m,'STATE',state);monkeypatch.setattr(m,'ROOT',root)
    monkeypatch.setattr(m,'LEASE',lease);monkeypatch.setattr(m,'ENV_FILE',env)
    monkeypatch.setattr(m,'load',lambda _: (source,io,helper,bootstrap,server,gate))
    monkeypatch.setattr(m,'service',lambda io,name,**kwargs:policies[name])
    args=SimpleNamespace(publisher_sha=publisher,apply=False,resume=False)
    return args,env,root,lease,calls,io,helper,bootstrap,policies


def test_preflight_is_read_only(tmp_path,monkeypatch):
    args,env,root,lease,calls,*_=fake_runtime(tmp_path,monkeypatch)
    before=env.read_bytes()
    assert m.execute(args)['state']=='READY'
    assert env.read_bytes()==before and not root.exists() and not lease.exists()
    assert calls.count('ci')==2 and calls.count('revision')==2


def test_apply_and_completed_readback_never_resend_or_restart(tmp_path,monkeypatch):
    args,env,root,lease,calls,*_=fake_runtime(tmp_path,monkeypatch)
    args.apply=True
    result=m.execute(args)
    assert result['state']=='CONFIGURATION_SUCCEEDED' and result['sms_delivery']=='not_attempted'
    assert m.selected(env.read_bytes())==m.NEW and not lease.exists()
    assert [x for x in calls if x in m.SERVICES]==list(m.SERVICES)
    assert m.execute(args)['state']=='CONFIGURATION_SUCCEEDED'
    assert [x for x in calls if x in m.SERVICES]==list(m.SERVICES)


def test_ci_failure_prevents_any_mutation(tmp_path,monkeypatch):
    args,env,root,lease,calls,*_=fake_runtime(tmp_path,monkeypatch)
    original=m.load(args.publisher_sha)
    def fail(*a):raise RuntimeError('ci failed')
    original[-1].verify_release=fail
    args.apply=True;before=env.read_bytes()
    with pytest.raises(RuntimeError):m.execute(args)
    assert env.read_bytes()==before and not root.exists() and not lease.exists()


def test_partial_restart_resumes_same_operation(tmp_path,monkeypatch):
    args,env,root,lease,calls,io,*_=fake_runtime(tmp_path,monkeypatch)
    run=io.run
    def fail(*args):
        if args[-1]=='celery-worker':raise RuntimeError('restart interrupted')
        return run(*args)
    io.run=fail;args.apply=True
    with pytest.raises(RuntimeError):m.execute(args)
    journal=__import__('json').loads((root/'journal.json').read_text())
    assert journal['state']=='NEEDS_OPERATOR' and lease.exists()
    assert journal['done']==['write','health-backend']
    with pytest.raises(m.ActivationError):m.execute(args)
    io.run=run;args.resume=True
    assert m.execute(args)['state']=='CONFIGURATION_SUCCEEDED'
    assert calls.count('health-backend')==1


def test_unrelated_env_drift_after_interruption_blocks_resume(tmp_path,monkeypatch):
    args,env,root,lease,calls,io,*_=fake_runtime(tmp_path,monkeypatch)
    def fail(*args):raise RuntimeError('restart interrupted')
    io.run=fail;args.apply=True
    with pytest.raises(RuntimeError):m.execute(args)
    env.write_bytes(env.read_bytes()+b'OTHER_MUTATION=1\n');args.resume=True
    with pytest.raises(m.ActivationError):m.execute(args)
    assert lease.exists()


@pytest.mark.parametrize('mutation', ['incomplete-success', 'unknown-phase', 'different-binding', 'same-digests'])
def test_corrupt_journal_cannot_claim_completed_or_resume(mutation):
    binding=dict(publisher_sha='a'*40,production_sha='a'*40,policy='public-phone-registration-v1')
    journal=dict(binding,before='b'*64,after='c'*64,done=list(m.PHASES),pending=None,state='CONFIGURATION_SUCCEEDED')
    if mutation=='incomplete-success':journal['done']=[]
    elif mutation=='unknown-phase':journal['pending']='unexpected'
    elif mutation=='different-binding':journal['publisher_sha']='d'*40
    elif mutation=='same-digests':journal['after']=journal['before']
    with pytest.raises(m.ActivationError):m.validate_journal(journal,binding)


@pytest.mark.parametrize('scenario', ['old','new','multi-env-old','multi-env-new','duplicate-property','mixed','override','later-source','pid-change','duplicate'])
def test_service_policy_readback_and_configuration_sources(tmp_path,monkeypatch,scenario):
    from types import SimpleNamespace
    original_path=Path
    def path(value):
        return original_path(tmp_path/str(value).lstrip('/'))
    proc=path('/proc/123/environ');proc.parent.mkdir(parents=True)
    policy=m.NEW if scenario in ('new','multi-env-new') else m.OLD
    if scenario=='mixed':policy=dict(m.OLD,AUTH_PHONE_SELF_REGISTRATION_ENABLED='true')
    raw=b'\0'.join(f'{k}={v}'.encode() for k,v in policy.items())
    if scenario=='duplicate':raw+=b'\0AUTH_PHONE_SELF_REGISTRATION_ENABLED=false'
    proc.write_bytes(raw)
    model=path('/var/lib/reva-vision-model/model.env');model.parent.mkdir(parents=True)
    model.write_bytes(b'AUTH_PHONE_SELF_REGISTRATION_ENABLED=true\n' if scenario=='later-source' else b'LLM_VISION_MODEL=qwen3.8-flash\n')
    props={'User':'health-app','ActiveState':'active','MainPID':'123',
        'EnvironmentFiles':'/opt/health-app/backend/.env (ignore_errors=no) /var/lib/reva-health-evidence-runtime/enabled.env (ignore_errors=yes) /var/lib/reva-vision-model/model.env (ignore_errors=no)',
        'Environment':'AUTH_PHONE_SELF_REGISTRATION_ENABLED=true' if scenario=='override' else '',
        'PassEnvironment':'','UnsetEnvironment':''}
    def run(*args):
        if args[-1]=='--value':return '124' if scenario=='pid-change' else '123'
        lines = [f'{k}={v}' for k,v in props.items()]
        if scenario.startswith('multi-env-'):
            lines = [line for line in lines if not line.startswith('EnvironmentFiles=')]
            lines.extend([
                'EnvironmentFiles=/opt/health-app/backend/.env (ignore_errors=no)',
                'EnvironmentFiles=/var/lib/reva-health-evidence-runtime/enabled.env (ignore_errors=yes)',
                'EnvironmentFiles=/var/lib/reva-vision-model/model.env (ignore_errors=no)',
            ])
        if scenario == 'duplicate-property':
            lines.append('User=health-app')
        return '\n'.join(lines)
    io=SimpleNamespace(run=run,secure=lambda *a,**kw:None,read=lambda p:p.read_bytes())
    monkeypatch.setattr(m,'Path',path)
    if scenario in ('old','new','multi-env-old','multi-env-new'):
        assert m.service(io,'health-backend')==policy
    else:
        with pytest.raises(m.ActivationError):m.service(io,'health-backend')


@pytest.mark.parametrize('scenario', ['old','new','mixed-services','partial'])
def test_public_host_requires_one_complete_policy_across_services(tmp_path,monkeypatch,scenario):
    from types import SimpleNamespace
    host=load('trusted_public_host')
    for pid in range(100,103):
        policy=dict(m.NEW if scenario=='new' or scenario=='mixed-services' and pid==101 else m.OLD)
        if scenario=='partial':policy['AUTH_PHONE_SELF_REGISTRATION_ENABLED']='true'
        path=tmp_path/str(pid)/'environ';path.parent.mkdir()
        path.write_bytes(b'\0'.join(f'{k}={v}'.encode() for k,v in policy.items()))
    original_path=Path
    monkeypatch.setattr(host,'Path',lambda p:original_path(tmp_path/str(p).removeprefix('/proc/')))
    calls=[]
    def run(*args):
        pid=100+list(m.SERVICES).index(args[2])
        return '\n'.join(['User=health-app','ActiveState=active',f'MainPID={pid}',
            'NoNewPrivileges=yes','ProtectSystem=strict','ProtectHome=yes',
            'MemoryMax=1000000','InaccessiblePaths=/mnt'])
    guard=SimpleNamespace(run=run,network_guard=lambda:calls.append('network'))
    if scenario in ('old','new'):
        host.verify_runtime(guard);assert calls==['network']
    else:
        with pytest.raises(RuntimeError):host.verify_runtime(guard)
        assert calls==[]


@pytest.mark.parametrize('mode,accepted', [(0o640, True), (0o600, True), (0o660, False), (0o642, False)])
def test_shared_io_security_allows_group_read_but_never_group_write(mode, accepted):
    import stat
    from types import SimpleNamespace
    io=load('trusted_edu_login')
    class SyntheticPath:
        def __init__(self, mode, parents=()):
            self.mode=mode
            self.parents=parents
        def lstat(self):
            return SimpleNamespace(st_uid=0,st_mode=self.mode,st_nlink=1)
    parent=SyntheticPath(stat.S_IFDIR | 0o755)
    file=SyntheticPath(stat.S_IFREG | mode,(parent,))
    if accepted:
        assert io.secure(file).st_mode == stat.S_IFREG | mode
    else:
        with pytest.raises(io.ActivationError):io.secure(file)


def test_shared_io_reads_actual_0640_file_without_changing_permissions(tmp_path,monkeypatch):
    io=load('trusted_edu_login')
    file=tmp_path/'production.env';file.write_bytes(b'FIXTURE=value\n');file.chmod(0o640)
    # Owner validation is covered above without requiring root on the developer machine.
    monkeypatch.setattr(io,'secure',lambda path:path.stat())
    assert io.read(file)==b'FIXTURE=value\n'
    assert file.stat().st_mode & 0o777==0o640
