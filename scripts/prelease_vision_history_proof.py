"""One content-bound, pre-business-lease failure; no retry or deployment authority.

The generic original error does not establish a particular GitHub error. The
pinned control flow and exact transcript prove only that mutation was not reached.
"""
import hashlib
import os
from pathlib import Path
import stat

FAILED = '17f9c29f32123ada929fac9af61a17e6521094d8'
PRODUCTION = '25b85536e3722dc111c528b8a915062a3f971397'
PROFILE = 'prelease-vision-history-failure'
IMPLEMENTATIONS = {
 'scripts/trusted_release_server.py':'25744743a662226f831e1f0852055eb9781799307a30a63db60a0c68e2425bd7',
 'scripts/trusted_release_gate.py':'7b85ec065a213c406cedeb65d79b25b16567485981f56ec7baecac3234111abe',
 'scripts/trusted_vision_model.py':'82213dc8f39ae112b43a346f7abec2afdf729e3f7d754fe34bca3e16bf06e3f8',
 'deploy.sh':'d01655afff653c26185c75b53ed7fd5f5280b867406f6374c510365ccba1009e',
}
INVENTORY = {'bin','completed.json','deployment-started.json','deployment.log','home',
 'preparation-started.json','preparation.log','prepared.json','source','started.json'}
LOG = b'\n\x1b[0;32m\xe2\x95\x94\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x97\x1b[0m\n\x1b[0;32m\xe2\x95\x91     \xe5\x81\xa5\xe5\xba\xb7\xe5\xba\x94\xe7\x94\xa8\xe9\x83\xa8\xe7\xbd\xb2\xe8\x84\x9a\xe6\x9c\xac v1.0              \xe2\x95\x91\x1b[0m\n\x1b[0;32m\xe2\x95\x9a\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x9d\x1b[0m\n\n{"state": "VISION_HISTORY_BLOCKED", "model_requests": 0}\n'


class PreleaseError(RuntimeError):
    pass


def validate_log(raw):
    if raw != LOG:
        raise PreleaseError('exact initial vision history failure required')


def validate_binding(sha, binding):
    if sha != FAILED or binding != IMPLEMENTATIONS:
        raise PreleaseError('prelease vision implementation binding differs')


def inspect(bootstrap, sha, source):
    binding = {}
    for name in IMPLEMENTATIONS:
        path=source/name;bootstrap.secure(path)
        binding[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    validate_binding(sha,binding)
    workspace=bootstrap.STATE/sha
    bootstrap.secure(workspace)
    if stat.S_IMODE(workspace.stat().st_mode)!=0o700 or {p.name for p in workspace.iterdir()}!=INVENTORY:
        raise PreleaseError('prelease workspace inventory differs')
    for name,state in [('started.json','STARTED'),('completed.json','NEEDS_OPERATOR'),
                       ('preparation-started.json','PREPARING'),('prepared.json','PREPARED'),
                       ('deployment-started.json','DEPLOYING')]:
        expected={'sha':sha,'state':state}
        if state=='PREPARING':expected['executor_sha256']=binding['scripts/trusted_release_server.py']
        bootstrap.secure(workspace/name,private=True)
        if bootstrap._read_json(workspace/name)!=expected:
            raise PreleaseError('prelease original phase chain differs')
    for name in ('home','bin','source'):
        bootstrap.secure(workspace/name)
        if stat.S_IMODE((workspace/name).stat().st_mode)!=0o700:
            raise PreleaseError('prelease private directory differs')
    if list((workspace/'home').iterdir()) or {p.name for p in (workspace/'bin').iterdir()}!={'ssh','scp','python3'}:
        raise PreleaseError('prelease tool inventory differs')
    for command in ('ssh','scp','python3'):
        path=workspace/'bin'/command;bootstrap.secure(path)
        target='/usr/bin/python3.12' if command=='python3' else '/usr/bin/'+command
        args='' if command=='python3' else ' -F /etc/reva-release/loopback.conf'
        if path.read_bytes()!=f'#!/bin/sh\nexec {target}{args} "$@"\n'.encode() or stat.S_IMODE(path.stat().st_mode)!=0o700:
            raise PreleaseError('prelease tool bytes differ')
    for name,digest in binding.items():
        path=workspace/'source'/name;bootstrap.secure(path)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise PreleaseError('prelease workspace implementation differs')
    path=workspace/'deployment.log';bootstrap.secure(path,private=True)
    if path.stat().st_size!=len(LOG):raise PreleaseError('prelease transcript size differs')
    validate_log(path.read_bytes())
    # Snapshot excludes mutable live observations; historical rotation can
    # validate the exact retained workspace without querying current state.
    return {'profile':PROFILE,'executor_sha256':binding['scripts/trusted_release_server.py'],
            'implementations':binding,'manifest':bootstrap._preparation_manifest(workspace)}


def configuration(bootstrap, failed_sha, production_sha, live):
    if failed_sha!=FAILED or production_sha!=PRODUCTION:
        raise PreleaseError('prelease production revision differs')
    workspace=bootstrap.STATE/failed_sha
    for path in (workspace/'deployment.env',bootstrap.BUSINESS_LEASE,
                 Path('/var/lib/reva-release/daily-journey-migrations')/failed_sha,
                 Path('/var/lib/reva-laya-release/sources')/failed_sha,
                 Path('/var/lib/reva-laya-release/install.json.pending'),
                 Path('/etc/reva-laya/service.env.pending'),
                 Path('/etc/systemd/system/reva-laya.service.pending')):
        if path != bootstrap.BUSINESS_LEASE:
            parent = path.parent
            while not os.path.lexists(parent):
                parent = parent.parent
            bootstrap.secure(parent)
        if os.path.lexists(path):raise PreleaseError('prelease mutation evidence exists')
    path=Path('/opt/health-app/backend/.env')
    bootstrap.secure(path);before=path.stat()
    identity=bootstrap._recovery_file_identity(path)
    after=path.stat()
    started=workspace/'started.json';bootstrap.secure(started,private=True)
    began=min(started.stat().st_ctime_ns,started.stat().st_mtime_ns)
    if (max(before.st_ctime_ns,before.st_mtime_ns)>=began
            or (before.st_ctime_ns,before.st_mtime_ns)!=(after.st_ctime_ns,after.st_mtime_ns)
            or identity['sha256']!=hashlib.sha256(live.encode()).hexdigest()):
        raise PreleaseError('prelease live environment chronology differs')
    return {'live':identity,'ctime_ns':before.st_ctime_ns,'mtime_ns':before.st_mtime_ns,
            'started_ns':began,'candidate_environment_absent':True,'historical_env_digest_available':False}
