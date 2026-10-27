"""Canonical one-shot Xiaoqihou review briefing, independent of retired 279 attempts.

Default: read-only database inspection. Apply requires the exact fresh digest
and separate explicit human approval. All uncertain results retain the intent
and business lease. No reset, updates, deletes, backup or retry is implemented.
"""
import argparse
import contextlib
import fcntl
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys

STATE = Path('/var/lib/reva-release')
TARGET = '8f7d94696424f92ff57243edb906cd6d2dd14a3a'
ATTEMPT = 'xiaoqihou-fixed-briefing-v1'
ENTRY = 'trusted_xiaoqihou_briefing.py'
ENV = {'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LC_ALL':'C'}


class BriefingError(Exception):
    """Bounded secret-free diagnostic."""


def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def context(sha, *, verify_ci=True, token_stdin=False):
    if (re.fullmatch('[a-f0-9]{40}',sha or '') is None or os.geteuid()!=0
            or sys.executable!='/usr/bin/python3.12' or not sys.flags.isolated
            or not sys.flags.no_site or not sys.flags.dont_write_bytecode
            or 'SSH_ORIGINAL_COMMAND' in os.environ):
        raise BriefingError('isolated canonical root required')
    source=STATE/'bootstrap'/sha/'source'
    entry=source/'scripts'/ENTRY
    if Path(__file__).absolute()!=entry:
        raise BriefingError('canonical entry required')
    helper=source/'scripts/review_maintenance_acknowledgement.py'
    for path in [*reversed(entry.parents),entry,helper]:
        info=path.lstat(); file=path in (entry,helper)
        if (info.st_uid!=0 or info.st_mode&0o022
                or not (stat.S_ISREG(info.st_mode) if file else stat.S_ISDIR(info.st_mode))
                or (file and info.st_nlink!=1)):
            raise BriefingError('unsafe canonical metadata')
    ack=load(helper,'xiaoqihou_ack')
    checked,b,server,readers=ack.context(sha,verify_ci=verify_ci,token_stdin=token_stdin)
    if checked!=source: raise BriefingError('canonical source changed')
    def reviewed(name):
        path=source/'scripts'/name
        b.secure(path)
        return load(path,'xiaoqihou_'+name[:-3])
    core=reviewed('review_xiaoqihou_briefing.py')
    shared=reviewed('trusted_review_briefing_repair.py')
    reset=reviewed('trusted_review_reset.py')
    closure=reviewed('review_maintenance_release_closure.py')
    if core.TARGET!=TARGET or core.rows.SCHEMA!='public':
        raise BriefingError('fixed target differs')
    return source,b,server,readers,core,shared,reset,closure


def record_path():
    return STATE/'review-xiaoqihou-briefings'/ATTEMPT


def legacy_evidence(source,b,closure):
    # Targeted immutable receipt chain only. Never scan historical backups or
    # turn the original closing operator into the new operator revision.
    root=b.STATE/'retired'/closure.TARGET
    inventory=b._inventory(root,{'intent.json','completed.json'})
    intent=b._read_json(root/'intent.json')
    end=b._read_json(root/'completed.json')
    original=intent.get('new_sha')
    if end!={'state':'RETIRED','old_sha':closure.TARGET,'new_sha':original}:
        raise BriefingError('historical retirement differs')
    proof=intent.get('review_maintenance_release_closure')
    if not isinstance(proof,dict): raise BriefingError('historical closure proof absent')
    result,_,_=closure.saved(b,source,original,proof=proof)
    if b._inventory(root,{'intent.json','completed.json'})!=inventory:
        raise BriefingError('historical evidence changed')
    return {'retirement':inventory,'closure':result}


def production(source,b,server,reset,closure):
    target=b.canonical_source(TARGET)
    reset._validate_production(TARGET,target,b,server)
    complete=b._read_json(b.STATE/TARGET/'completed.json')
    if complete!={'sha':TARGET,'state':'SUCCEEDED'}:
        raise BriefingError('fixed production deployment not complete')
    result={'target_sha':TARGET,'deployment':complete,'legacy':legacy_evidence(source,b,closure)}
    for unit in ('health-backend','celery-worker','celery-beat'):
        status=subprocess.run(['/usr/bin/systemctl','is-active',unit],env=ENV,stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,check=True)
        if status.stdout!=b'active\n': raise BriefingError('production service not active')
    return result


def assert_lease(b,server,reset,lease):
    if lease is None:
        if os.path.lexists(b.BUSINESS_LEASE): raise BriefingError('business lease exists')
    elif reset._lease_identity(str(b.BUSINESS_LEASE),lease['token'],b,server)!=tuple(tuple(x) for x in lease['identity']):
        raise BriefingError('business lease changed')


def validate_parent(source,sha,mode,proof_fd,launcher_fd,build_fd,b,server,shared,reset,proc=Path('/proc')):
    fds=(proof_fd,launcher_fd,build_fd)
    if any(type(fd) is not int or fd<3 for fd in fds) or len(set(fds))!=3:
        raise BriefingError('distinct inherited descriptors required')
    info=os.fstat(proof_fd)
    if not stat.S_ISFIFO(info.st_mode) or info.st_uid!=0: raise BriefingError('private proof pipe required')
    raw=os.read(proof_fd,4097)
    if not raw or len(raw)>4096 or os.read(proof_fd,1): raise BriefingError('bounded one-shot proof required')
    proof=json.loads(raw)
    if (not isinstance(proof,dict) or set(proof)!={'parent','nonce','sha','mode','evidence_sha256','lease','attempt'}
            or proof['sha']!=sha or proof['mode']!=mode or proof['attempt']!=ATTEMPT
            or re.fullmatch('[a-f0-9]{64}',proof.get('nonce') or '') is None
            or (mode=='apply' and (re.fullmatch('[a-f0-9]{64}',proof.get('evidence_sha256') or '') is None or proof['lease'] is None))
            or (mode=='inspect' and proof['evidence_sha256'] is not None)):
        raise BriefingError('parent proof does not authorize child')
    parent=os.getppid(); entry=proc/str(parent)
    def check():
        if parent<=1 or os.getppid()!=parent or proof['parent']!=shared.parent_identity(parent,proc):
            raise BriefingError('original canonical parent absent')
        uid=[line.split()[1:] for line in (entry/'status').read_bytes().splitlines() if line.startswith(b'Uid:')]
        if uid!=[[b'0']*4] or os.readlink(entry/'exe')!='/usr/bin/python3.12':
            raise BriefingError('parent identity differs')
        raw_argv=(entry/'cmdline').read_bytes(); argv=raw_argv.rstrip(b'\0').split(b'\0')
        expected=[b'/usr/bin/python3.12',b'-I',b'-S',b'-B',str(source/'scripts'/ENTRY).encode()]
        if (len(raw_argv)>16384 or argv[:5]!=expected or b'--database-probe' in argv
                or argv.count(b'--sha')!=1 or argv[argv.index(b'--sha')+1:argv.index(b'--sha')+2]!=[sha.encode()]
                or (mode=='apply' and (argv.count(b'--accept-xiaoqihou-briefing')!=1
                    or argv.count(b'--evidence-sha256')!=1
                    or argv[argv.index(b'--evidence-sha256')+1:argv.index(b'--evidence-sha256')+2]!=[proof['evidence_sha256'].encode()]))):
            raise BriefingError('parent lacks exact canonical authority')
        locks=(proc/'locks').read_text()
        if len(locks)>1048576: raise BriefingError('lock inventory exceeds bound')
        for fd,path in ((launcher_fd,STATE/'launcher.lock'),(build_fd,STATE/TARGET/'build.lock')):
            b._assert_original_lock(path,fd)
            own,original=os.fstat(fd),(entry/'fd'/str(fd)).stat()
            if (own.st_dev,own.st_ino)!=(original.st_dev,original.st_ino):
                raise BriefingError('inherited parent lock differs')
            found=False
            for line in locks.splitlines():
                fields=line.split()
                if len(fields)==8 and fields[1:4]==['FLOCK','ADVISORY','WRITE'] and fields[4]==str(parent):
                    dev=fields[5].split(':')
                    if len(dev)==3 and (int(dev[0],16),int(dev[1],16),int(dev[2]))==(os.major(own.st_dev),os.minor(own.st_dev),own.st_ino): found=True
            if not found: raise BriefingError('parent no longer holds both locks')
        assert_lease(b,server,reset,proof['lease'])
    check()
    return proof,check


def database_work(engine,core,shared,readers,email,fixture,key,check,*,evidence=None):
    if evidence is None:
        check()
        with engine.connect() as c,c.begin():
            c.exec_driver_sql('SET TRANSACTION READ ONLY')
            uid=shared.demo_identity(c,email)
            snapshot=core.inspect_briefing_metadata(c,email,uid)
            shared.assert_insert_surface(c)
            health=shared.health_snapshot(c,uid,key,readers)
        check()
        return {'demo_user_id':uid,**snapshot,'health_snapshot_sha256':health}
    core.validate_evidence(evidence); uid=evidence['demo_user_id']
    with engine.connect() as c:
        tx=c.begin()
        try:
            check()
            c.exec_driver_sql("SET LOCAL lock_timeout='2000ms'")
            c.exec_driver_sql("SET LOCAL statement_timeout='5000ms'")
            c.exec_driver_sql('LOCK TABLE public.agent_conversations,public.agent_messages IN SHARE ROW EXCLUSIVE MODE')
            shared.assert_insert_surface(c)
            if shared.demo_identity(c,email)!=uid or shared.health_snapshot(c,uid,key,readers)!=evidence['health_snapshot_sha256']:
                raise BriefingError('demo identity or health changed')
            result=core.create_briefing_rows(c,email,uid,evidence['database_snapshot_sha256'],fixture,
                                            ordering_metadata_plan=evidence['ordering_metadata_plan'])
            if shared.health_snapshot(c,uid,key,readers)!=evidence['health_snapshot_sha256']:
                raise BriefingError('health changed inside transaction')
            check()
            tx.commit()
        except BaseException:
            if tx.is_active: tx.rollback()
            raise
    check()
    with engine.connect() as c,c.begin():
        core.verify_created_briefing_rows(c,email,uid,result['after_sha256'],fixture)
        if shared.health_snapshot(c,uid,key,readers)!=evidence['health_snapshot_sha256']:
            raise BriefingError('post-commit health changed; no retry')
    check()
    return result


def database_child(args):
    source,b,server,readers,core,shared,reset,closure=context(args.sha,verify_ci=False)
    proof,check=validate_parent(source,args.sha,args.database_probe,args.parent_proof_fd,args.publisher_lock_fd,args.build_lock_fd,b,server,shared,reset)
    observed=production(source,b,server,reset,closure)
    evidence=None; record=record_path()
    if args.database_probe=='apply':
        b._inventory(record,{'intent.json'})
        intent=b._read_json(record/'intent.json'); evidence=intent.get('evidence')
        core.validate_evidence(evidence)
        if (intent.get('operator_sha')!=args.sha or intent.get('attempt')!=ATTEMPT
                or intent.get('accept_xiaoqihou_briefing') is not True or intent.get('lease')!=proof['lease']
                or intent.get('parent_binding')!={**proof['parent'],'nonce_sha256':hashlib.sha256(proof['nonce'].encode()).hexdigest()}
                or intent.get('evidence_sha256')!=proof['evidence_sha256'] or core.digest(evidence)!=proof['evidence_sha256']
                or evidence['production_evidence_sha256']!=core.digest(observed)
                or evidence['legacy_closure_sha256']!=core.digest(observed['legacy'])):
            raise BriefingError('fresh separately authorized bound intent required')
        check()
        readers.write_json(record/'database-started.json',{'state':'DATABASE_ATTEMPT_STARTED','operator_sha':args.sha,
                           'attempt':ATTEMPT,'evidence_sha256':proof['evidence_sha256']})
    reset._assert_isolated_search_path()
    target=b.canonical_source(TARGET)
    sys.path.append('/opt/health-app/backend/venv/lib/python3.12/site-packages')
    raw=server.read_production_env(); environment=reset._parse_maintenance_environment(raw)
    key=hmac.new(hashlib.sha256(raw.encode()).digest(),(ATTEMPT+':'+args.sha).encode(),hashlib.sha256).digest()
    del raw
    fixture=target/'backend/fixtures/demo_user_minimal.json'; b.secure(fixture)
    if hashlib.sha256(fixture.read_bytes()).hexdigest()!=core.FIXTURE_SHA256: raise BriefingError('fixture changed')
    os.environ.clear(); os.environ.update(environment); os.chdir(target/'backend'); sys.path.insert(0,str(target/'backend'))
    with contextlib.redirect_stdout(reset._BoundedSummary()),contextlib.redirect_stderr(reset._BoundedSummary()):
        reset._validate_effective_target(target,environment)
        from sqlalchemy import create_engine
        from sqlalchemy.engine import make_url
        if not make_url(environment['DATABASE_URL']).database: raise BriefingError('explicit database required')
        engine=create_engine(environment['DATABASE_URL'],isolation_level='SERIALIZABLE',connect_args={'connect_timeout':5})
        try:
            return database_work(engine,core,shared,readers,environment['APP_STORE_REVIEW_DEMO_ACCOUNT'],fixture,key,check,evidence=evidence)
        finally: engine.dispose()


def make_adapter(source,b,server,readers,core,shared,reset,closure,sha,launcher_fd,build_fd):
    class Adapter:
        record=record_path()
        def __init__(self):
            self.nonce=secrets.token_hex(32); self.parent=shared.parent_identity(os.getpid()); self.lease=None
        def check(self):
            b._assert_original_lock(STATE/'launcher.lock',launcher_fd)
            b._assert_original_lock(STATE/TARGET/'build.lock',build_fd)
            assert_lease(b,server,reset,self.lease)
            b._recovery_process_proof()
        def child(self,mode):
            self.check()
            proof={'sha':sha,'attempt':ATTEMPT,'parent':self.parent,'nonce':self.nonce,'mode':mode,'lease':self.lease,
                   'evidence_sha256':b._read_json(self.record/'intent.json')['evidence_sha256'] if mode=='apply' else None}
            raw=json.dumps(proof).encode()
            if len(raw)>4096: raise BriefingError('proof exceeds bound')
            rd,wr=os.pipe()
            try:
                if os.write(wr,raw)!=len(raw): raise BriefingError('proof pipe incomplete')
                os.close(wr); wr=None
                result=subprocess.run(['/usr/bin/python3.12','-I','-S','-B',str(source/'scripts'/ENTRY),'--sha',sha,
                    '--database-probe',mode,'--parent-proof-fd',str(rd),'--publisher-lock-fd',str(launcher_fd),
                    '--build-lock-fd',str(build_fd)],env=ENV,stdin=subprocess.DEVNULL,pass_fds=(rd,launcher_fd,build_fd),
                    stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=300,check=True)
            finally:
                os.close(rd)
                if wr is not None: os.close(wr)
            self.check()
            if len(result.stdout)>16384: raise BriefingError('database summary exceeds bound')
            return json.loads(result.stdout)
        def inspect(self):
            self.check(); before=production(source,b,server,reset,closure)
            database=self.child('inspect')
            if production(source,b,server,reset,closure)!=before: raise BriefingError('production drift')
            self.check()
            value={'target_sha':TARGET,'action':core.ACTION,'fixture_sha256':core.FIXTURE_SHA256,
                   'production_evidence_sha256':core.digest(before),'legacy_closure_sha256':core.digest(before['legacy']),**database}
            core.validate_evidence(value)
            return value
        def prepare_record(self):
            self.check()
            # Atomic reservation. Never replace another operation's lease.
            b.BUSINESS_LEASE.mkdir(mode=0o700)
            token=secrets.token_hex(32)
            b._write(b.BUSINESS_LEASE/'token',token.encode())
            identity=reset._lease_identity(str(b.BUSINESS_LEASE),token,b,server)
            self.lease={'token':token,'identity':identity}
            if not self.record.parent.exists():
                self.record.parent.mkdir(mode=0o700); readers.sync(self.record.parent.parent)
            b.secure(self.record.parent)
            if stat.S_IMODE(self.record.parent.stat().st_mode)!=0o700: raise BriefingError('private audit directory required')
            self.record.mkdir(mode=0o700); readers.sync(self.record.parent)
        def write(self,name,value):
            self.check()
            if name not in ('intent.json','completed.json'): raise BriefingError('invalid audit output')
            if name=='intent.json':
                value={**value,'operator_sha':sha,'attempt':ATTEMPT,'accept_xiaoqihou_briefing':True,'lease':self.lease,
                       'parent_binding':{**self.parent,'nonce_sha256':hashlib.sha256(self.nonce.encode()).hexdigest()}}
            readers.write_json(self.record/name,value)
        def apply_once(self,evidence):
            if core.digest(production(source,b,server,reset,closure))!=evidence['production_evidence_sha256']:
                raise BriefingError('production changed before apply')
            result=self.child('apply')
            if core.digest(production(source,b,server,reset,closure))!=evidence['production_evidence_sha256']:
                raise BriefingError('production changed after apply; no retry')
            return result
        def finish(self):
            if self.lease is None: return
            # Any begun database attempt without a verified completion keeps the
            # lease and audit for independent reconciliation, never replay.
            if (self.record/'database-started.json').exists() and not (self.record/'completed.json').exists(): return
            self.check()
            if {p.name for p in b.BUSINESS_LEASE.iterdir()}!={'token'}: raise BriefingError('unexpected lease inventory')
            # _lease_identity has validated the fixed /var/lock -> /run/lock
            # alias. sync deliberately refuses symlinks, so use its real parent.
            parent=b.BUSINESS_LEASE.parent.resolve(strict=True)
            (b.BUSINESS_LEASE/'token').unlink(); b.BUSINESS_LEASE.rmdir(); readers.sync(parent)
            self.lease=None
    return Adapter()


def main():
    try:
        p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
        p.add_argument('--sha',required=True); p.add_argument('--token-stdin',action='store_true')
        p.add_argument('--accept-xiaoqihou-briefing',action='store_true'); p.add_argument('--evidence-sha256')
        p.add_argument('--database-probe',choices=('inspect','apply'),help=argparse.SUPPRESS)
        for name in ('parent-proof-fd','publisher-lock-fd','build-lock-fd'): p.add_argument('--'+name,type=int,help=argparse.SUPPRESS)
        args=p.parse_args()
        if args.database_probe:
            if args.token_stdin or args.accept_xiaoqihou_briefing or args.evidence_sha256: raise BriefingError('child cannot consume authority')
            out=database_child(args)
        else:
            if any(v is not None for v in (args.parent_proof_fd,args.publisher_lock_fd,args.build_lock_fd)): raise BriefingError('child-only descriptors')
            if args.accept_xiaoqihou_briefing != bool(args.evidence_sha256): raise BriefingError('explicit authority and fresh digest required')
            source,b,server,readers,core,shared,reset,closure=context(args.sha,token_stdin=args.token_stdin)
            lock=STATE/'launcher.lock'; b.secure(lock,private=True)
            fd=os.open(lock,os.O_RDWR|os.O_NOFOLLOW); build_fd=None; adapter=None
            try:
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                build_fd=b._acquire_existing_build_lock(TARGET)
                if build_fd is None: raise BriefingError('existing fixed build lock required')
                adapter=make_adapter(source,b,server,readers,core,shared,reset,closure,args.sha,fd,build_fd)
                out=core.repair(adapter,authorized=args.accept_xiaoqihou_briefing,evidence_sha256=args.evidence_sha256)
            finally:
                if adapter is not None: adapter.finish()
                if build_fd is not None: os.close(build_fd)
                os.close(fd)
        print(json.dumps(out,sort_keys=True)); return 0
    except (Exception,KeyboardInterrupt):
        print('Xiaoqihou briefing rejected or incomplete; preserve evidence; do not retry',file=sys.stderr)
        return 1


if __name__=='__main__': sys.exit(main())
