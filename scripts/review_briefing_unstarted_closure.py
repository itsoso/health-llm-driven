"""Audit closure of one fixed briefing intent; never reset/retry/release authority.

The original reset remains UNKNOWN. The terminal describes only the reviewed
canonical write path, under the root-owned immutable-audit trust boundary.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import stat

TARGET = '1ba724dcb62ac389a72e41eecf40fea7aaca27e3'
PREDECESSOR = '1e676eaaaa025af20f248179715ab52630960c36'
INTENT_SHA256 = '9f9f82331243256975834805784e51646c3e03725f00a95dd81630f7c6fa3dd4'
ATTEMPT = 'after-1e676eaa-intent-only-v1'
TERMINAL = 'CANONICAL_WRITE_NOT_ENTERED'
AUTHORITY = {'reset':False, 'retry':False, 'release':False, 'rotation':False, 'new_attempt':False}
SUCCESSOR_OPERATOR = '49a742fa22606eec0186c9f6034538e7e554a00d'
SUCCESSOR_INTENT_SHA256 = 'b140be7864c78e729fc15a128680785ebfdc21748519df23589cda955dceb34d'
SUCCESSOR_SOURCE_HASHES = {
    'review_briefing_unstarted_closure.py':'d0aabfca82416bbf6cc19f22f49ad5f0bac10876b921b5eb5b62b96f197bd787',
    'trusted_review_briefing_repair.py':'e837a2d7cc9d42d5251c917d356af06f40c39f8d19d17b9242c9319eea6269cf',
    'review_demo_briefing_repair.py':'99fec38098c19cc5fbd8bb644a5a2b6cbaf24541ccacb49110ebcef2b42fffb9',
}
SOURCE_HASHES = {
    'trusted_review_briefing_repair.py':'4a1584a8cf4e39da97f8c6473f0701bf054444dcb6c78c7ab7de09d02fb333f5',
    'review_demo_briefing_repair.py':'99fec38098c19cc5fbd8bb644a5a2b6cbaf24541ccacb49110ebcef2b42fffb9',
    'review_maintenance_retirement.py':'fe289598f972ec8f2747bdfdae6fe2ecf35b56b56c25b88e355cdadb902e4987',
}


class ClosureError(Exception):
    """Static non-sensitive rejection."""


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def record_path(b):
    return b.STATE/'review-demo-briefing-unstarted-closures'/TARGET


def successor_path(b):
    return b.STATE/'review-demo-briefing-successors'/TARGET/ATTEMPT


def profile(sha):
    if re.fullmatch('[a-f0-9]{40}',sha or '') is None or sha in (TARGET,PREDECESSOR):
        raise ClosureError('distinct canonical closing operator required')


def predecessor(b):
    root=b.STATE/'review-demo-briefing-repairs'/TARGET
    inventory=b._inventory(root,{'intent.json'})
    if inventory['intent.json']['sha256'] != INTENT_SHA256:
        raise ClosureError('fixed original briefing intent differs')
    intent=b._read_json(root/'intent.json')
    if intent.get('operator_sha') != PREDECESSOR or intent.get('accept_demo_briefing_repair') is not True:
        raise ClosureError('fixed original briefing authority differs')
    # Full inode/time metadata is retained as well as the protected byte digest.
    identities={}
    for path in (root,root/'intent.json'):
        s=path.lstat()
        identities[path.name if path!=root else '.']={k:getattr(s,k) for k in
            ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')}
    if b._inventory(root,{'intent.json'}) != inventory:
        raise ClosureError('original briefing changed during observation')
    return {'inventory':inventory,'identities':identities}


def fixed_sources(b):
    source=b.canonical_source(PREDECESSOR)
    for name,expected in SOURCE_HASHES.items():
        path=source/'scripts'/name;b.secure(path)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ClosureError('original canonical write ordering differs')
    return SOURCE_HASHES.copy()


def closed_evidence(b,sha):
    """File-only history consumer. No live demo query or source execution."""
    profile(sha)
    root=record_path(b);inventory=b._inventory(root,{'intent.json','completed.json'})
    intent=b._read_json(root/'intent.json');end=b._read_json(root/'completed.json')
    evidence=intent.get('evidence',{})
    expected={'state':TERMINAL,'operator_sha':sha,'evidence_sha256':digest(evidence),
              'original_outcome':'UNKNOWN','authority':AUTHORITY}
    if (set(intent) != {'evidence','evidence_sha256','accept_briefing_unstarted_closure'}
            or set(evidence) != {'scope','operator_sha','target_sha','predecessor_operator_sha',
                                 'predecessor','write_ordering_source_hashes','production','reconciliation'}
            or intent.get('accept_briefing_unstarted_closure') is not True
            or intent.get('evidence_sha256')!=digest(evidence) or end!=expected
            or evidence.get('operator_sha')!=sha or evidence.get('target_sha')!=TARGET
            or evidence.get('predecessor_operator_sha')!=PREDECESSOR
            or evidence.get('predecessor')!=predecessor(b)
            or evidence.get('write_ordering_source_hashes')!=SOURCE_HASHES
            or evidence.get('scope')!='fixed_briefing_canonical_write_path_only'):
        raise ClosureError('complete fixed audit closure required')
    if b._inventory(root,{'intent.json','completed.json'})!=inventory:
        raise ClosureError('audit closure changed during observation')
    return {'inventory':inventory,'operator_sha':sha,'evidence_sha256':digest(evidence),
            'predecessor':evidence['predecessor']}


def close(adapter,*,accepted=False,evidence_sha256=None):
    if os.path.lexists(adapter.record):
        raise ClosureError('closure already attempted; no retry')
    evidence=adapter.inspect();fingerprint=digest(evidence)
    if evidence_sha256 is None:
        if accepted:raise ClosureError('fresh digest required with acceptance')
        return {'state':'INSPECTED_NO_CLOSURE_AUTHORITY','evidence_sha256':fingerprint}
    if accepted is not True or fingerprint!=evidence_sha256:
        raise ClosureError('separate explicit audit acceptance and fresh digest required')
    adapter.prepare()
    adapter.write('intent.json',{'evidence':evidence,'evidence_sha256':fingerprint,
                                'accept_briefing_unstarted_closure':True})
    if adapter.inspect()!=evidence:
        raise ClosureError('audit evidence changed after intent')
    end={'state':TERMINAL,'operator_sha':evidence.get('operator_sha'),
         'evidence_sha256':fingerprint,'original_outcome':'UNKNOWN','authority':AUTHORITY.copy()}
    adapter.write('completed.json',end)
    return end


def make_adapter(source,b,server,readers,ack,briefing,sha,check):
    profile(sha)
    guard=ack.make_adapter(source,b,server,readers,sha,TARGET,briefing.OPERATION,check)
    class Adapter:
        record=record_path(b)
        def inspect(self):
            check()
            if os.path.lexists(successor_path(b)):
                raise ClosureError('successor already exists')
            prior=predecessor(b);sources=fixed_sources(b)
            production=guard.inspect()
            reconciliation=briefing.acknowledgement_evidence(b,readers,ack,sha,allow_fixed_successor=True)
            if predecessor(b)!=prior or fixed_sources(b)!=sources:
                raise ClosureError('original intent or canonical source changed')
            check()
            return {'scope':'fixed_briefing_canonical_write_path_only','operator_sha':sha,
                    'target_sha':TARGET,'predecessor_operator_sha':PREDECESSOR,
                    'predecessor':prior,'write_ordering_source_hashes':sources,
                    'production':production,'reconciliation':reconciliation}
        def prepare(self):
            if not self.record.parent.exists():
                self.record.parent.mkdir(mode=0o700);readers.sync(self.record.parent.parent)
            b.secure(self.record.parent)
            if self.record.parent.stat().st_mode & 0o077:
                raise ClosureError('private closure directory required')
            self.record.mkdir(mode=0o700);readers.sync(self.record.parent)
        def write(self,name,value):
            if name not in ('intent.json','completed.json'):raise ClosureError('invalid audit record')
            readers.write_json(self.record/name,value)
    return Adapter()


def successor_history(b):
    """Verify immutable write ordering and consume only the old file receipt."""
    source=b.canonical_source(SUCCESSOR_OPERATOR)
    for name,expected in SUCCESSOR_SOURCE_HASHES.items():
        path=source/'scripts'/name;b.secure(path)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ClosureError('fixed successor canonical sources changed')
    path=source/'scripts/review_briefing_unstarted_closure.py'
    spec=importlib.util.spec_from_file_location('fixed_successor_prior_closure',path)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    return {'closure':old.closed_evidence(b,SUCCESSOR_OPERATOR),
            'source_hashes':SUCCESSOR_SOURCE_HASHES.copy()}


def successor_evidence(b):
    root=successor_path(b)
    inventory=b._inventory(root,{'intent.json'})
    if inventory.get('intent.json',{}).get('sha256')!=SUCCESSOR_INTENT_SHA256:
        raise ClosureError('fixed successor intent differs')
    intent=b._read_json(root/'intent.json');history=successor_history(b)
    if (intent.get('operator_sha')!=SUCCESSOR_OPERATOR
            or intent.get('attempt_profile')!=ATTEMPT
            or intent.get('accept_demo_briefing_repair') is not True
            or intent.get('accept_successor_briefing_attempt') is not True
            or intent.get('unstarted_closure')!=history['closure']
            or intent.get('evidence_sha256')!=digest(intent.get('evidence'))):
        raise ClosureError('fixed successor authority or history differs')
    identities={}
    for p in (root,root/'intent.json'):
        s=p.lstat()
        identities[p.name if p!=root else '.']={k:getattr(s,k) for k in
            ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')}
    if b._inventory(root,{'intent.json'})!=inventory:
        raise ClosureError('successor changed during observation')
    return {'inventory':inventory,'identities':identities,'history':history}


def make_successor_adapter(source,b,server,readers,ack,briefing,sha,check):
    profile(sha)
    if sha==SUCCESSOR_OPERATOR:raise ClosureError('distinct successor audit operator required')
    guard=ack.make_adapter(source,b,server,readers,sha,TARGET,briefing.OPERATION,check)
    class Adapter:
        record=b.STATE/'review-demo-briefing-successor-closures'/TARGET/ATTEMPT
        def inspect(self):
            check()
            prior=successor_evidence(b)
            production=guard.inspect()
            reconciliation=briefing.acknowledgement_evidence(
                b,readers,ack,SUCCESSOR_OPERATOR,allow_fixed_successor=True)
            if successor_evidence(b)!=prior:
                raise ClosureError('successor evidence changed')
            check()
            return {'scope':'fixed_successor_canonical_write_path_only',
                    'operator_sha':sha,'target_sha':TARGET,'attempt_profile':ATTEMPT,
                    'predecessor_operator_sha':SUCCESSOR_OPERATOR,'predecessor':prior,
                    'production':production,'reconciliation':reconciliation}
        def prepare(self):
            for parent in (self.record.parent.parent,self.record.parent):
                if not parent.exists():
                    parent.mkdir(mode=0o700);readers.sync(parent.parent)
                b.secure(parent)
                if parent.stat().st_mode&0o077:raise ClosureError('private audit directory required')
            self.record.mkdir(mode=0o700);readers.sync(self.record.parent)
        def write(self,name,value):
            if name not in ('intent.json','completed.json'):raise ClosureError('invalid audit record')
            readers.write_json(self.record/name,value)
    return Adapter()


def main():
    try:
        parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
        parser.add_argument('--sha',required=True)
        parser.add_argument('--accept-briefing-unstarted-closure',action='store_true')
        parser.add_argument('--evidence-sha256')
        parser.add_argument('--successor-audit',action='store_true')
        parser.add_argument('--token-stdin',action='store_true')
        args=parser.parse_args();profile(args.sha)
        source=Path('/var/lib/reva-release/bootstrap')/args.sha/'source'
        if Path(__file__).absolute()!=source/'scripts/review_briefing_unstarted_closure.py':
            raise ClosureError('canonical closure entry required')
        if (os.geteuid()!=0 or sys.executable!='/usr/bin/python3.12' or not sys.flags.isolated
                or not sys.flags.no_site or not sys.flags.dont_write_bytecode or sys.flags.optimize
                or 'SSH_ORIGINAL_COMMAND' in os.environ):
            raise ClosureError('isolated root closure required')
        entry=source/'scripts/trusted_review_briefing_repair.py'
        for path in [*reversed(entry.parents),entry,Path(__file__).absolute()]:
            info=path.lstat();file=path in (entry,Path(__file__).absolute())
            if (info.st_uid!=0 or info.st_mode&0o022
                    or not (stat.S_ISREG(info.st_mode) if file else stat.S_ISDIR(info.st_mode))
                    or (file and info.st_nlink!=1)):
                raise ClosureError('unsafe canonical closure source')
        spec=importlib.util.spec_from_file_location('closure_briefing',source/'scripts/trusted_review_briefing_repair.py')
        briefing=importlib.util.module_from_spec(spec);spec.loader.exec_module(briefing)
        source,b,server,readers,ack,core=briefing.context(args.sha,token_stdin=args.token_stdin)
        b.secure(Path(__file__))
        lock=b.STATE/'launcher.lock';b.secure(lock,private=True)
        fd=os.open(lock,os.O_RDWR|os.O_NOFOLLOW);build_fd=None
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            build_fd=b._acquire_existing_build_lock(TARGET)
            if build_fd is None:raise ClosureError('existing build lock required')
            def check():
                b._assert_original_lock(lock,fd);b._assert_original_lock(b.STATE/TARGET/'build.lock',build_fd)
            factory=make_successor_adapter if args.successor_audit else make_adapter
            a=factory(source,b,server,readers,ack,briefing,args.sha,check)
            result=close(a,accepted=args.accept_briefing_unstarted_closure,evidence_sha256=args.evidence_sha256)
        finally:
            if build_fd is not None:os.close(build_fd)
            os.close(fd)
        print(json.dumps(result,sort_keys=True));return 0
    except (Exception,KeyboardInterrupt):
        print('audit closure rejected or incomplete; preserve all evidence; no retry',file=sys.stderr);return 1

if __name__=='__main__':sys.exit(main())
