"""Read-only reuse of a sealed, already installed Laya generation.

No environment copies, installation, restart, generation writes or inference.
The immutable install.py remains byte-identical because it participates in the
original generation digest. Only the fixed local health GET is performed.
"""
import argparse
import grp
import hashlib
import hmac
import importlib.util
import json
import os
import re
import shlex
import stat
import sys
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

BASE = Path('/var/lib/reva-laya-release')
LIVE_ENV = Path('/opt/health-app/backend/.env')
PROC = Path('/proc')
STAGE_PATTERN = r'/tmp/health-app-backup-preflight-[A-Za-z0-9._-]+'
ASSETS = ('install.py', 'serve.py', 'model-manifest.json', 'requirements.lock', 'reva-laya.service.in', 'encoder-config.json.b64', 'rl-agent-config.json.b64', 'tokenizer-config.json.b64', 'model-NOTICE.txt')
STAGED = ('backup_db.sh','verify_backup_restore.sh','archive_backup_offsite.sh','verify_recent_offsite_backup.sh','rollback_release.sh','activate_health_evidence_runtime.sh','verify_locked_requirements.py','verify_runtime_schema_compatibility.py','quarantine_runtime_only_kb.py','runtime_state_release_transaction.py','review_manifest.json','health-backend-runtime-state.conf','celery-worker-runtime-state.conf','celery-beat-runtime-state.conf')


class VerificationError(RuntimeError):
    """Static diagnostics only; never disclose configuration or credentials."""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def secure(path, *, mode=None):
    for item in (path, *path.parents):
        info = item.lstat()
        shared_tmp = item != path and item == Path('/tmp') and stat.S_IMODE(info.st_mode) == 0o1777
        if (stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or (info.st_mode & 0o022 and not shared_tmp)
                or not (stat.S_ISDIR(info.st_mode) or item == path and stat.S_ISREG(info.st_mode) and info.st_nlink == 1)):
            raise VerificationError('unsafe_laya_verification_path')
    if mode is not None and stat.S_IMODE(path.lstat().st_mode) != mode:
        raise VerificationError('unexpected_laya_verification_mode')


def identity(path):
    value = path.lstat()
    return (value.st_dev,value.st_ino,value.st_mode,value.st_uid,value.st_gid,value.st_nlink,value.st_size,value.st_mtime_ns,value.st_ctime_ns)


def read(path, *, mode=None, limit=1_000_000):
    secure(path, mode=mode)
    before = identity(path)
    if not stat.S_ISREG(before[2]) or before[5] != 1 or before[6] > limit:
        raise VerificationError('invalid_laya_verification_file')
    with path.open('rb') as stream:
        raw = stream.read(limit+1)
    if len(raw)>limit or identity(path)!=before:
        raise VerificationError('laya_verification_file_changed')
    return raw, before


def object_json(raw):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise VerificationError('duplicate_laya_evidence_field')
            result[key]=value
        return result
    result=json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(result,dict): raise VerificationError('invalid_laya_evidence')
    return result


def load_installer(source):
    path=source/'install.py';read(path,mode=0o400)
    if os.path.lexists(source/'__pycache__'): raise VerificationError('cached_laya_code_forbidden')
    spec=importlib.util.spec_from_file_location('unchanged_laya_installer',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def generation_digest(source):
    return digest(b''.join(name.encode()+b'\0'+(source/name).read_bytes() for name in ASSETS))


def context(args):
    if sys.platform!='linux' or os.geteuid()!=0 or not re.fullmatch(r'[0-9a-f]{40}',args.sha):
        raise VerificationError('unsupported_laya_verification_context')
    source=BASE/'sources'/args.sha;secure(source,mode=0o700)
    raw,source_identity=read(source/'source.json',mode=0o400)
    proof=object_json(raw)
    if (set(proof)!={'sha','old_sha','old_has_decisions','files'} or proof['sha']!=args.sha
            or not isinstance(proof['old_sha'],str) or not re.fullmatch(r'[0-9a-f]{40}',proof['old_sha'])
            or type(proof['old_has_decisions']) is not bool or not isinstance(proof['files'],dict)
            or set(proof['files'])!=set(ASSETS) or {p.name for p in source.iterdir()}!=set(ASSETS)|{'source.json'}):
        raise VerificationError('laya_source_binding')
    identities={'source':source_identity}
    for name in ASSETS:
        data,identities[name]=read(source/name,mode=0o400)
        if digest(data)!=proof['files'][name]: raise VerificationError('laya_source_hash')
    installer=load_installer(source)
    if tuple(installer.ASSETS)!=ASSETS: raise VerificationError('laya_asset_contract')
    lock=installer.resolve_business_lease(args.lock)
    installer.secure(lock,mode=0o700,shared_parent=installer.LEASE_SHARED)
    stage=Path(args.stage)
    if re.fullmatch(STAGE_PATTERN,str(stage)) is None: raise VerificationError('laya_stage_path')
    secure(stage,mode=0o700)
    for name,expected in [('token',args.token+'\n'),('stage',str(stage)+'\n')]:
        installer.secure(lock/name,mode=0o600,shared_parent=installer.LEASE_SHARED)
        before=identity(lock/name);data=(lock/name).read_bytes()
        if identity(lock/name)!=before or not hmac.compare_digest(data,expected.encode()):
            raise VerificationError('laya_release_lease_mismatch')
        identities['lease_'+name]=before
    if {p.name for p in stage.iterdir()} != set(STAGED)|{'staged.sha256'}:
        raise VerificationError('laya_no_copy_stage_inventory')
    manifest,identities['manifest']=read(stage/'staged.sha256',mode=0o400)
    hashes={}
    for line in manifest.splitlines():
        match=re.fullmatch(rb'([0-9a-f]{64})  ([A-Za-z0-9._-]+)',line)
        if not match or match[2].decode() in hashes: raise VerificationError('laya_stage_manifest')
        hashes[match[2].decode()]=match[1].decode()
    if set(hashes)!=set(STAGED): raise VerificationError('laya_stage_manifest_inventory')
    for name,expected in hashes.items():
        data,identities['stage_'+name]=read(stage/name)
        if digest(data)!=expected: raise VerificationError('laya_stage_hash')
    env,identities['env']=read(LIVE_ENV,mode=0o640)
    if LIVE_ENV.stat().st_gid!=grp.getgrnam('health-app').gr_gid: raise VerificationError('laya_env_group')
    text=env.decode()
    for line in text.splitlines():
        if line.rstrip().endswith('\\'): raise VerificationError('noncanonical_laya_config')
        try: shlex.split(line,comments=True,posix=True)
        except ValueError: raise VerificationError('noncanonical_laya_config') from None
        if re.match(r'\s*(?:export\s+)?DECISION_',line) and not re.fullmatch(r'DECISION_[A-Z0-9_]+=[^\s]*',line):
            raise VerificationError('noncanonical_laya_config')
    config=installer.parse_config(text)
    if config is None: raise VerificationError('code_only_requires_existing_laya')
    identities['env_sha256']=digest(env)
    return {'source':source,'config':config,'identities':identities,'installer':installer}


def health_get():
    with build_opener(ProxyHandler({})).open('http://127.0.0.1:8092/health',timeout=5) as response:
        if response.status!=200: raise VerificationError('laya_health_status')
        raw=response.read(4097)
    if len(raw)>4096 or object_json(raw)!={'status':'ok','loaded':['multilingual'],'device':'cpu'}:
        raise VerificationError('laya_health_contract')


def process_binding(installer,generation,config):
    fields=installer.service_identity(generation)
    if fields.get('NRestarts')!='0': raise VerificationError('laya_service_restarted')
    proc=PROC/fields['MainPID']
    before=(proc/'stat').read_bytes().rsplit(b')',1)[-1].split()
    with (proc/'environ').open('rb') as stream: raw=stream.read(1_000_001)
    after=(proc/'stat').read_bytes().rsplit(b')',1)[-1].split()
    if len(raw)>1_000_000 or len(before)<20 or len(after)<20 or before[19]!=after[19]:
        raise VerificationError('laya_process_changed')
    values=[x for x in raw.split(b'\0') if x.startswith(b'LAYA_API_KEY=')]
    if values!=[('LAYA_API_KEY='+config['DECISION_API_KEY']).encode()]:
        raise VerificationError('laya_process_configuration_mismatch')
    return fields,before[19]


def assert_no_pending(installer):
    paths=(installer.STATE/'install.json.pending',
           installer.UNIT.with_name(installer.UNIT.name+'.pending'),
           installer.ENV.with_name(installer.ENV.name+'.pending'))
    if any(os.path.lexists(path) for path in paths):
        raise VerificationError('pending_laya_operation')


def verify_existing(args):
    before=context(args);installer=before['installer'];source=before['source'];config=before['config']
    assert_no_pending(installer)
    generation,unit,env,expected=installer.expected_install(source,config)
    receipt=installer.existing_install(expected)
    if receipt is None: raise VerificationError('missing_existing_laya_install')
    account=installer.validate_account()
    actual_unit,unit_identity=read(installer.UNIT,mode=0o644)
    actual_env,env_identity=read(installer.ENV,mode=0o640)
    if actual_unit!=unit or not hmac.compare_digest(actual_env,env) or installer.ENV.stat().st_gid!=account.pw_gid:
        raise VerificationError('existing_laya_configuration_drift')
    installer.verify_generation(source,generation)
    installer.command(['/usr/bin/systemd-analyze','verify',installer.UNIT])
    running=process_binding(installer,generation,config);health_get();time.sleep(7)
    if process_binding(installer,generation,config)!=running: raise VerificationError('laya_service_unstable')
    health_get()
    after=context(args)
    assert_no_pending(installer)
    if (before['identities']!=after['identities'] or before['config']!=after['config']
            or identity(installer.UNIT)!=unit_identity or identity(installer.ENV)!=env_identity
            or installer.existing_install(expected)!=receipt):
        raise VerificationError('laya_existing_proof_changed')
    assert_no_pending(installer)
    return {'state':'LAYA_EXISTING_HEALTH_VERIFIED','generation':expected['generation'],'inference_performed':False}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=('prepare','provision','activate','verify'))
    for name in ('sha','lock','token','stage'): parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    own=Path(__file__).absolute()
    if own!=BASE/'verifiers'/args.sha/'verify_laya_no_backup.py': raise VerificationError('laya_verifier_path')
    raw,_=read(own.parent/'source.json',mode=0o400);binding=object_json(raw)
    if binding!={'sha':args.sha,'sha256':digest(read(own,mode=0o400)[0])}: raise VerificationError('laya_verifier_binding')
    print(json.dumps(verify_existing(args),sort_keys=True))


if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('LAYA_EXISTING_BLOCKED:'+type(exc).__name__,file=sys.stderr)
        raise SystemExit(1) from None
