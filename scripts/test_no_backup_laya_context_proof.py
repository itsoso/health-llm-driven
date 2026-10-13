"""Narrow Laya context failure must not borrow preflight-failure authority."""
import pytest
import no_backup_preflight_proof as proof


def test_new_failure_requires_exact_success_prefix_and_no_mutation():
    raw = (b'RUNTIME_STATE_TRANSACTION_OK command=preflight-code result=current\n'
           + '\x1b[0;32m✓\x1b[0m 现行 env 未改变；仅验证摘要与权限，未生成配置副本\n'.encode()
           + b'LAYA_BLOCKED:FileNotFoundError\n'
           + '\x1b[0;31m✗\x1b[0m Laya preparation failed; backend writers unchanged, release evidence retained\n'.encode())
    proof.validate_laya_failure_log(raw)
    with pytest.raises(proof.ProofError):
        proof.validate_failure_log(raw)
    for bad in (raw.replace(b'result=current', b'result=legacy'),
                raw.replace(b'preflight-code', b'prepare-code'),
                b'phase=deactivation_started\n' + raw,
                b'RUNTIME_STATE_TRANSACTION_OK command=install\n' + raw,
                raw + b'other\n'):
        with pytest.raises(proof.ProofError):
            proof.validate_laya_failure_log(bad)


def test_profile_binding_is_independent_and_complete():
    assert proof.LAYA_FAILED_IMPLEMENTATIONS == {
        'deploy.sh': '7444684608ed028f53845e8cc8d94c1dd7c2abd1a0524bf0776898cc32560f90',
        'scripts/trusted_release_server.py': '4ec7fd78e5477100c6bbd0612046b40fab28cf27eefe87c56d0fcaeab9d0d226',
        'backend/scripts/runtime_state_release_transaction.py': '89306f825b3c89da0fc4c515752cc4b8a4f9e6c27dfb74b527cecffc00ba246a',
        'infra/laya/install.py': '306ccb538f0dea31d249488f2eb7663e2e8ba57d4ef22d296070a870ce0bba42',
    }
    assert proof.LAYA_FAILED_IMPLEMENTATIONS['backend/scripts/runtime_state_release_transaction.py'] != proof.FAILED_IMPLEMENTATIONS['backend/scripts/runtime_state_release_transaction.py']


@pytest.fixture
def live_case(tmp_path, monkeypatch):
    """Real canonical/exported/generation files; root ownership/time normalized only."""
    import hashlib, importlib.util, json, os, stat
    from datetime import UTC, datetime
    from pathlib import Path
    from types import SimpleNamespace
    import test_no_backup_preflight_proof as prior
    helper = proof._laya
    started = '2020-01-01T12:00:00Z\n'
    lease_ns = int(datetime.strptime(started,'%Y-%m-%dT%H:%M:%SZ\n').replace(tzinfo=UTC).timestamp()*1_000_000_000)
    roots = {name: tmp_path/name for name in ('old','failed','reviewed','origin')}
    for root in roots.values():
        (root/'infra/laya').mkdir(parents=True)
        (root/'backend/app').mkdir(parents=True)
        (root/'backend/app/config.py').write_text('DECISION_PROVIDER=laya\n')
    def write(path, raw, mode):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(mode)
    models = {'multilingual/model.bin': b'synthetic model bytes'}
    manifest = {'repository':'convaiinnovations/laya', 'revision':'d'*40, 'files': {
        name:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for name,raw in models.items()}}
    repo = Path(__file__).resolve().parents[1]
    for name in helper.ASSETS:
        raw = (json.dumps(manifest).encode() if name == 'model-manifest.json' else
               (repo/'infra/laya/reva-laya.service.in').read_bytes() if name == 'reva-laya.service.in' else
               name.encode())
        for root in roots.values(): write(root/'infra/laya'/name,raw,0o644)
    spec = importlib.util.spec_from_file_location('synthetic_real_laya_installer',repo/'infra/laya/install.py')
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    installer.BASE = tmp_path/'installed'
    installer.STATE = tmp_path/'laya-state'
    installer.UNIT = tmp_path/'units/reva-laya.service'
    installer.ENV = tmp_path/'laya-config/service.env'
    for key in ('BASE','STATE','UNIT','ENV'): monkeypatch.setattr(helper,key,getattr(installer,key))
    current = tmp_path/'production/backend/.env'
    config_text = ('DECISION_PROVIDER=laya\nDECISION_MODE=on\nDECISION_ADMIN_CONTROL_ENABLED=true\n'
        'DECISION_BASE_URL=http://127.0.0.1:8092/v1\nDECISION_MODEL=multilingual\nDECISION_API_KEY='+'k'*43+'\n')
    write(current,config_text.encode(),0o640)
    config = installer.parse_config(config_text)
    generation, unit, env, expected = installer.expected_install(roots['old']/'infra/laya',config)
    generation.mkdir(parents=True)
    generation.chmod(0o755)
    for name in helper.ASSETS: write(generation/name,(roots['old']/'infra/laya'/name).read_bytes(),0o644)
    for name,raw in models.items(): write(generation/'models'/name,raw,0o644)
    write(installer.UNIT,unit,0o644)
    write(installer.ENV,env,0o640)
    write(installer.STATE/'install.json',json.dumps({**expected,'state':'INSTALLED','candidate_sha':'d'*40,'lease':'e'*64}).encode(),0o600)
    receipts = tmp_path/'receipts'
    write(receipts/('b'*40)/'completed.json',json.dumps({'sha':'b'*40,'state':'SUCCEEDED'}).encode(),0o600)
    exported = installer.STATE/'sources'/('a'*40)
    exported.mkdir(parents=True)
    exported.chmod(0o700)
    assets = {name:hashlib.sha256((roots['old']/'infra/laya'/name).read_bytes()).hexdigest() for name in helper.ASSETS}
    for name in helper.ASSETS: write(exported/name,(roots['old']/'infra/laya'/name).read_bytes(),0o400)
    write(exported/'source.json',json.dumps({'sha':'a'*40,'old_sha':'b'*40,'old_has_decisions':True,'files':assets},sort_keys=True).encode(),0o400)
    proc = tmp_path/'proc'
    write(proc/'stat',b'btime 1000000000\n',0o644)
    write(proc/'sys/kernel/random/boot_id',b'11111111-1111-1111-1111-111111111111\n',0o644)
    write(proc/'12/stat',b'12 (python) '+b' '.join([b'0']*19+[b'100'])+b'\n',0o644)
    write(proc/'12/environ',('LAYA_API_KEY='+'k'*43+'\0').encode(),0o600)
    real_stat = Path.lstat
    initial_times = {}
    def lstat(path):
        info = real_stat(path)
        if not str(path).startswith(str(tmp_path)): return info
        fields = {k:getattr(info,k) for k in dir(info) if k.startswith('st_')}
        age = 100 if path == receipts/('b'*40)/'completed.json' else 200 if path == installer.STATE/'install.json' else 300
        baseline = initial_times.setdefault(str(path),(info.st_ctime_ns,info.st_mtime_ns))
        fields.update(st_uid=0,st_gid=0,st_ctime_ns=lease_ns-age+info.st_ctime_ns-baseline[0],
                      st_mtime_ns=lease_ns-age+info.st_mtime_ns-baseline[1])
        return SimpleNamespace(**fields)
    monkeypatch.setattr(Path,'lstat',lstat)
    def file(path, mode=None):
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or (mode is not None and stat.S_IMODE(info.st_mode)!=mode):
            raise proof.ProofError('fixture rejects unsafe file')
        raw=path.read_bytes()
        return raw,{'dev':info.st_dev,'ino':info.st_ino,'uid':0,'gid':0,'mode':stat.S_IMODE(info.st_mode),'sha256':hashlib.sha256(raw).hexdigest()}
    def directory(path, mode=0o700):
        info=path.lstat()
        assert stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode)==mode
        return {'dev':info.st_dev,'ino':info.st_ino,'uid':0,'gid':0,'mode':mode}
    instance = proof.NoBackupPreflightProof.__new__(proof.NoBackupPreflightProof)
    instance.source=roots['reviewed'];instance.production=tmp_path/'production'
    instance.failed_sha='a'*40;instance.production_sha='b'*40;instance.proc=proc
    instance.bootstrap=SimpleNamespace(STATE=receipts, canonical_source=lambda sha: roots[{'a':'failed','b':'old','d':'origin'}[sha[0]]],secure=lambda path: None)
    instance._file=file;instance._directory=directory;instance._secure_evidence=lambda path: None
    def absent(*paths):
        if any(os.path.lexists(path) for path in paths): raise proof.ProofError('unexpected pending file')
    instance._absent=absent
    instance._module=lambda *args: installer
    instance._pids=lambda unit:['12']
    instance._started_text=started;instance._chronology=prior.complete_snapshot()['no_backup_preflight']['chronology']
    class Transaction:
        @staticmethod
        def _stable_exec_start(_, value): return value
    instance.runtime=SimpleNamespace(ReleaseTransaction=Transaction)
    properties={'NeedDaemonReload':'no','ActiveEnterTimestampMonotonic':'100',
        'ControlGroup':'/system.slice/reva-laya.service','WorkingDirectory':str(generation),
        'EnvironmentFiles':str(installer.ENV)+' (ignore_errors=no)',
        'ExecStart':f'path={generation}/venv/bin/python\nargv[]={generation}/venv/bin/python -I {generation}/serve.py\nignore_errors=no'}
    instance.systemd=SimpleNamespace(show=lambda unit,key:properties[key])
    installer.service_identity=lambda gen:{'ActiveState':'active','SubState':'running','MainPID':'12','NRestarts':'0',
        'FragmentPath':str(installer.UNIT),'DropInPaths':'','User':'reva-laya','Group':'reva-laya','UnitFileState':'enabled'}
    installer.validate_account=lambda:SimpleNamespace(pw_gid=0)
    calls=[]
    installer.command=lambda argv: calls.append(argv) or 'LISTEN 0 128 127.0.0.1:8092 0.0.0.0:* users:(("python",pid=12,fd=4))\n'
    installer.verify_install=lambda *args:pytest.fail('inference forbidden')
    installer.probe=lambda *args:pytest.fail('model POST forbidden')
    monkeypatch.setattr(helper,'health_get',lambda:calls.append('GET /health') or dict(helper.HEALTH))
    identity=file(current,0o640)[1]
    return instance,roots,identity,installer,exported,generation,calls


def test_actual_laya_files_producer_to_consumer(live_case):
    instance, roots, identity, installer, exported, generation, calls = live_case
    value=proof._laya.inspect(instance,roots['failed'],roots['old'],identity)
    assert proof._laya.validate(value,'a'*40,'b'*40,instance._chronology['lease_started_ns'],identity)==value
    proof._laya.validate_history(instance.bootstrap,roots['reviewed'],value)
    assert calls.count('GET /health')==1
    assert all(not isinstance(c,list) or c[0]=='/usr/bin/ss' for c in calls)


@pytest.mark.parametrize('damage', ['export_extra','export_asset','old_decisions','receipt_generation',
    'receipt_origin','unit','service_env','generation_asset','model','pending','process_key','process_new',
    'health','canonical_changed','live_changed_during_get'])
def test_actual_laya_producer_rejects_tampering(live_case,monkeypatch,damage):
    import json
    instance,roots,identity,installer,exported,generation,calls=live_case
    helper=proof._laya
    if damage=='export_extra': (exported/'extra').write_text('unexpected')
    elif damage=='export_asset':
        path=exported/'serve.py';path.chmod(0o600);path.write_text('changed');path.chmod(0o400)
    elif damage=='old_decisions':
        path=exported/'source.json';record=json.loads(path.read_text());record['old_has_decisions']=False;path.chmod(0o600);path.write_text(json.dumps(record,sort_keys=True));path.chmod(0o400)
    elif damage.startswith('receipt_'):
        path=installer.STATE/'install.json';record=json.loads(path.read_text());record['generation' if damage=='receipt_generation' else 'candidate_sha']='f'*64 if damage=='receipt_generation' else instance.failed_sha;path.write_text(json.dumps(record))
    elif damage=='unit': installer.UNIT.write_text('changed')
    elif damage=='service_env': installer.ENV.write_text('LAYA_API_KEY=wrong\n')
    elif damage=='generation_asset': (generation/'serve.py').write_text('changed')
    elif damage=='model': (generation/'models/multilingual/model.bin').write_bytes(b'synthetic wrong bytes')
    elif damage=='pending': (installer.STATE/'install.json.pending').write_text('pending')
    elif damage=='process_key': (instance.proc/'12/environ').write_bytes(b'LAYA_API_KEY=wrong\0')
    elif damage=='process_new': (instance.proc/'12/stat').write_bytes(b'12 (python) '+b' '.join([b'0']*19+[b'99999999999999'])+b'\n')
    elif damage=='canonical_changed': (roots['failed']/'infra/laya/serve.py').write_text('changed')
    elif damage=='health': monkeypatch.setattr(helper,'health_get',lambda:{'status':'wrong'})
    else:
        def health():
            current=instance.production/'backend/.env'
            current.write_text(current.read_text()+'# changed\n')
            return dict(helper.HEALTH)
        monkeypatch.setattr(helper,'health_get',health)
    with pytest.raises((proof.ProofError,helper.LayaContextError)):
        helper.inspect(instance,roots['failed'],roots['old'],identity)


@pytest.mark.parametrize('damage',['extra','owner','mode','digest','source_hash','model_hash','chrono',
    'process','health','mixed_origin','unknown_service','extra_credential','witness'])
def test_saved_laya_consumer_rejects_tampering(live_case,damage):
    import copy
    instance,roots,identity,*_=live_case
    helper=proof._laya
    value=copy.deepcopy(helper.inspect(instance,roots['failed'],roots['old'],identity))
    if damage=='extra': value['backup']='forbidden'
    elif damage=='owner': value['receipt']['uid']=1
    elif damage=='mode': value['source_export']['files']['serve.py']['mode']=0o666
    elif damage=='digest': value['expected']['generation']='invalid'
    elif damage=='source_hash': value['source_export']['files']['source.json']['sha256']='f'*64
    elif damage=='model_hash': value['files']['models']['multilingual/model.bin']['sha256']='f'*64
    elif damage=='chrono': value['chronology']['env'][0]=instance._chronology['lease_started_ns']
    elif damage=='process': value['services']['MainPID']='13'
    elif damage=='health': value['health']['loaded']=['other']
    elif damage=='mixed_origin': value['origin_sha']=instance.failed_sha
    elif damage=='unknown_service': value['services']['unknown']='value'
    elif damage=='extra_credential': value['files']['env']['contents']='secret'
    else: value['old_decision_witness']['mode']=0o666
    with pytest.raises(helper.LayaContextError):
        helper.validate(value,'a'*40,'b'*40,instance._chronology['lease_started_ns'],identity)


def test_new_profile_real_inspect_close_postcondition_and_history(live_case,tmp_path,monkeypatch):
    """Real source/config producer, retirement writes/rename, bound post-close, history."""
    import hashlib,json,os
    from types import SimpleNamespace
    import test_contained_release_retirement as closure_tests
    import test_no_backup_preflight_proof as prior
    instance,roots,identity,installer,exported,generation,calls=live_case
    closure_root=tmp_path/'closure-fixture'
    closure_root.mkdir()
    m,adapter,b,r,audit=closure_tests.proof_fixture(closure_root,monkeypatch,build_lock=False)
    for path in audit.iterdir(): path.unlink()
    audit.rmdir()
    adapter.unchanged=True
    adapter.sha='c'*40
    adapter.record=b.STATE/'unchanged-release-closures'/instance.failed_sha
    lease,stage=adapter.proof.lease,adapter.proof.stage
    for path in stage.iterdir(): path.unlink()
    start=instance._started_text
    (lease/'started_at').write_text(start)
    (lease/'stage').write_text(str(stage)+'\n')
    (lease/'started_at').chmod(0o600)
    lines=[]
    for name,relative in proof.ARTIFACTS.items():
        path=roots['failed']/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(name.encode());path.chmod(0o644)
        target=stage/name;target.write_bytes(path.read_bytes());target.chmod(0o700 if name.endswith(('.sh','.py')) else 0o600)
        lines.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+name+'\n')
    (stage/'staged.sha256').write_text(''.join(lines));(stage/'staged.sha256').chmod(0o400)
    implementations=dict(proof.LAYA_FAILED_IMPLEMENTATIONS)
    for relative in implementations:
        path=roots['failed']/relative
        if not path.exists(): path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(relative.encode())
        implementations[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(proof,'LAYA_FAILED_IMPLEMENTATIONS',implementations)
    monkeypatch.setattr(proof,'STAGE_PATTERN',str(stage))
    current=instance.production/'backend/.env'
    current.write_text(''.join(k+'='+v+'\n' for k,v in proof.AUTHORITY.items())+current.read_text())
    # The actual stage method must observe the current config timestamp again.
    original_lstat=type(current).lstat
    def fixed_lstat(path):
        info=original_lstat(path)
        if path==current:
            info.st_ctime_ns=instance._chronology['env_ctime_ns'];info.st_mtime_ns=instance._chronology['env_mtime_ns']
        if path==b.STATE/instance.failed_sha/'started.json':
            info.st_ctime_ns=instance._chronology['receipt_ctime_ns']
        if path==b.STATE/instance.production_sha/'completed.json':
            info.st_ctime_ns=instance._chronology['lease_started_ns']-100;info.st_mtime_ns=info.st_ctime_ns
        return info
    from pathlib import Path
    monkeypatch.setattr(Path,'lstat',fixed_lstat)
    success=b.STATE/instance.production_sha/'completed.json'
    success.parent.mkdir(parents=True,exist_ok=True)
    success.write_text(json.dumps({'sha':instance.production_sha,'state':'SUCCEEDED'}));success.chmod(0o600)
    instance.bootstrap=b
    b.canonical_source=lambda sha:roots[{'a':'failed','b':'old','c':'reviewed','d':'origin'}[sha[0]]]
    instance.lease=lease;instance.stage=stage;instance.token='synthetic-token';instance._closed=False
    instance._directory=lambda path,mode=0o700: {'dev':path.lstat().st_dev,'ino':path.lstat().st_ino,'uid':0,'gid':0,'mode':mode}
    old_workspace=adapter.proof.snapshot()['workspace']
    instance._workspace=lambda failed:old_workspace
    instance.reset=SimpleNamespace(_revision_proof=lambda *args:None)
    instance.runtime_root=tmp_path/'runtime-state';instance.runtime_root.mkdir()
    terminal=tmp_path/'terminal.json';terminal.write_text(json.dumps({'phase':'COMMITTED','terminal_sha':instance.production_sha}));terminal.chmod(0o600)
    class Transaction:
        def __init__(self,*args): self.layout=SimpleNamespace(transaction_root=tmp_path/'absent-transaction')
        def _assert_release_lock(self,*args): assert lease.exists()
        def _preparing_root(self): return tmp_path/'absent-preparing'
        def _load_terminal_marker(self): return {'phase':'COMMITTED','terminal_sha':instance.production_sha}
        def _validate_retained_knowledge_authority(self): pass
        def _terminal_marker_path(self): return terminal
        @staticmethod
        def _stable_exec_start(_,value): return value
    instance.runtime=SimpleNamespace(ReleaseTransaction=Transaction,production_layout=lambda stage:None)
    instance._units=lambda *args,**kwargs:prior.complete_snapshot()['units']
    business={unit:{'NRestarts':'0','ActiveEnterTimestampMonotonic':'100','processes':{'13':'100'}} for unit in proof.UNITS}
    instance.running_snapshot=lambda:business
    instance.running_services_snapshot=lambda:business
    adapter.proof=instance
    lease_inode=lease.lstat().st_ino
    def archived(evidence):
        assert not lease.exists()
        assert adapter.volatile.lstat().st_ino==lease_inode
        for name in ('token','label','stage','started_at'):
            assert instance._file(adapter.volatile/name)[1]==evidence['snapshot']['stage'][name]
    adapter._verify_original_lease_archive=archived
    r._wait_ready=lambda p:business
    monkeypatch.setattr(proof.grp,'getgrnam',lambda name:SimpleNamespace(gr_gid=0))
    monkeypatch.setattr(proof._retained,'validate_archived_vision',lambda *args:None)
    monkeypatch.setattr(m,'_no_backup_module',lambda:proof)
    before={p.name:p.read_bytes() for p in stage.iterdir()}
    raw=(b'RUNTIME_STATE_TRANSACTION_OK command=preflight-code result=current\n' +
         '\x1b[0;32m✓\x1b[0m 现行 env 未改变；仅验证摘要与权限，未生成配置副本\n'.encode()+proof.LAYA_FAILURE_SUFFIX)
    (b.STATE/instance.failed_sha/'deployment.log').write_bytes(raw)
    failure_before=(b.STATE/instance.failed_sha/'completed.json').read_bytes()
    inspection=m.close_transaction(adapter)
    assert lease.exists() and b.AUTHORIZED.read_bytes()==b'unrelated\ncloud exact\nloopback exact\n'
    result=m.close_transaction(adapter,inspection['evidence_sha256'])
    assert result['state']=='CLOSED_UNCHANGED_RELEASE'
    assert not lease.exists()
    assert b.AUTHORIZED.read_bytes()==b'unrelated\n'
    assert not (b.CONFIG/'loopback.key').exists()
    assert {p.name:p.read_bytes() for p in stage.iterdir()}==before
    assert (b.STATE/instance.failed_sha/'completed.json').read_bytes()==failure_before
    assert set(p.name for p in adapter.record.iterdir())=={'intent.json','completed.json'}
    # After retirement historical consumption must use saved evidence/canonical code only.
    monkeypatch.setattr(b,'_installation_evidence',lambda *args:pytest.fail('retired library body'))
    monkeypatch.setattr(proof._laya,'health_get',lambda:pytest.fail('historical live GET'))
    installer.service_identity=lambda *args:pytest.fail('historical live service')
    history=m.closed_evidence(b,instance.failed_sha,result['receipt'],unchanged=True,historical=True)
    assert history['state']=='CLOSED_UNCHANGED_RELEASE'
    (roots['failed']/'infra/laya/serve.py').write_text('tampered canonical asset')
    with pytest.raises(proof.ProofError):
        m.closed_evidence(b,instance.failed_sha,result['receipt'],unchanged=True,historical=True)


@pytest.mark.parametrize('target',['receipt','unit','env'])
@pytest.mark.parametrize('dangling',[False,True])
def test_health_get_pending_creation_rejected(live_case,monkeypatch,target,dangling):
    instance,roots,identity,installer,*_=live_case
    path={'receipt':installer.STATE/'install.json.pending','unit':installer.UNIT.with_name(installer.UNIT.name+'.pending'),
          'env':installer.ENV.with_name(installer.ENV.name+'.pending')}[target]
    def health():
        if dangling: path.symlink_to(path.parent/'does-not-exist')
        else: path.write_text('new intent')
        return dict(proof._laya.HEALTH)
    monkeypatch.setattr(proof._laya,'health_get',health)
    with pytest.raises(proof.ProofError,match='pending'):
        proof._laya.inspect(instance,roots['failed'],roots['old'],identity)


def test_export_decision_integer_is_not_true(live_case):
    import json
    instance,roots,identity,_,exported,*_=live_case
    path=exported/'source.json'
    manifest=json.loads(path.read_text());manifest['old_has_decisions']=1
    path.chmod(0o600);path.write_text(json.dumps(manifest,sort_keys=True));path.chmod(0o400)
    with pytest.raises(proof._laya.LayaContextError):
        proof._laya.inspect(instance,roots['failed'],roots['old'],identity)


def test_saved_decision_integer_is_not_true(live_case):
    instance,roots,identity,*_=live_case
    value=proof._laya.inspect(instance,roots['failed'],roots['old'],identity)
    value['source_export']['manifest']['old_has_decisions']=1
    with pytest.raises(proof._laya.LayaContextError):
        proof._laya.validate(value,'a'*40,'b'*40,instance._chronology['lease_started_ns'],identity)
