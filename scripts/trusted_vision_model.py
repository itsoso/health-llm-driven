"""Root-only reviewed model selection transaction; never loads application secrets.

Config application is NOT model acceptance. A durable configuration terminal
receipt precedes release of this operation's business lease. A configuration-only terminal receipt never
claims that a paid model request succeeded. Unknown failures retain the lease.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time
import urllib.request

STATE = Path('/var/lib/reva-release')
PRODUCTION = Path('/opt/health-app')
LEASE = Path('/var/lock/health-app-release')
MODEL_ROOT = Path('/var/lib/reva-vision-model')
MODEL = MODEL_ROOT / 'model.env'
SYSTEMD = Path('/etc/systemd/system')
SERVICES = ('health-backend', 'celery-worker', 'celery-beat')
FLAGS = ('HEALTH_EVIDENCE_RUNTIME_ENABLED','AUTH_PHONE_SELF_REGISTRATION_ENABLED',
         'REGISTRATION_INVITATION_ENFORCEMENT_ENABLED','REGISTRATION_INVITATION_ROLLOUT_ENABLED')
DROPIN_NAME = 'zzzz-reva-vision-model.conf'
ENV = {'PATH':'/usr/bin:/bin','HOME':'/root','LC_ALL':'C',
       'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null',
       'GIT_CONFIG_SYSTEM':'/dev/null','GIT_NO_REPLACE_OBJECTS':'1'}
# Only configuration success is terminal here; model acceptance is independent.
PRODUCTION_APPLY_ENABLED = True
OLD_MODEL_RETIREMENT_UTC = 1791561600  # 2026-10-09T16:00:00Z
ROLLBACK_TIME_BUDGET = 240


class VisionError(Exception):
    """Sanitized operation failure."""


def checked_hex(value, length):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{%d}' % length, value) is None:
        raise VisionError('invalid exact operation binding')
    return value


def model_bytes(model):
    if model != 'qwen3.8-flash':
        raise VisionError('unsupported vision model')
    return b'LLM_VISION_MODEL=qwen3.8-flash\n'


def dropin_bytes():
    return b'[Service]\nEnvironmentFile=/var/lib/reva-vision-model/model.env\n'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':')).encode()).hexdigest()


def metadata(path, *, directory=False):
    """Metadata only: never opens credentials, grants or base EnvironmentFiles."""
    info = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode) or (not directory and info.st_nlink != 1):
        raise VisionError('unexpected configuration object')
    return {name: getattr(info, 'st_' + name) for name in
            ('dev','ino','mode','nlink','uid','gid','size','mtime_ns','ctime_ns')}


def secure_path(path, *, directory=False):
    for parent in reversed(path.parents):
        item = metadata(parent, directory=True)
        if item['uid'] != 0 or item['mode'] & 0o022:
            raise VisionError('unsafe configuration parent')
    item = metadata(path, directory=directory)
    if item['uid'] != 0 or item['mode'] & 0o022:
        raise VisionError('unsafe configuration ownership')
    return item


def optional_model_file(path):
    if not os.path.lexists(path):
        return None
    before = metadata(path)
    if before['size'] > 1024:
        raise VisionError('model file exceeds bound')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        if metadata(path) != before:
            raise VisionError('model file changed')
        raw = stream.read(1025)
    if raw not in (model_bytes('qwen3.8-flash'), dropin_bytes()):
        raise VisionError('model-only file has unknown contents')
    if metadata(path) != before:
        raise VisionError('model file changed')
    return {'metadata':before,'content':raw.decode()}


def atomic_model_write(path, raw):
    if raw not in (model_bytes('qwen3.8-flash'), dropin_bytes()):
        raise VisionError('model-only write rejected')
    temporary = path.with_name('.' + path.name + '.' + secrets.token_hex(16))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.lexists(temporary):
            temporary.unlink()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def run(args, *, timeout=90):
    try:
        return subprocess.run(args, env=ENV, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout, check=True, text=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        raise VisionError('fixed operation failed; evidence retained') from None


def validate_env_sources(value, *, installed):
    expected = ['/opt/health-app/backend/.env', '/var/lib/reva-health-evidence-runtime/enabled.env']
    if installed:
        expected.append(str(MODEL))
    rendered = [' '.join(path + (' (ignore_errors='+optional+')' if path == expected[1] else ' (ignore_errors=no)') for path in expected) for optional in ('yes','no')]
    if value not in rendered:
        raise VisionError('service EnvironmentFile order differs')


def validate_unset_environment(value):
    # Refuse all unset rules rather than parsing/printing possible NAME=value
    # payloads. The operator cannot prove a model survives unknown unsets.
    if value:
        raise VisionError('service environment unset rule requires review')


def validate_binding(expected, live, receipt):
    checked_hex(expected, 40)
    if live != expected or receipt != {'sha': expected, 'state':'SUCCEEDED'}:
        raise VisionError('deployed backend success binding differs')


def load_reviewed(publisher):
    source = STATE / 'bootstrap' / publisher / 'source'
    entry = source / 'scripts/trusted_vision_model.py'
    if Path(__file__).absolute() != entry:
        raise VisionError('canonical operator staging required')
    secure_path(entry)
    def module(name, filename):
        path = entry.with_name(filename)
        secure_path(path)
        spec = importlib.util.spec_from_file_location(name, path)
        value = importlib.util.module_from_spec(spec)
        sys.modules[name] = value
        spec.loader.exec_module(value)
        return value
    helper = module('vision_reviewed_helpers', 'trusted_review_reset.py')
    reviewed, bootstrap, server = helper.load_reviewed(publisher)
    if reviewed != source:
        raise VisionError('reviewed source differs')
    gate = module('vision_exact_ci_gate', 'trusted_release_gate.py')
    return source, helper, bootstrap, server, gate


def parse_service_properties(raw):
    values, environment = {}, []
    for line in raw.splitlines():
        key, separator, value = line.partition('=')
        if not separator:
            raise VisionError('invalid service property response')
        if key == 'EnvironmentFiles':
            environment.append(value)
        elif key in values:
            raise VisionError('duplicate service property response')
        else:
            values[key] = value
    values['EnvironmentFiles'] = ' '.join(environment)
    return values


def service_snapshot(*, installed):
    result = {}
    for service in SERVICES:
        raw = run(['/usr/bin/systemctl','show',service,
                   '--property=ActiveState,SubState,MainPID,NRestarts,ExecMainStartTimestampMonotonic,EnvironmentFiles,DropInPaths,UnsetEnvironment,User,Group,WorkingDirectory,NoNewPrivileges,ProtectSystem,ProtectHome,PrivateTmp,CapabilityBoundingSet'])
        values = parse_service_properties(raw)
        if values.get('ActiveState') != 'active' or values.get('SubState') != 'running' or not int(values.get('MainPID','0')):
            raise VisionError('service is not active and stable')
        validate_env_sources(values['EnvironmentFiles'], installed=installed)
        validate_unset_environment(values.get('UnsetEnvironment', ''))
        own = str(SYSTEMD / (service + '.service.d') / DROPIN_NAME)
        paths = values['DropInPaths'].split()
        if installed and (not paths or paths[-1] != own):
            raise VisionError('model dropin must be last')
        if not installed and own in paths:
            raise VisionError('unexpected model dropin loaded')
        values['process_start'] = process_start(int(values['MainPID']))
        values['authorization_flags'] = {key:target_process_value(int(values['MainPID']),key) for key in FLAGS}
        result[service] = values
    return result


def protected_metadata():
    paths = (PRODUCTION / 'backend/.env', Path('/var/lib/reva-health-evidence-runtime/enabled.env'),
             Path('/etc/reva-release/authorized-release.json'), Path('/root/.ssh/authorized_keys'))
    result = {}
    for path in paths:
        if os.path.lexists(path):
            result[str(path)] = secure_path(path)
        else:
            parent = path.parent
            while not os.path.lexists(parent):
                parent = parent.parent
            proof = secure_path(parent,directory=True)
            result[str(path)] = {'absent':True,'parent':str(parent),
                                 'parent_identity':{key:proof[key] for key in ('dev','ino','mode','uid','gid')}}
    return result


def inspect(publisher, production, operation, source, helper, bootstrap, server, gate):
    gate.verify_release(publisher, publisher)
    gate._latest(gate._get_json, production)
    helper._revision_proof(production, source, bootstrap)
    live = run(['/usr/bin/git','-c','core.hooksPath=/dev/null','-C',str(PRODUCTION),'rev-parse','HEAD'])
    validate_binding(production, live, bootstrap._read_json(STATE / production / 'completed.json'))
    bootstrap.assert_frontend_rebuild_history()
    server.assert_ota_history()
    audit = STATE / 'vision-models' / operation
    if os.path.lexists(LEASE) or os.path.lexists(audit):
        raise VisionError('existing lease or operation; no replay')
    before = {}
    # First revision installs only when no previous model operator artifacts exist.
    # An existing model state needs a separately reviewed replacement operation.
    for path in [MODEL, *(SYSTEMD / (s + '.service.d') / DROPIN_NAME for s in SERVICES)]:
        if os.path.lexists(path):
            raise VisionError('existing model state requires operator review')
        before[str(path)] = None
    if os.path.lexists(MODEL_ROOT):
        secure_path(MODEL_ROOT, directory=True)
    for service in SERVICES:
        parent = SYSTEMD / (service + '.service.d')
        secure_path(parent if parent.exists() else parent.parent, directory=True)
    return {'kind':'vision-model-selection','publisher_sha':publisher,'production_sha':production,
            'operation_id':operation,'model':'qwen3.8-flash','services':service_snapshot(installed=False),
            'protected_metadata':protected_metadata(),'before':before,
            'acceptance':'PENDING','production_apply_enabled':PRODUCTION_APPLY_ENABLED}



def process_start(pid, *, proc=Path('/proc')):
    # stat has a parenthesized command field that may contain spaces.
    raw = (proc / str(pid) / 'stat').read_text()
    fields = raw[raw.rfind(')')+2:].split()
    if len(fields) < 20 or not fields[19].isdigit():
        raise VisionError('process identity unknown')
    return fields[19]


def target_process_value(pid, name, *, proc=Path('/proc')):
    """Keep only the one nonsecret target variable, never other env values.

    NUL-delimited environment is scanned incrementally. Non-target bytes are
    discarded individually; credential values are never assembled or logged.
    """
    if not isinstance(pid, int) or pid <= 0:
        raise VisionError('invalid service PID')
    if name not in ('LLM_VISION_MODEL',*FLAGS):
        raise VisionError('target process variable rejected')
    started = process_start(pid,proc=proc)
    key = (name+'=').encode()
    matches, prefix, value = [], bytearray(), None
    count = 0
    with (proc / str(pid) / 'environ').open('rb', buffering=0) as stream:
        while True:
            char = stream.read(1)
            if not char:
                if prefix or value is not None:
                    raise VisionError('unterminated process environment')
                break
            count += 1
            if count > 1048576:
                raise VisionError('process environment exceeds bound')
            if char == b'\0':
                if value is not None:
                    matches.append(bytes(value))
                prefix, value = bytearray(), None
            elif value is not None:
                if len(value) >= 256:
                    raise VisionError('target model exceeds bound')
                value.extend(char)
            elif prefix is not None:
                prefix.extend(char)
                if not key.startswith(prefix):
                    prefix = None
                elif bytes(prefix) == key:
                    value = bytearray()
                    prefix = None
    if process_start(pid,proc=proc) != started or len(matches) > 1:
        raise VisionError('process target identity or uniqueness differs')
    if not matches:
        return None
    allowed = (b'qwen3.8-flash',b'qwen-vl-max') if name == 'LLM_VISION_MODEL' else (b'true',b'false',b'1',b'0',b'True',b'False')
    if matches[0] not in allowed:
        raise VisionError('target process value outside nonsecret allowlist')
    return matches[0].decode()


def target_process_model(pid, *, proc=Path('/proc'), expected='qwen3.8-flash'):
    if target_process_value(pid,'LLM_VISION_MODEL',proc=proc) != expected:
        raise VisionError('service target model not uniquely applied')
    return expected


def write_json(server, path, value):
    server._write_private(path, json.dumps(value,sort_keys=True,separators=(',',':')).encode())


def lease_check(helper, bootstrap, server, token, identity):
    if helper._lease_identity(str(LEASE),token,bootstrap,server) != identity:
        raise VisionError('business lease inode differs')


def release_own_lease(helper, bootstrap, server, token, identity):
    lease_check(helper,bootstrap,server,token,identity)
    if {p.name for p in LEASE.iterdir()} != {'token','label','stage','started_at'}:
        raise VisionError('lease inventory differs')
    for name in ('token','label','stage','started_at'):
        (LEASE / name).unlink()
    LEASE.rmdir()
    server._sync_business_lease_parent()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise VisionError('loopback health redirect rejected')


def health_response_healthy(raw):
    if len(raw) > 4096:
        return False
    def unique(pairs):
        value = {}
        for key,item in pairs:
            if key in value:
                raise ValueError('duplicate health field')
            value[key] = item
        return value
    try:
        value = json.loads(raw,object_pairs_hook=unique)
        return value == {'status':'healthy','services':{'api':'running','database':'connected','redis':'connected','celery':'connected'}}
    except (ValueError,TypeError):
        return False


def verify_health():
    # Public loopback health only, proxies and redirects disabled. Bounded body;
    # all dependencies healthy, no authentication or model inference.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            with opener.open('http://127.0.0.1:8000/health',timeout=2) as response:
                if response.status == 200 and health_response_healthy(response.read(4097)):
                    return
        except (OSError,ValueError):
            pass
        time.sleep(1)
    raise VisionError('bounded backend health verification failed')


def verify_stability(*, installed):
    # Three fresh observations over a bounded window; PID, starttime and restart
    # count must remain unchanged. No private request or model call occurs.
    first = service_snapshot(installed=installed)
    for _ in range(2):
        time.sleep(2)
        verify_health()
        if service_snapshot(installed=installed) != first:
            raise VisionError('service identity changed during stability window')
    return first


def verify_production_sha(expected):
    live = run(['/usr/bin/git','-c','core.hooksPath=/dev/null','-C',str(PRODUCTION),'rev-parse','HEAD'])
    if live != expected:
        raise VisionError('production revision changed')


def rollback_time_gate():
    if time.time() + ROLLBACK_TIME_BUDGET >= OLD_MODEL_RETIREMENT_UTC:
        raise VisionError('retired model rollback deadline or bounded restart window exceeded')


def configuration_readback(plan):
    if protected_metadata() != plan['protected_metadata']:
        raise VisionError('protected configuration metadata differs')
    services = service_snapshot(installed=True)
    for service, values in services.items():
        if values['MainPID'] == plan['services'][service]['MainPID']:
            raise VisionError('service PID did not change')
        target_process_model(int(values['MainPID']))
        if process_start(int(values['MainPID'])) != values['process_start']:
            raise VisionError('service process identity changed')
        if values['authorization_flags'] != plan['services'][service]['authorization_flags']:
            raise VisionError('effective authorization flags changed')
        if values['EnvironmentFiles'].removesuffix(' '+str(MODEL)+' (ignore_errors=no)') != plan['services'][service]['EnvironmentFiles']:
            raise VisionError('existing EnvironmentFile flags changed')
        for key in ('User','Group','WorkingDirectory','NoNewPrivileges','ProtectSystem','ProtectHome','PrivateTmp','CapabilityBoundingSet'):
            if values[key] != plan['services'][service][key]:
                raise VisionError('service identity or sandbox changed')
    if optional_model_file(MODEL)['content'] != model_bytes('qwen3.8-flash').decode():
        raise VisionError('model file readback differs')
    for service in SERVICES:
        path = SYSTEMD / (service + '.service.d') / DROPIN_NAME
        if optional_model_file(path)['content'] != dropin_bytes().decode():
            raise VisionError('model dropin readback differs')
    return services


def execute(plan, source, helper, bootstrap, server, gate):
    # The fresh gate, stable process snapshot and evidence digest are all
    # rechecked before durable intent and acquisition; never reclaim a lease.
    for values in plan['services'].values():
        target_process_model(int(values['MainPID']),expected='qwen-vl-max')
    current = inspect(plan['publisher_sha'],plan['production_sha'],plan['operation_id'],source,helper,bootstrap,server,gate)
    if current != plan:
        raise VisionError('preflight evidence changed')
    root = STATE / 'vision-models'
    root.mkdir(mode=0o700,exist_ok=True)
    secure_path(root,directory=True)
    audit = root / plan['operation_id']
    audit.mkdir(mode=0o700)
    sync_directory(root)
    write_json(server,audit / 'before.json',plan)
    write_json(server,audit / 'intent.json',{'state':'CONFIG_STARTED','evidence_sha256':digest(plan)})
    LEASE.mkdir(mode=0o700)
    token = secrets.token_hex(32)
    import time
    for name,value in {'token':token,'label':'vision-model-selection','stage':str(audit),'started_at':str(int(time.time()))}.items():
        server._write_private(LEASE / name,(value+'\n').encode())
    server._sync_business_lease_parent()
    identity = helper._lease_identity(str(LEASE),token,bootstrap,server)
    write_json(server,audit / 'lease.json',{'identity':identity})
    try:
        lease_check(helper,bootstrap,server,token,identity)
        if protected_metadata() != plan['protected_metadata']:
            raise VisionError('protected configuration metadata differs')
        MODEL_ROOT.mkdir(mode=0o700,exist_ok=True)
        secure_path(MODEL_ROOT,directory=True)
        for service in SERVICES:
            parent = SYSTEMD / (service+'.service.d')
            parent.mkdir(mode=0o755,exist_ok=True)
            secure_path(parent,directory=True)
        atomic_model_write(MODEL,model_bytes('qwen3.8-flash'))
        for service in SERVICES:
            lease_check(helper,bootstrap,server,token,identity)
            atomic_model_write(SYSTEMD / (service+'.service.d') / DROPIN_NAME,dropin_bytes())
        run(['/usr/bin/systemctl','daemon-reload'])
        # Validate effective merged source ordering BEFORE restarting anything.
        service_snapshot(installed=True)
        lease_check(helper,bootstrap,server,token,identity)
        run(['/usr/bin/systemctl','restart',*SERVICES],timeout=180)
        verify_health()
        services = configuration_readback(plan)
        if verify_stability(installed=True) != services:
            raise VisionError('configuration identity changed')
        verify_production_sha(plan['production_sha'])
        if protected_metadata() != plan['protected_metadata']:
            raise VisionError('protected metadata changed before completion')
        lease_check(helper,bootstrap,server,token,identity)
        # Actual service response health is still a separate independent check;
        # no authenticated application request or paid inference is manufactured.
        complete = {'state':'CONFIG_SUCCEEDED_PENDING_MODEL_ACCEPTANCE','publisher_sha':plan['publisher_sha'],
                    'production_sha':plan['production_sha'],'operation_id':plan['operation_id'],
                    'model':'qwen3.8-flash','model_acceptance':'PENDING','model_requests':0,
                    'evidence_sha256':digest(plan),'services':services}
        write_json(server,audit / 'verified.json',complete)
        lease_check(helper,bootstrap,server,token,identity)
        write_json(server,audit / 'completed.json',complete)
        release_own_lease(helper,bootstrap,server,token,identity)
        return complete
    except BaseException:
        write_json(server,audit / 'failed.json',{'state':'CONFIG_NEEDS_OPERATOR','model_acceptance':'PENDING','model_requests':0})
        raise VisionError('configuration outcome unknown; lease retained; do not retry') from None



def inspect_rollback(publisher,production,operation,source,helper,bootstrap,server,gate):
    server.assert_frontend_rebuild_history(pending_vision_operation=operation)
    server.assert_ota_history()
    gate.verify_release(publisher,publisher)
    gate._latest(gate._get_json,production)
    helper._revision_proof(production,source,bootstrap)
    live = run(['/usr/bin/git','-c','core.hooksPath=/dev/null','-C',str(PRODUCTION),'rev-parse','HEAD'])
    validate_binding(production,live,bootstrap._read_json(STATE / production / 'completed.json'))
    audit = STATE / 'vision-models' / operation
    secure_path(audit,directory=True)
    before = bootstrap._read_json(audit / 'before.json')
    if before['production_sha'] != production or before['operation_id'] != operation:
        raise VisionError('rollback baseline differs')
    if os.path.lexists(audit / 'rollback-intent.json'):
        raise VisionError('rollback previously attempted; no replay')
    if protected_metadata() != before['protected_metadata']:
        raise VisionError('protected configuration drift blocks rollback')
    files = {}
    for path in (MODEL,*(SYSTEMD / (s+'.service.d') / DROPIN_NAME for s in SERVICES)):
        files[str(path)] = optional_model_file(path)
        if files[str(path)] is not None:
            secure_path(path)
    if os.path.lexists(LEASE):
        # Only the original failed config operation lease is admissible.
        secure_path(LEASE,directory=True)
        for name in ('label','stage','token'):
            secure_path(LEASE / name)
        if (LEASE / 'label').read_bytes() != b'vision-model-selection\n' or (LEASE / 'stage').read_bytes() != (str(audit)+'\n').encode():
            raise VisionError('lease belongs to another operation')
        token = (LEASE / 'token').read_text().strip()
        identity = helper._lease_identity(str(LEASE),token,bootstrap,server)
        recorded = bootstrap._read_json(audit / 'lease.json')['identity']
        if [list(row) for row in identity] != recorded:
            raise VisionError('original lease inode differs')
        lease = {'identity':identity}
    else:
        if bootstrap._read_json(audit / 'completed.json')['state'] != 'CONFIG_SUCCEEDED_PENDING_MODEL_ACCEPTANCE':
            raise VisionError('missing lease without completed config receipt')
        lease = None
    return {'kind':'vision-model-rollback','publisher_sha':publisher,'production_sha':production,
            'operation_id':operation,'before':before,'files':files,'lease':lease}


def rollback(plan,source,helper,bootstrap,server,gate):
    rollback_time_gate()
    if inspect_rollback(plan['publisher_sha'],plan['production_sha'],plan['operation_id'],source,helper,bootstrap,server,gate) != plan:
        raise VisionError('rollback evidence changed')
    audit = STATE / 'vision-models' / plan['operation_id']
    write_json(server,audit / 'rollback-intent.json',{'state':'CONFIG_ROLLBACK_STARTED','evidence_sha256':digest(plan)})
    if plan['lease'] is None:
        LEASE.mkdir(mode=0o700)
        token = secrets.token_hex(32)
        import time
        for name,value in {'token':token,'label':'vision-model-selection','stage':str(audit),'started_at':str(int(time.time()))}.items():
            server._write_private(LEASE / name,(value+'\n').encode())
        server._sync_business_lease_parent()
        identity = helper._lease_identity(str(LEASE),token,bootstrap,server)
        write_json(server,audit / 'rollback-lease.json',{'identity':identity})
    else:
        token = (LEASE / 'token').read_text().strip()
        identity = helper._lease_identity(str(LEASE),token,bootstrap,server)
        write_json(server,audit / 'rollback-lease.json',{'identity':identity})
    try:
        lease_check(helper,bootstrap,server,token,identity)
        for path in (MODEL,*(SYSTEMD / (s+'.service.d') / DROPIN_NAME for s in SERVICES)):
            if optional_model_file(path) != plan['files'][str(path)]:
                raise VisionError('own model file changed before rollback')
            if os.path.lexists(path):
                path.unlink()
                sync_directory(path.parent)
        run(['/usr/bin/systemctl','daemon-reload'])
        for service in SERVICES:
            values = parse_service_properties(run(['/usr/bin/systemctl','show',service,'--property=EnvironmentFiles,UnsetEnvironment']))
            validate_env_sources(values['EnvironmentFiles'],installed=False)
            validate_unset_environment(values.get('UnsetEnvironment',''))
            if values['EnvironmentFiles'] != plan['before']['services'][service]['EnvironmentFiles']:
                raise VisionError('rollback source flags differ')
        lease_check(helper,bootstrap,server,token,identity)
        rollback_time_gate()
        run(['/usr/bin/systemctl','restart',*SERVICES],timeout=180)
        verify_health()
        services = verify_stability(installed=False)
        for service,values in services.items():
            target_process_model(int(values['MainPID']),expected='qwen-vl-max')
            previous = plan['before']['services'][service]
            if values['MainPID'] == previous['MainPID'] or process_start(int(values['MainPID'])) != values['process_start']:
                raise VisionError('rollback service restart identity differs')
            for key in ('User','Group','WorkingDirectory','NoNewPrivileges','ProtectSystem','ProtectHome','PrivateTmp','CapabilityBoundingSet'):
                if values[key] != previous[key]:
                    raise VisionError('rollback service identity or sandbox differs')
            if values['authorization_flags'] != previous['authorization_flags'] or values['EnvironmentFiles'] != previous['EnvironmentFiles']:
                raise VisionError('rollback effective authorization or source order differs')
        if protected_metadata() != plan['before']['protected_metadata']:
            raise VisionError('protected metadata changed during rollback')
        result = {'state':'CONFIG_ROLLED_BACK','operation_id':plan['operation_id'],
                  'production_sha':plan['production_sha'],'model_requests':0,'services':services,
                  'serving_acceptance':'NOT_VERIFIED_OLD_MODEL_RETIREMENT_APPLIES'}
        verify_production_sha(plan['production_sha'])
        lease_check(helper,bootstrap,server,token,identity)
        write_json(server,audit / 'rollback-verified.json',result)
        write_json(server,audit / 'rollback-completed.json',result)
        release_own_lease(helper,bootstrap,server,token,identity)
        return result
    except BaseException:
        write_json(server,audit / 'rollback-failed.json',{'state':'CONFIG_ROLLBACK_NEEDS_OPERATOR'})
        raise VisionError('rollback outcome unknown; lease retained') from None



def finalization_model_files(*, rolled_back):
    paths = [MODEL,*(SYSTEMD / (service+'.service.d') / DROPIN_NAME for service in SERVICES)]
    for path in paths:
        if rolled_back:
            if os.path.lexists(path):
                raise VisionError('rollback model files reappeared')
        else:
            secure_path(path)
            expected = model_bytes('qwen3.8-flash') if path == MODEL else dropin_bytes()
            value = optional_model_file(path)
            if value is None or value['content'] != expected.decode():
                raise VisionError('verified model file differs')


def inspect_finalization(publisher,production,operation,source,helper,bootstrap,server,gate,*,rolled_back):
    # This path proves an already durable verified effect; it NEVER replays
    # daemon-reload, restart, file installation, model requests or rollback.
    gate.verify_release(publisher,publisher)
    gate._latest(gate._get_json,production)
    helper._revision_proof(production,source,bootstrap)
    server.assert_frontend_rebuild_history(pending_vision_operation=operation)
    server.assert_ota_history()
    verify_production_sha(production)
    audit = STATE / 'vision-models' / operation
    secure_path(audit,directory=True)
    before = bootstrap._read_json(audit / 'before.json')
    if before['production_sha'] != production or before['operation_id'] != operation:
        raise VisionError('finalization baseline differs')
    verified_path = audit / ('rollback-verified.json' if rolled_back else 'verified.json')
    secure_path(verified_path)
    verified = bootstrap._read_json(verified_path)
    expected = 'CONFIG_ROLLED_BACK' if rolled_back else 'CONFIG_SUCCEEDED_PENDING_MODEL_ACCEPTANCE'
    if verified['state'] != expected or verified['operation_id'] != operation or verified['model_requests'] != 0:
        raise VisionError('durable configuration proof differs')
    if protected_metadata() != before['protected_metadata']:
        raise VisionError('protected metadata drift blocks finalization')
    finalization_model_files(rolled_back=rolled_back)
    verify_health()
    services = verify_stability(installed=not rolled_back)
    if services != verified['services']:
        raise VisionError('verified service identity changed; no replay')
    for values in services.values():
        target_process_model(int(values['MainPID']),expected='qwen-vl-max' if rolled_back else 'qwen3.8-flash')
    secure_path(LEASE,directory=True)
    for name in ('label','stage','token'):
        secure_path(LEASE / name)
    if (LEASE / 'label').read_bytes() != b'vision-model-selection\n' or (LEASE / 'stage').read_bytes() != (str(audit)+'\n').encode():
        raise VisionError('finalization lease belongs to another operation')
    token = (LEASE / 'token').read_text().strip()
    identity = helper._lease_identity(str(LEASE),token,bootstrap,server)
    recorded = bootstrap._read_json(audit / ('rollback-lease.json' if rolled_back else 'lease.json'))['identity']
    if [list(row) for row in identity] != recorded:
        raise VisionError('finalization lease inode differs')
    terminal = audit / ('rollback-completed.json' if rolled_back else 'completed.json')
    if os.path.lexists(terminal) and bootstrap._read_json(terminal) != verified:
        raise VisionError('existing terminal evidence differs')
    return {'kind':'vision-config-finalization','publisher_sha':publisher,'production_sha':production,
            'operation_id':operation,'rolled_back':rolled_back,'verified':verified,'lease_identity':identity}


def finalize(plan,source,helper,bootstrap,server,gate):
    if inspect_finalization(plan['publisher_sha'],plan['production_sha'],plan['operation_id'],source,helper,bootstrap,server,gate,rolled_back=plan['rolled_back']) != plan:
        raise VisionError('finalization evidence changed')
    audit = STATE / 'vision-models' / plan['operation_id']
    terminal = audit / ('rollback-completed.json' if plan['rolled_back'] else 'completed.json')
    if not os.path.lexists(terminal):
        write_json(server,terminal,plan['verified'])
    token = (LEASE / 'token').read_text().strip()
    release_own_lease(helper,bootstrap,server,token,plan['lease_identity'])
    write_json(server,audit / ('rollback-finalized.json' if plan['rolled_back'] else 'finalized.json'),
               {'state':'CONFIG_LEASE_FINALIZED','evidence_sha256':digest(plan),'model_requests':0})
    return {'state':'CONFIG_LEASE_FINALIZED','operation_id':plan['operation_id'],'model_requests':0}



def history_main(argv):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--publisher-sha',required=True)
    args = parser.parse_args(argv)
    try:
        if (os.geteuid() != 0 or sys.executable != '/usr/bin/python3.12'
                or not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode):
            raise VisionError('isolated system Python root operator required')
        checked_hex(args.publisher_sha,40)
        source,helper,bootstrap,server,gate = load_reviewed(args.publisher_sha)
        gate.verify_release(args.publisher_sha,args.publisher_sha)
        server.assert_vision_model_history()
        print(json.dumps({'state':'VISION_HISTORY_CLEAR','publisher_sha':args.publisher_sha,'model_requests':0}))
        return 0
    except Exception:
        print(json.dumps({'state':'VISION_HISTORY_BLOCKED','model_requests':0}))
        return 1


def main():
    if sys.argv[1:2] == ['--check-history']:
        return history_main(sys.argv[2:])
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--publisher-sha', required=True)
    parser.add_argument('--production-sha', required=True)
    parser.add_argument('--operation-id', required=True)
    parser.add_argument('--evidence-sha256')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--rollback',action='store_true')
    mode.add_argument('--finalize-config',action='store_true')
    mode.add_argument('--finalize-rollback',action='store_true')
    args = parser.parse_args()
    try:
        if (os.geteuid() != 0 or sys.executable != '/usr/bin/python3.12'
                or not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode):
            raise VisionError('isolated system Python root operator required')
        checked_hex(args.publisher_sha,40)
        checked_hex(args.production_sha,40)
        checked_hex(args.operation_id,32)
        if args.evidence_sha256 is not None:
            checked_hex(args.evidence_sha256,64)
        os.umask(0o077)
        source, helper, bootstrap, server, gate = load_reviewed(args.publisher_sha)
        lock = STATE / 'launcher.lock'
        secure_path(lock)
        with lock.open('r+b') as stream:
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX | fcntl.LOCK_NB)
            helper._assert_lock(server,lock,stream.fileno())
            if args.finalize_config or args.finalize_rollback:
                plan = inspect_finalization(args.publisher_sha,args.production_sha,args.operation_id,source,helper,bootstrap,server,gate,rolled_back=args.finalize_rollback)
            else:
                plan = (inspect_rollback if args.rollback else inspect)(args.publisher_sha,args.production_sha,args.operation_id,source,helper,bootstrap,server,gate)
            expected = digest(plan)
            if args.evidence_sha256 is not None:
                if args.evidence_sha256 != expected:
                    raise VisionError('preflight evidence changed')
                action = finalize if (args.finalize_config or args.finalize_rollback) else (rollback if args.rollback else execute)
                print(json.dumps(action(plan,source,helper,bootstrap,server,gate)))
                return 0
            print(json.dumps({'state':'VISION_ROLLBACK_PREFLIGHT' if args.rollback else 'VISION_PREFLIGHT_ONLY','evidence_sha256':expected,
                              'production_sha':args.production_sha,'model':'qwen3.8-flash',
                              'production_apply_enabled':PRODUCTION_APPLY_ENABLED,'model_requests':0}))
        return 0
    except Exception:
        print(json.dumps({'state':'VISION_BLOCKED','reason':'model-only preflight or admission failed',
                          'production_changed':'UNKNOWN_IF_APPLY_REQUESTED','model_requests':0}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
