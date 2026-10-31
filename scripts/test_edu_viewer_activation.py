import importlib.util
from pathlib import Path
import pytest
spec = importlib.util.spec_from_file_location('edu_viewer_activation', Path(__file__).with_name('edu_viewer_activation.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.configure(7, 8)

def old_env():
    return b'OTHER=keep\nEDU_SSO_OWNER_ID=7\nEDU_SSO_ENABLED=true\nEDU_SSO_SECRET=synthetic-test-secret-with-more-than-32-bytes\nEDU_SSO_ORIGIN=https://edu.executor.life\nEDU_SSO_ISSUER=https://health.executor.life\n'

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
        atomic=atomic,identity=lambda s:(s.st_dev,s.st_ino),wait_ready=lambda _:calls.append('healthy'),owner_database=lambda _:None)
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
    args=SimpleNamespace(publisher_sha=publisher,owner_id=7,viewer_id=8,apply=False,resume=False)
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
    assert result['state']=='CONFIGURATION_SUCCEEDED' and result['real_login']=='not_verified'
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
    binding=dict(publisher_sha='a'*40,production_sha='a'*40,policy='edu-viewer-v1',owner_id=7,viewer_id=8)
    journal=dict(binding,before='b'*64,after='c'*64,done=list(m.PHASES),pending=None,state='CONFIGURATION_SUCCEEDED')
    if mutation=='incomplete-success':journal['done']=[]
    elif mutation=='unknown-phase':journal['pending']='unexpected'
    elif mutation=='different-binding':journal['publisher_sha']='d'*40
    elif mutation=='same-digests':journal['after']=journal['before']
    with pytest.raises(m.ActivationError):m.validate_journal(journal,binding)


@pytest.mark.parametrize('scenario', ['old','new','multi-env-old','multi-env-new','duplicate-property','mixed','override','later-source','pid-change','duplicate','owner-override','disabled-sso','pending-transition'])
def test_service_policy_readback_and_configuration_sources(tmp_path,monkeypatch,scenario):
    from types import SimpleNamespace
    original_path=Path
    def path(value):
        return original_path(tmp_path/str(value).lstrip('/'))
    proc=path('/proc/123/environ');proc.parent.mkdir(parents=True)
    policy=m.NEW if scenario in ('new','multi-env-new') else m.OLD
    if scenario=='mixed':policy={m.KEY:'9'}
    raw=old_env().replace(b'\n',b'\0')+b'\0'+b'\0'.join(f'{k}={v}'.encode() for k,v in policy.items())
    if scenario=='duplicate':raw=b'EDU_SSO_VIEWER_IDS=8\0EDU_SSO_VIEWER_IDS=8'
    proc.write_bytes(raw)
    env=tmp_path/'base.env';env.write_bytes(old_env()+b''.join(f'{k}={v}\n'.encode() for k,v in policy.items()))
    monkeypatch.setattr(m,'ENV_FILE',env)
    if scenario == 'pending-transition': env.write_bytes(old_env()+b'EDU_SSO_VIEWER_IDS=8\n')
    if scenario == 'owner-override': proc.write_bytes(raw.replace(b'EDU_SSO_OWNER_ID=7',b'EDU_SSO_OWNER_ID=9'))
    if scenario == 'disabled-sso': proc.write_bytes(raw.replace(b'EDU_SSO_ENABLED=true',b'EDU_SSO_ENABLED=false'))
    model=path('/var/lib/reva-vision-model/model.env');model.parent.mkdir(parents=True)
    model.write_bytes(b'EDU_SSO_VIEWER_IDS=8\n' if scenario=='later-source' else b'LLM_VISION_MODEL=qwen3.8-flash\n')
    props={'User':'health-app','ActiveState':'active','MainPID':'123',
        'EnvironmentFiles':'/opt/health-app/backend/.env (ignore_errors=no) /var/lib/reva-health-evidence-runtime/enabled.env (ignore_errors=yes) /var/lib/reva-vision-model/model.env (ignore_errors=no)',
        'Environment':'EDU_SSO_VIEWER_IDS=8' if scenario=='override' else '',
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
    if scenario == 'pending-transition':
        assert m.service(io,'health-backend',allow_stopped=True)==m.OLD
        with pytest.raises(m.ActivationError): m.service(io,'health-backend')
        proc.write_bytes(raw+b'\0EDU_SSO_VIEWER_IDS=8')
        assert m.service(io,'health-backend')==m.NEW
    elif scenario in ('old','new','multi-env-old','multi-env-new'):
        assert m.service(io,'health-backend')==policy
    else:
        with pytest.raises(m.ActivationError):m.service(io,'health-backend')



@pytest.mark.parametrize('raw', [b'EDU_SSO_VIEWER_IDS=9\n', b'EDU_SSO_VIEWER_IDS=8\nEDU_SSO_VIEWER_IDS=8\n', b'export EDU_SSO_VIEWER_IDS=8\n', b'EDU_SSO_VIEWER_IDS=$(bad)\n', b'EDU_SSO_VIEWER_IDS=\n'])
def test_unknown_or_ambiguous_viewer_policy_rejected(raw):
    with pytest.raises(m.ActivationError): m.patch_env(raw)

def test_patch_changes_only_allowlist():
    before=old_env()+b'SECRET="synthetic=value"\n'
    after=m.patch_env(before)
    assert after == before+b'EDU_SSO_VIEWER_IDS=8\n'
    assert m.patch_env(after)==after

@pytest.mark.parametrize('owner,viewer', [(7,7),(0,8),(7,-1),(True,8)])
def test_invalid_identity_rejected(owner,viewer):
    with pytest.raises(m.ActivationError): m.configure(owner,viewer)

def test_owner_mismatch_stops_before_writes(tmp_path, monkeypatch):
    args,env,root,lease,calls,*_=fake_runtime(tmp_path,monkeypatch)
    args.owner_id=9;args.apply=True
    with pytest.raises(m.ActivationError): m.execute(args)
    assert not root.exists() and not lease.exists()

@pytest.mark.parametrize('change', [b'EDU_SSO_ENABLED=false', b'EDU_SSO_OWNER_ID=9', b'EDU_SSO_ORIGIN=https://other.test', b'EDU_SSO_SECRET=short'])
def test_authentication_base_rejects_ambiguous_fields(change):
    with pytest.raises(m.ActivationError): m.authentication_settings(old_env()+change+b'\n')

def test_authentication_requires_enabled_owner_and_exact_origins():
    for old,new in [(b'EDU_SSO_ENABLED=true',b'EDU_SSO_ENABLED=false'),(b'https://edu.executor.life',b'https://evil.test'),(b'EDU_SSO_OWNER_ID=7',b'EDU_SSO_OWNER_ID=0')]:
        with pytest.raises(m.ActivationError): m.authentication_settings(old_env().replace(old,new))
