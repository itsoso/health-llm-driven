import os,sys,json,stat,hashlib,subprocess,re,importlib.util
from pathlib import Path
SHA='fdd5659502888d44bf91c9b35a7368366932098f';OLD='f42bb4c6d1c962453a6eadd1318ca6b663174b80'
SOURCE=Path('/var/lib/reva-release/bootstrap')/SHA/'source';STATE=Path('/var/lib/reva-release')
FIELDS=('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_ctime_ns','st_mtime_ns')
ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LC_ALL':'C','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_SYSTEM':'/dev/null','GIT_NO_REPLACE_OBJECTS':'1','GIT_OPTIONAL_LOCKS':'0','GIT_TERMINAL_PROMPT':'0'}
def need(x):
 if not x:raise RuntimeError('incident proof blocked')
def identity(p):
 p=Path(p)
 for q in reversed(p.parents):
  st=q.lstat();need(stat.S_ISDIR(st.st_mode) and st.st_uid==0)
  need(not st.st_mode&0o022 or (q in (Path('/tmp'),Path('/run/lock')) and stat.S_IMODE(st.st_mode)==0o1777))
 a=p.lstat();need(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and a.st_uid==0 and not a.st_mode&0o022)
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:b=os.fstat(f.fileno());raw=f.read(16000001);c=os.fstat(f.fileno())
 z=p.lstat();need(len(raw)<=16000000 and all(getattr(a,k)==getattr(b,k)==getattr(c,k)==getattr(z,k) for k in FIELDS))
 return {**{k:getattr(a,k) for k in FIELDS},'sha256':hashlib.sha256(raw).hexdigest()},raw
def run(args):return subprocess.check_output(args,env=ENV,stderr=subprocess.DEVNULL,timeout=30).decode().strip()
def load(n,pin):
 p=SOURCE/'scripts'/n;i,raw=identity(p);need(i['sha256']==pin)
 spec=importlib.util.spec_from_file_location('incident_'+n[:-3],p);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;exec(compile(raw,str(p),'exec'),m.__dict__);return m
def collect(*, lease_path=Path('/run/lock/health-app-release')):
 need(os.geteuid()==0 and sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode)
 m=load('dinner_guard_recovery.py','941fc3830f00e1b63886329ed20352b93a02bea46052f89dd3b4e0ec883fbed4')
 need(run(['/usr/bin/git','-C','/opt/health-app','rev-parse','HEAD'])==OLD);run(['/usr/bin/git','-C','/opt/health-app','diff','--quiet','HEAD','--'])
 root=STATE/SHA;lease=lease_path
 result={'sha':SHA,'production_sha':OLD,'workspace_inventory':sorted(p.name for p in root.iterdir()),'lease_inventory':sorted(p.name for p in lease.iterdir())}
 result['workspace']={n:identity(root/n)[0] for n in ('started.json','completed.json','preparation-started.json','prepared.json','deployment-started.json','deployment.log','preparation.log')}
 need(json.loads(identity(root/'completed.json')[1])=={'sha':SHA,'state':'NEEDS_OPERATOR'})
 raw=identity(root/'deployment.log')[1]
 result['log_markers']={n.decode():raw.count(n) for n in (b'phase=remote_guard_started',b'phase=remote_writers_stopped',b'phase=remote_checkout_completed',b'command=prepare-code',b'command=install',b'command=commit',b'command=restore')}
 result['lease']={n:identity(lease/n)[0] for n in result['lease_inventory']}
 pointer=identity(lease/'stage')[1];need(re.fullmatch(rb'/tmp/health-app-backup-preflight-[A-Za-z0-9._-]+\n',pointer));stage=Path(pointer.decode().strip())
 result['stage_path']=str(stage);result['stage_inventory']=sorted(p.name for p in stage.iterdir());result['stage']={n:identity(stage/n)[0] for n in result['stage_inventory']}
 runtime=Path('/var/lib/health-app/release-state');result['runtime_inventory']=sorted(p.name for p in runtime.iterdir());result['terminal']=identity(runtime/'runtime-state-terminal.json')[0]
 terminal=json.loads(identity(runtime/'runtime-state-terminal.json')[1]);need(terminal['phase']=='COMMITTED' and terminal['terminal_sha']==OLD)
 result['files']={p:identity(p)[0] for p in m.FILE_PINS};result['files_match_old_pins']=all(result['files'][p]['sha256']==pin for p,pin in m.FILE_PINS.items())
 result['dependencies']={p:m.dependency_metadata(p) for p in ('/opt/health-app/backend/venv','/opt/health-app/backend/pi-runtime/node_modules')}
 result['static_units']={};result['services']={}
 for unit in ('health-backend.socket','health-backend.service','celery-worker.service','celery-beat.service'):
  raw=run(['/usr/bin/systemctl','show',unit,'--property=FragmentPath,DropInPaths,ExecStart,EnvironmentFiles,WorkingDirectory,User,Group,Requires,After,NeedDaemonReload']).encode()
  result['static_units'][unit]=m.unit_static_digest(m.unit_static_properties(raw))
  props=('ActiveState','SubState','MainPID','ControlPID','ControlGroup','NRestarts','Result','ExecMainStartTimestampMonotonic')
  values={k:run(['/usr/bin/systemctl','show',unit,'--property='+k,'--value']) for k in props}
  if values['MainPID'].isdigit() and int(values['MainPID'])>0:
   pid=values['MainPID'];f=Path('/proc/'+pid+'/stat').read_bytes().rsplit(b')',1)[-1].split();values['startticks']=int(f[19]);need(os.readlink('/proc/'+pid+'/cwd')=='/opt/health-app/backend')
  result['services'][unit]=values
 result['jobs_empty']=not run(['/usr/bin/systemctl','list-jobs','--no-legend','--plain','--no-pager'])
 result['policy']=identity('/etc/reva-release/authorized-release.json')[0] if Path('/etc/reva-release/authorized-release.json').exists() else None
 return result


def semantic_snapshot(snapshot):
    need(isinstance(snapshot, dict) and set(snapshot) == {'incident', 'config', 'installed'})
    v = snapshot['incident']
    units = {}
    for unit, pin in v['static_units'].items():
        prefix = '/etc/systemd/system/' + unit
        units[unit] = {'effective_sha256': pin, 'files': {
            path: value for path, value in v['files'].items()
            if path == prefix or path.startswith(prefix + '.d/')}}
    return {'lease': v['lease'], 'log': v['workspace']['deployment.log'],
            'completed': v['workspace']['completed.json'], 'terminal': v['terminal'],
            'files': v['files'], 'units': units, 'dependencies': v['dependencies'],
            'recovery_snapshot': snapshot}


def assert_incident(snapshot, *, lease_path=Path('/run/lock/health-app-release')):
    current = collect(lease_path=lease_path)
    immutable = {k: v for k, v in current.items() if k not in ('services', 'jobs_empty')}
    need(current['jobs_empty'] and immutable == snapshot['incident'])
    for path in ('/var/lib/reva-health-evidence-runtime/enabled.env',
                 '/run/reva-health-evidence-activation', '/opt/health-app/backend/.env.reva-release.tmp'):
        need(not os.path.lexists(path))
    for unit in ('health-backend.service', 'celery-worker.service', 'celery-beat.service'):
        need(not os.path.lexists(Path('/run/systemd/system') / (unit + '.d') / '90-reva-health-evidence-activation.conf'))
    return semantic_snapshot(snapshot)


class Helpers:
    FIELDS = FIELDS
    LIVE = Path('/opt/health-app')
    LEASE = Path('/run/lock/health-app-release')
    identity = staticmethod(identity)
    run = staticmethod(lambda args: subprocess.check_output(args, env=ENV, stderr=subprocess.DEVNULL, timeout=30))

    def __init__(self, snapshot):
        self.original = load('dinner_guard_recovery.py', '941fc3830f00e1b63886329ed20352b93a02bea46052f89dd3b4e0ec883fbed4')
        self.LEASE_PINS = {key: value['sha256'] for key, value in snapshot['incident']['lease'].items()}
        self.FILE_PINS = {key: value['sha256'] for key, value in snapshot['incident']['files'].items()}
        self.secure = self.original.secure
        self.dependency_metadata = self.original.dependency_metadata


class Proof:
    def __init__(self, source, b, server, snapshot, check):
        self.snapshot_value, self.check = snapshot, check
        self.helpers = Helpers(snapshot)
        module = self.helpers.original.load(source / 'scripts/contained_recovery_proof.py', 'fdd_closure_base')
        _, raw = identity(self.helpers.LEASE / 'token')
        need(re.fullmatch(rb'[A-Za-z0-9._:-]{1,255}\n', raw))
        self.base = module.RecoveryProof(source, b, server, SHA, OLD, raw[:-1].decode('ascii'))
        self.base._original_lease = self.base._lease_snapshot()

    def snapshot(self):
        self.check()
        value = assert_incident(self.snapshot_value)
        self.check()
        return value

    def unit_configuration(self):
        return self.snapshot()['units']

    def running_snapshot(self):
        self.check()
        value = self.base.running_snapshot()
        self.check()
        return value
