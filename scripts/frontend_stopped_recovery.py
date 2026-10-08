"""One explicitly authorized continuation of the intact 637078 frontend build."""
import hashlib
import os
from pathlib import Path
import re
import stat

OPERATION='637078dd8c584686a59000de91d2dad2'
ORIGINAL='f8dd4fe8cc962aed54a2db97dc981c82093b93ea'
PRODUCTION='dbad4e66c29f31c0ae149fecefa6c0d4f3e45283'
TREE='0e0a36d69a526e0ca5395f5c5082a77534dd739c'
ARTIFACT='2d8d765d014a5015ae6eaf016e77d8bab46ff262a3954ae15a4044914a3dfa8e'
ORIGINAL_CODE='d17d896f05340e20735cba86a92eaaf2eeb6b548fd0e56e084ed86e375d15c68'
ORIGINAL_FILES={'intent.json','before.json','build.log','install-started.json','failed.json'}
CGROUP=Path('/sys/fs/cgroup/system.slice/health-frontend.service')


class RecoveryError(Exception):
    """Private operator evidence never appears in public exception messages."""


def original_intent():
    return dict(kind='frontend-publication',publisher_sha=ORIGINAL,production_sha=PRODUCTION,
                operation_id=OPERATION,frontend_tree=TREE,state='FRONTEND_STARTED',artifact_digest=None)


def validate_original(intent,failed,install):
    if (intent!=original_intent() or failed!={**intent,'state':'FRONTEND_NEEDS_OPERATOR'}
            or install!={**intent,'state':'FRONTEND_INSTALLING','artifact_digest':ARTIFACT}):
        raise RecoveryError('original fixed failed publication differs')


def original_evidence(pub,server,build):
    audit=pub.STATE/'frontend-publications'/OPERATION
    server.secure_path(audit,directory=True)
    validate_original(*(server._json(server._read_private(audit/name))
                        for name in ('intent.json','failed.json','install-started.json')))
    before=server._json(server._read_private(audit/'before.json'))
    if any(before.get(k)!=v for k,v in original_intent().items()
           if k in ('publisher_sha','production_sha','operation_id','frontend_tree')):
        raise RecoveryError('original preflight binding differs')
    return before,{n:build.data_fingerprint(audit/n)[0] for n in sorted(ORIGINAL_FILES)}


def lease_evidence(pub,helper,bootstrap,server,build):
    helper._secure_lease_path(server,pub.LEASE,directory=True)
    if {p.name for p in pub.LEASE.iterdir()}!={'token','label','stage','started_at'}:
        raise RecoveryError('original lease inventory differs')
    raw,fingerprints={},{}
    for name in ('token','label','stage','started_at'):
        server.validate_metadata((pub.LEASE/name).lstat(),private=True)
        fingerprints[name],data=build.data_fingerprint(pub.LEASE/name)
        raw[name]=data.decode().strip()
    if (raw['label']!='frontend-publication' or raw['stage']!=str(pub.STATE/'frontend-publications'/OPERATION)
            or raw['started_at']!='1791008901' or re.fullmatch('[0-9a-f]{64}',raw['token']) is None):
        raise RecoveryError('original lease binding differs')
    identity=helper._lease_identity(str(pub.LEASE),raw['token'],bootstrap,server)
    return dict(identity=[list(x) for x in identity],files=fingerprints)


def assert_stopped(pub,build):
    command=['/usr/bin/systemctl','show','health-frontend','--property='+pub.STOP_FIELDS+',ControlGroup']
    raw=build.run(command);values=dict(line.split('=',1) for line in raw.splitlines())
    if values.pop('ControlGroup',None) not in ('','/system.slice/health-frontend.service'):
        raise RecoveryError('frontend control group differs')
    pub.validate_stopped(values)
    if CGROUP.exists() and any(p.read_text().strip() for p in CGROUP.rglob('cgroup.procs')):
        raise RecoveryError('frontend descendants remain')
    if build.run(command)!=raw:
        raise RecoveryError('frontend stop state changed')


def candidate_digest(pub,build):
    stage=pub.BUILDS/OPERATION/'frontend'
    # The builder's writable frontend directory is beneath a private root-owned
    # stage. Validate that boundary and every soon-to-be-public immutable inode.
    for parent in (stage.parent,*stage.parent.parents):
        info=parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
            raise RecoveryError('candidate stage boundary differs')
    if stat.S_IMODE(stage.parent.lstat().st_mode)!=0o700:
        raise RecoveryError('candidate stage must remain private')
    if not stat.S_ISDIR(stage.lstat().st_mode) or stage.lstat().st_uid!=0:
        raise RecoveryError('candidate frontend directory differs')
    if any(not (stage/n).is_dir() or (stage/n).is_symlink() for n in ('.next','node_modules')):
        raise RecoveryError('original candidate was moved or replaced')
    count=0
    for name in ('.next','node_modules'):
        root=stage/name;pending=[root]
        while pending:
            path=pending.pop();count+=1
            if count>300000:raise RecoveryError('candidate metadata inventory exceeds bound')
            info=path.lstat()
            if name=='.next' and (path==root/'cache' or (root/'cache') in path.parents):
                continue  # publication_artifact_digest validates the entire cache
            if info.st_uid!=0 or info.st_gid!=0 or (not stat.S_ISLNK(info.st_mode) and info.st_mode&0o022):
                raise RecoveryError('candidate immutable ownership differs')
            if stat.S_ISDIR(info.st_mode):pending.extend(path.iterdir())
    if pub.bundle_digest(stage,build)!=ARTIFACT:
        raise RecoveryError('original candidate digest differs')
    group=Path('/sys/fs/cgroup/system.slice')/f'reva-frontend-build-{OPERATION}.service'
    if group.exists() and any(p.read_text().strip() for p in group.rglob('cgroup.procs')):
        raise RecoveryError('original builder descendants remain')
    return ARTIFACT


def inspect(args,source,pub,helper,bootstrap,server,gate,build):
    if (args.operation_id!=OPERATION or args.production_sha!=PRODUCTION or args.frontend_tree!=TREE
            or getattr(args,'restore_preswitch_availability',False)):
        raise RecoveryError('only the explicitly authorized original operation may resume')
    gate.verify_release(args.publisher_sha,args.publisher_sha)
    gate._latest(gate._get_json,PRODUCTION)
    if build.git(source,'rev-parse','HEAD:frontend')!=TREE:
        raise RecoveryError('recovery cannot publish a different frontend')
    if server._json(server._read_private(pub.STATE/PRODUCTION/'completed.json'))!={'sha':PRODUCTION,'state':'SUCCEEDED'}:
        raise RecoveryError('original backend receipt differs')
    audit=pub.STATE/'frontend-publications'/OPERATION
    if {p.name for p in audit.iterdir()}!=ORIGINAL_FILES:
        raise RecoveryError('partial switch or recovery already attempted; no retry')
    server.assert_frontend_rebuild_history(pub.STATE,pending_stopped_publication=OPERATION)
    before,proofs=original_evidence(pub,server,build)
    pub.assert_preserved(before,source,helper,bootstrap,server,build)
    original_code=pub.STATE/'bootstrap'/ORIGINAL/'source/scripts/trusted_frontend_publish.py'
    build.secure_entry(original_code)
    if hashlib.sha256(original_code.read_bytes()).hexdigest()!=ORIGINAL_CODE:
        raise RecoveryError('original publisher control flow differs')
    candidate_digest(pub,build)
    build.run(['/usr/bin/node',str(source/'frontend/scripts/braces-depth-guard.cjs'),
               '--root',str(pub.BUILDS/OPERATION/'frontend')])
    for name in ('.next','node_modules'):
        server._frontend_publication_backup_digest(pub.PRODUCTION/'frontend'/name,live=True)
        if (pub.PRODUCTION/'frontend'/name).lstat().st_dev!=audit.lstat().st_dev or (pub.BUILDS/OPERATION/'frontend'/name).lstat().st_dev!=audit.lstat().st_dev:
            raise RecoveryError('same-filesystem artifact switch required')
    return dict(kind='frontend-stopped-recovery',state='PREFLIGHT',operation_id=OPERATION,
                recovery_publisher_sha=args.publisher_sha,original_proof=proofs,
                original_code_sha256=ORIGINAL_CODE,candidate_digest=ARTIFACT,
                old_bundle_digest=pub.bundle_digest(pub.PRODUCTION/'frontend',build),
                frontend_process=pub.stable_runtime(build),
                lease=lease_evidence(pub,helper,bootstrap,server,build))


def execute(plan,source,pub,helper,bootstrap,server,build,check_locks):
    audit=pub.STATE/'frontend-publications'/OPERATION
    stage=pub.BUILDS/OPERATION/'frontend'
    def preserved(*,candidate=True,frontend=True):
        check_locks()
        before,proofs=original_evidence(pub,server,build)
        if proofs!=plan['original_proof'] or lease_evidence(pub,helper,bootstrap,server,build)!=plan['lease']:
            raise RecoveryError('original evidence or lease changed')
        pub.assert_preserved(before,source,helper,bootstrap,server,build)
        if candidate:candidate_digest(pub,build)
        if frontend and pub.runtime(build)!=plan['frontend_process']:
            raise RecoveryError('restored frontend changed')
        return before
    def write(name,value):build.write_json(server,audit/name,value)
    def marker(state):return {**original_intent(),'state':state,'artifact_digest':ARTIFACT}
    preserved()
    if {p.name for p in audit.iterdir()}!=ORIGINAL_FILES:
        raise RecoveryError('recovery already attempted')
    intent={**plan,'state':'RECOVERY_STARTED'}
    write('recovery-intent.json',intent)
    try:
        preserved()
        if pub.bundle_digest(pub.PRODUCTION/'frontend',build)!=plan['old_bundle_digest']:
            raise RecoveryError('old bundle changed before stop')
        build.run(['/usr/bin/systemctl','stop','health-frontend'])
        assert_stopped(pub,build)
        preserved(frontend=False)
        if pub.bundle_digest(pub.PRODUCTION/'frontend',build)!=plan['old_bundle_digest']:
            raise RecoveryError('old bundle changed after stop')
        frozen={n:server._frontend_publication_backup_digest(pub.PRODUCTION/'frontend'/n,live=True)
                for n in ('.next','node_modules')}
        backups={}
        for name,backup in (('.next','previous-next'),('node_modules','previous-node-modules')):
            preserved(candidate=False,frontend=False)
            live=pub.PRODUCTION/'frontend'/name
            if live.lstat().st_dev!=audit.lstat().st_dev or (stage/name).lstat().st_dev!=audit.lstat().st_dev:
                raise RecoveryError('same-filesystem artifact switch required')
            live.rename(audit/backup);(stage/name).rename(live)
            backups[backup]=server._frontend_publication_backup_digest(audit/backup)
            if backups[backup]!=frozen[name]:raise RecoveryError('old backup changed')
            server._sync_directory(live.parent);server._sync_directory(audit)
        preserved(candidate=False,frontend=False)
        build.run(['/usr/bin/systemctl','start','health-frontend'])
        running=pub.stable_runtime(build);pub.verify_pages()
        if pub.runtime(build)!=running:raise RecoveryError('published frontend changed')
        preserved(candidate=False,frontend=False)
        if pub.bundle_digest(pub.PRODUCTION/'frontend',build)!=ARTIFACT:
            raise RecoveryError('published candidate differs')
        write('verified.json',marker('FRONTEND_VERIFIED'))
        recovery={**intent,'state':'RECOVERY_SUCCEEDED',
                  'intent_sha256':server._frontend_publication_file_digest(audit/'recovery-intent.json'),
                  'backups_digest':backups}
        write('recovery-completed.json',recovery)
        complete={**marker('FRONTEND_SUCCEEDED'),
                  'proof_sha256':{n:server._frontend_publication_file_digest(audit/n)
                      for n in ('before.json','build.log','install-started.json','verified.json')},
                  'backups_digest':backups,
                  'recovery_sha256':server._frontend_publication_file_digest(audit/'recovery-completed.json')}
        write('completed.json',complete)
        server.assert_frontend_publication_history(pub.STATE)
        check_locks()
        if lease_evidence(pub,helper,bootstrap,server,build)!=plan['lease']:
            raise RecoveryError('lease changed before release')
        for name in ('token','label','stage','started_at'):(pub.LEASE/name).unlink()
        pub.LEASE.rmdir();server._sync_business_lease_parent()
        return complete
    except BaseException:
        write('recovery-failed.json',{'kind':'frontend-stopped-recovery','operation_id':OPERATION,'state':'RECOVERY_NEEDS_OPERATOR'})
        raise RecoveryError('recovery failed; original evidence retained; no retry') from None
