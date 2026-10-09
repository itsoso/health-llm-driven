"""Prepare once in the existing host sandbox; consume only from canonical publisher.

No production service, business lease or release credential is changed by prepare.
Failed/unknown preparations remain immutable and cannot be retried with the same ID.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys

OWNER = 0
STATE = Path('/var/lib/reva-release')
BUILDS = Path('/var/lib/reva-frontend-builds')
MAX_PROOF = 2_000_000


class ArtifactError(Exception):
    """Sanitized rejection; detailed build output stays in private audit storage."""


def exact(value, length):
    if not isinstance(value,str) or re.fullmatch('[0-9a-f]{%d}'%length,value) is None:
        raise ArtifactError('invalid artifact identity')
    return value


def file_identity(info):
    return tuple(getattr(info,key) for key in ('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns'))


def private_bytes(path):
    info=path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != OWNER or stat.S_IMODE(info.st_mode)!=0o600
            or info.st_nlink!=1 or info.st_size>MAX_PROOF):
        raise ArtifactError('unsafe bounded artifact proof')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        if file_identity(os.fstat(stream.fileno()))!=file_identity(info): raise ArtifactError('artifact proof changed')
        data=stream.read(MAX_PROOF+1)
    if file_identity(path.lstat())!=file_identity(info) or len(data)>MAX_PROOF: raise ArtifactError('artifact proof changed')
    return data


def directory(path):
    info=path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=OWNER or stat.S_IMODE(info.st_mode)!=0o700:
        raise ArtifactError('unsafe artifact directory')


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def identity(publisher,tree,artifact,lock,environment,toolchain,recipe):
    for value,length in ((publisher,40),(tree,40),(artifact,32),(lock,64),(recipe,64)):exact(value,length)
    return dict(schema_version=1,publisher_sha=publisher,frontend_tree=tree,artifact_id=artifact,
                package_lock_sha256=lock,public_build_env=environment,toolchain=toolchain,recipe_sha256=recipe)


def binding(source,publisher,tree,artifact,environment,build):
    if build.git(source,'rev-parse','HEAD:frontend')!=tree:raise ArtifactError('frontend tree changed')
    package=json.loads((source/'frontend/package.json').read_bytes())
    if package.get('scripts',{}).get('build')!='node scripts/braces-depth-guard.cjs --root . --apply && next build':
        raise ArtifactError('unreviewed build recipe')
    recipe=b''.join((source/'scripts'/name).read_bytes() for name in
                   ('trusted_frontend_artifact.py','trusted_frontend_publish.py','trusted_frontend_rebuild.py'))
    toolchain=dict(node=build.run(['/usr/bin/node','--version']).strip(),
                   npm=build.run(['/usr/bin/npm','--version']).strip(),
                   system=platform.system(),release=platform.release(),machine=platform.machine(),
                   libc=list(platform.libc_ver()))
    return identity(publisher,tree,artifact,hash_bytes((source/'frontend/package-lock.json').read_bytes()),
                    environment,toolchain,hash_bytes(recipe))


def _audit(artifact):
    exact(artifact,32)
    root=STATE/'frontend-artifacts'
    directory(root)
    path=root/artifact
    directory(path)
    return path


def _verify(expected,publisher,build,server):
    """Re-read exact bytes and metadata before claim; never repair failed artifacts."""
    artifact=expected['artifact_id']; audit=_audit(artifact)
    if {p.name for p in audit.iterdir()}!={'intent.json','build.log','ready.json','prepare.lock'}:
        raise ArtifactError('artifact is unfinished, failed, claimed or unknown')
    raw=private_bytes(audit/'ready.json'); manifest=json.loads(raw)
    if (not isinstance(manifest,dict) or set(manifest)!={'binding','state','artifact_digest','intent_sha256','build_log_sha256'}
            or manifest['binding']!=expected or manifest['state']!='FRONTEND_ARTIFACT_READY'):
        raise ArtifactError('artifact binding differs')
    for key in ('artifact_digest','intent_sha256','build_log_sha256'):exact(manifest[key],64)
    intent=private_bytes(audit/'intent.json'); log=private_bytes(audit/'build.log')
    if json.loads(intent)!={'binding':expected,'state':'FRONTEND_ARTIFACT_PREPARING'}:
        raise ArtifactError('artifact intent differs')
    if hash_bytes(intent)!=manifest['intent_sha256'] or hash_bytes(log)!=manifest['build_log_sha256']:
        raise ArtifactError('artifact provenance differs')
    stage=BUILDS/artifact; directory(stage); directory(stage/'frontend')
    server.secure_path(stage,directory=True)
    # Normal frozen trees require root metadata; the bounded .next/cache exception
    # is checked by the existing publication inventory. The private stage parent
    # prevents health-web from reaching that cache before promotion.
    for name in ('.next','node_modules'):
        root=stage/'frontend'/name
        if not stat.S_ISDIR(root.lstat().st_mode):raise ArtifactError('artifact root must be a real directory')
        pending=[root];count=0
        while pending:
            path=pending.pop();count+=1
            if count>150000:raise ArtifactError('artifact inventory exceeds bound')
            if name=='.next' and path.is_relative_to(root/'cache'):continue
            info=path.lstat()
            if info.st_uid!=OWNER or (not stat.S_ISLNK(info.st_mode) and info.st_mode & 0o022) or (stat.S_ISREG(info.st_mode) and info.st_nlink!=1):
                raise ArtifactError('artifact metadata drift')
            if stat.S_ISDIR(info.st_mode):
                pending.extend(path.iterdir())
            elif stat.S_ISLNK(info.st_mode):
                if os.path.isabs(os.readlink(path)) or not path.resolve(strict=True).is_relative_to(root.resolve()):
                    raise ArtifactError('artifact link escapes bundle')
            elif not stat.S_ISREG(info.st_mode):
                raise ArtifactError('unsupported artifact object')
    if publisher.bundle_digest(stage/'frontend',build)!=manifest['artifact_digest']:
        raise ArtifactError('artifact content drift')
    return dict(artifact_id=artifact,manifest_sha256=hash_bytes(raw),manifest=manifest)


def assert_lock(path,fd):
    private_bytes(path)
    if file_identity(path.lstat())!=file_identity(os.fstat(fd)):
        raise ArtifactError('artifact lock identity changed')


def verify(expected,publisher,build,server):
    audit=_audit(expected['artifact_id'])
    private_bytes(audit/'prepare.lock')
    fd=os.open(audit/'prepare.lock',os.O_RDONLY|os.O_NOFOLLOW)
    try:
        assert_lock(audit/'prepare.lock',fd)
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=_verify(expected,publisher,build,server)
        assert_lock(audit/'prepare.lock',fd)
        return result
    finally:
        os.close(fd)


def claim(audit,proof,production,operation,server):
    exact(production,40);exact(operation,32)
    if proof['artifact_id']!=operation:raise ArtifactError('artifact and publication operation must match')
    value=dict(schema_version=1,artifact_id=operation,operation_id=operation,production_sha=production,
               manifest_sha256=proof['manifest_sha256'])
    server._write_private(audit/'claim.json',json.dumps(value,sort_keys=True).encode())
    server._sync_directory(audit)


def consume(plan,source,publisher,build,server,audit):
    """Caller already owns the original publication locks and business lease."""
    expected=binding(source,plan['publisher_sha'],plan['frontend_tree'],plan['operation_id'],plan['public_build_env'],build)
    proof=verify(expected,publisher,build,server)
    if proof!=plan['prepared_artifact']:raise ArtifactError('prepared evidence changed')
    original=_audit(plan['operation_id'])
    claim(original,proof,plan['production_sha'],plan['operation_id'],server)
    server._write_private(audit/'build.log',private_bytes(original/'build.log'))
    server._sync_directory(audit)
    return proof['manifest']['artifact_digest']


def _prepare_locked(plan,source,publisher,build,server):
    root=STATE/'frontend-artifacts'
    if not root.exists():root.mkdir(mode=0o700);server._sync_directory(root.parent)
    directory(root);server.secure_path(root,directory=True)
    audit=root/plan['artifact_id'];audit.mkdir(mode=0o700);server._sync_directory(root)
    server._write_private(audit/'prepare.lock',b'')
    with (audit/'prepare.lock').open('r+b') as lock:
        assert_lock(audit/'prepare.lock',lock.fileno())
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        build.write_json(server,audit/'intent.json',{'binding':plan,'state':'FRONTEND_ARTIFACT_PREPARING'})
        try:
            stage=BUILDS/plan['artifact_id']
            build.copy_build_inputs(source,stage,plan['public_build_env'])
            fd=os.open(audit/'build.log',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as log:
                subprocess.run(publisher.build_command(build,plan['artifact_id'],stage),env=build.ENV,
                               stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1900)
                log.flush();os.fsync(log.fileno())
            group=Path('/sys/fs/cgroup/system.slice')/f"reva-frontend-build-{plan['artifact_id']}.service"
            if group.exists() and any(p.read_text().strip() for p in group.rglob('cgroup.procs')):
                raise ArtifactError('build descendants remain')
            build.freeze_artifacts(stage);publisher.prepare_cache(stage/'frontend')
            (stage/'frontend').chmod(0o700)
            # Host package upgrades or recipe changes while building invalidate it.
            if binding(source,plan['publisher_sha'],plan['frontend_tree'],plan['artifact_id'],plan['public_build_env'],build)!=plan:
                raise ArtifactError('build inputs changed')
            manifest=dict(binding=plan,state='FRONTEND_ARTIFACT_READY',
                          artifact_digest=publisher.bundle_digest(stage/'frontend',build),
                          intent_sha256=hash_bytes(private_bytes(audit/'intent.json')),
                          build_log_sha256=hash_bytes(private_bytes(audit/'build.log')))
            build.write_json(server,audit/'ready.json',manifest)
            server._sync_directory(audit)
            _verify(plan,publisher,build,server)
            assert_lock(audit/'prepare.lock',lock.fileno())
            return manifest
        except BaseException:
            build.write_json(server,audit/'failed.json',{'state':'FRONTEND_ARTIFACT_FAILED','artifact_id':plan['artifact_id']})
            raise


def prepare(plan,source,publisher,build,server):
    # One compiler on the host, independent of the business publication lease.
    root=STATE/'frontend-artifacts'
    if not root.exists():root.mkdir(mode=0o700);server._sync_directory(root.parent)
    directory(root);server.secure_path(root,directory=True)
    lock=root/'prepare.lock'
    fd=os.open(lock,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        assert_lock(lock,fd)
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=_prepare_locked(plan,source,publisher,build,server)
        assert_lock(lock,fd)
        return result
    finally:
        os.close(fd)


def canonical_module(name,entry,source,sha):
    """Reject cached code before imports and execute only Git-verified source bytes.

    -B suppresses cache writes, not reads. The transitive legacy loaders are safe
    only after the entire root-owned canonical source has been proved cache-free.
    """
    from types import ModuleType
    exact(sha,40)
    relative=entry.relative_to(source)
    if relative.parts[0]!='scripts' or '..' in relative.parts:raise ArtifactError('invalid canonical module path')
    pending=[source];count=0
    while pending:
        path=pending.pop();count+=1
        if count>150000:raise ArtifactError('canonical inventory exceeds bound')
        if path.name=='__pycache__' or path.suffix in ('.pyc','.pyo'):
            raise ArtifactError('cached canonical code forbidden')
        info=path.lstat()
        if (info.st_uid!=OWNER or info.st_mode&0o022
                or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))
                or (stat.S_ISREG(info.st_mode) and info.st_nlink!=1)):
            raise ArtifactError('unsafe canonical source metadata')
        if stat.S_ISDIR(info.st_mode):pending.extend(path.iterdir())
    before=entry.lstat()
    fd=os.open(entry,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        if file_identity(os.fstat(stream.fileno()))!=file_identity(before):raise ArtifactError('canonical source changed')
        data=stream.read(MAX_PROOF+1)
    if len(data)>MAX_PROOF or file_identity(entry.lstat())!=file_identity(before):raise ArtifactError('canonical source changed')
    environment=dict(PATH='/usr/bin:/bin',HOME='/root',LC_ALL='C',GIT_CONFIG_NOSYSTEM='1',
                     GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_SYSTEM='/dev/null',GIT_NO_REPLACE_OBJECTS='1')
    result=subprocess.run(['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
                           '-C',str(source),'show',sha+':'+relative.as_posix()],env=environment,
                          stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,check=True)
    if result.stdout!=data:raise ArtifactError('canonical bytes differ')
    module=ModuleType(name);module.__file__=str(entry);module.__package__=''
    sys.modules[name]=module
    try:
        exec(compile(data,str(entry),'exec',dont_inherit=True),module.__dict__)
    except BaseException:
        del sys.modules[name]
        raise
    return module


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('publisher-sha','frontend-tree','artifact-id'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--evidence-sha256')
    args=parser.parse_args()
    try:
        if (not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode
                or os.geteuid()!=0 or sys.executable!='/usr/bin/python3.12'):
            raise ArtifactError('isolated system Python root required')
        exact(args.publisher_sha,40);exact(args.frontend_tree,40);exact(args.artifact_id,32)
        source=STATE/'bootstrap'/args.publisher_sha/'source'
        if Path(__file__).absolute()!=source/'scripts/trusted_frontend_artifact.py':raise ArtifactError('canonical artifact entry required')
        entry=source/'scripts/trusted_frontend_publish.py'
        for path in (*reversed(entry.parents),entry,Path(__file__)):
            info=path.lstat()
            if info.st_uid!=0 or info.st_mode&0o022 or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise ArtifactError('unsafe canonical entry')
        publisher=canonical_module('artifact_publisher',entry,source,args.publisher_sha)
        checked,helper,bootstrap,server,gate,build=publisher.load_reviewed(args.publisher_sha)
        if checked!=source:raise ArtifactError('canonical source differs')
        gate.verify_release(args.publisher_sha,args.publisher_sha)
        environment,_=publisher.configuration(build)
        plan=binding(source,args.publisher_sha,args.frontend_tree,args.artifact_id,environment,build)
        digest=build.evidence_digest(plan)
        if args.evidence_sha256 is None:
            print(json.dumps(dict(state='FRONTEND_ARTIFACT_PREFLIGHT',evidence_sha256=digest,**plan),sort_keys=True))
        else:
            exact(args.evidence_sha256,64)
            if args.evidence_sha256!=digest:raise ArtifactError('prepare evidence changed')
            os.umask(0o077)
            print(json.dumps(prepare(plan,source,publisher,build,server),sort_keys=True))
        return 0
    except Exception:
        print('frontend artifact preparation blocked or failed; inspect private evidence; no retry',file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
