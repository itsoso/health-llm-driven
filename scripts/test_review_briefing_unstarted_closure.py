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
