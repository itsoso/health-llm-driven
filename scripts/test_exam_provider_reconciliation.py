"""The one completed external provider receipt is data, never replay authority."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


def module(name='exam_provider_reconciliation'):
    path=Path(__file__).with_name(name+'.py')
    spec=importlib.util.spec_from_file_location('provider_test_'+name,path)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def meta(directory=False):
    result={'dev':1,'ino':2,'uid':0,'gid':0,'mode':0o700 if directory else 0o600}
    if not directory: result['sha256']='a'*64
    return result


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    m=module(); io=module('exam_recovery_credential')
    parent=tmp_path/'refresh'; parent.mkdir(); audit=parent/('exam-'+m.PUBLISHER); audit.mkdir(mode=0o700)
    source=tmp_path/'source'; (source/'scripts').mkdir(parents=True)
    provider=source/'scripts/exam_provider_refresh.py'; provider.write_bytes(b'raise AssertionError("must never execute")\n'); provider.chmod(0o644)
    lease={key:meta(key=='lease') for key in m.LEASE_KEYS}
    workspace={key:(sorted(m.WORKSPACE_INVENTORY) if key=='inventory' else meta(key=='directory')) for key in m.WORKSPACE_KEYS}
    intent={**m.SAFE_FIELDS,'state':'REFRESH_INTENT','lease':lease,'workspace':workspace}
    for name,state in [('intent.json','REFRESH_INTENT'),('completed.json','CREDENTIAL_REFRESHED')]:
        path=audit/name; path.write_text(json.dumps({**intent,'state':state},sort_keys=True)); path.chmod(0o600)
    monkeypatch.setattr(m,'REFRESH_ROOT',parent)
    monkeypatch.setattr(m,'PINS',{name:hashlib.sha256((audit/name).read_bytes()).hexdigest() for name in ('intent.json','completed.json')})
    monkeypatch.setattr(m,'PIN_METADATA',{name:m.metadata((audit/name).lstat()) for name in ('.','intent.json','completed.json')})
    monkeypatch.setattr(m,'SOURCE_PIN',hashlib.sha256(provider.read_bytes()).hexdigest())
    class TestDirectory(io.SecureDirectory):
        def __init__(self,path,**kwargs): super().__init__(path,_anchor=tmp_path,_owner_uid=os.getuid())
    monkeypatch.setattr(m,'directory_type',lambda bootstrap:TestDirectory)
    monkeypatch.setattr(m,'root_ids',lambda info: info.st_uid==os.getuid() and info.st_gid==os.getgid())
    bootstrap=SimpleNamespace(canonical_source=lambda sha:source)
    proof=SimpleNamespace(_lease_snapshot=lambda:lease,_workspace=lambda ignored:workspace)
    return m,audit,provider,bootstrap,proof,intent


def test_complete_exact_history_is_read_only_and_compares_live_metadata(fixture):
    m,audit,provider,b,proof,_=fixture
    before={p.name:p.read_bytes() for p in audit.iterdir()}
    evidence=m.historical_evidence(b,proof)
    assert evidence['publisher_sha']==m.PUBLISHER
    assert evidence['intent_sha256']==m.PINS['intent.json']
    assert evidence['credential_before_sha256']==m.SAFE_FIELDS['before_sha256']
    assert {p.name:p.read_bytes() for p in audit.iterdir()}==before


@pytest.mark.parametrize('change',['missing_complete','extra','link','hardlink','mode','raw','source','lease','workspace'])
def test_changed_or_partial_chain_is_not_admitted(fixture,change):
    m,audit,provider,b,proof,_=fixture
    if change=='missing_complete': (audit/'completed.json').unlink()
    if change=='extra': (audit/'unknown').write_text('x')
    if change=='link': (audit/'completed.json').unlink(); (audit/'completed.json').symlink_to('intent.json')
    if change=='hardlink': os.link(audit/'completed.json',audit.parent/'link')
    if change=='mode': (audit/'completed.json').chmod(0o644)
    if change=='raw': (audit/'completed.json').write_text('{}')
    if change=='source': provider.write_bytes(b'changed')
    if change=='lease': proof._lease_snapshot=lambda:{}
    if change=='workspace': proof._workspace=lambda ignored:{}
    with pytest.raises(m.ReconciliationError): m.historical_evidence(b,proof)


@pytest.mark.parametrize('field,value',[('state','REFRESH_INTENT'),('permissions',{'contents':'write'}),('app_id',True),('repository','other/repo'),('expires_at',False),('publisher_sha','f'*40)])
def test_fixed_13_field_values_are_validated_not_just_record_hash(fixture,field,value):
    m,audit,provider,b,proof,_=fixture
    data=json.loads((audit/'completed.json').read_bytes()); data[field]=value
    (audit/'completed.json').write_text(json.dumps(data)); m.PINS['completed.json']=hashlib.sha256((audit/'completed.json').read_bytes()).hexdigest()
    m.PIN_METADATA['completed.json']=m.metadata((audit/'completed.json').stat())
    with pytest.raises(m.ReconciliationError): m.historical_evidence(b,proof)


def test_duplicate_key_rejected_even_with_matching_hash(fixture):
    m,audit,provider,b,proof,_=fixture
    path=audit/'completed.json'; raw=path.read_bytes().rstrip(); path.write_bytes(raw[:-1]+b',"state":"CREDENTIAL_REFRESHED"}')
    m.PINS['completed.json']=hashlib.sha256(path.read_bytes()).hexdigest(); m.PIN_METADATA['completed.json']=m.metadata(path.stat())
    with pytest.raises(m.ReconciliationError): m.historical_evidence(b,proof)


def test_same_receipt_content_in_replaced_inode_is_rejected(fixture):
    m,audit,provider,b,proof,_=fixture
    path=audit/'completed.json'; raw=path.read_bytes(); path.unlink(); path.write_bytes(raw); path.chmod(0o600)
    with pytest.raises(m.ReconciliationError): m.historical_evidence(b,proof)


def test_receipt_changed_during_live_proof_is_rejected(fixture):
    m,audit,provider,b,proof,_=fixture
    def change(ignored):
        (audit/'completed.json').write_bytes(b'changed'); return proof._workspace_before
    proof._workspace_before=proof._workspace(None); proof._workspace=change
    with pytest.raises(m.ReconciliationError): m.historical_evidence(b,proof)


def test_current_credential_only_validates_fixed_hash_and_fields_without_returning_token(fixture,monkeypatch):
    m,audit,provider,b,proof,_=fixture
    path=audit.parent/'credential.json'; value={'repository':m.SAFE_FIELDS['repository'],'expires_at':m.SAFE_FIELDS['expires_at'],'token':'opaque-private-test-value'}
    raw=json.dumps(value).encode(); path.write_bytes(raw); path.chmod(0o600)
    monkeypatch.setattr(m,'CREDENTIAL',path); monkeypatch.setitem(m.SAFE_FIELDS,'after_sha256',hashlib.sha256(raw).hexdigest())
    result=m.validate_current_credential(b)
    assert 'opaque-private-test-value' not in json.dumps(result)
    assert result['sha256']==m.SAFE_FIELDS['after_sha256']


def own_refresh_fixture(fixture,monkeypatch):
    m,audit,provider,b,proof,_=fixture
    b.STATE=audit.parent/'state'; b.STATE.mkdir()
    own=b.STATE/'exam-a8-read-credential-v1'; own.mkdir(mode=0o700)
    sha='c'*40; original={'provider_reconciliation':m.historical_evidence(b,proof)}
    path=audit.parent/'credential.json'; value={'repository':m.SAFE_FIELDS['repository'],'expires_at':2000000000,'token':'new-private-value'}
    raw=json.dumps(value).encode(); path.write_bytes(raw); path.chmod(0o600)
    monkeypatch.setattr(m,'CREDENTIAL',path)
    old_identity={'st_'+key:val for key,val in {'dev':1,'ino':2,'uid':0,'gid':0,'mode':0o100600,'nlink':1,'size':100,'mtime_ns':1,'ctime_ns':1}.items()}
    evidence={'attempt':'exam-a8-read-credential-v1','recovery_sha':sha,'failed_sha':m.FAILED,'original':original,
      'original_credential':{'sha256':m.SAFE_FIELDS['after_sha256'],'identity':old_identity}}
    encoded=lambda obj:(json.dumps(obj,sort_keys=True,separators=(',',':'))+'\n').encode()
    evidence_sha=hashlib.sha256(encoded(evidence)).hexdigest(); newhash=hashlib.sha256(raw).hexdigest()
    intent={**evidence,'evidence_sha256':evidence_sha,'incoming_sha256':newhash,'incoming_expires_at':value['expires_at'],'ci_verified':True}
    complete={'state':'CREDENTIAL_REPLACED','attempt':evidence['attempt'],'recovery_sha':sha,'failed_sha':m.FAILED,
      'evidence_sha256':evidence_sha,'credential_sha256':newhash,'credential_expires_at':value['expires_at'],'ci_verified':True,
      'original_incident_preserved':True,'services_changed':False,'database_changed':False}
    for name,obj in [('intent.json',intent),('completed.json',complete)]:
        p=own/name;p.write_bytes(encoded(obj));p.chmod(0o600)
    return m,b,own,sha,original,path


def test_recovery_requires_completed_own_refresh_and_exact_current_readback(fixture,monkeypatch):
    m,b,own,sha,original,path=own_refresh_fixture(fixture,monkeypatch)
    result=m.validate_recovery_credential(b,sha,original)
    assert result['credential_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert 'new-private-value' not in json.dumps(result)


def successor_fixture(fixture, monkeypatch):
    m,b,own,sha,original,path=own_refresh_fixture(fixture,monkeypatch)
    original['g4_sha256']='1'*64
    original['strict_count']=1
    intent=json.loads((own/'intent.json').read_bytes())
    complete=json.loads((own/'completed.json').read_bytes())
    intent['original']=original
    encoded=lambda value:(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
    evidence={k:intent[k] for k in ('attempt','recovery_sha','failed_sha','original','original_credential')}
    intent['evidence_sha256']=hashlib.sha256(encoded(evidence)).hexdigest()
    complete['evidence_sha256']=intent['evidence_sha256']
    for name,value in [('intent.json',intent),('completed.json',complete)]: (own/name).write_bytes(encoded(value))
    raw_hashes={name:hashlib.sha256((own/name).read_bytes()).hexdigest() for name in ('intent.json','completed.json')}
    monkeypatch.setattr(m,'FIXED_CREDENTIAL_ORIGIN',sha,raising=False)
    monkeypatch.setattr(m,'FIXED_CREDENTIAL_RECEIPTS',raw_hashes.copy(),raising=False)
    monkeypatch.setattr(m,'FIXED_CREDENTIAL_G4','1'*64,raising=False)
    monkeypatch.setattr(m,'FIXED_CREDENTIAL_FILE',complete['credential_sha256'],raising=False)
    monkeypatch.setattr(m,'FIXED_CREDENTIAL_EXPIRY',complete['credential_expires_at'],raising=False)
    return m,b,own,'d'*40,{**original,'g4_sha256':'2'*64},path,intent,complete,raw_hashes


def test_exact_completed_credential_can_bind_new_review_without_replay(fixture,monkeypatch):
    m,b,own,sha,original,path,ci,cd,raw=successor_fixture(fixture,monkeypatch)
    before={p.name:p.read_bytes() for p in own.iterdir()}
    assert m.credential_binding_sha(sha,original,ci,cd,raw)==ci['recovery_sha']
    result=m.validate_recovery_credential(b,sha,original)
    assert result['credential_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert {p.name:p.read_bytes() for p in own.iterdir()}==before


@pytest.mark.parametrize('change',['intent_raw','complete_raw','parsed_intent','parsed_complete','incident','type','new_g4','old_g4','origin','file','expiry'])
def test_credential_successor_rejects_any_unbound_delta(fixture,monkeypatch,change):
    m,b,own,sha,original,path,ci,cd,raw=successor_fixture(fixture,monkeypatch)
    if change=='intent_raw':raw['intent.json']='0'*64
    if change=='complete_raw':raw['completed.json']='0'*64
    if change=='parsed_intent':ci['ci_verified']=False
    if change=='parsed_complete':cd['services_changed']=True
    if change=='incident':original['extra']='unknown'
    if change=='type':original['strict_count']=True
    if change=='new_g4':original['g4_sha256']='invalid'
    if change=='old_g4':ci['original']['g4_sha256']='3'*64
    if change=='origin':ci['recovery_sha']='e'*40
    if change=='file':monkeypatch.setattr(m,'FIXED_CREDENTIAL_FILE','0'*64)
    if change=='expiry':monkeypatch.setattr(m,'FIXED_CREDENTIAL_EXPIRY',0)
    with pytest.raises(m.ReconciliationError):m.credential_binding_sha(sha,original,ci,cd,raw)


@pytest.mark.parametrize('change',['pending','extra','wrong_original','wrong_sha','wrong_file','wrong_complete','duplicate'])
def test_recovery_blocks_unknown_or_mismatched_own_refresh(fixture,monkeypatch,change):
    m,b,own,sha,original,path=own_refresh_fixture(fixture,monkeypatch)
    if change=='pending': (own/'completed.json').unlink()
    if change=='extra': (own/'failure.json').write_text('{}')
    if change=='wrong_original': original={'other':'snapshot'}
    if change=='wrong_sha': sha='d'*40
    if change=='wrong_file': path.write_text('{}')
    if change=='wrong_complete':
        value=json.loads((own/'completed.json').read_bytes());value['services_changed']=True;(own/'completed.json').write_text(json.dumps(value))
    if change=='duplicate':
        raw=(own/'completed.json').read_bytes().rstrip();(own/'completed.json').write_bytes(raw[:-1]+b',"ci_verified":true}')
    with pytest.raises(m.ReconciliationError):m.validate_recovery_credential(b,sha,original)


@pytest.mark.parametrize('competitor',['none','other_provider','other_recovery','retired','temporary'])
def test_incident_consumer_admits_only_fixed_complete_provider(fixture,monkeypatch,competitor):
    m,audit,provider,b,proof,_=fixture
    b.STATE=audit.parent/'state'; b.STATE.mkdir(); credential=audit.parent/'credential'; credential.mkdir()
    retired=audit.parent/'retired-a8'
    server=SimpleNamespace(EXAM_COMPETING_RECORDS=('other-recovery',),EXAM_RETIRED_INSTALLATIONS=(retired,),
        EXAM_CREDENTIAL_ROOT=credential,_exam_directory_names=lambda p:set(os.listdir(p)) if p.exists() else set())
    original_load=m.load_sibling
    monkeypatch.setattr(m,'load_sibling',lambda boot,name:server if name=='trusted_release_server' else original_load(boot,name))
    if competitor=='other_provider': (audit.parent/'exam-another').mkdir()
    if competitor=='other_recovery': (b.STATE/'other-recovery').mkdir()
    if competitor=='retired': retired.mkdir()
    if competitor=='temporary': (credential/'credential.exam-unknown.tmp').touch()
    if competitor=='none': assert m.assert_reconciled_competition(b)==m.historical_evidence(b)
    else:
        with pytest.raises(m.ReconciliationError):m.assert_reconciled_competition(b)


def test_ordinary_publication_still_blocks_exact_external_completed_receipt(tmp_path,monkeypatch):
    helper=module('test_exam_recovery_history')
    server,state,refresh,credential=helper.competing_fixture(monkeypatch,tmp_path)
    refresh.mkdir(parents=True); record=refresh/('exam-'+module().PUBLISHER); record.mkdir()
    (record/'intent.json').write_text('{}');(record/'completed.json').write_text('{"state":"CREDENTIAL_REFRESHED"}')
    with pytest.raises(server.LaunchError):server.assert_exam_recovery_history(state)


@pytest.mark.parametrize('kind',['valid','mode','symlink','hardlink','missing','parent_writable'])
def test_provider_lock_uses_existing_private_file_and_retained_identity(fixture,monkeypatch,kind):
    m,audit,provider,b,proof,_=fixture
    path=audit.parent/'provider-refresh.lock';path.touch();path.chmod(0o600)
    monkeypatch.setattr(m,'PROVIDER_LOCK',path)
    if kind=='mode':path.chmod(0o644)
    if kind=='symlink':path.unlink();path.symlink_to('missing')
    if kind=='hardlink':os.link(path,audit.parent/'locklink')
    if kind=='missing':path.unlink()
    if kind=='parent_writable':path.parent.chmod(0o777)
    if kind!='valid':
        with pytest.raises(m.ReconciliationError):m.acquire_provider_lock(b)
        return
    fd,check=m.acquire_provider_lock(b)
    try:
        check()
        with pytest.raises(m.ReconciliationError):m.acquire_provider_lock(b)
        path.unlink();path.touch();path.chmod(0o600)
        with pytest.raises(m.ReconciliationError):check()
    finally:os.close(fd)
