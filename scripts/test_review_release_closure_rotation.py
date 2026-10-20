"""Real bootstrap rotation consumes the distinct release-only closure proof."""
import importlib.util
import json
from pathlib import Path
import pytest


def load(name):
    spec=importlib.util.spec_from_file_location('rotation_'+name,Path(__file__).with_name(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def rotation_fixture(tmp_path,monkeypatch):
    import json
    import hashlib
    import sys
    m=load('review_maintenance_release_closure')
    spec=importlib.util.spec_from_file_location('bootstrap_fixture_support',Path(__file__).with_name('test_bootstrap_trusted_release.py'))
    support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
    monkeypatch.setattr(support,'SHA',m.TARGET)
    b,calls=support.rotation_fixture(monkeypatch,tmp_path)
    monkeypatch.setitem(sys.modules,b.__name__,b)
    monkeypatch.setattr(b,'_review_release_closure_module',lambda:m)
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
    intent={'evidence':evidence,'evidence_sha256':m.digest(evidence),'accept_fixed_maintenance_release_closure':True,'accept_unknown':True,'without_demo':True,
            'receipt_sha256':hashlib.sha256(receipt.encode()).hexdigest()}
    installation=b._installation_evidence(m.TARGET,b.CONFIG,b.INSTALLED.parent)
    end={'state':m.READY,'original_outcome':'UNKNOWN','reset_authorized':False,
         'retry_authorized':False,'demo_verified':False,'intent_sha256':m.digest(intent),'installation':installation}
    record=b.STATE/'review-maintenance-release-closures'/m.TARGET
    record.mkdir(parents=True,mode=0o700);record.parent.chmod(0o700)
    for name,obj in [('intent.json',intent),('completed.json',end)]:
        p=record/name;p.write_text(json.dumps(obj));p.chmod(0o600)
    return m,b,support,sha,receipt,reset,original,checks,record,intent,end


def test_real_rotate_and_history(tmp_path,monkeypatch):
    m,b,support,sha,receipt,reset,original,checks,record,intent,end=rotation_fixture(tmp_path,monkeypatch)
    with pytest.raises(b.BootstrapError): b.rotate(m.TARGET,sha,0,support.PUBLIC)
    assert not (b.STATE/'retired'/m.TARGET).exists()
    result=b.rotate(m.TARGET,sha,0,support.PUBLIC,review_release_closure_receipt=receipt)
    assert result['state']=='INSTALLED'
    retired=b._retired_history()[m.TARGET]
    assert retired['workspace']['original_outcome']=='UNKNOWN'
    assert retired['review_maintenance_release_closure']['new_sha']==sha
    assert {p.name:p.read_bytes() for p in reset.iterdir()}==original
    assert len(checks)>=3
    with pytest.raises(b.BootstrapError): b._review_reset_evidence(m.TARGET)
    # History never reaches the live proof, even after production has moved.
    monkeypatch.setattr(m,'verify_live',lambda *a:pytest.fail('historical live read'))
    assert b._retired_history()[m.TARGET]==retired




@pytest.mark.parametrize('fault',['candidate','receipt','missing_completion','mixed_advance','mixed_recovery','mixed_native','accepted_unknown','without_demo','demo_claim'])
def test_rotate_rejects_partial_or_mixed_authority_before_retirement(tmp_path,monkeypatch,fault):
    m,b,support,sha,receipt,reset,original,checks,record,intent,end=rotation_fixture(tmp_path,monkeypatch)
    kwargs={'review_release_closure_receipt':receipt}
    if fault=='candidate':sha='e'*40
    elif fault=='receipt':kwargs['review_release_closure_receipt']='d'*64
    elif fault=='missing_completion':(record/'completed.json').unlink()
    elif fault=='mixed_advance':kwargs['review_advance_receipt']='a'*64
    elif fault=='mixed_recovery':kwargs['recovery_receipt']='a'*64
    elif fault=='mixed_native':kwargs['finalized_production_sha']='a'*40
    elif fault=='accepted_unknown':intent['accept_unknown']=False
    elif fault=='without_demo':intent['without_demo']=False
    elif fault=='demo_claim':end['demo_verified']=True
    if fault in ('accepted_unknown','without_demo','demo_claim'):
        end['intent_sha256']=m.digest(intent)
        (record/'intent.json').write_text(json.dumps(intent))
        (record/'completed.json').write_text(json.dumps(end))
    with pytest.raises((b.BootstrapError,m.AdvanceError)):
        b.rotate(m.TARGET,sha,0,support.PUBLIC,**kwargs)
    assert not (b.STATE/'retired'/m.TARGET).exists()
    assert {p.name:p.read_bytes() for p in reset.iterdir()}==original
    assert b._read_json(b.CONFIG/'authorized-release.json')['sha']==m.TARGET


@pytest.mark.parametrize('fault',['mixed','missing_closure','changed_closure','changed_candidate'])
def test_retired_history_revalidates_distinct_closure_chain(tmp_path,monkeypatch,fault):
    m,b,support,sha,receipt,reset,original,checks,record,intent,end=rotation_fixture(tmp_path,monkeypatch)
    b.rotate(m.TARGET,sha,0,support.PUBLIC,review_release_closure_receipt=receipt)
    root=b.STATE/'retired'/m.TARGET
    p=root/'intent.json'
    retired=json.loads(p.read_text())
    if fault=='mixed':
        retired['review_maintenance_advance']=retired['review_maintenance_release_closure']
        p.write_text(json.dumps(retired))
    elif fault=='missing_closure':(record/'completed.json').unlink()
    elif fault=='changed_closure':
        end['reset_authorized']=True;(record/'completed.json').write_text(json.dumps(end))
    else:
        retired['review_maintenance_release_closure']['new_sha']='e'*40
        p.write_text(json.dumps(retired))
    with pytest.raises((b.BootstrapError,m.AdvanceError)):
        b._retired_history()
    assert {p.name:p.read_bytes() for p in reset.iterdir()}==original
