"""Synthetic tests: accepted UNKNOWN retirement never repairs demo data."""
import importlib.util
import json
from pathlib import Path
import pytest
from types import SimpleNamespace


def load():
    spec=importlib.util.spec_from_file_location('release_closure_test',Path(__file__).with_name('review_maintenance_release_closure.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def adapter(tmp_path, fail=False):
    class Adapter:
        record=tmp_path/'closure'
        def inspect(self): return {'fixed': True}
        def prepare(self): self.record.mkdir()
        def write(self,name,value): (self.record/name).write_text(json.dumps(value))
        def revoke_once(self,evidence):
            assert (self.record/'intent.json').exists()
            if fail: raise OSError('uncertain')
            return {'synthetic':True}
    return Adapter()


@pytest.mark.parametrize('unknown,without',[(False,False),(True,False),(False,True)])
def test_both_explicit_acceptances_required(tmp_path,unknown,without):
    m=load();a=adapter(tmp_path)
    with pytest.raises(m.AdvanceError):
        m.advance(a,accepted=True,accept_unknown=unknown,without_demo=without,evidence_sha256=m.digest(a.inspect()))
    assert not a.record.exists()


def test_success_never_claims_demo_or_reset_success(tmp_path):
    m=load();a=adapter(tmp_path)
    result=m.advance(a,accepted=True,accept_unknown=True,without_demo=True,evidence_sha256=m.digest(a.inspect()))
    assert result['state']==m.READY
    intent=json.loads((a.record/'intent.json').read_text())
    end=json.loads((a.record/'completed.json').read_text())
    assert intent['accept_unknown'] is True and intent['without_demo'] is True
    assert end['original_outcome']=='UNKNOWN' and end['demo_verified'] is False
    assert end['reset_authorized'] is False and end['retry_authorized'] is False
    with pytest.raises(m.AdvanceError): m.advance(a)


def test_failure_preserves_intent_no_retry(tmp_path):
    m=load();a=adapter(tmp_path,True)
    with pytest.raises(OSError):m.advance(a,accepted=True,accept_unknown=True,without_demo=True,evidence_sha256=m.digest(a.inspect()))
    assert (a.record/'intent.json').exists() and not (a.record/'completed.json').exists()
    with pytest.raises(m.AdvanceError):m.advance(a)


def test_inspect_does_not_mutate(tmp_path):
    m=load();a=adapter(tmp_path)
    assert m.advance(a)['state']=='INSPECTED_NO_ADVANCE_AUTHORITY'
    assert not a.record.exists()


def saved_fixture(tmp_path, monkeypatch):
    import json
    import hashlib
    m = load()
    sha = 'b'*40
    root = tmp_path/'review-maintenance-release-closures'/m.TARGET
    root.mkdir(parents=True)
    deps = {'receipts': 'immutable'}
    evidence = {'kind':m.KIND,'old_sha':m.TARGET,'new_sha':sha,'operation_id':m.OPERATION,
                'original_outcome':'UNKNOWN','reset_authorized':False,'production':{},'dependencies':deps}
    receipt = 'c'*64
    intent = {'evidence':evidence,'evidence_sha256':m.digest(evidence),
              'accept_fixed_maintenance_release_closure':True,'accept_unknown':True,'without_demo':True,
              'receipt_sha256':hashlib.sha256(receipt.encode()).hexdigest()}
    end = {'state':m.READY,'original_outcome':'UNKNOWN','reset_authorized':False,
           'retry_authorized':False,'demo_verified':False,'intent_sha256':m.digest(intent),'installation':{'synthetic':'hash'}}
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
    elif fault=='accepted': intent['accept_fixed_maintenance_release_closure']=False
    elif fault=='digest': intent['evidence_sha256']='a'*64
    elif fault=='terminal': end['state']='SUCCEEDED'
    elif fault=='deps': monkeypatch.setattr(m,'dependencies',lambda *a:{'changed':True})
    elif fault=='proof': proof['new_sha']='a'*40
    write('intent.json',intent);write('completed.json',end)
    with pytest.raises(m.AdvanceError):
        m.saved(b,Path('/source'),sha,**({'proof':proof} if fault=='proof' else {'receipt':receipt}))




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
            m.advance(adapter,accepted=True,accept_unknown=True,without_demo=True,evidence_sha256=m.digest(snapshot))
        assert (adapter.record/'intent.json').exists()
        assert not (adapter.record/'completed.json').exists()
    else:
        result=m.advance(adapter,accepted=True,accept_unknown=True,without_demo=True,evidence_sha256=m.digest(snapshot))
        assert result['state']==m.READY
        assert not (b.CONFIG/'loopback.key').exists()
        end=json.loads((adapter.record/'completed.json').read_text())
        assert end['installation']==b._installation_evidence(m.TARGET,b.CONFIG,b.INSTALLED.parent)
        assert events.count('health')==1
    assert b.AUTHORIZED.read_bytes()==expected
    with pytest.raises(m.AdvanceError):m.advance(adapter)




@pytest.mark.parametrize('fault',[None,'marker','completed','intent','history','reconciliation'])
def test_dependencies_use_real_successor_reader_and_historical_operator(tmp_path,monkeypatch,fault):
    spec=importlib.util.spec_from_file_location('closure_support',Path(__file__).with_name('test_review_briefing_unstarted_closure.py'))
    support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
    closure,b,_,root=support.successor_fixture(tmp_path,monkeypatch)
    m=load();candidate='d'*40
    recon=b.STATE/'review-maintenance-ack-reconciliations'/m.TARGET
    recon.mkdir(parents=True)
    maintenance=b.STATE/'review-maintenance'/m.TARGET
    maintenance.mkdir(parents=True,mode=0o700)
    for name in ['started.json','completed.json']:
        (maintenance/name).write_text('{}');(maintenance/name).chmod(0o600)
    calls=[]
    def acknowledgement(*args,**kwargs):
        assert args[3]==closure.SUCCESSOR_OPERATOR and args[3]!=candidate
        assert kwargs=={'allow_fixed_successor':True}
        calls.append('history')
        if fault=='reconciliation':raise ValueError('reconciliation changed')
        return {'fixed':'reconciled'}
    monkeypatch.setattr(m,'modules',lambda *a:(SimpleNamespace(validate_failed_pair=lambda *a:None),
        SimpleNamespace(original_workspace=lambda *a:{'unknown':'accepted'}),
        SimpleNamespace(acknowledgement_evidence=acknowledgement),None))
    monkeypatch.setattr(m,'load',lambda *a:closure)
    if fault in ('marker','completed'):
        (root/('database-started.json' if fault=='marker' else 'completed.json')).write_text('{}')
    elif fault=='intent':(root/'intent.json').write_text('{}')
    elif fault=='history':monkeypatch.setattr(closure,'successor_history',lambda b:{'closure':{},'source_hashes':{}})
    if fault:
        with pytest.raises((closure.ClosureError,b.BootstrapError,ValueError)):
            m.dependencies(b,Path('/synthetic'),candidate)
    else:
        result=m.dependencies(b,Path('/synthetic'),candidate)
        assert result['successor_no_entry']==closure.successor_evidence(b)
        assert calls==['history']
        assert not (b.STATE/'review-demo-briefing-successor-closures').exists()


@pytest.mark.parametrize('field',['accept_unknown','without_demo'])
def test_saved_rejects_missing_explicit_scope(tmp_path,monkeypatch,field):
    m,b,sha,receipt,intent,end,write=saved_fixture(tmp_path,monkeypatch)
    intent[field]=False;end['intent_sha256']=m.digest(intent)
    write('intent.json',intent);write('completed.json',end)
    with pytest.raises(m.AdvanceError):m.saved(b,Path('/source'),sha,receipt=receipt)


@pytest.mark.parametrize('drift',['production','dependencies'])
def test_inspect_rejects_live_or_dependency_drift(tmp_path,monkeypatch,drift):
    m=load();counts={'production':0,'dependencies':0}
    def observe(kind):
        counts[kind]+=1
        return {'version':counts[kind] if kind==drift else 1}
    monkeypatch.setattr(m,'modules',lambda *a:(SimpleNamespace(make_adapter=lambda *a:
        SimpleNamespace(inspect=lambda:observe('production'))),None,None,None))
    monkeypatch.setattr(m,'dependencies',lambda *a:observe('dependencies'))
    b=SimpleNamespace(STATE=tmp_path,_assert_idle=lambda:None)
    a=m.make_adapter(b,Path('/source'),None,'b'*40,lambda:None)
    with pytest.raises(m.AdvanceError):a.inspect()
    assert not a.record.exists()


def test_stale_digest_does_not_prepare(tmp_path):
    m=load();a=adapter(tmp_path)
    with pytest.raises(m.AdvanceError):
        m.advance(a,accepted=True,accept_unknown=True,without_demo=True,evidence_sha256='a'*64)
    assert not a.record.exists()
