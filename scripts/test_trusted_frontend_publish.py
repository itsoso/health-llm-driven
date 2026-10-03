"""New-tree frontend publication boundary tests; no production operations."""
import importlib.util
from pathlib import Path
import pytest


def load():
    spec = importlib.util.spec_from_file_location('publisher_test', Path(__file__).with_name('trusted_frontend_publish.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_binding_allows_new_frontend_tree_but_never_backend_drift():
    m = load()
    m.validate_binding('a'*40, 'b'*40, 'c'*40, 'c'*40, 'b'*40, {'sha':'b'*40,'state':'SUCCEEDED'})
    for tree, live, proof in [('d'*40,'b'*40,{'sha':'b'*40,'state':'SUCCEEDED'}), ('c'*40,'d'*40,{'sha':'b'*40,'state':'SUCCEEDED'}), ('c'*40,'b'*40,{'sha':'b'*40,'state':'STARTED'})]:
        with pytest.raises(m.PublishError):
            m.validate_binding('a'*40,'b'*40,'c'*40,tree,live,proof)


def test_runtime_requires_direct_node_hardened_identity():
    m = load()
    good = dict(m.RUNTIME)
    m.validate_runtime(good)
    for key, value in [('User','root'),('ExecStart','/usr/bin/npm start'),('DropInPaths','/tmp/override'),('ProtectSystem','false')]:
        with pytest.raises(m.PublishError):
            m.validate_runtime({**good,key:value})


def test_entry_precedes_env_and_does_not_change_legacy():
    text = (Path(__file__).parents[1]/'deploy.sh').read_text()
    assert text.index('--publish-frontend') < text.index('ENV_FILE=')
    assert '--rebuild-deployed-frontend' in text


def test_receipt_is_not_backend_success():
    m=load()
    r=m.receipt('a'*40,'b'*40,'c'*32,'d'*40,'FRONTEND_SUCCEEDED','e'*64)
    assert r['kind']=='frontend-publication' and 'sha' not in r


def test_publication_cache_digest_binds_immutable_output_and_owner(tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace
    m=load()
    spec=importlib.util.spec_from_file_location('build_test',Path(__file__).with_name('trusted_frontend_rebuild.py'))
    b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
    monkeypatch.setattr(m.pwd,'getpwnam',lambda _:SimpleNamespace(pw_uid=os.getuid(),pw_gid=os.getgid()))
    root=tmp_path/'next'; root.mkdir(); (root/'cache').mkdir(); (root/'BUILD_ID').write_text('one')
    first=m.publication_artifact_digest(root,b)
    (root/'cache/item').write_text('mutable')
    assert m.publication_artifact_digest(root,b)==first
    (root/'BUILD_ID').write_text('two')
    assert m.publication_artifact_digest(root,b)!=first
    (root/'cache/escape').symlink_to('/etc/passwd')
    with pytest.raises(m.PublishError): m.publication_artifact_digest(root,b)


def execution_fixture(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import json
    import os
    m=load()
    for name in ('STATE','PRODUCTION','BUILDS','LEASE'): monkeypatch.setattr(m,name,tmp_path/name)
    for name in ('STATE','PRODUCTION','BUILDS'): getattr(m,name).mkdir()
    front=m.PRODUCTION/'frontend'; front.mkdir()
    for name in ('.next','node_modules'): (front/name).mkdir(); (front/name/'old').write_text('old')
    events=[]
    def write_private(path,data):
        with path.open('xb') as out: out.write(data)
    server=SimpleNamespace(secure_path=lambda *a,**kw:None,_sync_directory=lambda p:events.append(('sync',str(p))),_write_private=write_private,_sync_business_lease_parent=lambda:events.append(('lease-sync',)),_frontend_publication_backup_digest=lambda p,**kw:'f'*64)
    def copy(source,stage,env):
        (stage/'frontend').mkdir(parents=True)
        for name in ('.next','node_modules'): (stage/'frontend'/name).mkdir(); (stage/'frontend'/name/'new').write_text('new')
    def run(argv):
        events.append(tuple(argv))
        if 'show' in argv: return 'ActiveState=inactive\nSubState=dead\nMainPID=0\nControlPID=0\n'
        return ''
    def wjson(server,path,value): write_private(path,json.dumps(value).encode())
    build=SimpleNamespace(copy_build_inputs=copy,build_command=lambda *a:['npm ci --ignore-scripts --no-audit --no-fund\nnpm run build'],ENV={},freeze_artifacts=lambda s:None,write_json=wjson,run=run)
    helper=SimpleNamespace(_lease_identity=lambda *a:'identity')
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**kw:events.append(('sandbox-build',)))
    monkeypatch.setattr(m,'prepare_cache',lambda p:None)
    monkeypatch.setattr(m,'bundle_digest',lambda *a:'e'*64)
    monkeypatch.setattr(m,'assert_unchanged',lambda *a,**kw:events.append(('unchanged',)))
    monkeypatch.setattr(m,'verify_pages',lambda:events.append(('pages',)))
    monkeypatch.setattr(m,'runtime',lambda b:{'MainPID':'123','NRestarts':'0'})
    monkeypatch.setattr(m.time,'sleep',lambda _:None)
    plan=dict(publisher_sha='a'*40,production_sha='b'*40,operation_id='c'*32,frontend_tree='d'*40,public_build_env={})
    return m,plan,helper,server,build,events


def test_success_is_durable_artifact_only_and_preserves_previous_bundle(tmp_path,monkeypatch):
    import json
    m,plan,h,s,b,events=execution_fixture(tmp_path,monkeypatch)
    complete=m.execute(plan,tmp_path,h,None,s,b,lambda:events.append(('locks',)))
    audit=m.STATE/'frontend-publications'/plan['operation_id']
    assert complete['state']=='FRONTEND_SUCCEEDED' and not m.LEASE.exists()
    assert (audit/'previous-next/old').read_text()=='old'
    assert (m.PRODUCTION/'frontend/.next/new').read_text()=='new'
    assert json.loads((audit/'completed.json').read_text())==complete
    assert set(complete['proof_sha256'])=={'before.json','build.log','install-started.json','verified.json'}
    services=[e for e in events if e and e[0]=='/usr/bin/systemctl']
    assert all('health-frontend' in e for e in services)
    assert ('pages',) in events


def test_partial_switch_retains_lease_no_restart_no_retry(tmp_path,monkeypatch):
    m,plan,h,s,b,events=execution_fixture(tmp_path,monkeypatch)
    original=Path.rename
    def fail_second(self,target):
        if self.name=='node_modules' and 'frontend' in str(self.parent): raise OSError('interrupted')
        return original(self,target)
    monkeypatch.setattr(Path,'rename',fail_second)
    with pytest.raises(m.PublishError): m.execute(plan,tmp_path,h,None,s,b,lambda:None)
    audit=m.STATE/'frontend-publications'/plan['operation_id']
    assert m.LEASE.is_dir() and (audit/'failed.json').is_file()
    assert (audit/'install-started.json').is_file() and not (audit/'completed.json').exists()
    assert ('/usr/bin/systemctl','start','health-frontend') not in events


def test_build_failure_retains_lease_without_service_mutations(tmp_path,monkeypatch):
    import subprocess
    m,plan,h,s,b,events=execution_fixture(tmp_path,monkeypatch)
    def fail(*a,**kw): raise subprocess.CalledProcessError(1,['build'])
    monkeypatch.setattr(m.subprocess,'run',fail)
    with pytest.raises(m.PublishError): m.execute(plan,tmp_path,h,None,s,b,lambda:None)
    audit=m.STATE/'frontend-publications'/plan['operation_id']
    assert m.LEASE.exists() and (audit/'failed.json').exists()
    assert not (audit/'install-started.json').exists()
    assert not any(e[0]=='/usr/bin/systemctl' for e in events)


@pytest.mark.parametrize('bad',['redirect','oversize','missing','error'])
def test_public_readback_rejects_redirect_wrong_page_and_unbounded_body(monkeypatch,bad):
    from types import SimpleNamespace
    m=load()
    class Response:
        status=200
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def geturl(self): return 'https://health.executor.life/login' if bad=='redirect' else 'http://127.0.0.1:30001/privacy'
        def read(self,n):
            assert n==2_000_001
            return b'x'*n if bad=='oversize' else ('wrong' if bad=='missing' else '可选足迹与分享').encode()
    def open_request(*a,**kw):
        if bad=='error': raise OSError('network')
        return Response()
    monkeypatch.setattr(m.urllib.request,'build_opener',lambda *a:SimpleNamespace(open=open_request))
    monkeypatch.setattr(m.time,'sleep',lambda _:None)
    with pytest.raises(m.PublishError): m.verify_pages()


def test_inspection_checks_exact_ci_and_new_tree_before_any_publication(tmp_path,monkeypatch):
    from types import SimpleNamespace
    m=load(); events=[]
    args=SimpleNamespace(publisher_sha='a'*40,production_sha='b'*40,frontend_tree='c'*40,operation_id='d'*32)
    gate=SimpleNamespace(verify_release=lambda *a:events.append(('current-main-ci',a)),_latest=lambda *a:events.append(('historical-ci',a)),_get_json=None)
    helper=SimpleNamespace(_revision_proof=lambda *a:events.append(('production-proof',)))
    build=SimpleNamespace(git=lambda *a:'e'*40)
    with pytest.raises(m.PublishError): m.inspect(args,tmp_path,helper,None,None,gate,build)
    assert events[0]==('current-main-ci',('a'*40,'a'*40))
    assert events[1][0]=='historical-ci' and events[2][0]=='production-proof'


def test_pre_switch_backend_drift_never_stops_runtime(tmp_path,monkeypatch):
    m,plan,h,s,b,events=execution_fixture(tmp_path,monkeypatch)
    def drift(*a,**kw): raise m.PublishError('backend drift')
    monkeypatch.setattr(m,'assert_unchanged',drift)
    with pytest.raises(m.PublishError): m.execute(plan,tmp_path,h,None,s,b,lambda:None)
    assert m.LEASE.exists()
    assert not any(e[0]=='/usr/bin/systemctl' for e in events)


def test_build_disables_install_and_pre_post_build_lifecycle_hooks():
    from types import SimpleNamespace
    m=load()
    command=m.build_command(SimpleNamespace(build_command=lambda *a:['npm ci --ignore-scripts --no-audit --no-fund\nnpm run build']),'a'*32,Path('/tmp/stage'))
    assert command[-1]=='npm ci --ignore-scripts --no-audit --no-fund\nnpm run --ignore-scripts build'


@pytest.mark.parametrize('bad',['cache-symlink','file-symlink','hardlink','owner'])
def test_invalid_old_bundle_is_rejected_before_stop_or_rename(tmp_path,monkeypatch,bad):
    import os
    from types import SimpleNamespace
    m,plan,h,s,b,events=execution_fixture(tmp_path,monkeypatch)
    spec=importlib.util.spec_from_file_location('server_bad_bundle',Path(__file__).with_name('trusted_release_server.py'))
    server=importlib.util.module_from_spec(spec); spec.loader.exec_module(server)
    monkeypatch.setattr(server,'PRODUCTION',m.PRODUCTION)
    monkeypatch.setattr(server,'secure_path',lambda *a,**kw:None)
    # Root-owned production metadata simulated using actual test account IDs.
    original=server.validate_metadata
    monkeypatch.setattr(server,'validate_metadata',lambda info,**kw:None if info.st_uid==os.getuid() and not info.st_mode&0o022 else (_ for _ in ()).throw(server.LaunchError('owner')))
    monkeypatch.setattr(server.pwd,'getpwnam',lambda _:SimpleNamespace(pw_uid=os.getuid(),pw_gid=os.getgid()))
    root=m.PRODUCTION/'frontend/.next'
    if bad=='cache-symlink': (root/'cache').symlink_to(tmp_path)
    if bad=='file-symlink': (root/'escape').symlink_to('/etc/passwd')
    if bad=='hardlink': os.link(root/'old',root/'duplicate')
    if bad=='owner': (root/'old').chmod(0o666)
    s._frontend_publication_backup_digest=server._frontend_publication_backup_digest
    renames=[]
    original_rename=Path.rename
    monkeypatch.setattr(Path,'rename',lambda self,target:(renames.append((self,target)),original_rename(self,target))[1])
    with pytest.raises(m.PublishError): m.execute(plan,tmp_path,h,None,s,b,lambda:None)
    assert not renames
    assert not any(e[0]=='/usr/bin/systemctl' for e in events)
    assert (root/'old').exists() and m.LEASE.exists()
