"""No-lease vision-history closure cannot authorize deployment or retry."""
import importlib.util
from pathlib import Path
import pytest


def load():
    path=Path(__file__).with_name('prelease_vision_history_proof.py')
    spec=importlib.util.spec_from_file_location('prelease_vision_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_exact_prelease_transcript_and_no_followup():
    m=load()
    m.validate_log(m.LOG)
    for bad in [m.LOG+b'after\n',m.LOG.replace(b'BLOCKED',b'CLEAR'),m.LOG*2,
                b'REVA_RELEASE_TIMING phase=backend_started\n'+m.LOG]:
        with pytest.raises(m.PreleaseError):m.validate_log(bad)


def test_profile_code_binding_is_not_sha_only():
    m=load()
    m.validate_binding(m.FAILED,m.IMPLEMENTATIONS)
    for key in m.IMPLEMENTATIONS:
        bad=dict(m.IMPLEMENTATIONS);bad[key]='a'*64
        with pytest.raises(m.PreleaseError):m.validate_binding(m.FAILED,bad)
    with pytest.raises(m.PreleaseError):m.validate_binding('a'*40,m.IMPLEMENTATIONS)


@pytest.fixture
def workspace_case(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import json,hashlib
    m=load();source=tmp_path/'canonical';source.mkdir()
    root=tmp_path/'state';workspace=root/m.FAILED;workspace.mkdir(parents=True,mode=0o700)
    binding={}
    for name in m.IMPLEMENTATIONS:
        raw=name.encode();binding[name]=hashlib.sha256(raw).hexdigest()
        for base in (source,workspace/'source'):
            path=base/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    monkeypatch.setattr(m,'IMPLEMENTATIONS',binding)
    for name,state in [('started.json','STARTED'),('completed.json','NEEDS_OPERATOR'),
                       ('preparation-started.json','PREPARING'),('prepared.json','PREPARED'),
                       ('deployment-started.json','DEPLOYING')]:
        value={'sha':m.FAILED,'state':state}
        if state=='PREPARING':value['executor_sha256']=binding['scripts/trusted_release_server.py']
        (workspace/name).write_text(json.dumps(value))
    (workspace/'deployment.log').write_bytes(m.LOG)
    (workspace/'preparation.log').write_text('prepared')
    for name in ('home','bin','source'):
        (workspace/name).mkdir(exist_ok=True);(workspace/name).chmod(0o700)
    for command in ('ssh','scp','python3'):
        target='/usr/bin/python3.12' if command=='python3' else '/usr/bin/'+command
        args='' if command=='python3' else ' -F /etc/reva-release/loopback.conf'
        path=workspace/'bin'/command;path.write_bytes(f'#!/bin/sh\nexec {target}{args} "$@"\n'.encode());path.chmod(0o700)
    b=SimpleNamespace(STATE=root,secure=lambda *a,**kw:None,_read_json=lambda p:json.loads(p.read_text()),
                      _preparation_manifest=lambda p:{'retained':True})
    return m,b,source,workspace


def test_exact_workspace_is_independent_profile(workspace_case):
    m,b,source,w=workspace_case
    assert m.inspect(b,m.FAILED,source)['profile']==m.PROFILE


@pytest.mark.parametrize('damage',['env','build_lock','success','code','tool','followup','home','mode'])
def test_workspace_rejects_mutation_or_drift(workspace_case,damage):
    m,b,source,w=workspace_case
    if damage=='env':(w/'deployment.env').write_text('forbidden')
    elif damage=='build_lock':(w/'build.lock').write_text('')
    elif damage=='success':(w/'completed.json').write_text('{}')
    elif damage=='code':(w/'source/deploy.sh').write_text('changed')
    elif damage=='tool':(w/'bin/ssh').write_text('changed')
    elif damage=='followup':(w/'deployment.log').write_bytes(m.LOG+b'continued\n')
    elif damage=='home':(w/'home/new').write_text('changed')
    else:(w/'source').chmod(0o755)
    with pytest.raises(m.PreleaseError):m.inspect(b,m.FAILED,source)


def test_new_profile_routes_to_prestop_proof_without_loosening_old(monkeypatch):
    from test_bootstrap_trusted_release import load_bootstrap
    b=load_bootstrap();calls=[]
    monkeypatch.setattr(b,'_predeploy_production_proof',lambda *a,**kw:calls.append(kw))
    b._predeploy_workspace_production({'profile':'prelease-vision-history-failure'},'a','b','c')
    b._predeploy_workspace_production({'profile':'predeploy-attestation-failure'},'a','b','c')
    assert calls==[{'prelease_vision':True},{}]
    assert not b._is_predeploy_workspace({'profile':'unknown'})


def test_configuration_no_candidate_env_and_exact_chronology(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import hashlib
    m=load();live='DECISION_MODE=on\n';env=tmp_path/'env';env.write_text(live)
    state=tmp_path/'state';workspace=state/m.FAILED;workspace.mkdir(parents=True)
    (workspace/'started.json').write_text('{}')
    realpath=Path
    monkeypatch.setattr(m,'Path',lambda p:env if p=='/opt/health-app/backend/.env' else realpath(p))
    def reject_private_identity(path):
        pytest.fail('production 0640 env must not use the private 0600 identity helper')
    b=SimpleNamespace(STATE=state,BUSINESS_LEASE=tmp_path/'lease',secure=lambda *a,**k:None,
        _recovery_file_identity=reject_private_identity)
    monkeypatch.setattr(m, '_production_env_identity', lambda b,p: ({'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}, p.stat()))
    result=m.configuration(b,m.FAILED,m.PRODUCTION,live)
    assert result['candidate_environment_absent'] is True
    assert result['historical_env_digest_available'] is False
    (workspace/'deployment.env').write_text('forbidden')
    with pytest.raises(m.PreleaseError):m.configuration(b,m.FAILED,m.PRODUCTION,live)
    (workspace/'deployment.env').unlink()
    b.BUSINESS_LEASE.mkdir()
    with pytest.raises(m.PreleaseError):m.configuration(b,m.FAILED,m.PRODUCTION,live)
    b.BUSINESS_LEASE.rmdir()
    env.write_text('changed')
    with pytest.raises(m.PreleaseError):m.configuration(b,m.FAILED,m.PRODUCTION,live)


def test_new_branch_reuses_live_terminal_service_gates_without_candidate_env(monkeypatch,tmp_path):
    from types import SimpleNamespace
    from test_predeploy_attestation_proof import production_fixture, SHA, PRODUCTION
    b,w,root,marker,server,proof,values,calls=production_fixture(monkeypatch,tmp_path)
    import sys
    monkeypatch.setitem(sys.modules,b.__name__,b)
    (w/'deployment.env').unlink()
    checks=[]
    def config(*args):checks.append(True);return {'unchanged':True}
    monkeypatch.setattr(b,'_prelease_vision_module',lambda:SimpleNamespace(configuration=config))
    result=b._predeploy_production_proof(SHA,PRODUCTION,tmp_path,prelease_vision=True)
    assert result['candidate_environment_sha256'] is None
    assert result['prelease_configuration']=={'unchanged':True}
    assert checks==[True,True]
    values['service']['NRestarts']='1'
    with pytest.raises(b.BootstrapError,match='restarted'):
        b._predeploy_production_proof(SHA,PRODUCTION,tmp_path,prelease_vision=True)


def test_new_branch_rejects_configuration_drift_between_reads(monkeypatch,tmp_path):
    from types import SimpleNamespace
    import sys
    from test_predeploy_attestation_proof import production_fixture, SHA, PRODUCTION
    b,w,root,marker,server,proof,values,calls=production_fixture(monkeypatch,tmp_path)
    monkeypatch.setitem(sys.modules,b.__name__,b)
    (w/'deployment.env').unlink()
    values=iter([{'identity':'before'},{'identity':'changed'}])
    monkeypatch.setattr(b,'_prelease_vision_module',lambda:SimpleNamespace(configuration=lambda *a:next(values)))
    with pytest.raises(b.BootstrapError,match='configuration changed'):
        b._predeploy_production_proof(SHA,PRODUCTION,tmp_path,prelease_vision=True)


@pytest.mark.parametrize('damage', [None, 'owner', 'group', 'write', 'public', 'private', 'symlink', 'hardlink', 'changed', 'oversize'])
def test_production_environment_identity_retains_canonical_0640_contract(tmp_path, monkeypatch, damage):
    from types import SimpleNamespace
    from test_trusted_release_server import load_server
    import os, stat, hashlib
    m = load(); server = load_server()
    env = tmp_path / 'env'; env.write_bytes(b'SYNTHETIC=only\n'); env.chmod(0o640)
    # Local fixtures retain real modes, file types, links, inode and timestamps;
    # only root ownership/group are synthesized on developer machines.
    original_lstat = Path.lstat; original_fstat = os.fstat
    def metadata(info):
        fields = ('st_mode', 'st_nlink', 'st_ino', 'st_dev', 'st_size', 'st_ctime_ns', 'st_mtime_ns')
        result = {key: getattr(info, key) for key in fields}
        result.update(st_uid=1 if damage == 'owner' else 0, st_gid=997 if damage == 'group' else 996)
        return SimpleNamespace(**result)
    monkeypatch.setattr(Path, 'lstat', lambda p: metadata(original_lstat(p)) if p == env else original_lstat(p))
    monkeypatch.setattr(m.os, 'fstat', lambda fd: metadata(original_fstat(fd)))
    monkeypatch.setattr(server, 'secure_path', lambda p: server.validate_metadata(p.lstat()))
    monkeypatch.setattr(server.grp, 'getgrnam', lambda name: SimpleNamespace(gr_gid=996))
    b = SimpleNamespace(_predeploy_module=lambda source, name: server)
    if damage == 'write': env.chmod(0o660)
    if damage == 'public': env.chmod(0o644)
    if damage == 'private': env.chmod(0o600)
    if damage == 'hardlink': os.link(env, tmp_path / 'second')
    if damage == 'symlink':
        env.rename(tmp_path / 'target'); env.symlink_to(tmp_path / 'target')
    if damage == 'oversize': env.write_bytes(b'x' * 1_000_001)
    if damage == 'changed':
        calls = []
        def drifting(fd):
            info = metadata(original_fstat(fd)); calls.append(True)
            if len(calls) > 1: info.st_ino += 1
            return info
        monkeypatch.setattr(m.os, 'fstat', drifting)
    if damage:
        with pytest.raises((m.PreleaseError, server.LaunchError, OSError)):
            m._production_env_identity(b, env)
    else:
        identity, before = m._production_env_identity(b, env)
        assert identity['mode'] == 0o640
        assert identity['uid'] == 0 and identity['gid'] == 996
        assert identity['sha256'] == hashlib.sha256(b'SYNTHETIC=only\n').hexdigest()
        assert before.st_nlink == 1
