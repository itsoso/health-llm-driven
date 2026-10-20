"""A separate, fixed advance must not turn an unknown reset into success."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest


def load():
    spec = importlib.util.spec_from_file_location('review_advance_test', Path(__file__).with_name('review_maintenance_advance.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('old,new', [('a'*40,'b'*40), ('1ba724dcb62ac389a72e41eecf40fea7aaca27e3','1ba724dcb62ac389a72e41eecf40fea7aaca27e3'), ('1ba724dcb62ac389a72e41eecf40fea7aaca27e3','bad')])
def test_fixed_profile_only(old, new):
    m = load()
    with pytest.raises(m.AdvanceError): m.profile(old, new)


def test_inspect_and_stale_authorization_do_not_write(tmp_path):
    m = load()
    events = []
    a = SimpleNamespace(record=tmp_path/'new', inspect=lambda: {'fixed': True},
                        prepare=lambda: events.append('prepare'))
    assert m.advance(a)['state'] == 'INSPECTED_NO_ADVANCE_AUTHORITY'
    for accepted, value in [(False, m.digest({'fixed': True})), (True, 'a'*64)]:
        with pytest.raises(m.AdvanceError): m.advance(a, accepted=accepted, evidence_sha256=value)
    assert events == []


def test_existing_intent_never_replays(tmp_path):
    m = load()
    record = tmp_path/'new'
    record.mkdir()
    a = SimpleNamespace(record=record, inspect=lambda: pytest.fail('must reject before inspecting'))
    with pytest.raises(m.AdvanceError): m.advance(a)


def test_ordinary_reset_gate_still_rejects_unknown(tmp_path):
    spec = importlib.util.spec_from_file_location('ordinary_bootstrap_test', Path(__file__).with_name('bootstrap_trusted_release.py'))
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    m = load()
    b.STATE = tmp_path
    root = tmp_path/m.TARGET/'review-resets'/m.OPERATION
    root.mkdir(parents=True)
    b.secure = lambda *a, **k: None
    b._inventory = lambda *a, **k: {}
    b._read_json = lambda p: {'sha':m.TARGET,'operation_id':m.OPERATION,'state':'STARTED' if p.name=='started.json' else 'NEEDS_OPERATOR'}
    with pytest.raises(b.BootstrapError): b._review_reset_evidence(m.TARGET)


def test_one_shot_intent_precedes_revocation_and_unknown_is_preserved(tmp_path):
    import json
    m = load()
    events = []
    class Adapter:
        record = tmp_path/'advance'
        def inspect(self): return {'fixed': True}
        def prepare(self): self.record.mkdir(); events.append('intent-directory')
        def write(self, name, value):
            events.append(name)
            (self.record/name).write_text(json.dumps(value))
        def revoke_once(self, evidence):
            assert (self.record/'intent.json').exists()
            events.append('revoke')
            return {'installation': 'synthetic'}
    a = Adapter()
    result = m.advance(a, accepted=True, evidence_sha256=m.digest(a.inspect()))
    assert events == ['intent-directory','intent.json','revoke','completed.json']
    assert result['state'] == m.READY and result['original_outcome'] == 'UNKNOWN'
    end = json.loads((a.record/'completed.json').read_text())
    assert end['reset_authorized'] is False
    with pytest.raises(m.AdvanceError): m.advance(a, accepted=True, evidence_sha256=m.digest(a.inspect()))


def test_failed_revocation_never_writes_completion_or_retries(tmp_path):
    m = load()
    record = tmp_path/'advance'
    def revoke(_): raise OSError('synthetic uncertain revocation')
    a = SimpleNamespace(record=record, inspect=lambda: {}, prepare=record.mkdir,
                        write=lambda name,value: (record/name).write_text(str(value)), revoke_once=revoke)
    with pytest.raises(OSError): m.advance(a, accepted=True, evidence_sha256=m.digest({}))
    assert (record/'intent.json').exists() and not (record/'completed.json').exists()
    with pytest.raises(m.AdvanceError): m.advance(a)


def saved_fixture(tmp_path, monkeypatch):
    import json
    import hashlib
    m = load()
    sha = 'b'*40
    root = tmp_path/'review-maintenance-advances'/m.TARGET
    root.mkdir(parents=True)
    deps = {'receipts': 'immutable'}
    evidence = {'kind':m.KIND,'old_sha':m.TARGET,'new_sha':sha,'operation_id':m.OPERATION,
                'original_outcome':'UNKNOWN','reset_authorized':False,'production':{},'dependencies':deps}
    receipt = 'c'*64
    intent = {'evidence':evidence,'evidence_sha256':m.digest(evidence),
              'accept_fixed_review_maintenance_advance':True,
              'receipt_sha256':hashlib.sha256(receipt.encode()).hexdigest()}
    end = {'state':m.READY,'original_outcome':'UNKNOWN','reset_authorized':False,
           'intent_sha256':m.digest(intent),'installation':{'synthetic':'hash'}}
    def write(name,value): (root/name).write_text(json.dumps(value))
    write('intent.json',intent);write('completed.json',end)
    def inventory(path,names):
        assert set(p.name for p in path.iterdir()) == names
        return {p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in path.iterdir()}
    b=SimpleNamespace(STATE=tmp_path,_inventory=inventory,_read_json=lambda p:json.loads(p.read_text()))
    monkeypatch.setattr(m,'dependencies',lambda *a:deps)
    return m,b,sha,receipt,intent,end,write


def test_historical_consumption_binds_bytes_without_live_account(tmp_path, monkeypatch):
    m,b,sha,receipt,intent,end,write=saved_fixture(tmp_path,monkeypatch)
    proof,evidence,installation=m.saved(b,Path('/source'),sha,receipt=receipt)
    assert m.saved(b,Path('/source'),sha,proof=proof)[0] == proof
    assert m.workspace(evidence)['original_outcome']=='UNKNOWN'
    write('completed.json',dict(end,reset_authorized=True))
    with pytest.raises(m.AdvanceError): m.saved(b,Path('/source'),sha,proof=proof)


@pytest.mark.parametrize('fault',['receipt','candidate','operation','accepted','digest','terminal','deps','proof'])
def test_saved_authority_or_receipt_drift_rejected(tmp_path,monkeypatch,fault):
    m,b,sha,receipt,intent,end,write=saved_fixture(tmp_path,monkeypatch)
    proof,_,_=m.saved(b,Path('/source'),sha,receipt=receipt)
    if fault=='receipt': receipt='d'*64
    elif fault=='candidate': sha='a'*40
    elif fault=='operation': intent['evidence']['operation_id']='a'*32
    elif fault=='accepted': intent['accept_fixed_review_maintenance_advance']=False
    elif fault=='digest': intent['evidence_sha256']='a'*64
    elif fault=='terminal': end['state']='SUCCEEDED'
    elif fault=='deps': monkeypatch.setattr(m,'dependencies',lambda *a:{'changed':True})
    elif fault=='proof': proof['new_sha']='a'*40
    write('intent.json',intent);write('completed.json',end)
    with pytest.raises(m.AdvanceError):
        m.saved(b,Path('/source'),sha,**({'proof':proof} if fault=='proof' else {'receipt':receipt}))


def dependency_fixture(tmp_path,monkeypatch):
    import json
    import hashlib
    m=load()
    sha='b'*40
    def sibling(name):
        spec=importlib.util.spec_from_file_location('dep_'+name,Path(__file__).with_name(name+'.py'))
        obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj
    core=sibling('review_demo_briefing_repair')
    readers=sibling('review_maintenance_retirement')
    ack=sibling('review_maintenance_acknowledgement')
    b=sibling('bootstrap_trusted_release')
    b.STATE=tmp_path
    b.secure=lambda *a,**k:None # synthetic ownership only; actual inventory/JSON/hash readers
    work=tmp_path/m.TARGET
    reset=work/'review-resets'/m.OPERATION
    reset.mkdir(parents=True,mode=0o700)
    (work/'review-resets').chmod(0o700);work.chmod(0o700)
    def put(path,value):
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        path.write_text(json.dumps(value));path.chmod(0o600)
    for name,state in [('started.json','STARTED'),('completed.json','SUCCEEDED')]:
        put(work/name,{'sha':m.TARGET,'state':state})
    for name,state in [('started.json','STARTED'),('completed.json','NEEDS_OPERATOR')]:
        put(reset/name,{'sha':m.TARGET,'operation_id':m.OPERATION,'state':state})
    maintenance=tmp_path/'review-maintenance'/m.TARGET
    pair={'operator_sha':ack.ORIGINAL_OPERATOR,'target_sha':m.TARGET,'operation_id':m.OPERATION,
          'ci':{}, 'production_identity':[1,2,3,4,5,6], 'production_sha256':'a'*64,'environment_sha256':'b'*64,'state':'STARTED'}
    # Exact real schema checked below; no database object is even provided.
    put(maintenance/'started.json',pair)
    put(maintenance/'completed.json',{**pair,'state':'NEEDS_OPERATOR'})
    recon=tmp_path/'review-maintenance-ack-reconciliations'/m.TARGET
    recon.mkdir(parents=True)
    receipt={'completed_sha256':'a'*64}
    briefing=SimpleNamespace(acknowledgement_evidence=lambda *a, **kw:receipt)
    monkeypatch.setattr(m,'modules',lambda *a:(ack,readers,briefing,core))
    evidence={'target_sha':m.TARGET,'failed_operation':m.OPERATION,'fixture_sha256':core.FIXTURE_SHA256,
              'acknowledgement_sha256':'a'*64,'database_snapshot_sha256':'b'*64,
              'production_evidence_sha256':'c'*64,'health_snapshot_sha256':'d'*64,
              'demo_user_id':44,'action':core.ACTION}
    root=tmp_path/'review-demo-briefing-repairs'/m.TARGET
    intent={'operator_sha':sha,'accept_demo_briefing_repair':True,'evidence':evidence,'evidence_sha256':m.digest(evidence)}
    terminal={'state':'BRIEFING_REPAIRED_ONLY','evidence_sha256':m.digest(evidence),
              'result':{'state':'VERIFIED_BRIEFING_ONLY','before_sha256':'b'*64,'after_sha256':'e'*64},
              'original_outcome':'UNKNOWN','reset_authorized':False,'release_unblocked':False,'retry_authorized':False}
    put(root/'intent.json',intent)
    put(root/'database-started.json',{'state':'DATABASE_ATTEMPT_STARTED','operator_sha':sha,'evidence_sha256':m.digest(evidence)})
    put(root/'completed.json',terminal)
    return m,b,sha,root,terminal,put,reset


def test_actual_dependency_receipt_and_original_workspace_readers(tmp_path,monkeypatch):
    m,b,sha,root,terminal,put,reset=dependency_fixture(tmp_path,monkeypatch)
    result=m.dependencies(b,Path('/source'),sha)
    assert result['original']['operations'][m.OPERATION]['completed.json']['sha256']
    assert result['briefing']['completed.json']['sha256']
    before=(reset/'completed.json').read_bytes()
    assert m.dependencies(b,Path('/source'),sha)==result
    assert (reset/'completed.json').read_bytes()==before
    put(root/'completed.json',{**terminal,'release_unblocked':True})
    with pytest.raises(m.AdvanceError):m.dependencies(b,Path('/source'),sha)


def test_real_rotation_and_retired_history_consume_exclusive_fixed_proof(tmp_path,monkeypatch):
    import json
    import hashlib
    import sys
    m=load()
    spec=importlib.util.spec_from_file_location('bootstrap_fixture_support',Path(__file__).with_name('test_bootstrap_trusted_release.py'))
    support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
    monkeypatch.setattr(support,'SHA',m.TARGET)
    b,calls=support.rotation_fixture(monkeypatch,tmp_path)
    monkeypatch.setitem(sys.modules,b.__name__,b)
    monkeypatch.setattr(b,'_review_advance_module',lambda:m)
    checks=[]
    monkeypatch.setattr(m,'verify_live',lambda *args:checks.append('live'))
    # Live OS proof has dedicated ack tests; here exercise the actual bootstrap,
    # saved receipt validation, retirement intent and historical consumer.
    deps={'synthetic_original':'unknown'}
    monkeypatch.setattr(m,'dependencies',lambda *args:deps)
    sha=support.NEW_SHA
    reset=b.STATE/m.TARGET/'review-resets'/m.OPERATION
    reset.mkdir(parents=True,mode=0o700);reset.parent.chmod(0o700)
    for name,state in [('started.json','STARTED'),('completed.json','NEEDS_OPERATOR')]:
        p=reset/name;p.write_text(json.dumps({'sha':m.TARGET,'operation_id':m.OPERATION,'state':state}));p.chmod(0o600)
    original={p.name:p.read_bytes() for p in reset.iterdir()}
    evidence={'kind':m.KIND,'old_sha':m.TARGET,'new_sha':sha,'operation_id':m.OPERATION,
              'original_outcome':'UNKNOWN','reset_authorized':False,'production':{},'dependencies':deps}
    receipt='c'*64
    intent={'evidence':evidence,'evidence_sha256':m.digest(evidence),'accept_fixed_review_maintenance_advance':True,
            'receipt_sha256':hashlib.sha256(receipt.encode()).hexdigest()}
    installation=b._installation_evidence(m.TARGET,b.CONFIG,b.INSTALLED.parent)
    end={'state':m.READY,'original_outcome':'UNKNOWN','reset_authorized':False,
         'intent_sha256':m.digest(intent),'installation':installation}
    record=b.STATE/'review-maintenance-advances'/m.TARGET
    record.mkdir(parents=True,mode=0o700);record.parent.chmod(0o700)
    for name,obj in [('intent.json',intent),('completed.json',end)]:
        p=record/name;p.write_text(json.dumps(obj));p.chmod(0o600)
    with pytest.raises(b.BootstrapError): b.rotate(m.TARGET,sha,0,support.PUBLIC)
    assert not (b.STATE/'retired'/m.TARGET).exists()
    result=b.rotate(m.TARGET,sha,0,support.PUBLIC,review_advance_receipt=receipt)
    assert result['state']=='INSTALLED'
    retired=b._retired_history()[m.TARGET]
    assert retired['workspace']['original_outcome']=='UNKNOWN'
    assert retired['review_maintenance_advance']['new_sha']==sha
    assert {p.name:p.read_bytes() for p in reset.iterdir()}==original
    assert len(checks)>=3
    with pytest.raises(b.BootstrapError): b._review_reset_evidence(m.TARGET)
    # History never reaches the live proof, even after production has moved.
    monkeypatch.setattr(m,'verify_live',lambda *a:pytest.fail('historical live read'))
    assert b._retired_history()[m.TARGET]==retired


@pytest.mark.parametrize('fault',[None,'postcheck','unlink'])
def test_actual_revoke_once_preserves_unrelated_authorization_and_blocks_retry(tmp_path,monkeypatch,fault):
    import json
    m=load()
    spec=importlib.util.spec_from_file_location('advance_revoke_fixture',Path(__file__).with_name('test_bootstrap_trusted_release.py'))
    support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
    b,_=support.fixture(monkeypatch,tmp_path)
    b.install(m.TARGET,200,support.PUBLIC)
    source,server=b.reviewed_source('b'*40)
    b.canonical_source=lambda sha:source
    b._assert_idle=lambda:None
    deps={'original':'UNKNOWN'}
    monkeypatch.setattr(m,'dependencies',lambda *a:deps)
    original={'immutable':'original markers'}
    lease={'state':'ABSENT_NOT_AUTHORITY'}
    services={'stable':True}
    ssh={'fixed':'chatlog'}
    observed={'original':original,'lease':lease,'services':services,'ssh_observation':ssh}
    events=[]
    class Guard:
        ssh_observation=ssh
        c=SimpleNamespace(_private_directory=lambda *a:None)
        r=SimpleNamespace(_http_probes=lambda:events.append('health'))
        def inspect(self):
            assert (b.CONFIG/'loopback.key').exists()
            assert support.PUBLIC.split()[1] in b.AUTHORIZED.read_text()
            return observed
        def _quiescent(self):events.append('quiescent')
        def _base(self):return original
        def _lease(self):return lease
        def _services(self):
            if fault=='postcheck': raise RuntimeError('synthetic health changed')
            return services
    monkeypatch.setattr(m,'modules',lambda *a:(SimpleNamespace(make_adapter=lambda *a:Guard()),None,None,None))
    adapter=m.make_adapter(b,source,server,'b'*40,lambda:events.append('locks'))
    snapshot=adapter.inspect()
    raw=b.AUTHORIZED.read_bytes()
    expected=b'\n'.join(line for line in raw.split(b'\n') if support.PUBLIC.split()[1].encode() not in line and support.LOOPBACK.split()[1].encode() not in line)
    # The unrelated synthetic line models the preserved chatlog identity.
    original_unlink=Path.unlink
    def unlink(path,*a,**k):
        if fault=='unlink' and path==b.CONFIG/'loopback.key': raise OSError('synthetic unlink failure')
        return original_unlink(path,*a,**k)
    monkeypatch.setattr(Path,'unlink',unlink)
    if fault:
        with pytest.raises((RuntimeError,OSError)):
            m.advance(adapter,accepted=True,evidence_sha256=m.digest(snapshot))
        assert (adapter.record/'intent.json').exists()
        assert not (adapter.record/'completed.json').exists()
    else:
        result=m.advance(adapter,accepted=True,evidence_sha256=m.digest(snapshot))
        assert result['state']==m.READY
        assert not (b.CONFIG/'loopback.key').exists()
        end=json.loads((adapter.record/'completed.json').read_text())
        assert end['installation']==b._installation_evidence(m.TARGET,b.CONFIG,b.INSTALLED.parent)
        assert events.count('health')==1
    assert b.AUTHORIZED.read_bytes()==expected
    with pytest.raises(m.AdvanceError):m.advance(adapter)


def test_successor_advance_rejects_missing_or_changed_intent_binding(tmp_path,monkeypatch):
    m,b,sha,root,terminal,put,reset=dependency_fixture(tmp_path,monkeypatch)
    original=m.modules
    ack,readers,briefing,core=original(b,Path('/source'))
    receipt=briefing.acknowledgement_evidence()
    receipt['succession']={'predecessor_operator_sha':'2162488aedb9337690a9acc51d5e8f9ac28f4aec','operator_sha':sha}
    with pytest.raises(m.AdvanceError):m.dependencies(b,Path('/source'),sha)
    intent=b._read_json(root/'intent.json')
    put(root/'intent.json',{**intent,'reconciliation_succession':receipt['succession']})
    assert m.dependencies(b,Path('/source'),sha)['reconciliation']['succession']==receipt['succession']
    put(root/'intent.json',{**intent,'reconciliation_succession':{'operator_sha':'f'*40}})
    with pytest.raises(m.AdvanceError):m.dependencies(b,Path('/source'),sha)
