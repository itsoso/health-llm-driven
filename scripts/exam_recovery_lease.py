"""Retire only the original exam lease after proved forward recovery.

Separate once-only retirement audit. Never modifies the failed release receipt,
recovery receipt, runtime terminal, database, or credential claim.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

ROOT=Path('/var/lib/reva-release')
FAILED_SHA='a8cd1e7635eb697c0f0bc528382c98b3602893c3'
NAMES=('token','label','stage','started_at')

class LeaseBlocked(RuntimeError):
    """Static retirement rejection; retained intent forbids automatic replay."""

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def retire(adapter,expected_digest=None):
    evidence=adapter.inspection();fingerprint=digest(evidence)
    if expected_digest is None:return {'state':'INSPECTED','evidence_sha256':fingerprint}
    if re.fullmatch('[a-f0-9]{64}',expected_digest) is None or expected_digest!=fingerprint:
        raise LeaseBlocked('retirement inspection changed')
    adapter.consume(evidence,fingerprint)
    if adapter.inspection()!=evidence:raise LeaseBlocked('recovery changed after retirement intent')
    adapter.remove(evidence)
    result={'state':'EXAM_RECOVERY_LEASE_RETIRED','evidence_sha256':fingerprint,'proof':adapter.after_removal()}
    adapter.complete(result)
    return result


def remove_exact_lease(lease,expected,file_proof,directory_proof):
    if directory_proof(lease)!=expected['lease'] or set(p.name for p in lease.iterdir())!=set(NAMES):
        raise LeaseBlocked('original lease inventory or identity differs')
    fd=os.open(lease,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if (info.st_dev,info.st_ino)!=(expected['lease']['dev'],expected['lease']['ino']):
            raise LeaseBlocked('lease directory changed')
        for name in NAMES:
            if directory_proof(lease)!=expected['lease'] or file_proof(lease/name,0o600)[1]!=expected[name]:
                raise LeaseBlocked('original lease file changed')
            os.unlink(name,dir_fd=fd)
            os.fsync(fd)
        if directory_proof(lease)!=expected['lease'] or os.listdir(fd):
            raise LeaseBlocked('lease directory changed before removal')
        os.rmdir(lease)
    finally:os.close(fd)
    parent=os.open(lease.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(parent)
    finally:os.close(parent)


class ProductionAdapter:
    def __init__(self,recovery,outer):
        self.r,self.outer=recovery,outer
        self.record=ROOT/('exam-recovery-lease-retirement-'+FAILED_SHA)
        self.success=None
    def locks(self):
        r=self.r
        r.b._assert_original_lock(ROOT/'launcher.lock',r.launcher_fd)
        r.service._check_original_build_lock(r.b,FAILED_SHA,r.build_fd)
        r.b._recovery_process_proof()
        r.b._recovery_production_proof(FAILED_SHA,r.source)
    def read_success(self):
        r=self.r
        r.proof._directory(r.audit)
        if {p.name for p in r.audit.iterdir()}!={'intent.json','completed.json'}:
            raise LeaseBlocked('recovery success audit incomplete')
        intent_raw,intent_meta=r.proof._file(r.audit/'intent.json',0o600)
        completed_raw,completed_meta=r.proof._file(r.audit/'completed.json',0o600)
        intent=json.loads(intent_raw);completed=json.loads(completed_raw)
        if (intent.get('publisher_sha')!=r.sha or intent.get('evidence_sha256')!=digest(intent.get('evidence'))
                or completed.get('state')!='RECOVERED_CANDIDATE' or completed.get('evidence_sha256')!=intent['evidence_sha256']):
            raise LeaseBlocked('recovery success binding differs')
        admission=intent['evidence']['admission']
        if (admission['publisher_sha']!=r.sha or admission['failed_sha']!=FAILED_SHA or admission['old_sha']!=self.outer.OLD_SHA):
            raise LeaseBlocked('recovery incident differs')
        return intent,completed,{'intent':intent_meta,'completed':completed_meta}
    def inspection(self):
        self.locks();r=self.r
        intent,completed,files=self.read_success()
        admission=intent['evidence']['admission']
        if r.proof._lease_snapshot()!=admission['lease']:
            raise LeaseBlocked('original lease differs from recovery intent')
        r.proof._original_lease=admission['lease'];r.workspace=admission['workspace'];r.journal=admission['journal']
        finalized=r.finalized_proof()
        if finalized!=completed['finalized']:raise LeaseBlocked('finalized proof changed')
        database=r.database_inspect()
        if database!=completed['database']:raise LeaseBlocked('database proof changed')
        r.candidate_preflight();r.service._http_probes()
        services=r.proof.running_snapshot();time.sleep(2)
        if services!=r.proof.running_snapshot() or services!=completed['guard']['services']:
            raise LeaseBlocked('recovered service generation changed')
        r.assert_authorized()
        self.success=files
        return {'publisher_sha':r.sha,'failed_sha':FAILED_SHA,'success':files,'lease':admission['lease'],
                'finalized':finalized,'database':database,'services':services}
    def consume(self,evidence,fingerprint):
        self.locks()
        self.record.mkdir(mode=0o700);self.r.h.sync_directory(ROOT)
        self.r.h.write_once(self.record/'intent.json',{'evidence_sha256':fingerprint,'evidence':evidence})
    def remove(self,evidence):
        self.r.assert_authorized()
        remove_exact_lease(self.r.proof.lease,evidence['lease'],self.r.proof._file,self.r.proof._directory)
    def after_removal(self):
        self.locks();r=self.r
        if os.path.lexists(r.proof.lease):raise LeaseBlocked('lease still present')
        _,completed,files=self.read_success()
        if files!=self.success:raise LeaseBlocked('recovery success audit changed')
        marker=r.tx._load_terminal_marker()
        self.outer.validate_finalized_terminal(r.retained,marker)
        if marker!=completed['finalized']['terminal'] or r.tx.layout.transaction_root.exists():
            raise LeaseBlocked('terminal changed')
        r.service._http_probes()
        return {'lease_absent':True,'terminal':marker,'recovery_success':files}
    def complete(self,result):self.r.h.write_once(self.record/'completed.json',result)


def context(sha):
    if (re.fullmatch('[a-f0-9]{40}',sha or '') is None or os.geteuid()!=0 or sys.platform!='linux'
            or sys.executable!='/usr/bin/python3.12' or not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode)
            or 'SSH_ORIGINAL_COMMAND' in os.environ):raise LeaseBlocked('isolated canonical operator required')
    source=ROOT/'bootstrap'/sha/'source';entry=source/'scripts/exam_recovery_lease.py'
    if Path(__file__).absolute()!=entry:raise LeaseBlocked('canonical retirement path required')
    outer_path=entry.with_name('exam_release_recovery.py')
    for p in [*reversed(entry.parents),entry,outer_path]:
        s=p.lstat()
        if s.st_uid!=0 or s.st_gid!=0 or s.st_mode&0o022 or not(stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode)) or stat.S_ISREG(s.st_mode) and s.st_nlink!=1:
            raise LeaseBlocked('unsafe canonical path')
    if os.path.lexists(entry.parent/'__pycache__'):raise LeaseBlocked('cached operator forbidden')
    spec=importlib.util.spec_from_file_location('exam_lease_outer',outer_path)
    outer=importlib.util.module_from_spec(spec);spec.loader.exec_module(outer)
    verified,bootstrap=outer.context(sha)
    return outer,verified,bootstrap


def main():
    try:
        parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
        parser.add_argument('--sha',required=True);parser.add_argument('--evidence-sha256')
        args=parser.parse_args();outer,source,b=context(args.sha)
        raw=sys.stdin.buffer.read(257)
        if re.fullmatch(rb'[A-Za-z0-9._:-]{1,255}\n',raw) is None:raise LeaseBlocked('original token required')
        lock=ROOT/'launcher.lock';b.secure(lock,private=True)
        fd=os.open(lock,os.O_RDWR|os.O_NOFOLLOW);build_fd=r=None
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            build_fd=b._acquire_existing_build_lock(FAILED_SHA)
            r=outer.ProductionAdapter(source,b,args.sha,raw[:-1].decode(),fd,build_fd)
            print(json.dumps(retire(ProductionAdapter(r,outer),args.evidence_sha256),sort_keys=True))
        finally:
            if r is not None and r.engines is not None:
                for engine in r.engines:engine.dispose()
            if build_fd is not None:os.close(build_fd)
            os.close(fd)
        return 0
    except BaseException:
        print('EXAM_RECOVERY_LEASE_BLOCKED: preserve retirement intent and original evidence; no automatic replay',file=sys.stderr)
        return 1

if __name__=='__main__':raise SystemExit(main())
