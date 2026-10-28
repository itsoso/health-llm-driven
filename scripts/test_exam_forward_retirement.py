"""Fixed incident closure tests. Local files and synthetic adapters only."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


def load():
    path = Path(__file__).with_name('exam_forward_retirement.py')
    spec = importlib.util.spec_from_file_location('exam_forward_close_test', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Fake:
    def __init__(self, path):
        self.record = path / 'closures' / 'fixed'
        self.events = []
        self.value = {'attempt': 'exam-a8-forward-close-v1', 'old_sha': 'a'*40}
    def inspect(self):
        self.events.append('inspect')
        return copy.deepcopy(self.value)
    def authorized_guards(self, value):
        assert (self.record / 'intent.json').is_file()
        self.events.append('synthetic-rollback-guards')
    def retire(self, value):
        self.events.append('revoke-rename')
    def verify_closed(self, value):
        self.events.append('verify')
        return {'installation': {'config': {}, 'library': {}}}


def test_inspect_has_no_audit_or_synthetic_write(tmp_path):
    m, a = load(), Fake(tmp_path)
    result = m.close_transaction(a)
    assert result['state'] == 'INSPECTED_EXAM_FORWARD_FAILURE'
    assert a.events == ['inspect'] and not a.record.parent.exists()


@pytest.mark.parametrize('digest,accept', [(None, True), ('a'*64, False), ('bad', True)])
def test_authorization_pair_rejected_without_inspection(tmp_path, digest, accept):
    m, a = load(), Fake(tmp_path)
    with pytest.raises(m.ClosureError):
        m.close_transaction(a, digest, accept=accept)
    assert a.events == [] and not a.record.exists()


def test_durable_intent_guards_revoke_and_single_receipt(tmp_path):
    m, a = load(), Fake(tmp_path)
    digest = m.close_transaction(a)['evidence_sha256']
    result = m.close_transaction(a, digest, accept=True)
    assert result['state'] == m.TERMINAL == 'CLOSED_EXAM_FORWARD_FAILURE'
    assert a.events[-3:] == ['synthetic-rollback-guards', 'revoke-rename', 'verify']
    assert {p.name for p in a.record.iterdir()} == {'intent.json', 'completed.json'}
    raw = (a.record/'intent.json').read_bytes()
    assert result['receipt'].encode() not in raw
    assert json.loads(raw)['receipt_sha256'] == hashlib.sha256(result['receipt'].encode()).hexdigest()
    with pytest.raises(m.ClosureError):
        m.close_transaction(a, digest, accept=True)


@pytest.mark.parametrize('phase', ['authorized_guards', 'retire', 'verify_closed'])
def test_consumed_failure_is_durable_and_never_replayed(tmp_path, phase):
    m, a = load(), Fake(tmp_path)
    digest = m.close_transaction(a)['evidence_sha256']
    def fail(*args):
        raise RuntimeError('secret must never appear')
    setattr(a, phase, fail)
    with pytest.raises(m.ClosureError, match='preserve'):
        m.close_transaction(a, digest, accept=True)
    audit = (a.record/'failure.json').read_text()
    assert 'secret' not in audit and 'NEEDS_OPERATOR' in audit
    assert not (a.record/'completed.json').exists()
    with pytest.raises(m.ClosureError):
        m.close_transaction(a)


def test_changed_digest_does_not_consume(tmp_path):
    m, a = load(), Fake(tmp_path)
    digest = m.close_transaction(a)['evidence_sha256']
    a.value['changed'] = True
    with pytest.raises(m.ClosureError):
        m.close_transaction(a, digest, accept=True)
    assert not a.record.parent.exists()


def terminal(m):
    transaction = hashlib.sha256(f'{m.PREVIOUS}:{m.FAILED}'.encode()).hexdigest()[:32]
    return {'version':1,'mode':'code-only-no-backup','old_sha':m.PREVIOUS,
        'candidate_sha':m.FAILED,'terminal_sha':m.FAILED,'phase':'COMMITTED',
        'target':'candidate','result':'finalized','transaction_id':transaction,
        'reap_name':'runtime-state-transaction.reap-'+transaction}


@pytest.mark.parametrize('change', [{'version':2},{'mode':'backup'}, {'phase':'ROLLED_BACK'},
    {'terminal_sha':'a'*40},{'result':'committed'},{'extra':True},{'transaction_id':'1'*32}])
def test_final_terminal_contract_is_v1_exact(change):
    m = load()
    value = terminal(m)
    m.validate_terminal(value)
    value.update(change)
    with pytest.raises(m.ClosureError): m.validate_terminal(value)


def records(m):
    sha = '1'*40
    provider = {'schema':'exam-provider-reconciliation.v1','evidence':'synthetic'}
    original = {key:{} for key in m.ORIGINAL_FIELDS}
    original.update(original_runtime_journal_sha256=m.JOURNAL_PIN,
        original_runtime_journal={'version':2,'mode':'code-only-no-backup','phase':'INSTALLED',
        'candidate_sha':m.FAILED,'old_sha':m.PREVIOUS,'boot_gate_armed':True,
        'boot_gate_released':False,'release_target':None,'transaction_id':terminal(m)['transaction_id'],
        'beat_authority':'current','old_upload_authority':'external','upload_authority':'external',
        'old_effective':{},'original_enablement':{u:'enabled' for u in m.UNITS}}, provider_reconciliation=provider,
        g4_sha256='2'*64)
    m.JOURNAL_PIN=m.credential_digest(original['original_runtime_journal'])
    original['original_runtime_journal_sha256']=m.JOURNAL_PIN
    database={'database_state':'PENDING','database_sha256':'3'*64,'laya':{},
              'dependencies':{},'active_release_processes':False}
    evidence={'attempt':m.RECOVERY_ATTEMPT,'recovery_sha':sha,'failed_sha':m.FAILED,
              'previous_sha':m.PREVIOUS,'original':original,'database':database}
    intent={**evidence,'evidence_sha256':m.digest(evidence)}
    plan={'attempt':m.RECOVERY_ATTEMPT,'recovery_sha':sha,'source_sha':m.FAILED,
          'original_intent_sha256':m.INTENT_PIN,'original_journal_sha256':m.JOURNAL_PIN,
          'evidence_sha256':intent['evidence_sha256']}
    db={'binding':plan,'schema_sha256':'4'*64}
    health={'health_score':{'score':60,'maximum':60,'critical_failures':[],
        'runtime_pause_preserved':False,'runtime':'disabled'},
        'skills_manifest':{'count':1,'slugs_sha256':'5'*64}}
    # Full nested service and model contract is validated against the original
    # reviewed runtime helper by live proof. Historical schema still rejects
    # missing/unknown branches and nonempty authorization flags.
    services={unit:{'MainPID':str(i+20),'processes':{str(i+20):'10'}}
              for i,unit in enumerate(m.UNITS)}
    services[m.UNITS[0]]={'MainPID':''}
    for unit,service in services.items():
        service.update(ActiveState='active',SubState='listening' if unit.endswith('.socket') else 'running',
            NRestarts='' if unit.endswith('.socket') else '0',ActiveEnterTimestampMonotonic='100',
            ControlGroup='/system.slice/'+unit,Result='success')
    models={unit.removesuffix('.service'):{services[unit]['MainPID']:
         {'start':'10','model':'qwen3.8-flash','authorization_flags':
          {flag:'false' for flag in m.FLAGS}}} for unit in m.UNITS[1:]}
    stable={'services':services,'vision':{'model':'qwen3.8-flash','services':{
        u.removesuffix('.service'):{'MainPID':services[u]['MainPID'],'process_start':'10',
          'authorization_flags':{f:'false' for f in m.FLAGS}} for u in m.UNITS[1:]},
        'history':{},'files':{},'raw_dropins':{}},'cgroup_model_identity':models}
    done={'state':'FORWARD_RECOVERED','attempt':m.RECOVERY_ATTEMPT,'recovery_sha':sha,
      'production_sha':m.FAILED,'previous_sha':m.PREVIOUS,'original_release_state':'NEEDS_OPERATOR',
      'original_lease_and_authorization_preserved':True,'notification_fix_deployed':False,
      'evidence_sha256':intent['evidence_sha256'],'database':db,'runtime_terminal':terminal(m),
      'stable_services':stable,'health_guards':health}
    ce={'attempt':m.CREDENTIAL_ATTEMPT,'recovery_sha':sha,'failed_sha':m.FAILED,
        'original':original,'original_credential':{'sha256':m.EXTERNAL_CREDENTIAL_PIN,
        'identity':{**{k:1 for k in m.META},'st_uid':0,'st_gid':0,'st_mode':0o100600,'st_nlink':1}}}
    ci={**ce,'evidence_sha256':m.credential_digest(ce),'incoming_sha256':'6'*64,
        'incoming_expires_at':1234567,'ci_verified':True}
    cd={'state':'CREDENTIAL_REPLACED','attempt':m.CREDENTIAL_ATTEMPT,'recovery_sha':sha,
        'failed_sha':m.FAILED,'evidence_sha256':ci['evidence_sha256'],
        'credential_sha256':'6'*64,'credential_expires_at':1234567,'ci_verified':True,
        'original_incident_preserved':True,'services_changed':False,'database_changed':False}
    return intent,plan,db,done,ci,cd,provider


def test_complete_recovery_credential_chain_accepts_same_candidate_and_expired_history():
    m = load()
    m.validate_records(*records(m))


@pytest.mark.parametrize('change',[None,'incident','type','receipt','mixed','current_rotation'])
def test_successor_closure_uses_shared_byte_pinned_history(tmp_path,monkeypatch,change):
    m=load(); values=list(copy.deepcopy(records(m)))
    path=Path(__file__).with_name('exam_provider_reconciliation.py')
    spec=importlib.util.spec_from_file_location('closure_credential_binding_test',path)
    reconciliation=importlib.util.module_from_spec(spec);spec.loader.exec_module(reconciliation)
    ci,cd=values[4:6]; ci['original']=copy.deepcopy(ci['original'])
    old_sha='c'*40
    ci['recovery_sha']=cd['recovery_sha']=old_sha
    ci['original']['g4_sha256']='a'*64
    evidence={k:ci[k] for k in ('attempt','recovery_sha','failed_sha','original','original_credential')}
    ci['evidence_sha256']=cd['evidence_sha256']=m.credential_digest(evidence)
    pins={'intent.json':m.credential_digest(ci),'completed.json':m.credential_digest(cd)}
    monkeypatch.setattr(reconciliation,'FIXED_CREDENTIAL_ORIGIN',old_sha)
    monkeypatch.setattr(reconciliation,'FIXED_CREDENTIAL_G4','a'*64)
    monkeypatch.setattr(reconciliation,'FIXED_CREDENTIAL_RECEIPTS',pins.copy())
    monkeypatch.setattr(reconciliation,'FIXED_CREDENTIAL_FILE',ci['incoming_sha256'])
    monkeypatch.setattr(reconciliation,'FIXED_CREDENTIAL_EXPIRY',ci['incoming_expires_at'])
    # History remains valid after expiration or replacement of the live token.
    credential=tmp_path/'credential.json';credential.write_text('expired or rotated')
    monkeypatch.setattr(reconciliation,'CREDENTIAL',credential)
    if change=='incident':ci['original']['configuration']={'drift':True}
    if change=='type':ci['original']['original_runtime_journal']['version']=True
    if change=='receipt':pins['completed.json']='0'*64
    if change=='mixed':cd['recovery_sha']='d'*40
    if change=='current_rotation':credential.unlink()
    binder=lambda sha,original,ci,cd:reconciliation.credential_binding_sha(sha,original,ci,cd,pins)
    if change in (None,'current_rotation'):
        m.validate_records(*values,credential_binding=binder)
        # Cross-candidate input cannot enter the legacy same-candidate route.
        with pytest.raises(m.ClosureError):m.validate_records(*values)
    else:
        with pytest.raises((m.ClosureError,reconciliation.ReconciliationError)):
            m.validate_records(*values,credential_binding=binder)


@pytest.mark.parametrize('index,path,value', [
    (0,('original','provider_reconciliation'),{}), (0,('extra',),True),
    (1,('original_intent_sha256',),'0'*64),(2,('schema_sha256',),'bad'),
    (3,('notification_fix_deployed',),True),(3,('original_release_state',),'SUCCEEDED'),
    (3,('runtime_terminal','version'),2),(3,('stable_services',),{}),
    (3,('stable_services','cgroup_model_identity','celery-worker'),{}),
    (3,('health_guards','health_score','score'),34),
    (3,('health_guards','skills_manifest','count'),0),
    (4,('original_credential','sha256'),'0'*64),(4,('incoming_sha256',),'bad'),
    (5,('credential_expires_at',),1234568),(5,('services_changed',),True),
    (5,('state',),'REFRESHED')])
def test_chain_rejects_incomplete_or_spliced_records(index,path,value):
    m = load(); values=list(copy.deepcopy(records(m)))
    target=values[index]
    for part in path[:-1]: target=target[part]
    target[path[-1]]=value
    with pytest.raises(m.ClosureError): m.validate_records(*values)


def test_json_duplicates_rejected():
    m = load()
    with pytest.raises(m.ClosureError): m.object_json(b'{"state":1,"state":2}')


def test_original_recovery_adapter_constructor_never_used():
    m=load()
    source=Path(m.__file__).read_text()
    assert 'recovery.Adapter(' not in source


@pytest.mark.parametrize('location', [('services','celery-worker.service','Result'),
    ('services','health-backend.service','ActiveState'),
    ('services','celery-beat.service','ControlGroup')])
def test_stable_service_fields_cannot_be_omitted(location):
    m=load(); stable=records(m)[3]['stable_services']
    target=stable
    for part in location[:-1]: target=target[part]
    del target[location[-1]]
    with pytest.raises(m.ClosureError): m.validate_stable(stable)


def test_every_cgroup_child_model_and_authority_is_bound():
    m=load(); stable=records(m)[3]['stable_services']
    unit='celery-worker'; pid='999'
    stable['services'][unit+'.service']['processes'][pid]='77'
    with pytest.raises(m.ClosureError): m.validate_stable(stable)
    stable['cgroup_model_identity'][unit][pid]={'start':'77','model':'qwen3.8-flash',
        'authorization_flags':{f:'false' for f in m.FLAGS}}
    m.validate_stable(stable)
    stable['cgroup_model_identity'][unit][pid]['model']='qwen-vl-max'
    with pytest.raises(m.ClosureError): m.validate_stable(stable)


def test_original_journal_reconstruction_is_pinned():
    m=load(); values=list(records(m))
    values[0]['original']['original_runtime_journal']['old_effective']['drift']=True
    values[0]['evidence_sha256']=m.digest({k:v for k,v in values[0].items() if k!='evidence_sha256'})
    with pytest.raises(m.ClosureError,match='journal hash'): m.validate_records(*values)


@pytest.mark.parametrize('state,ack', [('paused:reconciliation_detected:generation=3:ack=2',True),
    ('active:none:generation=3:ack=3',False),('active:manual_resume:generation=2:ack=2',False)])
def test_valid_health_circuit_states(state,ack):
    m=load(); health=records(m)[3]['health_guards']
    health['health_score'].update(runtime=state,runtime_pause_preserved=ack)
    m.validate_health(health)
    health['health_score']['runtime']='paused:other:generation=3:ack=2'
    with pytest.raises(m.ClosureError): m.validate_health(health)


@pytest.mark.parametrize('mutation',['nan','boolean','unknown','unacknowledged','badcount'])
def test_health_guard_never_accepts_uncertain_summary(mutation):
    m=load(); health=records(m)[3]['health_guards']
    if mutation=='nan': health['health_score']['score']=float('nan')
    if mutation=='boolean': health['health_score']['score']=True
    if mutation=='unknown': health['health_score']['runtime']='unknown'
    if mutation=='unacknowledged': health['health_score']['runtime']='active:none:generation=2:ack=1'
    if mutation=='badcount': health['skills_manifest']['count']=True
    with pytest.raises(m.ClosureError): m.validate_health(health)


def test_record_reader_rejects_hardlink_and_symlink(tmp_path):
    m=load(); b=SimpleNamespace(secure=lambda *a,**k:None)
    p=tmp_path/'record'; p.write_text('{"safe":true}'); p.chmod(0o600)
    assert m.read_record(b,p)[0]=={'safe':True}
    link=tmp_path/'hard'; os.link(p,link)
    with pytest.raises(m.ClosureError): m.read_record(b,p)
    link.unlink(); p.unlink(); p.symlink_to(tmp_path/'missing')
    with pytest.raises(OSError): m.read_record(b,p)


def test_record_reader_detects_same_inode_content_change(tmp_path,monkeypatch):
    m=load(); b=SimpleNamespace(secure=lambda *a,**k:None)
    path=tmp_path/'record'; path.write_text('{"value":1}')
    real=m.os.fstat; calls=[]
    def altered(fd):
        calls.append(fd)
        if len(calls)==2: path.write_text('{"value":2}')
        return real(fd)
    monkeypatch.setattr(m.os,'fstat',altered)
    with pytest.raises(m.ClosureError): m.read_record(b,path)


def test_readonly_guards_do_not_execute_synthetic_probe():
    m=load(); intent,_,_,done,*_=records(m)
    proof=object.__new__(m.Proof); calls=[]
    proof.intent,proof.done=intent,done
    proof.dependencies=intent['database']['dependencies']; proof.original_laya=intent['database']['laya']
    proof.bootstrap=proof.source=proof.journal=proof.proof=None
    proof.retained=SimpleNamespace(candidate_laya=lambda *a:proof.original_laya)
    proof.static=lambda:calls.append('static'); proof.database=lambda:calls.append('metadata-read')
    proof._dependencies=lambda:calls.append('dependencies')
    proof._application_guard=lambda **kw:calls.append(('synthetic',kw))
    proof.http=lambda:done['health_guards']; proof.stable=lambda:done['stable_services']
    proof.guards()
    assert not any(isinstance(c,tuple) for c in calls)
    proof.guards(synthetic=True)
    assert ('synthetic',{'schema':True}) in calls


def closure_values(m):
    *_,done,ci,cd,provider=records(m)
    def inventory(names):
        return {n:{'uid':0,'gid':0,'mode':0o700 if n=='.' else 0o600,
            'inode':1,'device':1,'sha256':None if n=='.' else 'a'*64} for n in {'.',*names}}
    evidence={'attempt':m.ATTEMPT,'old_sha':m.FAILED,'closing_sha':'1'*40,'production_sha':m.FAILED,
        'recovery':{'chain':True},'workspace':{'manifest':True},'lease_directory':{'preserved':True},
        'config':inventory({'known_hosts','loopback.conf','authorized-release.json','loopback.pub','cloud.pub','loopback.key'}),
        'library':inventory({'trusted_release_server.py'}),'authorized':{},'services':done['stable_services'],
        'health_guards':done['health_guards'],'launcher':{},'build':None}
    receipt='7'*64
    intent={**evidence,'evidence_sha256':m.digest(evidence),'receipt_sha256':hashlib.sha256(receipt.encode()).hexdigest()}
    completed={'old_sha':m.FAILED,'state':m.TERMINAL,'intent_sha256':m.digest(intent),
        'installation':{'config':{k:v for k,v in intent['config'].items() if k!='loopback.key'},'library':intent['library']}}
    return intent,completed,receipt


@pytest.mark.parametrize('kind',['mode','owner','missing','extra','state','receipt_hash'])
def test_closure_saved_inventory_and_terminal_strict(kind):
    m=load(); intent,done,_=closure_values(m)
    m.validate_closure(intent,done)
    if kind=='mode': intent['config']['cloud.pub']['mode']=0o644
    if kind=='owner': intent['library']['trusted_release_server.py']['uid']=1
    if kind=='missing': del intent['config']['known_hosts']
    if kind=='extra': intent['library']['cache']={}
    if kind=='state': done['state']='SUCCEEDED'
    if kind=='receipt_hash': intent['receipt_sha256']='invalid'
    intent['evidence_sha256']=m.digest({k:v for k,v in intent.items() if k in m.EVIDENCE_FIELDS})
    done['intent_sha256']=m.digest(intent)
    with pytest.raises(m.ClosureError): m.validate_closure(intent,done)


def retirement_fixture(m,tmp_path):
    intent,done,receipt=closure_values(m); result=m.validate_closure(intent,done)
    old={'old_sha':m.FAILED,'new_sha':'2'*40,'installation':done['installation'],'workspace':result,
        'retirement_policy':'no-backup-v1','public_keys':{'cloud.pub':'cloud','loopback.pub':'loop'},
        'recovery_receipt':receipt}
    path=tmp_path/'retired'/m.FAILED; path.mkdir(parents=True)
    (path/'intent.json').write_text(json.dumps(old))
    b=SimpleNamespace(STATE=tmp_path,CONFIG=tmp_path/'removed',INSTALLED=tmp_path/'removed/server',
        _archives=lambda sha:(tmp_path/'absent1',tmp_path/'absent2'),
        _retired_public_keys=lambda sha,v:v['public_keys'],validate_install=lambda *a,**k:None,
        _installation_evidence=lambda *a:done['installation'])
    return b,path,intent,done,result,old


def test_pending_rotation_is_not_ordinary_history(tmp_path,monkeypatch):
    m=load(); b,path,intent,done,result,old=retirement_fixture(m,tmp_path)
    def audit(b,p,names):
        assert p==path
        m.need({x.name for x in path.iterdir()}==set(names))
        return {n:json.loads((p/n).read_text()) for n in names},{}
    monkeypatch.setattr(m,'audit',audit)
    with pytest.raises(m.ClosureError): m.retired_history(b,intent,done,result)
    assert m.retired_history(b,intent,done,result,pending=old)
    drift=copy.deepcopy(old); drift['new_sha']='3'*40
    with pytest.raises(m.ClosureError): m.retired_history(b,intent,done,result,pending=drift)
    (path/'completed.json').write_text(json.dumps({'old_sha':m.FAILED,'new_sha':'2'*40,'state':'RETIRED'}))
    assert m.retired_history(b,intent,done,result)
    with pytest.raises(m.ClosureError): m.retired_history(b,intent,done,result,pending=old)


@pytest.mark.parametrize('field,value',[('retirement_policy','backup'),('recovery_receipt','8'*64),
    ('old_sha','9'*40),('workspace',{}),('installation',{}),('extra',True)])
def test_retirement_history_cannot_be_spliced(tmp_path,monkeypatch,field,value):
    m=load(); b,path,intent,done,result,old=retirement_fixture(m,tmp_path)
    old[field]=value
    records={'intent.json':old,'completed.json':{'old_sha':m.FAILED,'new_sha':'2'*40,'state':'RETIRED'}}
    monkeypatch.setattr(m,'audit',lambda *a:(records,{}))
    with pytest.raises(m.ClosureError): m.retired_history(b,intent,done,result)


def test_pending_rotation_binds_current_canonical_bootstrap(tmp_path,monkeypatch):
    m=load(); new='2'*40; source=tmp_path/new/'source'
    b=SimpleNamespace(__file__=str(source/'scripts/bootstrap_trusted_release.py'),canonical_source=lambda sha:tmp_path/sha/'source')
    calls=[]
    monkeypatch.setattr(m,'_history_evidence',lambda b,**kw:calls.append(kw) or {'safe':True})
    assert m.validate_pending_rotation(b,{'new_sha':new})=={'safe':True}
    with pytest.raises(m.ClosureError): m.validate_pending_rotation(b,{'new_sha':'3'*40})
    assert len(calls)==1


def test_archived_lease_does_not_grant_authority_without_same_inode_proof(monkeypatch):
    m=load(); proof=object.__new__(m.Proof); proof.bootstrap=object(); proof.lease_expected={'original':True}
    proof.proof=SimpleNamespace(_closed=False); proof.closed=False
    monkeypatch.setattr(m,'moved_lease',lambda *a:(_ for _ in ()).throw(m.ClosureError()))
    with pytest.raises(m.ClosureError): proof.retired()
    assert proof.proof._closed is False and proof.closed is False


# This fixture creates and drops isolated roles/database on an explicitly local
# dedicated cluster; it refuses a nonlocal or non-test DSN.
_pg_spec=importlib.util.spec_from_file_location('exam_close_pg_fixture',Path(__file__).with_name('test_exam_attempts_release_postgres.py'))
_pg=importlib.util.module_from_spec(_pg_spec); _pg_spec.loader.exec_module(_pg)
pg=_pg.pg


def pg_proof(pg):
    from types import MethodType
    m=load(); helper,migration,runtime,role,plan,expected,directory=pg
    path=Path(__file__).with_name('exam_release_recovery.py')
    spec=importlib.util.spec_from_file_location('exam_close_pg_recovery',path)
    recovery=importlib.util.module_from_spec(spec);spec.loader.exec_module(recovery)
    root=Path(__file__).resolve().parents[1]
    with migration.begin() as conn: helper.apply_exact(conn,root,plan,role)
    helper.write_once(directory/'intent.json',plan)
    with migration.connect() as conn:
        committed=helper.committed_proof(conn,plan,directory,role)
        migration_id=helper.role_identity(conn)
    with runtime.connect() as conn: runtime_id=helper.role_identity(conn)
    bound=hashlib.sha256(json.dumps([migration_id,runtime_id],sort_keys=True).encode()).hexdigest()
    proof=object.__new__(m.Proof)
    proof.helper=helper;proof.runtime=runtime;proof.migration=migration
    proof.original_record=directory;proof.expected=expected;proof.old_plan={'database_sha256':bound}
    proof.intent={'database':{'database_sha256':bound}}
    proof.done={'database':committed};proof._authority=lambda:None;proof._connect=lambda:None
    proof._database=MethodType(recovery.Adapter._database,proof)
    return m,proof


def test_postgres_closure_readback_uses_only_readonly_catalog_and_ledger(pg):
    from sqlalchemy import event
    import re
    m,proof=pg_proof(pg); statements=[]
    def observe(conn,cursor,statement,parameters,context,executemany): statements.append(statement)
    event.listen(proof.migration,'before_cursor_execute',observe)
    event.listen(proof.runtime,'before_cursor_execute',observe)
    assert proof.database()==proof.done['database']
    assert statements[0]=='SET TRANSACTION READ ONLY'
    assert not any(re.search(r'\b(?:INSERT|DELETE|UPDATE|ALTER|CREATE|DROP|nextval)\s*\(?\s*(?:INTO|FROM|TABLE|SEQUENCE|public\.|life_exam)',s,re.I) for s in statements)
    assert not any(re.search(r'FROM\s+(?:public\.)?(?:life_exam_attempts|users)\b',s,re.I) for s in statements)
    assert {p.name for p in proof.original_record.iterdir()}=={'intent.json'}


@pytest.mark.parametrize('grant', ['GRANT UPDATE ON life_exam_attempts TO {role}',
    'GRANT SELECT ON SEQUENCE life_exam_attempts_sequence_seq TO {role}'])
def test_postgres_closure_rejects_acl_drift_without_repair(pg,grant):
    from sqlalchemy import text
    m,proof=pg_proof(pg)
    with proof.migration.begin() as conn: conn.execute(text(grant.format(role=pg[3])))
    with pytest.raises(proof.helper.ReleaseBlocked): proof.database()
    assert {p.name for p in proof.original_record.iterdir()}=={'intent.json'}


def test_postgres_closure_rejects_metadata_binding_drift(pg):
    m,proof=pg_proof(pg)
    proof.done['database']['binding']={**proof.done['database']['binding'],'spliced':True}
    with pytest.raises(proof.helper.ReleaseBlocked): proof.database()


def history_fixture(tmp_path,monkeypatch):
    m=load(); intent,done,receipt=closure_values(m)
    original,_,_,recovered,*_=records(m)
    intent['lease_directory']={k:{} for k in ('lease','token','label','stage','started_at')}
    original['original']['lease_stage']=intent['lease_directory']
    intent['recovery']={'provider':{'fixed':True}}
    intent['evidence_sha256']=m.digest({k:v for k,v in intent.items() if k in m.EVIDENCE_FIELDS})
    done['intent_sha256']=m.digest(intent)
    root=tmp_path/m.ROOT_NAME/m.FAILED;root.mkdir(parents=True)
    values={'intent.json':intent,'completed.json':done}
    b=SimpleNamespace(STATE=tmp_path,CONFIG=tmp_path/'removed',INSTALLED=tmp_path/'removed/server',
        canonical_source=lambda sha:tmp_path/'bootstrap'/sha/'source',
        _recovery_file_identity=lambda p:{})
    server=SimpleNamespace(EXAM_COMPETING_RECORDS=('retired/'+m.FAILED,'exam-service-recovery-'+m.FAILED),
        EXAM_RETIRED_INSTALLATIONS=(tmp_path/'removed-old-config',tmp_path/'removed-old-library'),
        EXAM_CREDENTIAL_ROOT=tmp_path/'credentials',
        _exam_directory_names=lambda p:{x.name for x in p.iterdir()} if p.exists() else set())
    refresh=tmp_path/'provider';refresh.mkdir();(refresh/'exam-fixed').mkdir()
    provider=SimpleNamespace(REFRESH_ROOT=refresh,PUBLISHER='fixed',historical_evidence=lambda b:{'fixed':True})
    monkeypatch.setattr(m,'private_directory',lambda b,p:m.need(p.is_dir()))
    monkeypatch.setattr(m,'audit',lambda *a:(values,{}))
    monkeypatch.setattr(m,'recovery_evidence',lambda *a:(original,recovered,intent['recovery']))
    monkeypatch.setattr(m,'workspace',lambda b:intent['workspace'])
    monkeypatch.setattr(m,'load',lambda b,p,n:provider if 'provider' in n else server)
    return m,b,intent,done,receipt,server,provider


def test_historical_closure_never_reads_current_credential_config_or_services(tmp_path,monkeypatch):
    m,b,intent,done,receipt,_,_=history_fixture(tmp_path,monkeypatch)
    def forbidden(*a,**k): raise AssertionError('live evidence must not be read in historical path')
    b._installation_evidence=forbidden
    monkeypatch.setattr(m,'lease_identity',forbidden)
    monkeypatch.setattr(m,'Adapter',forbidden)
    value=m.closed_evidence(b,m.FAILED,receipt,historical=True)
    assert value=={'state':m.TERMINAL,'closure':m.digest(done),'workspace':intent['workspace']}
    with pytest.raises(m.ClosureError):m.closed_evidence(b,m.FAILED,'8'*64,historical=True)


@pytest.mark.parametrize('where',['provider','credential','alternate','legacy','unknown_closure'])
def test_completed_closure_does_not_whitelist_competing_attempts(tmp_path,monkeypatch,where):
    m,b,_,_,_,server,provider=history_fixture(tmp_path,monkeypatch)
    if where=='provider': (provider.REFRESH_ROOT/'exam-unknown').mkdir()
    if where=='credential':
        server.EXAM_CREDENTIAL_ROOT.mkdir();(server.EXAM_CREDENTIAL_ROOT/'credential.exam-malformed').symlink_to(tmp_path/'missing')
    if where=='alternate': (tmp_path/('exam-service-recovery-'+m.FAILED)).mkdir()
    if where=='legacy': server.EXAM_RETIRED_INSTALLATIONS[0].symlink_to(tmp_path/'missing')
    if where=='unknown_closure': (tmp_path/m.ROOT_NAME/'unknown').mkdir()
    with pytest.raises(m.ClosureError):m.history_evidence(b)


def test_live_closed_consumer_requires_lease_and_health_recheck(tmp_path,monkeypatch):
    m,b,intent,done,receipt,_,_=history_fixture(tmp_path,monkeypatch)
    b.reviewed_source=lambda sha:(b.canonical_source(sha),object())
    events=[]
    class Live:
        def __init__(self,*args,**kwargs):
            assert kwargs=={'closed':True};events.append('construct archived proof')
        def verify_closed(self,evidence):
            assert set(evidence)==m.EVIDENCE_FIELDS; events.append('verify lease health schema metadata')
        def close(self):events.append('dispose')
    monkeypatch.setattr(m,'Adapter',Live)
    m.closed_evidence(b,m.FAILED,receipt)
    assert events==['construct archived proof','verify lease health schema metadata','dispose']


def test_socket_without_process_cgroup_is_a_valid_runtime_snapshot():
    m=load(); stable=records(m)[3]['stable_services']
    stable['services'][m.UNITS[0]]['ControlGroup']=''
    m.validate_stable(stable)


@pytest.mark.parametrize('reused',[None,True,False,1,'true'])
def test_persistent_cloud_reuse_is_only_exact_optional_true(tmp_path,monkeypatch,reused):
    m=load(); b,path,intent,done,result,old=retirement_fixture(m,tmp_path)
    if reused is not None: old['cloud_key_reused']=reused
    records={'intent.json':old,'completed.json':{'old_sha':m.FAILED,'new_sha':'2'*40,'state':'RETIRED'}}
    monkeypatch.setattr(m,'audit',lambda *a:(records,{}))
    if reused is None or reused is True: assert m.retired_history(b,intent,done,result)
    else:
        with pytest.raises(m.ClosureError):m.retired_history(b,intent,done,result)
