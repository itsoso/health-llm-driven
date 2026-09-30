"""Fixed post-hardening monitor ingress repair; no service or staking mutation."""
import fcntl
import hashlib
import json
import os
import pwd
from pathlib import Path
import re
import secrets
import shlex
import stat
import subprocess
import time
import urllib.request

BASE = '56eec9e36f27e168f48dfca2ce8c17bf3d8c902b'
PRODUCTION = '051ee281f8247d162bcdef7b3f93fdf51930c94c'
STATE = Path('/var/lib/reva-release')
LEASE = Path('/var/lock/health-app-release')
RETIRED_PARENT = Path('/run/lock')
FAMILIES = (('/usr/sbin/iptables','ufw-before-input',Path('/etc/ufw/before.rules')),
            ('/usr/sbin/ip6tables','ufw6-before-input',Path('/etc/ufw/before6.rules')))
RULE = ('!', '-i', 'lo', '-p', 'tcp', '-m', 'multiport', '--dports', '9090,9100', '-j', 'DROP')
ALLOWED = {'scripts/monitor_ingress_repair.py','scripts/trusted_public_host.py',
           'scripts/bootstrap_trusted_release.py','scripts/test_public_host_boundaries.py',
           'scripts/test_public_host_network_native.py','docs/security/2026-09-30-host-preflight-recovery.md'}
SERVICES = {'health-backend','celery-worker','celery-beat','health-frontend',
            'lighthouse-validator','lighthouse-beacon','eth1','prometheus','prometheus-node-exporter'}


def validate_intent(value):
    def require(ok):
        if not ok:raise RuntimeError('monitor intent inner evidence differs')
    def integer(x,minimum=0):return type(x) is int and x>=minimum
    def sha(x,length=64):return isinstance(x,str) and re.fullmatch('[a-f0-9]{'+str(length)+'}',x) is not None
    require(isinstance(value,dict) and set(value)=={'production_sha','publisher_sha','host_history','services','families'})
    require(value['production_sha']==PRODUCTION and sha(value['publisher_sha'],40) and value['publisher_sha'] not in (BASE,PRODUCTION))
    host=value['host_history']
    require(isinstance(host,dict) and set(host)=={'kind','intent_sha256','completion_sha256'} and host['kind']=='recovered-host-hardening'
            and sha(host['intent_sha256']) and sha(host['completion_sha256']))
    require(isinstance(value['services'],dict) and set(value['services'])==SERVICES)
    for name,entry in value['services'].items():
        require(isinstance(entry,dict) and set(entry)=={'properties','process'})
        props,proc=entry['properties'],entry['process']
        require(isinstance(props,dict) and set(props)=={'ActiveState','MainPID','NRestarts','NeedDaemonReload'}
                and props['ActiveState']=='active' and props['NeedDaemonReload']=='no'
                and isinstance(props['NRestarts'],str) and props['NRestarts'].isdigit())
        require(isinstance(proc,dict) and set(proc)=={'pid','starttime','uid','cgroup','argv_sha256'}
                and integer(proc['pid'],2) and props['MainPID']==str(proc['pid'])
                and isinstance(proc['starttime'],str) and proc['starttime'].isdigit()
                and isinstance(proc['cgroup'],str) and bool(proc['cgroup']) and sha(proc['argv_sha256']))
        require(isinstance(proc['uid'],list) and len(proc['uid'])==4 and len(set(proc['uid']))==1
                and all(isinstance(x,str) and x.isdigit() for x in proc['uid']))
        if name in ('health-backend','celery-worker','celery-beat','health-frontend'):require(int(proc['uid'][0])>0)
        if name in ('lighthouse-validator','lighthouse-beacon','eth1'):require(proc['uid']==['0']*4)
    require(isinstance(value['families'],dict) and set(value['families'])=={x[0] for x in FAMILIES})
    for binary,chain,_ in FAMILIES:
        entry=value['families'][binary]
        require(isinstance(entry,dict) and set(entry)=={'policy','config'})
        policy=entry['policy'];config=entry['config']
        require(isinstance(policy,list) and bool(policy) and all(isinstance(x,str) and x and not x.startswith('#') for x in policy)
                and policy[-1]=='COMMIT' and policy.count('*filter')==1 and ':INPUT DROP [COUNTERS]' in policy)
        require(isinstance(config,dict) and set(config)=={'text','mode','uid','gid','sha256'}
                and config['uid']==0 and config['gid']==0 and config['mode'] in (0o600,0o640,0o644)
                and isinstance(config['text'],str) and len(config['text'])<=1000000 and sha(config['sha256'])
                and hashlib.sha256(config['text'].encode()).hexdigest()==config['sha256'])
        policy_after(policy,chain);config_after(config['text'],chain)


def rule_line(chain):
    if chain not in {x[1] for x in FAMILIES}:raise RuntimeError('fixed monitor chain required')
    return '-A '+chain+' '+' '.join(RULE)


def policy_after(before, chain):
    line=rule_line(chain)
    if line in before:raise RuntimeError('monitor boundary already attempted')
    indexes=[i for i,x in enumerate(before) if x.startswith('-A '+chain+' ')]
    if not indexes:raise RuntimeError('monitor input chain absent')
    i=indexes[0]
    return [*before[:i],line,*before[i:]]


def config_after(raw, chain):
    if ('\r' in raw or '\x00' in raw or not raw.endswith('\n') or raw.count('*filter\n')!=1 or raw.count('COMMIT\n')!=1
            or f':{chain} - [0:0]\n' not in raw):
        raise RuntimeError('unsupported persistent monitor configuration')
    lines=raw.splitlines()
    active=[x for x in lines if x and not x.startswith('#')]
    if (active[0]!='*filter' or active[-1]!='COMMIT'
        or any(not (x.startswith('-A ') or re.fullmatch(r':[A-Za-z0-9_-]+ (?:-|ACCEPT|DROP) \[[0-9]+:[0-9]+\]',x)) for x in active[1:-1])):
        raise RuntimeError('persistent monitor filter boundaries differ')
    result='\n'.join(policy_after(lines,chain))+'\n'
    if result.replace(rule_line(chain)+'\n','',1)!=raw:raise RuntimeError('persistent monitor bytes differ')
    return result


def verify_delta(before, after, chain):
    if after!=policy_after(before,chain):raise RuntimeError('monitor firewall delta differs')


def verify_reachability(rows, logging, chain):
    prefix=chain.removesuffix('input')
    if logging != ['-N '+prefix+'logging-input']:
        raise RuntimeError('earlier logging chain may bypass monitor deny')
    target='-A INPUT -j '+chain
    if rows.count(target)!=1:raise RuntimeError('monitor chain attachment differs')
    for row in rows[:rows.index(target)]:
        parts=shlex.split(row)
        if row in ('-P INPUT DROP','-A INPUT -j '+prefix+'logging-input'):
            continue
        if row=='-A INPUT -p tcp -m multiport --dports 22 -j f2b-sshd':
            continue
        if len(parts)==6 and parts[:3]==['-A','INPUT','-s'] and parts[-2:]==['-j','DROP']:
            continue
        raise RuntimeError('earlier input rule may bypass monitor deny')


def source_scope(source,b):
    base=b.canonical_source(BASE)
    def tree(root):
        raw=subprocess.check_output(['/usr/bin/git','-C',str(root),'ls-tree','-rz','--full-tree','HEAD'])
        return dict(row.split(b'\t',1)[::-1] for row in raw.split(b'\0') if row)
    old,new=tree(base),tree(source)
    changed={p.decode() for p in old.keys()|new.keys() if old.get(p)!=new.get(p)}
    if not changed or not changed<=ALLOWED:raise RuntimeError('monitor repair source scope differs')


def config_snapshot(path,b):
    b.secure(path)
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_gid!=0 or info.st_nlink!=1 or info.st_size>1000000:
        raise RuntimeError('unsafe monitor configuration')
    raw=path.read_bytes().decode('utf-8')
    return {'text':raw,'mode':stat.S_IMODE(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,
            'sha256':hashlib.sha256(raw.encode()).hexdigest()}


def service_snapshot(r,g):
    result=r.services(g)
    for name in ('health-frontend','prometheus','prometheus-node-exporter'):
        props=dict(row.split('=',1) for row in g.run('/usr/bin/systemctl','show',name,
            '-p','ActiveState,MainPID,NRestarts,NeedDaemonReload').splitlines())
        if props['ActiveState']!='active' or props['NeedDaemonReload']!='no' or int(props['MainPID'])<=1:
            raise RuntimeError('protected service not stable')
        result[name]={'properties':props,'process':r.process_identity(props['MainPID'])}
    return result


def readiness():
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):raise RuntimeError('monitor readiness redirect forbidden')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    for url in ('http://127.0.0.1:9090/-/healthy','http://127.0.0.1:9100/',
                'http://127.0.0.1:8000/health','http://127.0.0.1:30001/login'):
        with opener.open(url,timeout=5) as response:
            if response.status!=200 or response.geturl()!=url:raise RuntimeError('local service readiness differs')


def verify_output(g):
    for binary,_,_ in FAMILIES:
        jumps=[]
        for user in g.APPLICATION_PORTS:
            chain,rules,jump=g.firewall_rules(user,pwd.getpwnam(user).pw_uid,binary.endswith('/ip6tables'))
            rows=[shlex.split(x)[2:] for x in g.run(binary,'-S',chain).splitlines() if x.startswith('-A ')]
            if [g.canonical_rule(x) for x in rows]!=[g.canonical_rule(x) for x in rules]:raise RuntimeError('application output boundary changed')
            jumps.insert(0,jump)
        rows=[shlex.split(x)[2:] for x in g.run(binary,'-S','OUTPUT').splitlines() if x.startswith('-A ')]
        if [g.canonical_rule(x) for x in rows[:2]]!=[g.canonical_rule(x) for x in jumps]:raise RuntimeError('application owner attachment changed')


class Adapter:
    def __init__(self,source,host,helper,b,server,g,r,publisher,check):
        self.source,self.host,self.helper,self.b,self.server,self.g,self.r,self.publisher=source,host,helper,b,server,g,r,publisher
        self.record=STATE/'monitor-ingress-repairs'/PRODUCTION
        self.check=check

    def preserved(self):
        proof=self.r.history_evidence(self.b,PRODUCTION)
        done=self.b._read_json(STATE/'host-hardening-recoveries'/PRODUCTION/'completed.json')
        if done['publisher_sha']!=BASE:raise RuntimeError('fixed host completion required')
        return proof

    def inspect(self):
        self.check()
        self.b._recovery_process_proof()
        self.helper._revision_proof(PRODUCTION,self.b.canonical_source(PRODUCTION),self.b)
        self.host.verify_runtime(self.g,check_network=False)
        verify_output(self.g)
        result={'production_sha':PRODUCTION,'publisher_sha':self.publisher,'host_history':self.preserved(),
                'services':service_snapshot(self.r,self.g),'families':{}}
        for binary,chain,path in FAMILIES:
            before=self.r.firewall_policy(self.g.run(binary+'-save'))
            config=config_snapshot(path,self.b)
            candidate=config_after(config['text'],chain);policy_after(before,chain)
            restore=Path(binary+'-restore').resolve(strict=True)
            self.b.secure(restore)
            subprocess.run([binary+'-restore','--test','--noflush','--wait','5'],input=candidate,text=True,
                           check=True,timeout=15,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if self.r.firewall_policy(self.g.run(binary+'-save'))!=before:raise RuntimeError('syntax validation changed firewall')
            verify_reachability(self.g.run(binary,'-S','INPUT').splitlines(),
                                self.g.run(binary,'-S',chain.removesuffix('input')+'logging-input').splitlines(),chain)
            result['families'][binary]={'policy':before,'config':config}
        readiness()
        validate_intent(result);self.check()
        return result

    def apply(self,before):
        for binary,chain,path in FAMILIES:
            self.check()
            old=before['families'][binary]
            if config_snapshot(path,self.b)!=old['config'] or self.r.firewall_policy(self.g.run(binary+'-save'))!=old['policy']:
                raise RuntimeError('monitor boundary drift before mutation')
            self.g.atomic_write(path,config_after(old['config']['text'],chain),old['config']['mode'])
            self.check()
            self.g.run(binary,'-w','5','-I',chain,'1',*RULE)
            verify_delta(old['policy'],self.r.firewall_policy(self.g.run(binary+'-save')),chain)

    def verify(self,before):
        self.check()
        verify_output(self.g)
        for binary,chain,path in FAMILIES:
            old=before['families'][binary]
            verify_delta(old['policy'],self.r.firewall_policy(self.g.run(binary+'-save')),chain)
            wanted=config_after(old['config']['text'],chain)
            if config_snapshot(path,self.b)!={**old['config'],'text':wanted,'sha256':hashlib.sha256(wanted.encode()).hexdigest()}:
                raise RuntimeError('persistent monitor boundary differs')
            verify_reachability(self.g.run(binary,'-S','INPUT').splitlines(),
                                self.g.run(binary,'-S',chain.removesuffix('input')+'logging-input').splitlines(),chain)
        if service_snapshot(self.r,self.g)!=before['services'] or self.preserved()!=before['host_history']:
            raise RuntimeError('protected services or historical evidence changed')
        readiness()
        self.check()


def lease_snapshot(server,values):
    server._testflight_lease_parent()
    info=LEASE.lstat();server.validate_metadata(info,directory=True)
    if stat.S_IMODE(info.st_mode)!=0o700 or {p.name for p in LEASE.iterdir()}!=set(values):
        raise RuntimeError('monitor lease differs')
    def metadata(info,raw=None):
        return {'dev':info.st_dev,'ino':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,
                'mode':stat.S_IMODE(info.st_mode),'sha256':None if raw is None else hashlib.sha256(raw).hexdigest()}
    result={'.':metadata(info)}
    for name,value in values.items():
        path=LEASE/name
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno());server.validate_metadata(info,private=True)
            raw=stream.read(4097)
            if raw!=(value+'\n').encode():raise RuntimeError('monitor lease ownership changed')
            result[name]=metadata(info,raw)
    return result


def transaction(a,evidence_sha256=None):
    a.check()
    if os.path.lexists(a.record) or os.path.lexists(LEASE):raise RuntimeError('existing monitor attempt or business lease; no retry')
    before=a.inspect();digest=a.r.digest(before)
    if evidence_sha256 is None:return {'state':'MONITOR_INGRESS_PREFLIGHT','evidence_sha256':digest}
    if evidence_sha256!=digest:raise RuntimeError('monitor preflight evidence changed')
    a.check()
    a.record.parent.mkdir(mode=0o700,exist_ok=True);a.server.secure_path(a.record.parent,directory=True)
    a.record.mkdir(mode=0o700);a.server._sync_directory(a.record.parent)
    a.server._write_private(a.record/'intent.json',json.dumps(before,sort_keys=True).encode())
    a.server._testflight_lease_parent();LEASE.mkdir(mode=0o700)
    values={'token':secrets.token_hex(32),'label':'monitor-ingress','stage':str(a.record),'started_at':str(int(time.time()))}
    for name,value in values.items():a.server._write_private(LEASE/name,(value+'\n').encode())
    a.server._sync_business_lease_parent();identity=lease_snapshot(a.server,values)
    a.server._write_private(a.record/'lease.json',json.dumps(identity,sort_keys=True).encode())
    if a.inspect()!=before:raise RuntimeError('monitor evidence changed after intent')
    a.apply(before);a.verify(before)
    time.sleep(3);a.verify(before)
    a.check()
    if lease_snapshot(a.server,values)!=identity:raise RuntimeError('monitor lease replaced')
    archive=a.record/'lease';archive.mkdir(mode=0o700)
    for name,value in values.items():a.server._write_private(archive/name,(value+'\n').encode())
    a.server._sync_directory(a.record)
    retired=RETIRED_PARENT/('health-app-release.monitor-retired-'+PRODUCTION)
    if os.path.lexists(retired) or LEASE.lstat().st_dev!=retired.parent.stat().st_dev:raise RuntimeError('monitor lease retirement unavailable')
    subprocess.run(['/usr/bin/mv','--no-clobber','-T','--',str(LEASE),str(retired)],check=True,timeout=15,
                   stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    a.server._sync_business_lease_parent()
    if os.path.lexists(LEASE) or (retired.stat().st_dev,retired.stat().st_ino)!=(identity['.']['dev'],identity['.']['ino']):raise RuntimeError('monitor lease retirement unproven')
    done={'state':'MONITOR_INGRESS_LOCAL_VERIFIED','production_sha':PRODUCTION,'publisher_sha':a.publisher,
          'intent_sha256':digest,'lease_sha256':a.r.digest(identity),'external_readback_required':True}
    a.server._write_private(a.record/'completed.json',json.dumps(done,sort_keys=True).encode())
    return done


def execute(source,host,helper,b,server,gate,g,r,publisher,production,evidence_sha256=None):
    if production!=PRODUCTION or publisher in (BASE,PRODUCTION):raise RuntimeError('fixed monitor incident required')
    gate.verify_release(publisher,publisher);source_scope(source,b)
    lock=STATE/'launcher.lock';b.secure(lock,private=True)
    with lock.open('r+b') as stream:
        fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        build=b._acquire_existing_build_lock(PRODUCTION)
        try:
            def check():
                b._assert_original_lock(lock,stream.fileno())
                if build is not None:b._assert_original_lock(STATE/PRODUCTION/'build.lock',build)
            check();server.assert_ota_history()
            return transaction(Adapter(source,host,helper,b,server,g,r,publisher,check),evidence_sha256)
        finally:
            if build is not None:os.close(build)


def history_evidence(b,host_history):
    root=STATE/'monitor-ingress-repairs'
    if not os.path.lexists(root):return None
    b.secure(root)
    if {p.name for p in root.iterdir()}!={PRODUCTION}:raise RuntimeError('unknown monitor history')
    record=root/PRODUCTION;b.secure(record)
    if not record.is_dir() or stat.S_IMODE(record.stat().st_mode)!=0o700 or {p.name for p in record.iterdir()}!={'intent.json','completed.json','lease.json','lease'}:
        raise RuntimeError('monitor recovery inventory differs')
    before=b._read_json(record/'intent.json');done=b._read_json(record/'completed.json')
    validate_intent(before)
    if (set(before)!={'production_sha','publisher_sha','host_history','services','families'}
        or before['production_sha']!=PRODUCTION or before['host_history']!=host_history
        or re.fullmatch('[a-f0-9]{40}',str(before['publisher_sha'])) is None
        or set(before['families'])!={x[0] for x in FAMILIES}):raise RuntimeError('monitor history binding differs')
    source_scope(b.canonical_source(before['publisher_sha']),b)
    digest=hashlib.sha256(json.dumps(before,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    lease=b._read_json(record/'lease.json')
    lease_digest=hashlib.sha256(json.dumps(lease,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if done!={'state':'MONITOR_INGRESS_LOCAL_VERIFIED','production_sha':PRODUCTION,'publisher_sha':before['publisher_sha'],
              'intent_sha256':digest,'lease_sha256':lease_digest,'external_readback_required':True}:raise RuntimeError('monitor completion differs')
    b._inventory(record/'lease',{'token','label','stage','started_at'})
    if ((record/'lease/label').read_text()!='monitor-ingress\n' or (record/'lease/stage').read_text()!=str(record)+'\n'
        or re.fullmatch('[a-f0-9]{64}\n',(record/'lease/token').read_text()) is None
        or re.fullmatch('[0-9]+\n',(record/'lease/started_at').read_text()) is None):raise RuntimeError('monitor historical lease differs')
    if not isinstance(lease,dict) or set(lease)!={'.','token','label','stage','started_at'}:raise RuntimeError('monitor lease schema differs')
    for name,info in lease.items():
        if (not isinstance(info,dict) or set(info)!={'dev','ino','uid','gid','mode','sha256'} or info['uid']!=0 or info['gid']!=0
            or any(type(info[x]) is not int or info[x]<1 for x in ('dev','ino'))
            or info['mode']!=(0o700 if name=='.' else 0o600)
            or info['sha256']!=(None if name=='.' else hashlib.sha256((record/'lease'/name).read_bytes()).hexdigest())):
            raise RuntimeError('monitor lease inner evidence differs')
    for _,chain,_ in FAMILIES:
        old=before['families'][next(x[0] for x in FAMILIES if x[1]==chain)]
        policy_after(old['policy'],chain);config_after(old['config']['text'],chain)
        if hashlib.sha256(old['config']['text'].encode()).hexdigest()!=old['config']['sha256']:raise RuntimeError('monitor backup bytes differ')
    completion_digest=hashlib.sha256(json.dumps(done,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'kind':'monitor-ingress-repair','intent_sha256':digest,'completion_sha256':completion_digest}
