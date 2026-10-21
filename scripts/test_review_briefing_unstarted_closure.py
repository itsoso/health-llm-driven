"""Synthetic tests; no production data or operation execution."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest


def load():
    p=Path(__file__).with_name('review_briefing_unstarted_closure.py')
    s=importlib.util.spec_from_file_location('unstarted_test',p)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def test_inspect_has_no_authority_and_stale_digest_cannot_write(tmp_path):
    m=load();events=[]
    a=SimpleNamespace(record=tmp_path/'closure',inspect=lambda:{'synthetic':True},prepare=lambda:events.append('write'))
    assert m.close(a)['state']=='INSPECTED_NO_CLOSURE_AUTHORITY'
    with pytest.raises(m.ClosureError):m.close(a,accepted=True,evidence_sha256='a'*64)
    assert events==[]


def test_closure_is_audit_only_and_never_replays(tmp_path):
    import json
    m=load();record=tmp_path/'closure'
    a=SimpleNamespace(record=record,inspect=lambda:{'synthetic':True},prepare=record.mkdir,
      write=lambda name,v:(record/name).write_text(json.dumps(v)))
    result=m.close(a,accepted=True,evidence_sha256=m.digest(a.inspect()))
    assert result['state']=='CANONICAL_WRITE_NOT_ENTERED'
    assert result['original_outcome']=='UNKNOWN'
    assert all(v is False for v in result['authority'].values())
    with pytest.raises(m.ClosureError):m.close(a,accepted=True,evidence_sha256=m.digest(a.inspect()))


def closure_fixture(tmp_path,monkeypatch):
    import json,hashlib
    m=load()
    def sibling(name):
        spec=importlib.util.spec_from_file_location('fixture_'+name,Path(__file__).with_name(name+'.py'))
        value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
    b=sibling('bootstrap_trusted_release');readers=sibling('review_maintenance_retirement')
    b.STATE=tmp_path;monkeypatch.setattr(b,'secure',lambda *a,**k:None)
    original=tmp_path/'review-demo-briefing-repairs'/m.TARGET
    original.mkdir(parents=True,mode=0o700)
    raw=json.dumps({'operator_sha':m.PREDECESSOR,'accept_demo_briefing_repair':True}).encode()
    (original/'intent.json').write_bytes(raw);(original/'intent.json').chmod(0o600)
    monkeypatch.setattr(m,'INTENT_SHA256',hashlib.sha256(raw).hexdigest())
    source=tmp_path/'canonical';(source/'scripts').mkdir(parents=True)
    hashes={}
    for name in m.SOURCE_HASHES:
        (source/'scripts'/name).write_text('synthetic source '+name)
        hashes[name]=hashlib.sha256((source/'scripts'/name).read_bytes()).hexdigest()
    monkeypatch.setattr(m,'SOURCE_HASHES',hashes)
    monkeypatch.setattr(b,'canonical_source',lambda sha:source)
    ack=SimpleNamespace(make_adapter=lambda *a:SimpleNamespace(inspect=lambda:{'stable':'production'}))
    briefing=SimpleNamespace(OPERATION='a'*32,acknowledgement_evidence=lambda *a,**k:{'receipt':'fixed'})
    sha='d'*40;a=m.make_adapter(source,b,object(),readers,ack,briefing,sha,lambda:None)
    return m,b,a,original,source,sha


def test_real_adapter_closes_sibling_only_and_reader_binds_every_original_byte(tmp_path,monkeypatch):
    m,b,a,original,source,sha=closure_fixture(tmp_path,monkeypatch)
    before=m.predecessor(b)
    observed=m.close(a);assert not a.record.exists()
    m.close(a,accepted=True,evidence_sha256=observed['evidence_sha256'])
    assert m.closed_evidence(b,sha)['predecessor']==before
    assert m.predecessor(b)==before and {p.name for p in original.iterdir()}=={'intent.json'}
    with pytest.raises(m.ClosureError):m.closed_evidence(b,'e'*40)


@pytest.mark.parametrize('fault',['database_started','completed','different_intent','source','successor','evidence_drift'])
def test_closure_refuses_uncertain_or_changed_original(tmp_path,monkeypatch,fault):
    m,b,a,original,source,sha=closure_fixture(tmp_path,monkeypatch)
    old=a.inspect()
    if fault=='database_started':(original/'database-started.json').write_text('{}')
    elif fault=='completed':(original/'completed.json').write_text('{}')
    elif fault=='different_intent':(original/'intent.json').write_text('{}')
    elif fault=='source':next((source/'scripts').iterdir()).write_text('changed')
    elif fault=='successor':m.successor_path(b).mkdir(parents=True)
    else:
        old_inspect=a.inspect;calls=[]
        def changed():
            value=old_inspect();calls.append(1)
            return value if len(calls)==1 else {**value,'changed':True}
        a.inspect=changed
    with pytest.raises((m.ClosureError,b.BootstrapError)):
        m.close(a,accepted=True,evidence_sha256=m.digest(old))
    assert not (a.record/'completed.json').exists()


@pytest.mark.parametrize('fault',['terminal','authority','digest','missing_completion','old_identity'])
def test_closed_reader_refuses_terminal_only_or_drift(tmp_path,monkeypatch,fault):
    import json
    m,b,a,original,source,sha=closure_fixture(tmp_path,monkeypatch)
    m.close(a,accepted=True,evidence_sha256=m.digest(a.inspect()))
    path=a.record/'completed.json';value=json.loads(path.read_text())
    if fault=='terminal':value['state']='SUCCEEDED'
    elif fault=='authority':value['authority']['new_attempt']=True
    elif fault=='digest':value['evidence_sha256']='a'*64
    elif fault=='missing_completion':path.unlink()
    elif fault=='old_identity':
        raw=(original/'intent.json').read_bytes();(original/'intent.json').unlink();(original/'intent.json').write_bytes(raw)
    if fault not in ('missing_completion','old_identity'):path.write_text(json.dumps(value))
    with pytest.raises((m.ClosureError,b.BootstrapError)):m.closed_evidence(b,sha)


def test_cli_rejects_noncanonical_before_loading_any_source(monkeypatch):
    import sys
    m=load();monkeypatch.setattr(sys,'argv',['closure','--sha','d'*40])
    monkeypatch.setattr(m.importlib.util,'spec_from_file_location',lambda *a:pytest.fail('must reject before loading'))
    assert m.main()==1


def successor_fixture(tmp_path, monkeypatch):
    import hashlib, json
    m,b,_,original,source,sha=closure_fixture(tmp_path,monkeypatch)
    root=m.successor_path(b);root.mkdir(parents=True,mode=0o700)
    chain={'fixed':'prior_closed'}
    raw=json.dumps({'operator_sha':m.SUCCESSOR_OPERATOR,
        'accept_demo_briefing_repair':True,'accept_successor_briefing_attempt':True,
        'attempt_profile':m.ATTEMPT,'unstarted_closure':chain,
        'evidence':{'synthetic':True},'evidence_sha256':m.digest({'synthetic':True})}).encode()
    (root/'intent.json').write_bytes(raw);(root/'intent.json').chmod(0o600)
    monkeypatch.setattr(m,'SUCCESSOR_INTENT_SHA256',hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(m,'successor_history',lambda b:{'closure':chain,'source_hashes':{'fixed':'source'}})
    readers=SimpleNamespace(sync=lambda p:None,write_json=lambda p,v:p.write_text(json.dumps(v)))
    ack=SimpleNamespace(make_adapter=lambda *a:SimpleNamespace(inspect=lambda:{'production':'stable'}))
    briefing=SimpleNamespace(OPERATION='a'*32,acknowledgement_evidence=lambda *a,**k:{'fixed':'receipt'})
    a=m.make_successor_adapter(source,b,object(),readers,ack,briefing,sha,lambda:None)
    return m,b,a,root


def test_successor_audit_is_separate_and_does_not_authorize_retry(tmp_path,monkeypatch):
    m,b,a,root=successor_fixture(tmp_path,monkeypatch)
    before=(root/'intent.json').read_bytes()
    evidence=m.close(a)
    assert not a.record.exists()
    result=m.close(a,accepted=True,evidence_sha256=evidence['evidence_sha256'])
    assert result['state']=='CANONICAL_WRITE_NOT_ENTERED'
    assert all(v is False for v in result['authority'].values())
    assert a.record==b.STATE/'review-demo-briefing-successor-closures'/m.TARGET/m.ATTEMPT
    assert (root/'intent.json').read_bytes()==before
    assert {p.name for p in root.iterdir()}=={'intent.json'}
    with pytest.raises(m.ClosureError):m.close(a)


@pytest.mark.parametrize('fault',['marker','complete','intent','chain','drift'])
def test_successor_audit_rejects_uncertain_state(tmp_path,monkeypatch,fault):
    m,b,a,root=successor_fixture(tmp_path,monkeypatch)
    observed=m.close(a)
    if fault=='marker':(root/'database-started.json').write_text('{}')
    elif fault=='complete':(root/'completed.json').write_text('{}')
    elif fault=='intent':(root/'intent.json').write_text('{}')
    elif fault=='chain':monkeypatch.setattr(m,'successor_history',lambda b:{'closure':{},'source_hashes':{}})
    else:
        original=a.inspect;calls=[]
        def drift():
            result=original();calls.append(1)
            return result if len(calls)==1 else {**result,'changed':True}
        a.inspect=drift
    with pytest.raises((m.ClosureError,b.BootstrapError)):
        m.close(a,accepted=True,evidence_sha256=observed['evidence_sha256'])
    assert not (a.record/'completed.json').exists()


@pytest.mark.parametrize('fault',['none','source','closure'])
def test_successor_history_loads_only_pinned_file_consumer(tmp_path,monkeypatch,fault):
    import hashlib
    m=load();source=tmp_path/'source';(source/'scripts').mkdir(parents=True)
    code="def closed_evidence(b, sha):\n    assert sha == '"+m.SUCCESSOR_OPERATOR+"'\n    return {'fixed':True}\n"
    hashes={}
    for name in m.SUCCESSOR_SOURCE_HASHES:
        p=source/'scripts'/name;p.write_text(code if name=='review_briefing_unstarted_closure.py' else '# no execution\n')
        hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    monkeypatch.setattr(m,'SUCCESSOR_SOURCE_HASHES',hashes)
    b=SimpleNamespace(canonical_source=lambda sha:source,secure=lambda p:None)
    if fault=='source':(source/'scripts/trusted_review_briefing_repair.py').write_text('raise RuntimeError()')
    elif fault=='closure':(source/'scripts/review_briefing_unstarted_closure.py').write_text('raise RuntimeError()')
    if fault!='none':
        with pytest.raises(m.ClosureError):m.successor_history(b)
    else:assert m.successor_history(b)=={'closure':{'fixed':True},'source_hashes':hashes}
