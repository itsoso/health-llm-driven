"""Read-only reconciliation of one byte-pinned completed external refresh.

This consumes historical evidence without executing its old CLI or claiming a
live token issuance. Ordinary publication history continues to reject it. Only
the separately reviewed fixed incident consumers call this module.
"""
from __future__ import annotations
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat

PUBLISHER='3127c8678bec90e57cc05f359e629f072e0d133f'
FAILED='a8cd1e7635eb697c0f0bc528382c98b3602893c3'
REFRESH_ROOT=Path('/var/lib/reva-github-api/refresh')
PROVIDER_LOCK=Path('/var/lib/reva-github-api/provider-refresh.lock')
CREDENTIAL=Path('/etc/reva-github-api/credential.json')
SOURCE_PIN='088e1b7b9e00f5c365a83a17d2b3b9cd6d251c3a26d2ae007a43d95b94b01f87'
PINS={'intent.json':'6ef77cc7ee895c9ab5a4cb96dda606397293e306a3c29d968ff7591f171dff35',
      'completed.json':'c349dba585209cfb31a296b994c9a3540665b02026bad4ee700986eae024541d'}
PIN_METADATA={
 '.':{'uid':0,'gid':0,'mode':0o700,'size':4096,'nlink':2,'ino':17472919,'mtime_ns':1793118086820344549,'ctime_ns':1793118086820344549},
 'intent.json':{'uid':0,'gid':0,'mode':0o600,'size':2769,'nlink':1,'ino':17472920,'mtime_ns':1793117997456248933,'ctime_ns':1793117997456248933},
 'completed.json':{'uid':0,'gid':0,'mode':0o600,'size':2775,'nlink':1,'ino':17472921,'mtime_ns':1793118086820344549,'ctime_ns':1793118086820344549}}
SAFE_FIELDS={'publisher_sha':PUBLISHER,'failed_sha':FAILED,'repository':'itsoso/health-llm-driven',
 'app_id':5376682,'installation_id':172918270,'permissions':{'actions':'read','contents':'read','metadata':'read'},
 'provider_sha256':'3d3d5c7fed2c28bd106543a6c2c7fa58b5e3feb7620f03c7605d2d0d1b6cb399',
 'before_sha256':'e3b759a2e51b676de917501d2466f0f6de793c6d3bf9ddaa95b62fd1239e02a8',
 'after_sha256':'699aa3167a7b44ba74309e265add3ff34433c25116b85fd019aa3bb040e34826',
 'expires_at':1793121501}
LEASE_KEYS={'lease','label','stage','started_at','token'}
WORKSPACE_KEYS={'directory','completed.json','deployment-started.json','deployment.log','executor','inventory',
 'policy','preparation-started.json','preparation.log','prepared.json','started.json'}
WORKSPACE_INVENTORY={'bin','completed.json','deployment-started.json','deployment.log','home',
 'preparation-started.json','preparation.log','prepared.json','source','started.json'}


class ReconciliationError(RuntimeError): pass


def need(value,message='fixed external provider reconciliation rejected'):
    if not value: raise ReconciliationError(message)


def root_ids(info): return info.st_uid==0 and info.st_gid==0


def metadata(info):
    return {'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode),'size':info.st_size,
            'nlink':info.st_nlink,'ino':info.st_ino,'mtime_ns':info.st_mtime_ns,'ctime_ns':info.st_ctime_ns}


def load_sibling(bootstrap,name):
    path=Path(__file__).with_name(name+'.py')
    bootstrap.secure(Path(__file__)); bootstrap.secure(path)
    need(not os.path.lexists(path.parent/'__pycache__'),'cached reconciliation code rejected')
    spec=importlib.util.spec_from_file_location('exam_reconciliation_'+name,path)
    module=importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(),str(path),'exec',dont_inherit=True),module.__dict__)
    return module


def directory_type(bootstrap):
    return load_sibling(bootstrap,'exam_recovery_credential').SecureDirectory


def unique(pairs):
    result=dict(pairs); need(len(result)==len(pairs),'duplicate external receipt fields'); return result


def parsed(raw):
    try: return json.loads(raw,object_pairs_hook=unique)
    except Exception: raise ReconciliationError('external receipt JSON rejected') from None


def names(directory):
    directory.check(); before=os.fstat(directory.fd); result=set()
    with os.scandir(directory.fd) as entries:
        for entry in entries:
            result.add(entry.name); need(len(result)<=10000,'external inventory exceeds bound')
    need(metadata(os.fstat(directory.fd))==metadata(before),'external inventory changed')
    directory.check(); return result


def metadata_map(value,keys,directory_key):
    need(isinstance(value,dict) and set(value)==keys)
    for key,item in value.items():
        if key=='inventory':
            need(type(item) is list and item==sorted(WORKSPACE_INVENTORY)); continue
        fields={'dev','ino','uid','gid','mode'} | (set() if key==directory_key else {'sha256'})
        need(isinstance(item,dict) and set(item)==fields)
        need(all(type(item[k]) is int and item[k]>=0 for k in ('dev','ino','uid','gid','mode')))
        need(item['ino']>0 and item['uid']==item['gid']==0 and item['mode']==(0o700 if key==directory_key else 0o600))
        if key!=directory_key: need(isinstance(item['sha256'],str) and re.fullmatch('[a-f0-9]{64}',item['sha256']))


def records(intent,completed):
    required=set(SAFE_FIELDS)|{'state','lease','workspace'}
    for value,state in ((intent,'REFRESH_INTENT'),(completed,'CREDENTIAL_REFRESHED')):
        need(isinstance(value,dict) and set(value)==required and value['state']==state)
        need(all(type(value[k]) is type(v) and value[k]==v for k,v in SAFE_FIELDS.items()))
        metadata_map(value['lease'],LEASE_KEYS,'lease'); metadata_map(value['workspace'],WORKSPACE_KEYS,'directory')
    need({k:v for k,v in intent.items() if k!='state'}=={k:v for k,v in completed.items() if k!='state'})


def historical_evidence(bootstrap,proof=None):
    """Never read current credential; optional proof compares live lease/workspace."""
    try:
        directory=directory_type(bootstrap)
        source=bootstrap.canonical_source(PUBLISHER)
        with directory(source/'scripts') as code:
            raw,code_id=code.read('exam_provider_refresh.py',private=False,max_bytes=1000000)
            need(hashlib.sha256(raw).hexdigest()==SOURCE_PIN and root_ids(os.stat('exam_provider_refresh.py',dir_fd=code.fd,follow_symlinks=False)), 'external provider canonical source differs')
            with directory(REFRESH_ROOT/('exam-'+PUBLISHER)) as audit:
                need(names(audit)==set(PINS) and metadata(os.fstat(audit.fd))==PIN_METADATA['.'])
                need(root_ids(os.fstat(audit.fd)))
                raw_records={}; identities={}
                for name,pin in PINS.items():
                    raw_records[name],identities[name]=audit.read(name)
                    info=os.stat(name,dir_fd=audit.fd,follow_symlinks=False)
                    need(root_ids(info) and metadata(info)==PIN_METADATA[name])
                    need(hashlib.sha256(raw_records[name]).hexdigest()==pin,'external receipt raw hash differs')
                intent,completed=(parsed(raw_records[name]) for name in ('intent.json','completed.json'))
                records(intent,completed)
                if proof is not None:
                    need(proof._lease_snapshot()==intent['lease'],'external receipt original lease differs')
                    need(proof._workspace(bootstrap.canonical_source(FAILED))==intent['workspace'],'external receipt original workspace differs')
                for name in PINS:
                    again,identity=audit.read(name)
                    need(again==raw_records[name] and identity==identities[name],'external receipt changed during proof')
                need(names(audit)==set(PINS) and metadata(os.fstat(audit.fd))==PIN_METADATA['.'])
                again,identity=code.read('exam_provider_refresh.py',private=False,max_bytes=1000000)
                need(identity==code_id and hashlib.sha256(again).hexdigest()==SOURCE_PIN)
                return {'schema':'exam-provider-reconciliation.v1','publisher_sha':PUBLISHER,'failed_sha':FAILED,
                    'intent_sha256':PINS['intent.json'],'completed_sha256':PINS['completed.json'],
                    'provider_source_sha256':SOURCE_PIN,'receipt_identity':identities,
                    'credential_before_sha256':intent['before_sha256'],'credential_after_sha256':intent['after_sha256'],
                    'credential_expires_at':intent['expires_at'],'lease':intent['lease'],'workspace':intent['workspace']}
    except Exception:
        raise ReconciliationError('external provider history incomplete or changed') from None


def assert_reconciled_competition(bootstrap):
    """Fixed incident-only consumer; no caller-selected allowlist or skip flag."""
    try:
        server=load_sibling(bootstrap,'trusted_release_server')
        before=historical_evidence(bootstrap)
        paths=[*(bootstrap.STATE/name for name in server.EXAM_COMPETING_RECORDS), *server.EXAM_RETIRED_INSTALLATIONS]
        for path in paths:
            need(path.name not in server._exam_directory_names(path.parent),'competing exam recovery evidence exists')
        provider_names=server._exam_directory_names(REFRESH_ROOT)
        need({name for name in provider_names if name.startswith('exam-')}=={'exam-'+PUBLISHER},'unreconciled exam provider history exists')
        need(not any(name.startswith('credential.exam-') for name in server._exam_directory_names(server.EXAM_CREDENTIAL_ROOT)), 'competing exam credential artifact exists')
        need(historical_evidence(bootstrap)==before,'external provider history changed')
        return before
    except Exception:
        raise ReconciliationError('competing or unreconciled exam recovery evidence exists') from None


def validate_current_credential(bootstrap):
    """Initial fixed old-file admission only; token bytes never leave this scope."""
    try:
        with directory_type(bootstrap)(CREDENTIAL.parent) as directory:
            raw,identity=directory.read(CREDENTIAL.name)
            need(root_ids(os.stat(CREDENTIAL.name,dir_fd=directory.fd,follow_symlinks=False)))
            need(hashlib.sha256(raw).hexdigest()==SAFE_FIELDS['after_sha256'])
            value=parsed(raw)
            need(isinstance(value,dict) and set(value)=={'repository','expires_at','token'} and
                 value['repository']==SAFE_FIELDS['repository'] and type(value['expires_at']) is int and
                 value['expires_at']==SAFE_FIELDS['expires_at'] and isinstance(value['token'],str) and
                 re.fullmatch('[A-Za-z0-9_.-]{1,4096}',value['token']))
            again,after=directory.read(CREDENTIAL.name)
            need(again==raw and after==identity)
            return {'sha256':hashlib.sha256(raw).hexdigest(),'identity':identity}
    except Exception:
        raise ReconciliationError('fixed external credential readback rejected') from None


def acquire_provider_lock(bootstrap):
    """Acquire an existing lock only; return fd and an identity recheck callable."""
    directory=directory_type(bootstrap); fd=None
    try:
        with directory(PROVIDER_LOCK.parent) as parent:
            info=os.stat(PROVIDER_LOCK.name,dir_fd=parent.fd,follow_symlinks=False)
            need(root_ids(info) and stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1)
            fd=os.open(PROVIDER_LOCK.name,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent.fd)
            need(metadata(os.fstat(fd))==metadata(info)); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB); parent.check()
        def check():
            with directory(PROVIDER_LOCK.parent) as parent:
                current=os.stat(PROVIDER_LOCK.name,dir_fd=parent.fd,follow_symlinks=False)
                need(metadata(current)==metadata(info)==metadata(os.fstat(fd)),'provider lock identity changed')
        check(); return fd,check
    except Exception:
        if fd is not None: os.close(fd)
        raise ReconciliationError('original provider lock unavailable or changed') from None


def validate_recovery_credential(bootstrap,recovery_sha,original):
    """A replaced token without our complete bound receipt is not recovery authority."""
    try:
        need(isinstance(recovery_sha,str) and re.fullmatch('[a-f0-9]{40}',recovery_sha))
        directory=directory_type(bootstrap)
        with directory(bootstrap.STATE/'exam-a8-read-credential-v1') as audit:
            before=metadata(os.fstat(audit.fd))
            need(root_ids(os.fstat(audit.fd)) and before['mode']==0o700 and names(audit)=={'intent.json','completed.json'})
            raw={}; ids={}
            for name in ('intent.json','completed.json'):
                raw[name],ids[name]=audit.read(name,max_bytes=1000000)
                need(root_ids(os.stat(name,dir_fd=audit.fd,follow_symlinks=False)))
            intent=parsed(raw['intent.json']); complete=parsed(raw['completed.json'])
            evidence_keys={'attempt','recovery_sha','failed_sha','original','original_credential'}
            need(isinstance(intent,dict) and set(intent)==evidence_keys|{'evidence_sha256','incoming_sha256','incoming_expires_at','ci_verified'})
            evidence={key:intent[key] for key in evidence_keys}
            encoded=(json.dumps(evidence,sort_keys=True,separators=(',',':'))+'\n').encode()
            evidence_hash=hashlib.sha256(encoded).hexdigest()
            need(intent['attempt']=='exam-a8-read-credential-v1' and intent['recovery_sha']==recovery_sha and
                 intent['failed_sha']==FAILED and intent['original']==original and intent['ci_verified'] is True and
                 intent['evidence_sha256']==evidence_hash and type(intent['incoming_expires_at']) is int and
                 isinstance(intent['incoming_sha256'],str) and re.fullmatch('[a-f0-9]{64}',intent['incoming_sha256']))
            need(isinstance(original,dict) and original.get('provider_reconciliation')==historical_evidence(bootstrap))
            old=intent['original_credential']; fields={'st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns'}
            need(isinstance(old,dict) and set(old)=={'sha256','identity'} and old['sha256']==SAFE_FIELDS['after_sha256'])
            old_id=old['identity'];need(isinstance(old_id,dict) and set(old_id)==fields and all(type(v) is int and v>=0 for v in old_id.values()))
            need(old_id['st_uid']==old_id['st_gid']==0 and stat.S_ISREG(old_id['st_mode']) and stat.S_IMODE(old_id['st_mode'])==0o600 and old_id['st_nlink']==1)
            expected={'state':'CREDENTIAL_REPLACED','attempt':intent['attempt'],'recovery_sha':recovery_sha,'failed_sha':FAILED,
              'evidence_sha256':evidence_hash,'credential_sha256':intent['incoming_sha256'],
              'credential_expires_at':intent['incoming_expires_at'],'ci_verified':True,
              'original_incident_preserved':True,'services_changed':False,'database_changed':False}
            need(type(complete) is dict and set(complete)==set(expected) and all(type(complete[k]) is type(v) and complete[k]==v for k,v in expected.items()))
            with directory(CREDENTIAL.parent) as credential:
                current,current_id=credential.read(CREDENTIAL.name)
                need(root_ids(os.stat(CREDENTIAL.name,dir_fd=credential.fd,follow_symlinks=False)))
                value=parsed(current)
                need(hashlib.sha256(current).hexdigest()==expected['credential_sha256'] and isinstance(value,dict) and
                     set(value)=={'repository','token','expires_at'} and value['repository']==SAFE_FIELDS['repository'] and
                     type(value['expires_at']) is int and value['expires_at']==expected['credential_expires_at'] and
                     isinstance(value['token'],str) and re.fullmatch('[A-Za-z0-9_.-]{1,4096}',value['token']))
                for name in raw:
                    again,identity=audit.read(name,max_bytes=1000000)
                    need(again==raw[name] and identity==ids[name])
                again,identity=credential.read(CREDENTIAL.name);need(again==current and identity==current_id)
            need(names(audit)==set(raw) and metadata(os.fstat(audit.fd))==before)
            return {'intent_sha256':hashlib.sha256(raw['intent.json']).hexdigest(),
                    'completed_sha256':hashlib.sha256(raw['completed.json']).hexdigest(),
                    'credential_sha256':expected['credential_sha256']}
    except Exception:
        raise ReconciliationError('complete fixed credential recovery evidence required') from None
