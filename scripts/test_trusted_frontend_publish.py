"""Frontend helper and historical receipt contracts; new backup publication is frozen."""
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
        if 'show' in argv: return 'ActiveState=inactive\nSubState=dead\nMainPID=0\nControlPID=0\nResult=success\nExecMainCode=0\nExecMainStatus=0\n'
        return ''
    def wjson(server,path,value): write_private(path,json.dumps(value).encode())
    build=SimpleNamespace(copy_build_inputs=copy,build_command=lambda *a:['npm ci --ignore-scripts --no-audit --no-fund\nnpm run build'],ENV={},freeze_artifacts=lambda s:None,write_json=wjson,run=run)
    helper=SimpleNamespace(_lease_identity=lambda *a:'identity')
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**kw:events.append(('sandbox-build',)))
    monkeypatch.setattr(m,'prepare_cache',lambda p:None)
    monkeypatch.setattr(m,'bundle_digest',lambda *a:'e'*64)
    monkeypatch.setattr(m,'assert_unchanged',lambda *a,**kw:events.append(('unchanged',)))
    monkeypatch.setattr(m,'verify_pages',lambda:events.append(('pages',)))
    monkeypatch.setattr(m,'verify_availability_pages',lambda:events.append(('availability-pages',)))
    monkeypatch.setattr(m,'runtime',lambda b:{'MainPID':'123','NRestarts':'0'})
    monkeypatch.setattr(m.time,'sleep',lambda _:None)
    plan=dict(publisher_sha='a'*40,production_sha='b'*40,operation_id='c'*32,frontend_tree='d'*40,public_build_env={})
    return m,plan,helper,server,build,events


@pytest.mark.parametrize('bad',['redirect','oversize','missing','error','stale_privacy'])
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
            return b'x'*n if bad=='oversize' else ('wrong' if bad=='missing' else '可选足迹与分享' if bad=='stale_privacy' else '可选城市足迹与分享').encode()
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


def test_build_disables_install_and_pre_post_build_lifecycle_hooks():
    from types import SimpleNamespace
    m=load()
    command=m.build_command(SimpleNamespace(build_command=lambda *a:['npm ci --ignore-scripts --no-audit --no-fund\nnpm run build']),'a'*32,Path('/tmp/stage'))
    assert command[-1]=='npm ci --ignore-scripts --no-audit --no-fund\nnpm run --ignore-scripts build'


def runtime_build(m, counter='1518'):
    from types import SimpleNamespace
    values={**m.RUNTIME,'ActiveState':'active','SubState':'running','MainPID':'3784950','NRestarts':counter,
            'ExecMainStartTimestampMonotonic':'26527954314920','Environment':'NODE_ENV=production BACKEND_URL=http://127.0.0.1:8000'}
    values['ExecStart']='{ path=/usr/bin/node ; argv[]='+m.RUNTIME['ExecStart']+' ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }'
    return SimpleNamespace(run=lambda a:'\n'.join(k+'='+v for k,v in values.items()))


def test_stable_historical_restart_count_is_accepted(monkeypatch):
    m=load(); sleeps=[]
    monkeypatch.setattr(m.time,'sleep',sleeps.append)
    result=m.stable_runtime(runtime_build(m))
    assert result['NRestarts']=='1518' and sleeps==[6]


@pytest.mark.parametrize('field,value',[('NRestarts','1519'),('MainPID','3784951'),('ExecMainStartTimestampMonotonic','26527954314921')])
def test_preflight_rejects_restart_counter_or_process_identity_change(monkeypatch,field,value):
    m=load()
    first=m.runtime(runtime_build(m)); second={**first,field:value}
    samples=iter([first,second])
    monkeypatch.setattr(m,'runtime',lambda _:next(samples))
    monkeypatch.setattr(m.time,'sleep',lambda _:None)
    with pytest.raises(m.PublishError): m.stable_runtime(None)


@pytest.mark.parametrize('counter',['-1','01','unknown','1.5','9'*21])
def test_runtime_rejects_invalid_restart_counters(counter):
    m=load()
    with pytest.raises(m.PublishError): m.runtime(runtime_build(m,counter))


@pytest.mark.parametrize('endpoint', ['http://localhost:8000', 'http://127.0.0.1:8000'])
def test_allowlisted_loopback_build_endpoint_matches_fixed_runtime_without_editing_config(tmp_path, monkeypatch, endpoint):
    m = load()
    spec = importlib.util.spec_from_file_location('endpoint_build_test', Path(__file__).with_name('trusted_frontend_rebuild.py'))
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    monkeypatch.setattr(m, 'PRODUCTION', tmp_path)
    (tmp_path / 'frontend').mkdir()
    config = tmp_path / 'frontend/.env.local'
    config.write_text('BACKEND_URL=' + endpoint + '\n')
    before = config.read_bytes()
    environment, fingerprints = m.configuration(build)
    assert environment['BACKEND_URL'] == 'http://127.0.0.1:8000'
    assert config.read_bytes() == before
    assert fingerprints['.env.local'] == build.data_fingerprint(config)[0]


@pytest.mark.parametrize('endpoint', ['http://localhost:8001', 'http://127.0.0.2:8000',
                                    'http://localhost.example:8000', 'http://169.254.169.254'])
def test_unreviewed_build_backend_endpoint_still_rejected(tmp_path, monkeypatch, endpoint):
    m = load()
    spec = importlib.util.spec_from_file_location('bad_endpoint_build_test', Path(__file__).with_name('trusted_frontend_rebuild.py'))
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    monkeypatch.setattr(m, 'PRODUCTION', tmp_path)
    (tmp_path / 'frontend').mkdir()
    config = tmp_path / 'frontend/.env.local'
    config.write_text('BACKEND_URL=' + endpoint + '\n')
    with pytest.raises(build.RebuildError):
        m.configuration(build)
    assert config.read_text() == 'BACKEND_URL=' + endpoint + '\n'


def stopped143():
    return dict(ActiveState='failed',SubState='failed',MainPID='0',ControlPID='0',Result='exit-code',ExecMainCode='1',ExecMainStatus='143')


@pytest.mark.parametrize('code,status',[('0','0'),('1','0'),('2','15')])
def test_normal_stopped_success_accepts_documented_exit_or_sigterm(code,status):
    m=load()
    m.validate_stopped(dict(ActiveState='inactive',SubState='dead',MainPID='0',ControlPID='0',Result='success',ExecMainCode=code,ExecMainStatus=status))


@pytest.mark.parametrize('code,status',[('2','9'),('1','143'),('1','1'),('0','15')])
def test_inactive_success_does_not_hide_other_signal_or_exit(code,status):
    m=load()
    with pytest.raises(m.PublishError):
        m.validate_stopped(dict(ActiveState='inactive',SubState='dead',MainPID='0',ControlPID='0',Result='success',ExecMainCode=code,ExecMainStatus=status))


def test_old_availability_verifies_only_fixed_internal_and_public_privacy(monkeypatch):
    from types import SimpleNamespace
    m=load(); urls=[]
    class Response:
        status=200
        def __init__(self,url): self.url=url
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def geturl(self): return self.url
        def read(self,n):
            assert n==2_000_001
            return '可选足迹与分享'.encode()
    def open_request(request,**kw):
        urls.append(request.full_url)
        return Response(request.full_url)
    monkeypatch.setattr(m.urllib.request,'build_opener',lambda *a:SimpleNamespace(open=open_request))
    m.verify_availability_pages()
    assert urls==['http://127.0.0.1:30001/privacy','https://health.executor.life/privacy']


def kbase_config_pair():
    candidate = (Path(__file__).parents[1] / 'frontend/next.config.js').read_bytes()
    start = candidate.index(b'    const eduOrigin =')
    end = candidate.index(b'    return headers;', start)
    candidate = candidate[:start] + candidate[end:]
    candidate = candidate.replace(b"      {\n        source: '/api/v1/auth/sso/edu',\n        destination: `${backendUrl}/api/v1/auth/sso/edu`,\n      },\n", b'')
    previous = candidate.replace(b"process.env.KBASE_SSO_ORIGIN ?? 'https://kbase.executor.life'", b"process.env.KBASE_SSO_ORIGIN")
    return previous, candidate


def test_only_reviewed_build_time_header_config_pair_is_allowed():
    m = load()
    previous, candidate = kbase_config_pair()
    m.validate_runtime_input_change(['frontend/next.config.js'], previous, candidate)
    for paths, before, after in [
        (['frontend/next.config.js'], candidate, previous),
        (['frontend/next.config.js'], previous, candidate + b'\n'),
        (['frontend/next.config.js'], previous + b'\n', candidate),
        (['frontend/next.config.mjs'], previous, candidate),
        (['frontend/next.config.js', 'frontend/public/icon.svg'], previous, candidate),
        (['frontend/public/icon.svg'], previous, candidate),
    ]:
        with pytest.raises(m.PublishError):
            m.validate_runtime_input_change(paths, before, after)


def login_headers(form="'self' https://kbase.executor.life"):
    from email.message import Message
    headers = Message()
    headers['Content-Security-Policy'] = "default-src 'self'; form-action " + form
    headers['Referrer-Policy'] = 'strict-origin'
    headers['Cache-Control'] = 'private, no-cache, no-store, max-age=0'
    return headers


def test_served_login_policy_requires_exact_single_csp_and_private_response():
    m = load()
    assert m.valid_login_headers(login_headers(), '/connect/kbase')
    assert m.valid_login_headers(login_headers("'self'"), '/login')
    assert not m.valid_login_headers(login_headers(), '/login')
    for form in ["'self'", "'self' https://evil.test", "'self' https://kbase.executor.life *", "'self' https://kbase.executor.life; form-action 'self'"]:
        assert not m.valid_login_headers(login_headers(form), '/connect/kbase')
    for key, value in [('Content-Security-Policy', "form-action 'self'"), ('Referrer-Policy', 'unsafe-url'), ('Cache-Control', 'public')]:
        headers = login_headers()
        if key != 'Content-Security-Policy': del headers[key]
        headers[key] = value
        assert not m.valid_login_headers(headers, '/connect/kbase')


def test_raw_git_config_reader_does_not_normalize_line_endings(tmp_path):
    import subprocess
    from types import SimpleNamespace
    m = load()
    previous, candidate = kbase_config_pair()
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path), 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_SYSTEM': '/dev/null',
           'GIT_AUTHOR_NAME': 'Test', 'GIT_AUTHOR_EMAIL': 'test@example.test',
           'GIT_COMMITTER_NAME': 'Test', 'GIT_COMMITTER_EMAIL': 'test@example.test'}
    def git(*args, data=None):
        return subprocess.run(['/usr/bin/git', '-C', str(tmp_path), *args], input=data,
                              env=env, capture_output=True, check=True).stdout.strip()
    git('init')
    for raw in (candidate, candidate.replace(b'\n', b'\r\n')):
        blob = git('hash-object', '-w', '--stdin', data=raw)
        subtree = git('mktree', data=b'100644 blob ' + blob + b'\tnext.config.js\n')
        tree = git('mktree', data=b'040000 tree ' + subtree + b'\tfrontend\n')
        revision = git('commit-tree', tree.decode(), '-m', 'fixture').decode()
        actual = m.runtime_config_bytes(tmp_path, revision, SimpleNamespace(ENV=env))
        assert actual == raw
        if raw == candidate:
            m.validate_runtime_input_change(['frontend/next.config.js'], previous, actual)
        else:
            with pytest.raises(m.PublishError):
                m.validate_runtime_input_change(['frontend/next.config.js'], previous, actual)


def test_complete_page_readback_accepts_csr_login_without_translated_text(monkeypatch):
    from types import SimpleNamespace
    m = load(); visited = []
    monkeypatch.setattr(m.time, 'sleep', lambda _: None)
    class Response:
        status = 200
        def __init__(self, url):
            self.url = url
            origin = {'kbase': 'https://kbase.executor.life', 'edu': 'https://edu.executor.life'}.get(url.rsplit('/', 1)[-1])
            self.headers = login_headers("'self'" + (' ' + origin if origin else ''))
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def geturl(self): return self.url
        def read(self, bound):
            path = self.url.split('/', 3)[3]
            privacy_source = (Path(__file__).parents[1] / 'frontend/src/app/privacy/page.tsx').read_text()
            import re
            privacy_title = re.search(r"title: '(可选[^']*足迹与分享)'", privacy_source).group(1)
            return {'privacy': privacy_title, 'connect/health': '小巴健康 · 数据连接',
                    'connect/kbase': '登录知识库 <meta name="referrer" content="strict-origin">',
                    'connect/edu': '登录Edu <meta name="referrer" content="strict-origin">',
                    'login': '<!DOCTYPE html><html><body><div id="root"></div></body></html>'}[path].encode()
    def request(req, **kwargs):
        visited.append(req.full_url)
        return Response(req.full_url)
    monkeypatch.setattr(m.urllib.request, 'build_opener', lambda *args: SimpleNamespace(open=request))
    m.verify_pages()
    assert len(visited) == 10 and len(set(visited)) == 10
    monkeypatch.setattr(m.time, 'sleep', lambda _: None)
    original = Response.__init__
    def bad(self, url):
        original(self, url)
        if url.endswith('/login'): self.headers = login_headers("'self' https://evil.test")
    monkeypatch.setattr(Response, '__init__', bad)
    with pytest.raises(m.PublishError): m.verify_pages()


def test_edu_runtime_change_is_exact_and_keeps_login_and_kbase_isolated():
    m = load()
    _, previous = kbase_config_pair()
    candidate = (Path(__file__).parents[1] / 'frontend/next.config.js').read_bytes()
    m.validate_runtime_input_change(['frontend/next.config.js'], previous, candidate)
    for before, after in [(candidate, previous), (previous, candidate + b'\n'),
                          (previous + b'\n', candidate),
                          (previous, candidate.replace(b'https://edu.executor.life', b'https://evil.test'))]:
        with pytest.raises(m.PublishError):
            m.validate_runtime_input_change(['frontend/next.config.js'], before, after)
    good = login_headers("'self' https://edu.executor.life")
    assert m.valid_login_headers(good, '/connect/edu')
    assert not m.valid_login_headers(good, '/connect/kbase')
    assert not m.valid_login_headers(good, '/login')
    for form in ["'self'", "'self' https://kbase.executor.life", "'self' https://evil.test",
                 "'self' https://edu.executor.life *",
                 "'self' https://edu.executor.life; form-action 'self'"]:
        assert not m.valid_login_headers(login_headers(form), '/connect/edu')
    for key, value in [('Content-Security-Policy', "form-action 'self'"),
                       ('Referrer-Policy', 'unsafe-url'), ('Cache-Control', 'public')]:
        headers = login_headers("'self' https://edu.executor.life")
        if key != 'Content-Security-Policy': del headers[key]
        headers[key] = value
        assert not m.valid_login_headers(headers, '/connect/edu')
