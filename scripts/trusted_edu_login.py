"""Bounded first-time Health/Edu owner link; no password sharing or backups.

Only the Health environment is replaced, atomically. This is a journaled,
resumable sequence; the separate Edu host is never contacted or configured. Unknown outcomes retain
both the original intent and the shared release lease. Browser acceptance is
separate from CONFIGURATION_SUCCEEDED.
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
import shlex
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

STATE = Path('/var/lib/reva-release')
ROOT = Path('/var/lib/reva-edu-login')
LEASE = Path('/run/lock/health-app-release')
HEALTH = 'https://health.executor.life'
EDU = 'https://edu.executor.life'
FILES = {'health': Path('/opt/health-app/backend/.env')}
SERVICES = {'health': 'health-backend'}
PREFIXES = ('EDU_SSO_',)
KEYS = frozenset({'EDU_SSO_ENABLED', 'EDU_SSO_SECRET', 'EDU_SSO_OWNER_ID', 'EDU_SSO_ORIGIN', 'EDU_SSO_ISSUER'})
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/root', 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1',
       'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_SYSTEM': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1'}


class ActivationError(Exception):
    """Errors contain no environment, identity response or subprocess output."""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def secure(path, directory=False):
    for item in [*reversed(path.parents), path]:
        info = item.lstat()
        if item == Path('/run/lock') and stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o1777:
            continue
        is_dir = item != path or directory
        if (info.st_uid != 0 or info.st_mode & 0o022 or
                not (stat.S_ISDIR(info.st_mode) if is_dir else stat.S_ISREG(info.st_mode)) or
                (not is_dir and info.st_nlink != 1)):
            raise ActivationError('unsafe configuration or operator path')
    return info


def identity(info):
    return tuple(getattr(info, 'st_' + key) for key in ('dev', 'ino', 'mode', 'nlink', 'uid', 'gid', 'size', 'mtime_ns', 'ctime_ns'))


def read(path):
    before = secure(path)
    if before.st_size > 1024 * 1024:
        raise ActivationError('configuration exceeds size bound')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
        if identity(os.fstat(stream.fileno())) != identity(before) or identity(path.lstat()) != identity(before):
            raise ActivationError('configuration changed while reading')
    return raw


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic(path, raw, expected=None):
    secure(path.parent, directory=True)
    before = secure(path) if os.path.lexists(path) else None
    if expected is not None and (before is None or sha(read(path)) != expected):
        raise ActivationError('configuration changed before replacement')
    temporary = path.with_name('.' + path.name + '.' + secrets.token_hex(16))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            if before:
                os.fchown(stream.fileno(), before.st_uid, before.st_gid)
                os.fchmod(stream.fileno(), stat.S_IMODE(before.st_mode))
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if before and (identity(path.lstat()) != identity(before) or (expected is not None and sha(read(path)) != expected)):
            raise ActivationError('configuration changed at replacement boundary')
        os.replace(temporary, path)
        sync(path.parent)
    finally:
        if os.path.lexists(temporary):
            temporary.unlink()


def selected(raw):
    result = {}
    for line in raw.decode('utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if any(prefix in line.split('=', 1)[0].upper() for prefix in PREFIXES):
            key, sep, value = line.partition('=')
            if (not sep or key in result or key not in KEYS
                    or not re.fullmatch(r'[A-Za-z0-9_:/.-]*', value)):
                raise ActivationError('ambiguous authentication configuration')
            result[key] = value
    return result


def patch_env(raw, values):
    present = selected(raw)
    if any(key not in KEYS or not re.fullmatch(r'[A-Za-z0-9_:/.-]+', value)
           for key, value in values.items()):
        raise ActivationError('unsupported authentication setting')
    out = []
    for line in raw.splitlines(keepends=True):
        key = line.split(b'=', 1)[0].decode('utf-8')
        out.append((key + '=' + values[key] + '\n').encode() if key in values else line)
    result = b''.join(out)
    if result and not result.endswith(b'\n'):
        result += b'\n'
    result += ''.join(key + '=' + value + '\n' for key, value in values.items() if key not in present).encode()
    return result


def check_owner(value, owner):
    if (type(value.get('id')) is not int or value['id'] != owner or value.get('is_active') is not True
            or value.get('is_approved') is not True or value.get('is_managed') is not False
            or value.get('is_proxy') or value.get('proxy_user_id')):
        raise ActivationError('authenticated identity is not the approved owner')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ActivationError('unexpected HTTP redirect')


def request(url, *, headers=None, data=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(urllib.request.Request(url, headers=headers or {}, data=data), timeout=15) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ActivationError('HTTP response exceeds bound')
            return response.status, response.headers, raw
    except urllib.error.HTTPError as error:
        return error.code, error.headers, b''


JWT_PROOF_CODE = """import logging,sys,time
logging.disable(logging.CRITICAL)
sys.path.insert(0, '/opt/health-app/backend')
try:
    from app.services.auth import auth_service
    token = sys.stdin.buffer.read(4097)
    if len(token) > 4096:
        raise ValueError('bounded credential required')
    claims = auth_service.decode_token(token.decode('ascii'))
    if (not isinstance(claims, dict) or claims.get('sub') != sys.argv[1]
            or 'acting_as' in claims or 'original_user' in claims
            or type(claims.get('exp')) is not int or claims['exp'] <= int(time.time())):
        raise ValueError('personal current session required')
except Exception:
    sys.exit(1)
"""


def credential_format(token):
    return (isinstance(token, str) and 1 <= len(token) <= 4096
            and re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)?', token) is not None)


def personal_jwt_proof(token, owner):
    try:
        subprocess.run(['/usr/sbin/runuser', '--user', 'health-app', '--', '/usr/bin/env', '-i',
                        'PATH=/usr/bin:/bin', '/opt/health-app/backend/venv/bin/python', '-I', '-B',
                        '-c', JWT_PROOF_CODE, str(owner)],
                       input=token.encode('ascii'), env=ENV, cwd='/opt/health-app/backend',
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120, check=True)
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise ActivationError('personal owner session verification failed') from None


def owner_proof(token, owner):
    if not credential_format(token):
        raise ActivationError('bounded personal owner credential required')
    if '.' in token:
        personal_jwt_proof(token, owner)
    status, _, raw = request(HEALTH + '/api/v1/auth/me', headers={'Authorization': 'Bearer ' + token})
    if status != 200:
        raise ActivationError('owner identity verification failed')
    value = json.loads(raw)
    if (type(value.get('id')) is not int or value['id'] != owner or value.get('is_active') is not True
            or value.get('is_approved') is not True):
        raise ActivationError('authenticated owner differs')


def owner_database(owner):
    # Fixed read-only columns; no password, health data, token or family roster.
    code = '''import json,sys
sys.path.insert(0, '/opt/health-app/backend')
from sqlalchemy import text
from app.database import SessionLocal
with SessionLocal() as db:
    db.execute(text('SET TRANSACTION READ ONLY'))
    row = db.execute(text('SELECT id,is_active,is_approved,is_managed FROM users WHERE id=:owner'), {'owner': int(sys.argv[1])}).mappings().one()
    print(json.dumps(dict(row)))
'''
    value = run('/usr/sbin/runuser', '--user', 'health-app', '--', '/usr/bin/env', '-i', 'PATH=/usr/bin:/bin',
                '/opt/health-app/backend/venv/bin/python', '-I', '-B', '-c', code, str(owner), cwd='/opt/health-app/backend')
    check_owner(json.loads(value), owner)


def run(*args, cwd=None):
    try:
        return subprocess.run(args, cwd=cwd, env=ENV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=120, check=True, text=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        raise ActivationError('fixed service operation failed') from None


def service(which, *, allow_stopped=False):
    props = {}
    for line in run('/usr/bin/systemctl', 'show', SERVICES[which],
                    '--property=User,ActiveState,MainPID,EnvironmentFiles,Environment,PassEnvironment,UnsetEnvironment').splitlines():
        key, _, value = line.partition('=')
        props[key] = props.get(key, '') + (' ' if key in props else '') + value
    expected = '/opt/health-app/backend/.env (ignore_errors=no) /var/lib/reva-health-evidence-runtime/enabled.env (ignore_errors=yes) /var/lib/reva-vision-model/model.env (ignore_errors=no)'
    if (props.get('EnvironmentFiles') != expected or props.get('User') != 'health-app'
            or props.get('PassEnvironment') or props.get('UnsetEnvironment')
            or (not allow_stopped and props.get('ActiveState') != 'active')):
        raise ActivationError('service configuration source or identity differs')
    if any(item.upper().startswith(PREFIXES) for item in shlex.split(props.get('Environment', ''))):
        raise ActivationError('unit overrides authentication settings')
    if which == 'health':
        for path in (Path('/var/lib/reva-health-evidence-runtime/enabled.env'), Path('/var/lib/reva-vision-model/model.env')):
            if path == Path('/var/lib/reva-health-evidence-runtime/enabled.env') and not os.path.lexists(path):
                secure(path.parent, directory=True)
                continue
            if selected(read(path)):
                raise ActivationError('later environment source overrides authentication')
    pid = int(props['MainPID'])
    if allow_stopped and pid == 0 and props.get('ActiveState') in ('inactive', 'failed'):
        return {}
    if pid <= 1:
        raise ActivationError('running service required')
    entries = Path(f'/proc/{pid}/environ').read_bytes().split(b'\0')
    return {key.decode(): value.decode() for item in entries if b'=' in item
            for key, value in [item.split(b'=', 1)] if key.decode().upper().startswith(PREFIXES)}


def wait_ready(which):
    endpoint = 'http://127.0.0.1:8000/health'
    for _ in range(20):
        try:
            status, _, raw = request(endpoint)
            value = json.loads(raw)
            ready = status == 200 and value.get('status') == 'healthy'
        except (OSError, ValueError):
            ready = False
        if ready:
            return
        time.sleep(1)
    raise ActivationError('service readiness timed out')


def exact_form_policy(policies):
    if len(policies) != 1:
        return False
    directives = [part.split() for part in policies[0].split(';') if part.strip()]
    return [item[1:] for item in directives if item[0].lower() == 'form-action'] == [["'self'", EDU]]


def frontend_proof():
    status, headers, raw = request(HEALTH + '/connect/edu')
    policies = headers.get_all('Content-Security-Policy', [])
    if (status != 200 or not exact_form_policy(policies)
            or headers.get('Referrer-Policy') != 'strict-origin' or 'no-store' not in headers.get('Cache-Control', '')
            or b'name="referrer" content="strict-origin"' not in raw):
        raise ActivationError('served login page policy differs')


def settings(owner, secret):
    if type(owner) is not int or owner <= 0 or not re.fullmatch('[a-f0-9]{64}', secret):
        raise ActivationError('exact owner and bounded shared secret required')
    return {'health': {'EDU_SSO_ENABLED': 'true', 'EDU_SSO_SECRET': secret,
                      'EDU_SSO_OWNER_ID': str(owner), 'EDU_SSO_ORIGIN': EDU, 'EDU_SSO_ISSUER': HEALTH}}


def endpoint_proof():
    for suffix in ('', '/native'):
        status, _, _ = request(HEALTH + '/api/v1/auth/sso/edu' + suffix,
                              data=b'{}', headers={'Content-Type': 'application/json'})
        if status not in (401, 403):
            raise ActivationError('Edu identity endpoint missing or accepts anonymous access')


def installed_code(source, args):
    run('/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
        '-C', str(source), 'diff', '--exit-code', args.production_sha, args.publisher_sha, '--',
        'backend/app/api/auth.py', 'backend/app/config.py', 'backend/app/schemas/auth.py',
        'backend/app/services/edu_sso.py')


def parse_input(raw):
    if len(raw) > 8192:
        raise ActivationError('operator input exceeds bound')
    value = json.loads(raw)
    if (not isinstance(value, dict) or set(value) != {'owner_token', 'shared_secret'}
            or not isinstance(value['owner_token'], str)
            or not credential_format(value['owner_token'])
            or not isinstance(value['shared_secret'], str)
            or not re.fullmatch('[a-f0-9]{64}', value['shared_secret'])):
        raise ActivationError('bounded owner proof and shared secret stdin required')
    return value['owner_token'], value['shared_secret']


def advance(journal, actions, save):
    names = [name for name, _ in actions]
    done = journal['done']
    pending = journal.get('pending')
    if (not isinstance(done, list) or done != names[:len(done)] or len(done) > len(names)
            or pending not in (None, names[len(done)] if len(done) < len(names) else None)):
        raise ActivationError('unknown activation journal phase')
    for name, action in actions[len(done):]:
        journal['pending'] = name
        save(journal)
        action()
        journal['done'].append(name)
        journal['pending'] = None
        save(journal)


def load(publisher):
    source = STATE / 'bootstrap' / publisher / 'source'
    if Path(__file__).absolute() != source / 'scripts/trusted_edu_login.py':
        raise ActivationError('canonical operator required')
    secure(Path(__file__))
    def module(filename, name):
        path = source / 'scripts' / filename
        secure(path)
        spec = importlib.util.spec_from_file_location(name, path)
        result = importlib.util.module_from_spec(spec)
        sys.modules[name] = result
        spec.loader.exec_module(result)
        return result
    helper = module('trusted_review_reset.py', 'edu_reviewed')
    checked, bootstrap, server = helper.load_reviewed(publisher)
    if checked != source:
        raise ActivationError('reviewed source differs')
    gate = module('trusted_release_gate.py', 'edu_gate')
    return source, helper, bootstrap, server, gate


def execute(args, token, shared_secret):
    source, helper, bootstrap, server, gate = load(args.publisher_sha)
    gate.verify_release(args.publisher_sha, args.publisher_sha)
    helper._revision_proof(args.production_sha, source, bootstrap)
    if bootstrap._read_json(STATE / args.production_sha / 'completed.json') != {'sha': args.production_sha, 'state': 'SUCCEEDED'}:
        raise ActivationError('backend success receipt required')
    policy = server.validate_policy(bootstrap._read_json(bootstrap.CONFIG / 'authorized-release.json'), now=time.time())
    expected = sha((source / 'scripts/trusted_release_server.py').read_bytes())
    if policy['sha'] != args.publisher_sha or policy['executor_sha256'] != expected or sha(read(bootstrap.INSTALLED)) != expected:
        raise ActivationError('installed authorization differs')
    helper._validate_venv(server)
    owner_database(args.owner_id)
    if not args.resume:
        owner_proof(token, args.owner_id)
        endpoint_proof()
    frontend_proof()
    installed_code(source, args)
    lock = STATE / 'launcher.lock'
    secure(lock)
    with lock.open('r+b') as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        helper._revision_proof(args.production_sha, source, bootstrap)
        gate.verify_release(args.publisher_sha, args.publisher_sha)
        current_policy = server.validate_policy(bootstrap._read_json(bootstrap.CONFIG / 'authorized-release.json'), now=time.time())
        if current_policy != policy or sha(read(bootstrap.INSTALLED)) != expected:
            raise ActivationError('installed authorization changed before activation')
        server.assert_frontend_rebuild_history()
        server.assert_ota_history()
        binding = dict(publisher_sha=args.publisher_sha, production_sha=args.production_sha,
                       owner_id=args.owner_id, secret_sha256=sha(shared_secret.encode()), policy='no-backup-v1')
        settings(args.owner_id, shared_secret)
        if not ROOT.exists():
            if args.resume or LEASE.exists():
                raise ActivationError('unexpected existing operation')
            before = {}
            for which, path in FILES.items():
                raw = read(path)
                if selected(raw) or service(which):
                    raise ActivationError('first activation requires unconfigured authentication')
                before[which] = sha(raw)
            if not args.apply:
                return dict(state='READY', **binding)
            ROOT.mkdir(mode=0o700)
            sync(ROOT.parent)
            journal = dict(binding, before=before, done=[], pending=None, state='ACTIVATING')
            atomic(ROOT / 'journal.json', json.dumps(journal).encode())
            LEASE.mkdir(mode=0o700)
            for key, value in {'token': secrets.token_hex(32), 'label': 'edu-login', 'stage': str(ROOT), 'started_at': str(int(time.time()))}.items():
                atomic(LEASE / key, (value + '\n').encode())
            sync(LEASE.parent)
        else:
            secure(ROOT, directory=True)
            journal = json.loads(read(ROOT / 'journal.json'))
            if any(journal.get(key) != value for key, value in binding.items()):
                raise ActivationError('original activation binding differs')
            if journal.get('state') not in ('ACTIVATING', 'NEEDS_OPERATOR', 'CONFIGURATION_SUCCEEDED'):
                raise ActivationError('unknown activation state')
            if journal['state'] == 'CONFIGURATION_SUCCEEDED' and not LEASE.exists():
                raise ActivationError('activation already completed; use fresh readback for acceptance')
            if not args.resume or not args.apply:
                raise ActivationError('explicit resume of original activation required')
        secure(LEASE, directory=True)
        if read(LEASE / 'label') != b'edu-login\n' or read(LEASE / 'stage') != (str(ROOT) + '\n').encode():
            raise ActivationError('activation lease differs')
        lease_identity, lease_token = identity(LEASE.lstat()), read(LEASE / 'token')
        def check_lease():
            if identity(LEASE.lstat()) != lease_identity or read(LEASE / 'token') != lease_token:
                raise ActivationError('activation lease changed')
        target = settings(args.owner_id, shared_secret)
        def save(value):
            check_lease()
            atomic(ROOT / 'journal.json', json.dumps(value, sort_keys=True).encode())
        def write_env(which):
            current = read(FILES[which])
            present = selected(current)
            if present == target[which]:
                if sha(current) != journal['after'][which]:
                    raise ActivationError('unrelated configuration changed')
                return
            if present or sha(current) != journal['before'][which]:
                raise ActivationError('configuration differs from original intent')
            replacement = patch_env(current, target[which])
            journal.setdefault('after', {})[which] = sha(replacement)
            save(journal)
            atomic(FILES[which], replacement, journal['before'][which])
        def restart(which):
            if selected(read(FILES[which])) != target[which]:
                raise ActivationError('configuration missing before restart')
            if service(which, allow_stopped=True) != target[which]:
                run('/usr/bin/systemctl', 'restart', SERVICES[which])
            wait_ready(which)
            if service(which) != target[which]:
                raise ActivationError('effective configuration differs')
        def verify(which):
            if sha(read(FILES[which])) != journal['after'][which]:
                raise ActivationError('configuration changed after installation')
            if service(which) != target[which]:
                raise ActivationError('effective authentication differs')
            owner_proof(token, args.owner_id)
            endpoint_proof()
        actions = [(name + '-' + which, action) for which in ('health',) for name, action in
                   [('write', lambda w=which: write_env(w)), ('restart', lambda w=which: restart(w)), ('verify', lambda w=which: verify(w))]]
        try:
            advance(journal, actions, save)
            for which in FILES:
                verify(which)
            helper._revision_proof(args.production_sha, source, bootstrap)
            frontend_proof()
            journal['state'] = 'CONFIGURATION_SUCCEEDED'
            save(journal)
            check_lease()
            if {item.name for item in LEASE.iterdir()} != {'token', 'label', 'stage', 'started_at'}:
                raise ActivationError('lease inventory changed')
            for item in LEASE.iterdir():
                item.unlink()
            LEASE.rmdir()
            sync(LEASE.parent)
            return dict(state='CONFIGURATION_SUCCEEDED', edu_activation='separate', browser_acceptance='required', native_acceptance='required', **binding)
        except BaseException:
            journal['state'] = 'NEEDS_OPERATOR'
            save(journal)
            raise


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    for name in ('publisher-sha', 'production-sha'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--owner-id', type=int, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    try:
        if (not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode or os.geteuid() != 0
                or sys.executable != '/usr/bin/python3.12' or 'SSH_ORIGINAL_COMMAND' in os.environ
                or args.owner_id <= 0 or any(not re.fullmatch('[a-f0-9]{40}', value) for value in (args.publisher_sha, args.production_sha))):
            raise ActivationError('isolated root and exact bindings required')
        token, shared_secret = parse_input(sys.stdin.buffer.read(8193))
        os.umask(0o077)
        os.environ.clear()
        os.environ.update(ENV)
        print(json.dumps(execute(args, token, shared_secret)))
        return 0
    except Exception:
        print('Edu activation rejected; inspect protected operation state', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
