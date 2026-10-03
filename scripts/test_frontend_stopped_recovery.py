"""One-operation recovery must preserve failures and refuse unknown outcomes."""
import importlib.util
from pathlib import Path
import pytest


def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('change',[None,{'operation_id':'a'*32},{'publisher_sha':'a'*40},
    {'production_sha':'a'*40},{'frontend_tree':'a'*40},{'state':'FRONTEND_SUCCEEDED'}])
def test_only_original_failed_operation_is_eligible(change):
    m=load('frontend_stopped_recovery')
    intent=m.original_intent();failed={**intent,'state':'FRONTEND_NEEDS_OPERATOR'}
    install={**intent,'state':'FRONTEND_INSTALLING','artifact_digest':m.ARTIFACT}
    if change:failed.update(change)
    if change:
        with pytest.raises(m.RecoveryError):m.validate_original(intent,failed,install)
    else:m.validate_original(intent,failed,install)


@pytest.mark.parametrize('bad',[None,'live','descendant','drift','other-code'])
def test_stopped_proof_rejects_live_processes_and_drift(tmp_path,monkeypatch,bad):
    from types import SimpleNamespace
    m=load('frontend_stopped_recovery');p=load('trusted_frontend_publish')
    group=tmp_path/'group';group.mkdir();monkeypatch.setattr(m,'CGROUP',group)
    value='ActiveState=failed\nSubState=failed\nMainPID=0\nControlPID=0\nResult=exit-code\nExecMainCode=1\nExecMainStatus=143\nControlGroup=\n'
    if bad=='other-code':value=value.replace('Status=143','Status=1')
    if bad in ('live','descendant'):
        path=group if bad=='live' else group/'nested';path.mkdir(exist_ok=True);(path/'cgroup.procs').write_text('123')
    calls=[]
    def run(_):
        calls.append(1)
        return value.replace('MainPID=0','MainPID=123') if bad=='drift' and len(calls)>1 else value
    if bad:
        with pytest.raises(Exception):m.assert_stopped(p,SimpleNamespace(run=run))
    else:m.assert_stopped(p,SimpleNamespace(run=run))


def execution(tmp_path,monkeypatch):
    import json,hashlib
    m=load('frontend_stopped_recovery')
    pub,_,helper,server,build,events=load('test_trusted_frontend_publish').execution_fixture(tmp_path,monkeypatch)
    original_run=build.run
    build.run=lambda argv:original_run(argv)+'ControlGroup=\n' if 'show' in argv else original_run(argv)
    audit=pub.STATE/'frontend-publications'/m.OPERATION;audit.mkdir(parents=True)
    records={'intent.json':m.original_intent(),'failed.json':{**m.original_intent(),'state':'FRONTEND_NEEDS_OPERATOR'},
             'before.json':m.original_intent(),'install-started.json':{**m.original_intent(),'state':'FRONTEND_INSTALLING','artifact_digest':m.ARTIFACT}}
    for n,v in records.items():(audit/n).write_text(json.dumps(v))
    (audit/'build.log').write_text('original build')
    original={p.name:p.read_bytes() for p in audit.iterdir()}
    stage=pub.BUILDS/m.OPERATION/'frontend';stage.mkdir(parents=True)
    for n in ('.next','node_modules'):(stage/n).mkdir();(stage/n/'new').write_text('candidate')
    pub.LEASE.mkdir()
    for n in ('token','label','stage','started_at'):(pub.LEASE/n).write_text(n)
    monkeypatch.setattr(m,'original_evidence',lambda *a:({},'original-proof'))
    monkeypatch.setattr(m,'lease_evidence',lambda *a:'original-lease')
    def candidate(*a):
        if not all((stage/n/'new').exists() for n in ('.next','node_modules')):raise m.RecoveryError('candidate missing')
        return m.ARTIFACT
    monkeypatch.setattr(m,'candidate_digest',candidate)
    monkeypatch.setattr(m,'CGROUP',tmp_path/'absent-cgroup')
    monkeypatch.setattr(pub,'assert_preserved',lambda *a:events.append(('preserved',)))
    monkeypatch.setattr(pub,'bundle_digest',lambda front,b:m.ARTIFACT if (front/'.next/new').exists() else '0'*64)
    server._frontend_publication_file_digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    server.assert_frontend_publication_history=lambda p:events.append(('history',))
    plan=dict(kind='frontend-stopped-recovery',state='PREFLIGHT',operation_id=m.OPERATION,
              recovery_publisher_sha='a'*40,original_proof='original-proof',lease='original-lease',
              old_bundle_digest='0'*64,frontend_process=pub.runtime(build))
    return m,pub,helper,server,build,events,plan,audit,stage,original


def test_resume_switches_original_candidate_and_retains_original_failure(tmp_path,monkeypatch):
    m,p,h,s,b,events,plan,audit,stage,original=execution(tmp_path,monkeypatch)
    complete=m.execute(plan,tmp_path,p,h,None,s,b,lambda:events.append(('locks',)))
    assert complete['state']=='FRONTEND_SUCCEEDED' and not p.LEASE.exists()
    assert original=={n:(audit/n).read_bytes() for n in original}
    assert (p.PRODUCTION/'frontend/.next/new').exists() and (audit/'previous-next/old').exists()
    assert (audit/'recovery-completed.json').exists() and not (audit/'recovery-failed.json').exists()
    assert ('sandbox-build',) not in events


@pytest.mark.parametrize('failure',['lease','evidence','candidate','first-rename','second-rename','pages','completion','lease-release'])
def test_resume_unknown_outcomes_preserve_failure_and_never_retry(tmp_path,monkeypatch,failure):
    m,p,h,s,b,events,plan,audit,stage,original=execution(tmp_path,monkeypatch)
    if failure=='lease':plan['lease']='changed'
    if failure=='evidence':plan['original_proof']='changed'
    if failure=='candidate':(stage/'node_modules/new').unlink()
    if failure in ('first-rename','second-rename'):
        rename=Path.rename;calls=[]
        def move(self,target):
            calls.append(1)
            if len(calls)==(1 if failure=='first-rename' else 2):raise OSError('rename interrupted')
            return rename(self,target)
        monkeypatch.setattr(Path,'rename',move)
    if failure=='pages':monkeypatch.setattr(p,'verify_pages',lambda:(_ for _ in ()).throw(OSError('page failed')))
    if failure=='completion':
        original_write=b.write_json
        def write(server,path,value):
            if path.name=='completed.json':raise OSError('disk failed')
            return original_write(server,path,value)
        b.write_json=write
    if failure=='lease-release':
        unlink=Path.unlink
        def remove(self,*a,**kw):
            if self==p.LEASE/'token':raise OSError('release failed')
            return unlink(self,*a,**kw)
        monkeypatch.setattr(Path,'unlink',remove)
    with pytest.raises(m.RecoveryError):m.execute(plan,tmp_path,p,h,None,s,b,lambda:None)
    assert p.LEASE.exists() and original=={n:(audit/n).read_bytes() for n in original}
    if failure in ('lease','evidence','candidate'):
        assert not (audit/'recovery-intent.json').exists()
        assert ('/usr/bin/systemctl','stop','health-frontend') not in events
    else:
        assert (audit/'recovery-failed.json').exists()
        with pytest.raises(m.RecoveryError):m.execute(plan,tmp_path,p,h,None,s,b,lambda:None)


@pytest.mark.parametrize('mutation',[None,'failed-bytes','original-inode','recovery-intent',
    'recovery-completion','completion-binding','backup','unfinished','other-operation'])
def test_recovered_history_requires_complete_immutable_chain(tmp_path,monkeypatch,mutation):
    import json,hashlib
    m=load('frontend_stopped_recovery')
    fixture=load('test_trusted_frontend_publish_history').evidence.__wrapped__
    server,state,old,complete=fixture(tmp_path,monkeypatch)
    op=old.with_name(m.OPERATION);old.rename(op)
    def write(name,value):(op/name).write_text(json.dumps(value))
    intent=m.original_intent();write('intent.json',intent);write('before.json',intent)
    write('failed.json',{**intent,'state':'FRONTEND_NEEDS_OPERATOR'})
    for n,s in (('install-started.json','FRONTEND_INSTALLING'),('verified.json','FRONTEND_VERIFIED')):
        write(n,{**intent,'state':s,'artifact_digest':m.ARTIFACT})
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    proofs={}
    for n in m.ORIGINAL_FILES:
        info=(op/n).stat();proofs[n]=dict(dev=info.st_dev,ino=info.st_ino,mode=info.st_mode,
                                       uid=info.st_uid,gid=info.st_gid,sha256=digest(op/n))
    recovery=dict(kind='frontend-stopped-recovery',state='RECOVERY_STARTED',operation_id=m.OPERATION,
                  recovery_publisher_sha='a'*40,original_proof=proofs,original_code_sha256=m.ORIGINAL_CODE,
                  candidate_digest=m.ARTIFACT,old_bundle_digest='0'*64,frontend_process={},lease={})
    write('recovery-intent.json',recovery)
    write('recovery-completed.json',{**recovery,'state':'RECOVERY_SUCCEEDED',
           'intent_sha256':digest(op/'recovery-intent.json'),'backups_digest':complete['backups_digest']})
    complete.update(intent,state='FRONTEND_SUCCEEDED',artifact_digest=m.ARTIFACT,
                    recovery_sha256=digest(op/'recovery-completed.json'))
    complete['proof_sha256']={n:digest(op/n) for n in ('before.json','build.log','install-started.json','verified.json')}
    write('completed.json',complete)
    if mutation=='failed-bytes':(op/'failed.json').write_text('{}')
    if mutation=='original-inode':
        raw=(op/'build.log').read_bytes();(op/'build.log').rename(op/'old-log');(op/'build.log').write_bytes(raw);(op/'old-log').unlink()
    if mutation=='recovery-intent':(op/'recovery-intent.json').write_text('{}')
    if mutation=='recovery-completion':(op/'recovery-completed.json').write_text('{}')
    if mutation=='completion-binding':
        complete['recovery_sha256']='0'*64;write('completed.json',complete)
    if mutation=='backup':(op/'previous-next/file').write_text('changed')
    if mutation=='unfinished':(op/'completed.json').unlink()
    if mutation=='other-operation':op.rename(op.with_name('b'*32))
    if mutation:
        with pytest.raises(server.LaunchError):server.assert_frontend_rebuild_history(state)
    else:server.assert_frontend_rebuild_history(state)


@pytest.mark.parametrize('operation',['637078dd8c584686a59000de91d2dad2','a'*32])
def test_pending_recovery_never_exempts_an_unrelated_failed_operation(tmp_path,monkeypatch,operation):
    server,state,op,_=load('test_trusted_frontend_publish_history').evidence.__wrapped__(tmp_path,monkeypatch)
    (op/'failed.json').write_text('{}')
    with pytest.raises(server.LaunchError):server.assert_frontend_rebuild_history(state,pending_stopped_publication=operation)
