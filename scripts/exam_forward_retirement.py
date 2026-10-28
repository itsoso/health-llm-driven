#!/usr/bin/env python3
"""Fixed, no-copy closure of the a8 forward-recovered failed release.

Inspection is read-only. Execution consumes one durable attempt before synthetic
rollback-only guards, exact key revocation and an inode-preserving lease rename.
It never edits the original failure or deploys a new application revision.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
from types import MethodType

FAILED = 'a8cd1e7635eb697c0f0bc528382c98b3602893c3'
PREVIOUS = '83876750fcbb404255b7439482688fee82a490d4'
ROOT_NAME = 'exam-forward-closures'
ATTEMPT = 'exam-a8-forward-close-v1'
RECOVERY_ATTEMPT = 'exam-a8-forward-acl-v1'
CREDENTIAL_ATTEMPT = 'exam-a8-read-credential-v1'
TERMINAL = 'CLOSED_EXAM_FORWARD_FAILURE'
JOURNAL_PIN = '79c9088df6c9861eabb07806b05809be7e977ac76b4ca841401e424348bd1c8f'
INTENT_PIN = '0c0e14c8537aac6f3eccb74fa18b7a13a338d2cbe685ba71062b576043f2c589'
EXTERNAL_CREDENTIAL_PIN = '699aa3167a7b44ba74309e265add3ff34433c25116b85fd019aa3bb040e34826'
STATE = Path('/var/lib/reva-release')
LEASE = Path('/run/lock/health-app-release')
RETIRED_LEASE = LEASE.with_name('health-app-release.retired-' + FAILED)
UNITS = ('health-backend.socket','health-backend.service','celery-worker.service','celery-beat.service')
FLAGS = ('HEALTH_EVIDENCE_RUNTIME_ENABLED','AUTH_PHONE_SELF_REGISTRATION_ENABLED',
         'REGISTRATION_INVITATION_ENFORCEMENT_ENABLED','REGISTRATION_INVITATION_ROLLOUT_ENABLED')
ORIGINAL_FIELDS = {'lease_stage','workspace','original_migration_intent',
    'original_runtime_journal_sha256','original_runtime_journal','previous_runtime_terminal',
    'configuration','g4_sha256','provider_reconciliation'}
EVIDENCE_FIELDS = {'attempt','old_sha','closing_sha','production_sha','recovery','workspace',
    'lease_directory','config','library','authorized','services','health_guards','launcher','build'}
CONFLICTS = ('contained-release-closures','unchanged-release-closures','retained-candidate-closures',
    'rolled-back-release-closures','native-only-closures','partial-laya-closures',
    'review-maintenance-closures','recoveries','lost-closure-receipt-acknowledgments',
    'dinner-guard-closures')
ENV = {'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LC_ALL':'C'}
META = ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')


class ClosureError(RuntimeError):
    """Only fixed secret-free error messages cross this boundary."""


def need(value, message='exam forward closure proof rejected'):
    if not value:
        raise ClosureError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':')).encode()).hexdigest()


def credential_digest(value):
    return hashlib.sha256((json.dumps(value, sort_keys=True, separators=(',',':'))+'\n').encode()).hexdigest()


def hash_string(value, length=64):
    return isinstance(value,str) and re.fullmatch('[a-f0-9]{'+str(length)+'}',value) is not None


def object_json(raw):
    def unique(pairs):
        value=dict(pairs)
        need(len(value)==len(pairs))
        return value
    try:
        value=json.loads(raw,object_pairs_hook=unique)
    except (ValueError,TypeError,UnicodeError):
        raise ClosureError('invalid protected audit JSON') from None
    need(isinstance(value,dict))
    return value


def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def write_once(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write((json.dumps(value,sort_keys=True)+'\n').encode())
        stream.flush(); os.fsync(stream.fileno())
    sync(path.parent)


def close_transaction(adapter,evidence_sha256=None,*,accept=False):
    need((evidence_sha256 is not None)==accept,'digest and fixed authorization required together')
    need(evidence_sha256 is None or hash_string(evidence_sha256))
    need(not os.path.lexists(adapter.record),'closure attempt already consumed; no retry')
    evidence=adapter.inspect()
    inspected=digest(evidence)
    if evidence_sha256 is None:
        return {'state':'INSPECTED_EXAM_FORWARD_FAILURE','attempt':ATTEMPT,'evidence_sha256':inspected}
    need(evidence_sha256==inspected,'inspection evidence changed')
    if not os.path.lexists(adapter.record.parent):
        adapter.record.parent.mkdir(mode=0o700); sync(adapter.record.parent.parent)
    adapter.record.mkdir(mode=0o700); sync(adapter.record.parent)
    receipt=secrets.token_hex(32)
    phase='intent'
    try:
        intent={**evidence,'evidence_sha256':inspected,
                'receipt_sha256':hashlib.sha256(receipt.encode()).hexdigest()}
        write_once(adapter.record/'intent.json',intent)
        adapter.closure_intent=intent
        need(adapter.inspect()==evidence,'evidence changed after intent')
        phase='synthetic_rollback_guards'
        adapter.authorized_guards(evidence)
        phase='revoke_and_rename'
        adapter.retire(evidence)
        phase='closed_verification'
        result=adapter.verify_closed(evidence)
        phase='completed'
        write_once(adapter.record/'completed.json',{'old_sha':evidence['old_sha'],'state':TERMINAL,
            'intent_sha256':digest(intent),**result})
        return {'sha':evidence['old_sha'],'state':TERMINAL,'receipt':receipt}
    except BaseException:
        write_once(adapter.record/'failure.json',{'state':'NEEDS_OPERATOR','attempt':ATTEMPT,
            'phase':phase,'automatic_retry_forbidden':True})
        raise ClosureError('closure failed; preserve original and consumed attempt; no retry') from None


def validate_terminal(value):
    transaction=hashlib.sha256(f'{PREVIOUS}:{FAILED}'.encode()).hexdigest()[:32]
    need(value=={'version':1,'mode':'code-only-no-backup','old_sha':PREVIOUS,
        'candidate_sha':FAILED,'terminal_sha':FAILED,'phase':'COMMITTED','target':'candidate',
        'result':'finalized','transaction_id':transaction,
        'reap_name':'runtime-state-transaction.reap-'+transaction})
    need(type(value['version']) is int)


def validate_health(value):
    need(isinstance(value,dict) and set(value)=={'health_score','skills_manifest'})
    score,manifest=value['health_score'],value['skills_manifest']
    need(isinstance(score,dict) and set(score)=={'score','maximum','critical_failures','runtime_pause_preserved','runtime'})
    need(type(score['score']) in (int,float) and 35<=score['score']<=60 and score['maximum']==60
         and score['critical_failures']==[] and type(score['runtime_pause_preserved']) is bool)
    detail=score['runtime']
    if score['runtime_pause_preserved']:
        match=re.fullmatch(r'paused:reconciliation_detected:generation=([0-9]+):ack=([0-9]+)',str(detail))
        need(match is not None and int(match[1])>int(match[2]))
    else:
        match=re.fullmatch(r'active:(?:none|manual_resume):generation=([0-9]+):ack=([0-9]+)',str(detail))
        need(detail in ('disabled','not_initialized') or match is not None and int(match[1])==int(match[2]))
    need(isinstance(manifest,dict) and set(manifest)=={'count','slugs_sha256'} and
         type(manifest['count']) is int and manifest['count']>0 and hash_string(manifest['slugs_sha256']))


def validate_stable(value):
    need(isinstance(value,dict) and set(value)=={'services','vision','cgroup_model_identity'})
    services,vision,models=value['services'],value['vision'],value['cgroup_model_identity']
    need(isinstance(services,dict) and set(services)==set(UNITS))
    for unit,service in services.items():
        expected={'ActiveState','SubState','MainPID','NRestarts','ActiveEnterTimestampMonotonic','ControlGroup','Result'}
        if unit.endswith('.service'): expected.add('processes')
        need(isinstance(service,dict) and set(service)==expected and service['ActiveState']=='active'
             and service['SubState'] in ({'listening','running'} if unit.endswith('.socket') else {'running'})
             and service['Result']=='success' and isinstance(service['ActiveEnterTimestampMonotonic'],str)
             and service['ActiveEnterTimestampMonotonic'].isdecimal() and int(service['ActiveEnterTimestampMonotonic'])>0
             and isinstance(service['ControlGroup'],str))
        if unit.endswith('.service'):
            need(service['ControlGroup'].startswith('/') and isinstance(service['NRestarts'],str) and service['NRestarts'].isdecimal())
    names={u.removesuffix('.service') for u in UNITS[1:]}
    need(isinstance(vision,dict) and set(vision)=={'model','history','files','services','raw_dropins'}
         and vision['model']=='qwen3.8-flash' and set(vision['services'])==names
         and isinstance(models,dict) and set(models)==names)
    for unit in UNITS[1:]:
        name=unit.removesuffix('.service'); service=services[unit]; model=vision['services'][name]
        need(isinstance(service,dict) and isinstance(service.get('processes'),dict) and service['processes'])
        pid=service.get('MainPID')
        need(isinstance(pid,str) and pid.isdecimal() and int(pid)>0 and pid in service['processes'])
        flags=model.get('authorization_flags')
        need(isinstance(flags,dict) and set(flags)==set(FLAGS) and
             all(v in (None,'true','false','1','0','True','False') for v in flags.values()) and
             flags[FLAGS[0]] in ('false','0','False'))
        need(model.get('MainPID')==pid and model.get('process_start')==service['processes'][pid])
        need(isinstance(models[name],dict) and set(models[name])==set(service['processes']))
        for child,started in service['processes'].items():
            need(child.isdecimal() and int(child)>0 and isinstance(started,str) and started.isdecimal())
            need(models[name][child]=={'start':started,'model':'qwen3.8-flash','authorization_flags':flags})


def validate_records(intent,plan,database,done,credential_intent,credential_done,provider,*,credential_binding=None):
    need(isinstance(intent,dict) and set(intent)=={'attempt','recovery_sha','failed_sha','previous_sha','original','database','evidence_sha256'})
    sha=intent['recovery_sha']; original=intent['original']; preflight=intent['database']
    need(hash_string(sha,40) and sha not in (FAILED,PREVIOUS) and intent['attempt']==RECOVERY_ATTEMPT
         and intent['failed_sha']==FAILED and intent['previous_sha']==PREVIOUS)
    need(intent['evidence_sha256']==digest({k:v for k,v in intent.items() if k!='evidence_sha256'}))
    need(isinstance(original,dict) and set(original)==ORIGINAL_FIELDS and
         original['original_runtime_journal_sha256']==JOURNAL_PIN and hash_string(original['g4_sha256'])
         and original['provider_reconciliation']==provider)
    journal=original['original_runtime_journal']
    need(credential_digest(journal)==JOURNAL_PIN, 'immutable original journal hash differs')
    need(isinstance(journal,dict) and set(journal)=={'version','mode','old_sha','candidate_sha','transaction_id','phase',
         'beat_authority','old_upload_authority','upload_authority','old_effective','original_enablement',
         'boot_gate_armed','boot_gate_released','release_target'} and all(type(journal.get(k)) is type(v) and journal.get(k)==v for k,v in {
         'version':2,'mode':'code-only-no-backup','phase':'INSTALLED','candidate_sha':FAILED,
         'old_sha':PREVIOUS,'beat_authority':'current','old_upload_authority':'external',
         'upload_authority':'external','boot_gate_armed':True,'boot_gate_released':False,'release_target':None}.items())
         and not {'snapshots','metadata'} & journal.keys())
    need(isinstance(preflight,dict) and set(preflight)=={'database_state','database_sha256','laya','dependencies','active_release_processes'}
         and preflight['database_state']=='PENDING' and preflight['active_release_processes'] is False
         and hash_string(preflight['database_sha256']))
    expected_plan={'attempt':RECOVERY_ATTEMPT,'recovery_sha':sha,'source_sha':FAILED,
        'original_intent_sha256':INTENT_PIN,'original_journal_sha256':JOURNAL_PIN,
        'evidence_sha256':intent['evidence_sha256']}
    need(plan==expected_plan and isinstance(database,dict) and set(database)=={'binding','schema_sha256'}
         and database['binding']==plan and hash_string(database['schema_sha256']))
    expected={'state':'FORWARD_RECOVERED','attempt':RECOVERY_ATTEMPT,'recovery_sha':sha,
        'production_sha':FAILED,'previous_sha':PREVIOUS,'original_release_state':'NEEDS_OPERATOR',
        'original_lease_and_authorization_preserved':True,'notification_fix_deployed':False,
        'evidence_sha256':intent['evidence_sha256'],'database':database}
    need(isinstance(done,dict) and set(done)==set(expected)|{'runtime_terminal','stable_services','health_guards'}
         and all(type(done[k]) is type(v) and done[k]==v for k,v in expected.items()))
    validate_terminal(done['runtime_terminal']); validate_stable(done['stable_services']); validate_health(done['health_guards'])
    ci,cd=credential_intent,credential_done
    need(isinstance(ci,dict) and set(ci)=={'attempt','recovery_sha','failed_sha','original','original_credential',
        'evidence_sha256','incoming_sha256','incoming_expires_at','ci_verified'})
    if credential_binding is None:
        need(ci['recovery_sha']==sha and credential_digest(ci['original'])==credential_digest(original))
        credential_sha=sha
    else:
        credential_sha=credential_binding(sha,original,ci,cd)
    need(ci['attempt']==CREDENTIAL_ATTEMPT and ci['recovery_sha']==credential_sha and ci['failed_sha']==FAILED
         and ci['ci_verified'] is True and hash_string(ci['incoming_sha256'])
         and type(ci['incoming_expires_at']) is int and ci['incoming_expires_at']>0)
    old=ci['original_credential']
    need(isinstance(old,dict) and set(old)=={'sha256','identity'} and old['sha256']==EXTERNAL_CREDENTIAL_PIN)
    identity=old['identity']
    need(isinstance(identity,dict) and set(identity)==set(META) and all(type(v) is int and v>=0 for v in identity.values())
         and identity['st_uid']==identity['st_gid']==0 and stat.S_ISREG(identity['st_mode'])
         and stat.S_IMODE(identity['st_mode'])==0o600 and identity['st_nlink']==1)
    credential_evidence={k:v for k,v in ci.items() if k not in {'evidence_sha256','incoming_sha256','incoming_expires_at','ci_verified'}}
    need(ci['evidence_sha256']==credential_digest(credential_evidence))
    expected_credential={'state':'CREDENTIAL_REPLACED','attempt':CREDENTIAL_ATTEMPT,'recovery_sha':credential_sha,'failed_sha':FAILED,
        'evidence_sha256':ci['evidence_sha256'],'credential_sha256':ci['incoming_sha256'],
        'credential_expires_at':ci['incoming_expires_at'],'ci_verified':True,
        'original_incident_preserved':True,'services_changed':False,'database_changed':False}
    need(isinstance(cd,dict) and set(cd)==set(expected_credential) and
         all(type(cd[k]) is type(v) and cd[k]==v for k,v in expected_credential.items()))


def private_directory(b,path):
    b.secure(path)
    info=path.lstat()
    need(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode)==0o700 and info.st_gid==0)


def read_record(b,path):
    b.secure(path,private=True)
    before=path.lstat(); need(before.st_size<=16*1024*1024 and before.st_nlink==1)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        opened=os.fstat(stream.fileno()); raw=stream.read(16*1024*1024+1); after=os.fstat(stream.fileno())
    named=path.lstat()
    need(len(raw)<=16*1024*1024 and all(getattr(before,k)==getattr(opened,k)==getattr(after,k)==getattr(named,k) for k in META))
    return object_json(raw),{**{k:getattr(before,k) for k in META},'sha256':hashlib.sha256(raw).hexdigest()}


def audit(b,root,names):
    private_directory(b,root)
    before=root.lstat()
    need({p.name for p in root.iterdir()}==set(names))
    values,identities={},{}
    for name in sorted(names): values[name],identities[name]=read_record(b,root/name)
    after=root.lstat()
    need({p.name for p in root.iterdir()}==set(names) and all(getattr(before,k)==getattr(after,k) for k in META))
    return values,{'directory':{k:getattr(before,k) for k in META},'files':identities}


def load(b,path,name):
    b.secure(path); need(not os.path.lexists(path.parent/'__pycache__'))
    spec=importlib.util.spec_from_file_location(name,path); module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    exec(compile(path.read_bytes(),str(path),'exec',dont_inherit=True),module.__dict__)
    return module


def recovery_evidence(b,source):
    reconciliation=load(b,source/'scripts/exam_provider_reconciliation.py','exam_close_provider')
    provider=reconciliation.historical_evidence(b)
    values,identity=audit(b,b.STATE/RECOVERY_ATTEMPT,{'intent.json','database-started.json','database-completed.json','completed.json'})
    credentials,credential_identity=audit(b,b.STATE/CREDENTIAL_ATTEMPT,{'intent.json','completed.json'})
    intent,done=values['intent.json'],values['completed.json']
    validate_records(intent,values['database-started.json'],values['database-completed.json'],done,
        credentials['intent.json'],credentials['completed.json'],provider,
        credential_binding=lambda sha,original,ci,cd: reconciliation.credential_binding_sha(sha,original,ci,cd,
            {name:identity['sha256'] for name,identity in credential_identity['files'].items()}))
    canonical=b.canonical_source(intent['recovery_sha'])
    retained=load(b,source/'scripts/retained_candidate_retirement.py','exam_close_saved_vision')
    retained.validate_archived_vision(b,source,done['stable_services']['vision'])
    recovery=load(b,source/'scripts/exam_release_recovery.py','exam_close_saved_recovery')
    overlay=done['stable_services']['vision']
    projected={**overlay,'services':{unit:{key:service[key] for key in recovery.VISION_STATIC_PROPERTIES}
        for unit,service in overlay['services'].items()}}
    need(projected==intent['original']['configuration']['vision_overlay'])
    provider_lease={k:intent['original']['lease_stage'][k] for k in ('lease','token','label','stage','started_at')}
    need(provider['lease']==provider_lease and provider['workspace']==intent['original']['workspace'])
    need(hashlib.sha256((canonical/'scripts/exam_release_recovery.py').read_bytes()).hexdigest()==
         hashlib.sha256((source/'scripts/exam_release_recovery.py').read_bytes()).hexdigest())
    g4,g4_identity=read_record(b,canonical.parent/'exam-forward-g4.json')
    need(set(g4)=={'schema','attempt','reviewed_sha','verdict','review_sha256'} and
         g4['schema']=='exam-forward-g4.v1' and g4['attempt']==RECOVERY_ATTEMPT and
         g4['reviewed_sha']==intent['recovery_sha'] and g4['verdict']=='GO' and hash_string(g4['review_sha256'])
         and g4_identity['sha256']==intent['original']['g4_sha256'])
    return intent,done,{'recovery':identity,'credential':credential_identity,'provider':provider,'g4':g4_identity}


def workspace(b):
    root=b.STATE/FAILED
    private_directory(b,root)
    expected={'bin','completed.json','deployment-started.json','deployment.log','home',
        'preparation-started.json','preparation.log','prepared.json','source','started.json'}
    need({p.name for p in root.iterdir()}==expected)
    executor=hashlib.sha256((b.canonical_source(FAILED)/'scripts/trusted_release_server.py').read_bytes()).hexdigest()
    for name,state in (('started.json','STARTED'),('preparation-started.json','PREPARING'),
        ('prepared.json','PREPARED'),('deployment-started.json','DEPLOYING'),('completed.json','NEEDS_OPERATOR')):
        expected_value={'sha':FAILED,'state':state}
        if name=='preparation-started.json': expected_value['executor_sha256']=executor
        need(read_record(b,root/name)[0]==expected_value)
    return {'executor_sha256':executor,'manifest':b._preparation_manifest(root)}


def lease_identity(b,path):
    need(path in (LEASE,RETIRED_LEASE))
    # /run/lock is the single permitted shared ancestor, never a symlink.
    for parent in reversed(path.parents):
        if parent==Path('/run/lock'):
            s=parent.lstat(); need(stat.S_ISDIR(s.st_mode) and s.st_uid==s.st_gid==0 and stat.S_IMODE(s.st_mode)==0o1777)
        else: b.secure(parent)
    info=path.lstat()
    need(stat.S_ISDIR(info.st_mode) and info.st_uid==info.st_gid==0 and stat.S_IMODE(info.st_mode)==0o700)
    need({p.name for p in path.iterdir()}=={'token','label','stage','started_at'})
    result={'lease':{'dev':info.st_dev,'ino':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,'mode':0o700}}
    contents={}
    for name in ('token','label','stage','started_at'):
        child=path/name; start=child.lstat()
        need(stat.S_ISREG(start.st_mode) and start.st_nlink==1 and start.st_uid==start.st_gid==0 and stat.S_IMODE(start.st_mode)==0o600)
        fd=os.open(child,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            opened=os.fstat(stream.fileno()); raw=stream.read(4097); after=os.fstat(stream.fileno())
        named=child.lstat()
        need(len(raw)<=4096 and all(getattr(start,k)==getattr(opened,k)==getattr(after,k)==getattr(named,k) for k in META))
        result[name]={'dev':start.st_dev,'ino':start.st_ino,'uid':start.st_uid,'gid':start.st_gid,
                      'mode':0o600,'sha256':hashlib.sha256(raw).hexdigest()}
        contents[name]=(raw,result[name])
    end=path.lstat(); need(all(getattr(info,k)==getattr(end,k) for k in META))
    return result,contents


def moved_lease(b,expected):
    need(not os.path.lexists(LEASE))
    actual,_=lease_identity(b,RETIRED_LEASE)
    need(actual==expected)


class Proof:
    """Read-only reuse of reviewed probes; never construct the recovery operator."""
    def __init__(self,source,b,server,core,recovery,check,intent,done,*,closed=False):
        self.source,self.bootstrap,self.server,self.core=source,b,server,core
        self.recovery_sha,self.check=source.parent.name,check
        self.recovery,self.intent,self.done=recovery,intent,done
        self.provider=load(b,source/'scripts/exam_provider_reconciliation.py','exam_close_live_provider')
        self.provider.assert_reconciled_competition(b)
        self.helper=load(b,source/'scripts/exam_attempts_release.py','exam_close_ddl')
        module=load(b,source/'scripts/no_backup_preflight_proof.py','exam_close_original')
        self.object_json=module._contained.object_json
        self.base_units=module._contained.RecoveryProof._units
        original=intent['original']; lease={k:original['lease_stage'][k] for k in ('lease','token','label','stage','started_at')}
        current,contents=lease_identity(b,RETIRED_LEASE if closed else LEASE)
        need(current==lease)
        raw=contents['token'][0]; need(re.fullmatch(rb'[A-Za-z0-9._:-]{1,200}\n',raw))
        self.token=raw[:-1].decode('ascii')
        self.proof=module.NoBackupPreflightProof(source,b,server,FAILED,PREVIOUS,self.token)
        if closed:
            self.proof._closed=True; self.proof._original_lease=lease; self.proof._lease_contents=contents
        self.closed=closed; self.lease_expected=lease
        self.failed_source=b.canonical_source(FAILED)
        for name in ('backend/scripts/runtime_state_release_transaction.py','scripts/contained_recovery_proof.py',
                     'scripts/no_backup_preflight_proof.py','scripts/retained_candidate_retirement.py'):
            need(self.helper.git(source,'show',f'HEAD:{name}')==
                 self.helper.git(self.failed_source,'show',f'HEAD:{name}'))
        need(self.proof._stage(self.failed_source)==original['lease_stage'])
        self.transaction=self.proof.runtime.ReleaseTransaction(self.proof.runtime.production_layout(self.proof.stage),self.proof.systemd,code_only=True)
        self.journal=original['original_runtime_journal']; recovery.validate_journal(self.journal)
        self.transaction._validate_code_only_layout(self.journal)
        self.transaction._validate_base_units()
        self.original_record=self.helper.STATE/FAILED
        self.proof._directory(self.original_record)
        need({p.name for p in self.original_record.iterdir()}=={'intent.json'})
        raw,self.intent_identity=self.proof._file(self.original_record/'intent.json',0o600)
        need(hashlib.sha256(raw).hexdigest()==INTENT_PIN and self.intent_identity==original['original_migration_intent'])
        self.old_plan=self.object_json(raw)
        need(set(self.old_plan)=={'old','candidate','checksum','lease_sha256','database_sha256'} and
             self.old_plan['old']==PREVIOUS and self.old_plan['candidate']==FAILED and
             self.old_plan['checksum']==self.helper.SQL_HASH and
             self.old_plan['lease_sha256']==hashlib.sha256(self.token.encode()).hexdigest())
        self.expected=self.helper.expected_migrations(self.failed_source)
        self.retained=load(b,source/'scripts/retained_candidate_retirement.py','exam_close_retained')
        self.vision=load(b,source/'scripts/trusted_vision_model.py','exam_close_vision')
        self.reset=self.proof.reset; self.finalized=True
        self.runtime=self.migration=None; self.db_identity=None
        self.dependencies=intent['database']['dependencies']; self.original_laya=intent['database']['laya']
        # Explicit read-only list: no apply/start/stop/commit/finalize capability.
        for name in ('_vision_static','_configuration','_dependencies','_pi_dependencies','_connect',
                     '_database','_application_guard','running_snapshot','stable','http','close'):
            setattr(self,name,MethodType(getattr(recovery.Adapter,name),self))
        self.static()

    def _authority(self):
        self.check(); self.provider.assert_reconciled_competition(self.bootstrap)
        if self.closed: moved_lease(self.bootstrap,self.lease_expected)
        else: self.proof._assert_original_lease()
        self.bootstrap._recovery_process_proof(); self.check()

    def static(self):
        self._authority()
        original=self.intent['original']
        self.reset._revision_proof(FAILED,self.failed_source,self.bootstrap)
        need(self.proof._stage(self.failed_source)==original['lease_stage'])
        need(self.proof._workspace(self.failed_source)==original['workspace'])
        need(self.proof._file(self.original_record/'intent.json',0o600)[1]==original['original_migration_intent'])
        need({p.name for p in self.original_record.iterdir()}=={'intent.json'})
        terminal=self.transaction._load_terminal_marker(); validate_terminal(terminal)
        need(terminal==self.done['runtime_terminal'])
        root=self.transaction.layout.transaction_root.parent
        need({p.name for p in root.iterdir()}=={'runtime-state-terminal.json'})
        need(self._configuration()==original['configuration'])
        self.proof._absent(self.recovery.LIVE/'backend/.env.reva-release.tmp',Path('/var/lib/reva-health-evidence-runtime/enabled.env'),Path('/run/reva-health-evidence-activation'))
        for unit in UNITS[1:]: self.proof._absent(Path('/run/systemd/system')/(unit+'.d')/'90-reva-health-evidence-activation.conf')
        self._authority()

    def database(self):
        self._authority(); self._connect()
        with self.migration.connect() as connection:
            self.helper.sql(connection,'SET TRANSACTION READ ONLY')
            self.helper.sql(connection,"SET LOCAL statement_timeout='15s'")
            need(self._database(connection)=={'database_state':'APPLIED','database_sha256':self.intent['database']['database_sha256']})
            # Original migration directory remains intent-only. committed_proof
            # reads table COMMENT/catalog/ledger, never business health rows.
            value=self.helper.committed_proof(connection,self.done['database']['binding'],self.original_record,self.runtime_role)
        need(value==self.done['database']); self._authority()
        return value

    def guards(self,*,synthetic=False):
        self.static(); self.database(); self._dependencies()
        need(self.dependencies==self.intent['database']['dependencies'])
        need(self.retained.candidate_laya(self.bootstrap,self.source,FAILED,self.journal,self.proof)==self.original_laya)
        if synthetic: self._application_guard(schema=True)
        health=self.http(); validate_health(health)
        stable=self.stable(); validate_stable(stable)
        need(stable==self.done['stable_services'] and health==self.done['health_guards'])
        self.static()
        return stable,health

    def retired(self):
        moved_lease(self.bootstrap,self.lease_expected)
        self.closed=True; self.proof._closed=True
        # Original NoBackupPreflightProof uses cached original bytes only after
        # an independent same-inode archive proof on every authority check.
        _,contents=lease_identity(self.bootstrap,RETIRED_LEASE)
        self.proof._lease_contents=contents


def installation_before(b):
    config=b._inventory(b.CONFIG,{'known_hosts','loopback.conf','authorized-release.json','loopback.pub','cloud.pub','loopback.key'})
    library=b._inventory(b.INSTALLED.parent,{b.INSTALLED.name})
    executor=hashlib.sha256((b.canonical_source(FAILED)/'scripts/trusted_release_server.py').read_bytes()).hexdigest()
    need(read_record(b,b.CONFIG/'authorized-release.json')[0]=={'sha':FAILED,'expires_at':0,'executor_sha256':executor})
    need(library[b.INSTALLED.name]['sha256']==executor)
    keys=[(b.CONFIG/name).read_text().strip() for name in ('cloud.pub','loopback.pub')]
    need(keys[0]!=keys[1])
    b.secure(b.AUTHORIZED,private=True)
    lines=b.AUTHORIZED.read_text().splitlines()
    for key,line in zip(keys,b.key_lines(0,*keys)):
        b.validate_install(FAILED,0,key,now=0)
        need([v for v in lines if key.split()[1] in v]==[line])
    return config,library,b._recovery_file_identity(b.AUTHORIZED)


class Adapter:
    def __init__(self,source,b,server,recovery,core,check,*,closed=False):
        self.source,self.b,self.server,self.recovery,self.core,self.check=source,b,server,recovery,core,check
        self.sha=source.parent.name; self.record=b.STATE/ROOT_NAME/FAILED
        self.intent,self.done,self.chain=recovery_evidence(b,source)
        need(self.sha not in (FAILED,PREVIOUS) and hash_string(self.sha,40))
        self.proof=Proof(source,b,server,core,recovery,check,self.intent,self.done,closed=closed)

    def authority(self):
        self.check(); self.proof._authority()
        for name in CONFLICTS:
            path=self.b.STATE/name/FAILED
            need(path.name not in self.server._exam_directory_names(path.parent))
        if os.path.lexists(self.record.parent):
            private_directory(self.b,self.record.parent)
            need({p.name for p in self.record.parent.iterdir()}<={FAILED})
        if os.path.lexists(self.record):
            private_directory(self.b,self.record)
            need({p.name for p in self.record.iterdir()}<={'intent.json','completed.json'})
            if getattr(self,'closure_intent',None) is not None:
                need(read_record(self.b,self.record/'intent.json')[0]==self.closure_intent)
                if os.path.lexists(self.record/'completed.json'):
                    need(getattr(self,'closure_completed',None) is not None and
                         read_record(self.b,self.record/'completed.json')[0]==self.closure_completed)
        need(recovery_evidence(self.b,self.source)[2]==self.chain)
        self.check()

    def inspect(self):
        self.authority(); need(not self.proof.closed and not os.path.lexists(RETIRED_LEASE))
        config,library,authorized=installation_before(self.b)
        stable,health=self.proof.guards()
        value={'attempt':ATTEMPT,'old_sha':FAILED,'closing_sha':self.sha,'production_sha':FAILED,
            'recovery':self.chain,'workspace':workspace(self.b),'lease_directory':self.proof.lease_expected,
            'config':config,'library':library,'authorized':authorized,'services':stable,'health_guards':health,
            'launcher':self.b._recovery_file_identity(self.b.STATE/'launcher.lock'),
            'build':None}
        need(not os.path.lexists(self.b.STATE/FAILED/'build.lock'))
        self.authority(); return value

    def authorized_guards(self,evidence):
        self.authority(); self.proof.guards(synthetic=True)
        need(self.inspect()==evidence)

    def retire(self,evidence):
        need(self.inspect()==evidence)
        b=self.b
        keys=[(b.CONFIG/name).read_text().strip() for name in ('cloud.pub','loopback.pub')]
        exact=b.key_lines(0,*keys)
        retained=b''.join(line for line in b.AUTHORIZED.read_bytes().splitlines(keepends=True)
            if line.decode().rstrip('\r\n') not in exact)
        need(b._recovery_file_identity(b.AUTHORIZED)==evidence['authorized'])
        self.authority(); b._replace_authorized(retained)
        need(b.AUTHORIZED.read_bytes()==retained)
        self.authority()
        need(b._inventory(b.CONFIG,evidence['config'].keys()-{'.'})==evidence['config'])
        (b.CONFIG/'loopback.key').unlink(); sync(b.CONFIG)
        expected={'config':{k:v for k,v in evidence['config'].items() if k!='loopback.key'},'library':evidence['library']}
        need(b._installation_evidence(FAILED,b.CONFIG,b.INSTALLED.parent)==expected)
        self.proof.guards(); self.authority()
        need(lease_identity(b,LEASE)[0]==evidence['lease_directory'] and not os.path.lexists(RETIRED_LEASE))
        b.secure(Path('/usr/bin/mv'))
        need(LEASE.lstat().st_dev==LEASE.parent.lstat().st_dev)
        subprocess.run(['/usr/bin/mv','--no-clobber','-T','--',str(LEASE),str(RETIRED_LEASE)],
            env=ENV,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=15)
        sync(LEASE.parent); moved_lease(b,evidence['lease_directory'])
        self.proof.retired(); self.authority()

    def verify_closed(self,evidence):
        self.authority(); moved_lease(self.b,evidence['lease_directory'])
        need(workspace(self.b)==evidence['workspace'])
        stable,health=self.proof.guards()
        need(stable==evidence['services'] and health==evidence['health_guards'])
        expected={'config':{k:v for k,v in evidence['config'].items() if k!='loopback.key'},'library':evidence['library']}
        need(self.b._installation_evidence(FAILED,self.b.CONFIG,self.b.INSTALLED.parent)==expected)
        self.authority()
        return {'installation':expected}

    def close(self): self.proof.close()


def inventory_contract(value,names):
    need(isinstance(value,dict) and set(value)==set(names)|{'.'})
    for name,item in value.items():
        need(isinstance(item,dict) and set(item)=={'uid','gid','mode','inode','device','sha256'}
             and all(type(item[k]) is int and item[k]>=0 for k in ('uid','gid','mode','inode','device'))
             and item['uid']==item['gid']==0 and item['inode']>0
             and item['mode']==(0o700 if name=='.' else 0o600)
             and (item['sha256'] is None if name=='.' else hash_string(item['sha256'])))


def validate_closure(intent,done):
    need(isinstance(intent,dict) and set(intent)==EVIDENCE_FIELDS|{'evidence_sha256','receipt_sha256'})
    need(intent['attempt']==ATTEMPT and intent['old_sha']==intent['production_sha']==FAILED
         and hash_string(intent['closing_sha'],40) and intent['closing_sha'] not in (FAILED,PREVIOUS)
         and hash_string(intent['receipt_sha256']) and intent['build'] is None)
    need(intent['evidence_sha256']==digest({k:v for k,v in intent.items() if k in EVIDENCE_FIELDS}))
    validate_stable(intent['services']); validate_health(intent['health_guards'])
    need(isinstance(intent['config'],dict) and set(intent['config'])=={
        '.','known_hosts','loopback.conf','authorized-release.json','loopback.pub','cloud.pub','loopback.key'})
    inventory_contract(intent['config'],{'known_hosts','loopback.conf','authorized-release.json','loopback.pub','cloud.pub','loopback.key'})
    inventory_contract(intent['library'],{'trusted_release_server.py'})
    expected={'config':{k:v for k,v in intent['config'].items() if k!='loopback.key'},'library':intent['library']}
    need(done=={'old_sha':FAILED,'state':TERMINAL,'intent_sha256':digest(intent),'installation':expected})
    return {'state':TERMINAL,'closure':digest(done),'workspace':intent['workspace']}


def retired_history(b,intent,done,workspace_result,*,pending=None):
    """No-copy successor proof without _retired_history recursion or live files."""
    path=b.STATE/'retired'/FAILED
    if not os.path.lexists(path): return False
    records,_=audit(b,path,{'intent.json'} if pending is not None else {'intent.json','completed.json'})
    old=records['intent.json']
    if pending is not None:
        need(old==pending)
        need(b._installation_evidence(FAILED,b.CONFIG,b.INSTALLED.parent)==done['installation'])
    need(set(old)-{'cloud_key_reused'}=={'old_sha','new_sha','installation','workspace','retirement_policy','public_keys','recovery_receipt'})
    need('cloud_key_reused' not in old or old['cloud_key_reused'] is True)
    need(old['old_sha']==FAILED and hash_string(old['new_sha'],40) and old['new_sha']!=FAILED
         and old['installation']==done['installation'] and old['workspace']==workspace_result
         and old['retirement_policy']=='no-backup-v1' and hash_string(old['recovery_receipt'])
         and secrets.compare_digest(hashlib.sha256(old['recovery_receipt'].encode()).hexdigest(),intent['receipt_sha256']))
    if pending is None:
        need(records['completed.json']=={'old_sha':FAILED,'new_sha':old['new_sha'],'state':'RETIRED'})
    need(not any(os.path.lexists(path) for path in b._archives(FAILED)))
    # Existing helper validates exact public-key schema and both saved hashes.
    keys=b._retired_public_keys(FAILED,old)
    need(set(keys)=={'cloud.pub','loopback.pub'} and keys['cloud.pub']!=keys['loopback.pub'])
    for public in keys.values(): b.validate_install(FAILED,1,public,now=0)
    return True


def _history_evidence(b,*,pending=None):
    root=b.STATE/ROOT_NAME
    private_directory(b,root); need({p.name for p in root.iterdir()}=={FAILED})
    values,closure_identity=audit(b,root/FAILED,{'intent.json','completed.json'})
    intent,done=values['intent.json'],values['completed.json']
    result=validate_closure(intent,done)
    source=b.canonical_source(intent['closing_sha'])
    original,recovered,chain=recovery_evidence(b,source)
    need(chain==intent['recovery'] and recovered['stable_services']==intent['services']
         and recovered['health_guards']==intent['health_guards'] and workspace(b)==intent['workspace'])
    need(intent['lease_directory']=={k:original['original']['lease_stage'][k]
        for k in ('lease','token','label','stage','started_at')})
    need(b._recovery_file_identity(b.STATE/'launcher.lock')==intent['launcher']
         and not os.path.lexists(b.STATE/FAILED/'build.lock'))
    retired=retired_history(b,intent,done,result,pending=pending)
    need(pending is None or retired)
    provider=load(b,source/'scripts/exam_provider_reconciliation.py','exam_close_historical_provider')
    server=load(b,source/'scripts/trusted_release_server.py','exam_close_historical_server')
    # Only the verified no-copy retirement is a permitted competing record.
    for name in server.EXAM_COMPETING_RECORDS:
        path=b.STATE/name
        if name=='retired/'+FAILED and retired: continue
        need(path.name not in server._exam_directory_names(path.parent))
    for path in server.EXAM_RETIRED_INSTALLATIONS:
        need(path.name not in server._exam_directory_names(path.parent))
    for name in CONFLICTS:
        path=b.STATE/name/FAILED; need(path.name not in server._exam_directory_names(path.parent))
    need({n for n in server._exam_directory_names(provider.REFRESH_ROOT) if n.startswith('exam-')}=={'exam-'+provider.PUBLISHER})
    need(not any(n.startswith('credential.exam-') for n in server._exam_directory_names(server.EXAM_CREDENTIAL_ROOT)))
    need(provider.historical_evidence(b)==chain['provider'])
    # Directory hashes bind all originals; mutable current credential, config,
    # services, /run lease and /tmp stage are deliberately not read in history.
    need(audit(b,root/FAILED,{'intent.json','completed.json'})==(values,closure_identity))
    return result


def history_evidence(b):
    return _history_evidence(b)


def validate_pending_rotation(b,immutable_intent):
    """Only the locked pre-discard boundary may use this exact intent proof."""
    need(isinstance(immutable_intent,dict) and hash_string(immutable_intent.get('new_sha'),40))
    source=b.canonical_source(immutable_intent['new_sha'])
    need(Path(b.__file__).absolute()==source/'scripts/bootstrap_trusted_release.py')
    return _history_evidence(b,pending=immutable_intent)


def closed_evidence(b,sha,receipt,*,historical=False):
    need(sha==FAILED and hash_string(receipt))
    result=history_evidence(b)
    values,_=audit(b,b.STATE/ROOT_NAME/FAILED,{'intent.json','completed.json'})
    intent=values['intent.json']
    need(secrets.compare_digest(hashlib.sha256(receipt.encode()).hexdigest(),intent['receipt_sha256']))
    if not historical:
        source=b.canonical_source(intent['closing_sha'])
        recovery=load(b,source/'scripts/exam_release_recovery.py','exam_closed_recovery')
        core=load(b,source/'scripts/recover_contained_services.py','exam_closed_core')
        _,server=b.reviewed_source(intent['closing_sha'])
        def check():
            need(b._recovery_file_identity(b.STATE/'launcher.lock')==intent['launcher'])
            need(not os.path.lexists(b.STATE/FAILED/'build.lock'))
        adapter=Adapter(source,b,server,recovery,core,check,closed=True)
        adapter.closure_intent=intent; adapter.closure_completed=values['completed.json']
        try: adapter.verify_closed({k:v for k,v in intent.items() if k in EVIDENCE_FIELDS})
        finally: adapter.close()
    return result


def context(sha):
    need(os.geteuid()==0 and sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
         and not sys.flags.optimize and sys.executable=='/usr/bin/python3.12'
         and 'SSH_ORIGINAL_COMMAND' not in os.environ)
    need(hash_string(sha,40) and sha not in (FAILED,PREVIOUS))
    source=STATE/'bootstrap'/sha/'source'; entry=source/'scripts/exam_forward_retirement.py'
    need(Path(__file__).absolute()==entry)
    dependency=entry.with_name('exam_release_recovery.py')
    for path in [*reversed(entry.parents),entry,dependency]:
        info=path.lstat()
        need(info.st_uid==0 and not info.st_mode&0o022 and
             (stat.S_ISDIR(info.st_mode) if path in entry.parents else stat.S_ISREG(info.st_mode) and info.st_nlink==1))
    need(not os.path.lexists(entry.parent/'__pycache__'))
    spec=importlib.util.spec_from_file_location('exam_close_context',dependency)
    recovery=importlib.util.module_from_spec(spec)
    exec(compile(dependency.read_bytes(),str(dependency),'exec',dont_inherit=True),recovery.__dict__)
    checked,b,server=recovery.context(sha,verify_ci=False)
    need(checked==source)
    return recovery,source,b,server


def main():
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--sha',required=True)
    parser.add_argument('--github-token-stdin',required=True,action='store_true')
    parser.add_argument('--evidence-sha256')
    parser.add_argument('--accept-exam-a8-forward-close-v1',action='store_true')
    args=parser.parse_args()
    need((args.evidence_sha256 is not None)==args.accept_exam_a8_forward_close_v1)
    recovery,source,b,server=context(args.sha)
    raw=sys.stdin.buffer.read(4097); need(re.fullmatch(rb'[A-Za-z0-9_.-]{1,4096}',raw))
    subprocess.run(['/usr/bin/python3.12','-I','-S','-B',str(source/'scripts/trusted_release_gate.py'),
        '--sha',args.sha,'--workflow-sha',args.sha,'--token-stdin'],input=raw,env=recovery.ENV,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=90)
    del raw
    os.umask(0o077)
    core=load(b,source/'scripts/recover_contained_services.py','exam_close_core')
    provider=load(b,source/'scripts/exam_provider_reconciliation.py','exam_close_locked_provider')
    launcher=b.STATE/'launcher.lock'; b.secure(launcher,private=True)
    fd=os.open(launcher,os.O_RDWR|os.O_NOFOLLOW); build=provider_fd=adapter=None
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        build=b._acquire_existing_build_lock(FAILED)
        provider_fd,provider_check=provider.acquire_provider_lock(b)
        def check():
            b._assert_original_lock(launcher,fd)
            core._check_original_build_lock(b,FAILED,build); provider_check()
        check(); b._recovery_process_proof()
        adapter=Adapter(source,b,server,recovery,core,check)
        result=close_transaction(adapter,args.evidence_sha256,accept=args.accept_exam_a8_forward_close_v1)
        check(); print(json.dumps(result,sort_keys=True))
    finally:
        if adapter is not None: adapter.close()
        if provider_fd is not None: os.close(provider_fd)
        if build is not None: os.close(build)
        os.close(fd)


if __name__=='__main__':
    try: main()
    except Exception:
        print('EXAM_FORWARD_CLOSURE_BLOCKED: preserve original and consumed attempt; no retry',file=sys.stderr)
        raise SystemExit(70) from None
