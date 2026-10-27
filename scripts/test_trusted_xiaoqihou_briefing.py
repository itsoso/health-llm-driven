"""Authorization, lease, parent and uncertain-commit regression coverage."""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_trusted_review_briefing_repair import Engine, database_stubs
from test_review_xiaoqihou_briefing import load as core_load


def load():
    path=Path(__file__).with_name('trusted_xiaoqihou_briefing.py')
    spec=importlib.util.spec_from_file_location('trusted_xiaoqihou_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def evidence(core):
    return dict(target_sha=core.TARGET,action=core.ACTION,fixture_sha256=core.FIXTURE_SHA256,
        legacy_closure_sha256='a'*64,production_evidence_sha256='b'*64,database_snapshot_sha256='c'*64,
        health_snapshot_sha256='d'*64,demo_user_id=44,ordering_metadata_plan=core.empty_ordering_plan())


def test_canonical_entry_required():
    m=load()
    with pytest.raises(m.BriefingError): m.context('a'*40)


@pytest.mark.parametrize('flags',[
 ['--accept-xiaoqihou-briefing'], ['--evidence-sha256','a'*64],
 ['--database-probe','apply','--token-stdin'],['--database-probe','apply','--accept-xiaoqihou-briefing'],
 ['--parent-proof-fd','9']])
def test_cli_rejects_incomplete_authority(monkeypatch,flags):
    m=load();monkeypatch.setattr(m.sys,'argv',['briefing','--sha','a'*40,*flags])
    monkeypatch.setattr(m,'context',lambda *a,**k:pytest.fail('must not reach context'))
    monkeypatch.setattr(m,'database_child',lambda *a:pytest.fail('must not reach database child'))
    assert m.main()==1


@pytest.mark.parametrize('fault',[None,'commit_lost','health_before','health_after','health_readback','readback','parent_before_commit'])
def test_database_preserves_no_retry_semantics(monkeypatch,fault):
    m=load();core=core_load()
    shared=m.load(Path(__file__).with_name('trusted_review_briefing_repair.py'),'test_xiao_shared')
    engine=Engine(fail_commit=fault=='commit_lost')
    health=['d'*64]*3
    if fault and fault.startswith('health_'):
        health[{'health_before':0,'health_after':1,'health_readback':2}[fault]]='f'*64
    readers=database_stubs(monkeypatch,shared,core,engine,health_values=health,readback_fail=fault=='readback')
    monkeypatch.setattr(shared,'demo_identity',lambda *a:44)
    n=0
    def check():
        nonlocal n
        n+=1
        if fault=='parent_before_commit' and n==2: raise m.BriefingError('lost original parent')
    def run(): return m.database_work(engine,core,shared,readers,'fixture@example.invalid',Path('/fixture'),b'x'*32,check,evidence=evidence(core))
    if fault is None:
        assert run()['state']=='VERIFIED_BRIEFING_ONLY'
        assert engine.events.count('commit')==1 and engine.events.count('connect')==2
    else:
        with pytest.raises((m.BriefingError,OSError,ValueError)): run()
        assert engine.events.count('commit') <= 1 and engine.events.count('insert') <= 1
        if fault in ('health_before','health_after','parent_before_commit'):
            assert 'commit' not in engine.events and engine.events.count('rollback')==1
        else: assert engine.events.count('commit')==1


@pytest.mark.parametrize('fault',[None,'holder','start','exe','argv','uid','nonce','attempt','authority','digest','lease'])
def test_inherited_proof_and_live_parent_lease(tmp_path,monkeypatch,fault):
    m=load();shared=m.load(Path(__file__).with_name('trusted_review_briefing_repair.py'),'test_xiao_parent')
    proc=tmp_path/'proc';parent=proc/'900';(parent/'fd').mkdir(parents=True)
    fields=['S','1','1','1','0']+['0']*14+['1234']
    (parent/'stat').write_text('900 (python) '+' '.join(fields));(parent/'status').write_text('Uid:\t0\t0\t0\t0\n')
    source=tmp_path/'canonical';sha='a'*40;digest='b'*64
    argv=['/usr/bin/python3.12','-I','-S','-B',str(source/'scripts'/m.ENTRY),'--sha',sha,
          '--accept-xiaoqihou-briefing','--evidence-sha256',digest]
    (parent/'exe').symlink_to('/usr/bin/python3.12')
    launcher,build=tmp_path/'launcher',tmp_path/'build';launcher.touch();build.touch()
    lfd,bfd=os.open(launcher,os.O_RDWR),os.open(build,os.O_RDWR);rd,wr=os.pipe()
    try:
        for fd,path in ((lfd,launcher),(bfd,build)): (parent/'fd'/str(fd)).symlink_to(path)
        lines=[]
        for n,fd in enumerate((lfd,bfd)):
            st=os.fstat(fd)
            lines.append(f'{n}: FLOCK ADVISORY WRITE {901 if fault=="holder" else 900} {os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino} 0 EOF')
        (proc/'locks').write_text('\n'.join(lines))
        proof={'parent':{'pid':900,'start_ticks':'1234'},'nonce':'c'*64,'sha':sha,'mode':'apply',
               'evidence_sha256':digest,'attempt':m.ATTEMPT,'lease':{'token':'d'*64,'identity':[[1,2],[1,3]]}}
        if fault=='start':proof['parent']['start_ticks']='999'
        elif fault=='exe':(parent/'exe').unlink();(parent/'exe').symlink_to('/usr/bin/python3.11')
        elif fault=='argv':argv=['python','-c','unrelated']
        elif fault=='uid':(parent/'status').write_text('Uid:\t1000\t1000\t1000\t1000\n')
        elif fault=='nonce':proof['nonce']='wrong'
        elif fault=='attempt':proof['attempt']='old'
        elif fault=='authority':argv.remove('--accept-xiaoqihou-briefing')
        elif fault=='digest':proof['evidence_sha256']='e'*64
        (parent/'cmdline').write_bytes(b'\0'.join(x.encode() for x in argv)+b'\0')
        os.write(wr,json.dumps(proof).encode());os.close(wr);wr=None
        actual=os.fstat
        monkeypatch.setattr(m.os,'fstat',lambda fd:SimpleNamespace(st_mode=actual(fd).st_mode,st_uid=0) if fd==rd else actual(fd))
        monkeypatch.setattr(m.os,'getppid',lambda:900)
        b=SimpleNamespace(_assert_original_lock=lambda *a:None,BUSINESS_LEASE=tmp_path/'lease')
        reset=SimpleNamespace(_lease_identity=lambda *a:((1,2),(1,4 if fault=='lease' else 3)))
        def run():return m.validate_parent(source,sha,'apply',rd,lfd,bfd,b,object(),shared,reset,proc)
        if fault is not None:
            with pytest.raises(m.BriefingError):run()
        else:
            verified,check=run();assert verified==proof
            (proc/'locks').write_text('')
            with pytest.raises(m.BriefingError):check()
    finally:
        for fd in (lfd,bfd,rd,wr):
            if fd is not None:os.close(fd)


@pytest.mark.parametrize('unknown',[False,True])
def test_actual_adapter_intent_lease_and_cleanup(tmp_path,monkeypatch,unknown):
    m=load();core=core_load();m.STATE=tmp_path
    shared=m.load(Path(__file__).with_name('trusted_review_briefing_repair.py'),'test_xiao_adapter')
    actual_readers=m.load(Path(__file__).with_name('review_maintenance_retirement.py'),'xiao_actual_sync')
    readers=SimpleNamespace(sync=actual_readers.sync,write_json=lambda p,v:p.write_text(json.dumps(v)))
    (tmp_path/'run-lock').mkdir()
    (tmp_path/'var-lock').symlink_to(tmp_path/'run-lock',target_is_directory=True)
    b=SimpleNamespace(STATE=tmp_path,BUSINESS_LEASE=tmp_path/'var-lock'/'lease',secure=lambda *a,**k:None,
        _write=lambda p,v:p.write_bytes(v),_read_json=lambda p:json.loads(p.read_text()),_assert_original_lock=lambda *a:None,
        _recovery_process_proof=lambda:None)
    reset=SimpleNamespace(_lease_identity=lambda *a:tuple((p.stat().st_dev,p.stat().st_ino) for p in (b.BUSINESS_LEASE,b.BUSINESS_LEASE/'token')))
    monkeypatch.setattr(shared,'parent_identity',lambda pid:{'pid':pid,'start_ticks':'12'})
    production={'legacy':{'immutable':'historical'}}
    monkeypatch.setattr(m,'production',lambda *a:production)
    calls=[]
    def run(argv,**kwargs):
        proof=json.loads(os.read(kwargs['pass_fds'][0],4096)); mode=proof['mode'];calls.append(mode)
        if mode=='inspect':value={'demo_user_id':44,'database_snapshot_sha256':'c'*64,'health_snapshot_sha256':'d'*64,'ordering_metadata_plan':core.empty_ordering_plan()}
        else:
            (m.record_path()/'database-started.json').write_text('{}')
            if unknown:raise OSError('lost response')
            value={'state':'VERIFIED_BRIEFING_ONLY','before_sha256':'c'*64,'after_sha256':'e'*64}
        return SimpleNamespace(stdout=json.dumps(value).encode())
    monkeypatch.setattr(m.subprocess,'run',run)
    a=m.make_adapter(tmp_path,b,object(),readers,core,shared,reset,object(),'a'*40,10,11)
    observed=core.repair(a);assert not a.record.exists() and not b.BUSINESS_LEASE.exists()
    try:
        if unknown:
            with pytest.raises(OSError):core.repair(a,authorized=True,evidence_sha256=observed['evidence_sha256'])
        else:assert core.repair(a,authorized=True,evidence_sha256=observed['evidence_sha256'])['state']=='BRIEFING_REPAIRED_ONLY'
    finally:a.finish()
    assert b.BUSINESS_LEASE.exists()==unknown
    assert (a.record/'intent.json').is_file()
    with pytest.raises(core.RepairError):core.repair(a,authorized=True,evidence_sha256=observed['evidence_sha256'])
    assert calls.count('apply')==1


@pytest.fixture
def pg_adapter():
    """A random disposable database on an explicitly supplied synthetic cluster."""
    import os
    import uuid
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    url = os.environ.get('REVA_REVIEW_CLOSURE_TEST_DATABASE_URL')
    if not url:
        pytest.skip('dedicated PostgreSQL integration URL required')
    parsed = make_url(url)
    # This fixture creates only a new synthetic database; never adopt public
    # tables in a supplied database or a remote/production server.
    if parsed.host not in (None, '', 'localhost', '127.0.0.1') or (parsed.query.get('host') and not str(parsed.query['host']).startswith('/tmp/reva-')):
        pytest.fail('dedicated local Unix-socket test cluster required')
    name = 'briefing_adapter_' + uuid.uuid4().hex
    control = create_engine(url, isolation_level='AUTOCOMMIT')
    with control.connect() as c:
        c.execute(text('CREATE DATABASE ' + name + " ENCODING 'UTF8' TEMPLATE template0"))
    engine = create_engine(parsed.set(database=name), isolation_level='SERIALIZABLE')
    m=load();core=core_load();shared=m.load(Path(__file__).with_name('trusted_review_briefing_repair.py'),'xiao_pg_shared')
    root = Path(__file__).resolve().parents[1]
    readers = m.load(root / 'scripts/review_maintenance_retirement.py', 'pg_adapter_readers')
    fixture = root / 'backend/fixtures/demo_user_minimal.json'
    try:
        with engine.begin() as c:
            c.execute(text('CREATE TABLE public.users (id SERIAL PRIMARY KEY, email TEXT UNIQUE, is_active BOOLEAN, is_approved BOOLEAN, is_admin BOOLEAN)'))
            c.execute(text('CREATE TABLE public.agent_conversations (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), title TEXT, session_key TEXT, created_at TIMESTAMP, updated_at TIMESTAMP)'))
            c.execute(text('CREATE TABLE public.agent_messages (id SERIAL PRIMARY KEY, conversation_id INTEGER REFERENCES agent_conversations(id), role TEXT, content TEXT, image_url TEXT, meta JSONB, created_at TIMESTAMP)'))
            c.execute(text("INSERT INTO users VALUES (1,'review@example.invalid',true,true,false),(2,'other@example.invalid',true,true,false)"))
            c.execute(text("INSERT INTO agent_conversations(user_id,title,session_key,created_at,updated_at) VALUES (1,'old','old',now()-interval '1 day',now()-interval '1 day'),(2,'other','other',now()-interval '1 day',now()-interval '1 day')"))
            c.execute(text("INSERT INTO agent_messages(conversation_id,role,content,created_at) VALUES(1,'user','old content',now()),(2,'user','other content',now())"))
            for table in readers.DIRECT_TABLES:
                if table == 'agent_conversations':
                    continue
                c.execute(text(f'CREATE TABLE public.{table} (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), payload JSONB)'))
                c.execute(text(f'INSERT INTO public.{table} VALUES (1,1,\'{{"synthetic":"demo"}}\'),(2,2,\'{{"synthetic":"other"}}\')'))
            for table, (fk, parent) in readers.CHILD_TABLES.items():
                if table == 'agent_messages':
                    continue
                c.execute(text(f'CREATE TABLE public.{table} (id INTEGER PRIMARY KEY, {fk} INTEGER REFERENCES public.{parent}(id), payload JSONB)'))
                c.execute(text(f'INSERT INTO public.{table} VALUES (1,1,\'{{"synthetic":"demo-child"}}\'),(2,2,\'{{"synthetic":"other-child"}}\')'))
        yield m, core, shared, readers, engine, fixture
    finally:
        engine.dispose()
        with control.connect() as c:
            c.execute(text('DROP DATABASE ' + name))
        control.dispose()


def test_postgres_actual_database_work_public_schema(pg_adapter):
    from sqlalchemy import text
    m, core, shared, readers, engine, fixture = pg_adapter
    observed = m.database_work(engine, core, shared, readers, 'review@example.invalid', fixture, b'k' * 32, lambda:None)
    before = evidence(core)
    before.update(observed)
    result = m.database_work(engine, core, shared, readers, 'review@example.invalid', fixture, b'k' * 32, lambda:None, evidence=before)
    assert result['state'] == 'VERIFIED_BRIEFING_ONLY'
    with engine.begin() as c:
        assert c.execute(text('SELECT count(*) FROM agent_conversations')).scalar_one() == 3
        assert c.execute(text('SELECT count(*) FROM agent_messages')).scalar_one() == 4
        assert c.execute(text("SELECT content FROM agent_messages WHERE id=2")).scalar_one() == 'other content'
        assert shared.health_snapshot(c, 1, b'k' * 32, readers) == before['health_snapshot_sha256']
    with pytest.raises(core.RepairError, match='already exists'):
        m.database_work(engine, core, shared, readers, 'review@example.invalid', fixture, b'k' * 32, lambda:None)


def test_postgres_trigger_blocks_before_any_insert(pg_adapter):
    from sqlalchemy import text
    m, core, shared, readers, engine, fixture = pg_adapter
    observed = m.database_work(engine, core, shared, readers, 'review@example.invalid', fixture, b'k' * 32, lambda:None)
    before = evidence(core)
    before.update(observed)
    with engine.begin() as c:
        c.execute(text("CREATE FUNCTION unwanted() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN UPDATE weight_records SET payload='{}'::jsonb; RETURN NEW; END $$"))
        c.execute(text('CREATE TRIGGER unwanted BEFORE INSERT ON agent_conversations FOR EACH ROW EXECUTE FUNCTION unwanted()'))
    with pytest.raises(shared.BriefingError, match='unreviewed'):
        m.database_work(engine, core, shared, readers, 'review@example.invalid', fixture, b'k' * 32, lambda:None, evidence=before)
    with engine.begin() as c:
        assert c.execute(text('SELECT count(*) FROM agent_conversations')).scalar_one() == 2
        assert shared.health_snapshot(c, 1, b'k' * 32, readers) == before['health_snapshot_sha256']


def test_postgres_email_reassignment_does_not_change_bound_owner(pg_adapter):
    from sqlalchemy import text
    m, core, shared, readers, engine, fixture = pg_adapter
    observed = m.database_work(engine, core, shared, readers, 'review@example.invalid', fixture, b'k' * 32, lambda:None)
    before = evidence(core)
    before.update(observed)
    with engine.begin() as c:
        c.execute(text("UPDATE users SET email='old-review@example.invalid' WHERE id=1"))
        c.execute(text("UPDATE users SET email='review@example.invalid' WHERE id=2"))
    with pytest.raises(m.BriefingError, match='demo identity'):
        m.database_work(engine, core, shared, readers, 'review@example.invalid', fixture, b'k' * 32, lambda:None, evidence=before)
    with engine.begin() as c:
        assert c.execute(text('SELECT count(*) FROM agent_conversations')).scalar_one() == 2


def history_fixture(tmp_path):
    core=core_load();value=evidence(core);fingerprint=core.digest(value)
    root=tmp_path/'review-xiaoqihou-briefings';root.mkdir(mode=0o700)
    record=root/'xiaoqihou-fixed-briefing-v1';record.mkdir(mode=0o700)
    intent={'evidence':value,'evidence_sha256':fingerprint,'operator_sha':'a'*40,'attempt':record.name,
            'accept_xiaoqihou_briefing':True,'lease':{'token':'b'*64,'identity':[[1,2],[1,3]]},
            'parent_binding':{'pid':42,'start_ticks':'100','nonce_sha256':'f'*64}}
    start={'state':'DATABASE_ATTEMPT_STARTED','operator_sha':'a'*40,'attempt':record.name,'evidence_sha256':fingerprint}
    end={'state':'BRIEFING_REPAIRED_ONLY','evidence_sha256':fingerprint,
         'result':{'state':'VERIFIED_BRIEFING_ONLY','before_sha256':value['database_snapshot_sha256'],'after_sha256':'e'*64},
         'original_outcome':'UNKNOWN','reset_authorized':False,'release_unblocked':False,'retry_authorized':False}
    for n,v in [('intent.json',intent),('database-started.json',start),('completed.json',end)]:
        (record/n).write_text(json.dumps(v));(record/n).chmod(0o600)
    return record,intent,start,end


@pytest.mark.parametrize('fault',[None,'no_completion','no_start','no_intent','wrong_operator','wrong_hash','retry','extra','other_attempt','wrong_target'])
def test_durable_history_admission_without_volatile_lease(tmp_path,monkeypatch,fault):
    from test_trusted_release_server import load_server
    server=load_server();monkeypatch.setattr(server,'STATE',tmp_path)
    monkeypatch.setattr(server,'secure_path',lambda *a,**k:None)
    monkeypatch.setattr(server,'validate_metadata',lambda *a,**k:None)
    record,intent,start,end=history_fixture(tmp_path)
    if fault and fault.startswith('no_'):
        (record/{'no_completion':'completed.json','no_start':'database-started.json','no_intent':'intent.json'}[fault]).unlink()
    elif fault=='wrong_operator':start['operator_sha']='b'*40;(record/'database-started.json').write_text(json.dumps(start))
    elif fault=='wrong_hash':end['evidence_sha256']='0'*64;(record/'completed.json').write_text(json.dumps(end))
    elif fault=='retry':end['retry_authorized']=True;(record/'completed.json').write_text(json.dumps(end))
    elif fault=='extra':(record/'other.json').write_text('{}')
    elif fault=='other_attempt':(record.parent/'another').mkdir()
    elif fault=='wrong_target':intent['evidence']['target_sha']='c'*40;(record/'intent.json').write_text(json.dumps(intent))
    assert not (tmp_path/'lease').exists()
    if fault is None:server.assert_xiaoqihou_briefing_history()
    else:
        with pytest.raises(server.LaunchError):server.assert_xiaoqihou_briefing_history()


def test_true_publisher_admission_blocks_unknown_before_consumption(tmp_path,monkeypatch):
    from test_trusted_release_server import setup_state, policy
    server=setup_state(monkeypatch,tmp_path);monkeypatch.setattr(server,'STATE',tmp_path)
    record,_,_,_=history_fixture(tmp_path);(record/'completed.json').unlink()
    workspace=tmp_path/('a'*40);workspace.mkdir()
    for entry in [lambda:server.run_once(policy(),workspace,lambda *a:pytest.fail('prepare'),lambda *a:pytest.fail('deploy')),
                  lambda:server.check_readiness(policy()),lambda:server.claim_build(policy(),workspace),
                  lambda:server.claim_testflight(policy(),workspace),
                  lambda:server.assert_frontend_rebuild_history(tmp_path),lambda:server.assert_ota_history()]:
        with pytest.raises(server.LaunchError,match='maintenance incomplete'):entry()
    assert not (workspace/'started.json').exists() and not (workspace/'build-started.json').exists()
    assert not (workspace/'native-started.json').exists()


def test_true_bootstrap_idle_and_known_activity_block_unknown(tmp_path,monkeypatch):
    from test_trusted_release_server import setup_state
    server=setup_state(monkeypatch,tmp_path);monkeypatch.setattr(server,'STATE',tmp_path)
    m=load();b=m.load(Path(__file__).with_name('bootstrap_trusted_release.py'),'xiaoqihou_bootstrap_admission_test')
    monkeypatch.setattr(b,'STATE',tmp_path);monkeypatch.setattr(b,'BUSINESS_LEASE',tmp_path/'absent-volatile-lease')
    # OS metadata/loading is tested by the bootstrap suite. Keep actual public
    # aggregate functions and actual strict receipt validator for this regression.
    monkeypatch.setattr(b,'_exam_history_server',lambda:server)
    monkeypatch.setattr(b,'assert_xiaoqihou_briefing_history',lambda:server.assert_xiaoqihou_briefing_history(tmp_path))
    record,_,_,_=history_fixture(tmp_path);(record/'completed.json').unlink()
    for call in (lambda:b._assert_known_activity({}),b._assert_idle,b.assert_frontend_rebuild_history,b.assert_ota_history):
        with pytest.raises(server.LaunchError,match='maintenance incomplete'):call()


@pytest.mark.parametrize('fault',[None,'installed','policy_sha','executor'])
def test_current_installed_history_guard_required_before_database(tmp_path,monkeypatch,fault):
    import hashlib
    m=load();sha='a'*40;source=tmp_path/sha/'source';(source/'scripts').mkdir(parents=True)
    code=b'reviewed launcher with durable guard';(source/'scripts/trusted_release_server.py').write_bytes(code)
    installed=tmp_path/'installed.py';installed.write_bytes(code if fault!='installed' else b'old launcher')
    policy={'sha':'b'*40 if fault=='policy_sha' else sha,'expires_at':0,
            'executor_sha256':'0'*64 if fault=='executor' else hashlib.sha256(code).hexdigest()}
    b=SimpleNamespace(INSTALLED=installed,CONFIG=tmp_path/'config',STATE=tmp_path,secure=lambda *a:None,
        canonical_source=lambda *a:tmp_path/'target',_read_json=lambda p:policy if p.name=='authorized-release.json' else {'sha':m.TARGET,'state':'SUCCEEDED'})
    server=SimpleNamespace(validate_policy=lambda *a,**k:None)
    reset=SimpleNamespace(_validate_production=lambda *a:None)
    monkeypatch.setattr(m,'legacy_evidence',lambda *a:{'immutable':True})
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**k:SimpleNamespace(stdout=b'active\n'))
    if fault is None: assert m.production(source,b,server,reset,object())['target_sha']==m.TARGET
    else:
        with pytest.raises(m.BriefingError,match='installed launcher'):m.production(source,b,server,reset,object())
