"""One-way explicit Edu viewer allowlist activation; no backups or Health sharing.

Run only from the installed reviewed canonical source, after that exact backend
revision has a SUCCEEDED receipt. This is not a general environment editor.
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
import sys
import time

STATE = Path('/var/lib/reva-release')
ROOT = Path('/var/lib/reva-edu-viewer')
LEASE = Path('/run/lock/health-app-release')
ENV_FILE = Path('/opt/health-app/backend/.env')
SERVICES = ('health-backend', 'celery-worker', 'celery-beat')
PHASES = ['write', *SERVICES, 'verify']
KEY = 'EDU_SSO_VIEWER_IDS'
OLD = {}
NEW = {}

ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/root', 'LC_ALL': 'C',
       'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
       'GIT_CONFIG_SYSTEM': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1'}


class ActivationError(Exception):
    """Fixed messages must not contain configuration or subprocess output."""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def selected(raw):
    values = {}
    for line in raw.decode('utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        lhs = line.split('=', 1)[0]
        if not any(key in lhs.upper() for key in (KEY,)):
            continue
        key, sep, value = line.partition('=')
        if not sep or key != KEY or key in values or not re.fullmatch(r'[1-9][0-9]*', value):
            raise ActivationError('ambiguous viewer configuration')
        values[key] = value
    return values


def validate_policy(value):
    if value not in (OLD, NEW):
        raise ActivationError('partial or unknown viewer policy')


def patch_env(raw):
    current = selected(raw)
    validate_policy(current)
    if current == NEW:
        return raw
    if raw and not raw.endswith(b'\n'):
        raise ActivationError('environment must end with newline')
    return raw + f'{KEY}={NEW[KEY]}\n'.encode()


def authentication_settings(raw, *, complete=True):
    allowed = {KEY, 'EDU_SSO_ENABLED', 'EDU_SSO_OWNER_ID', 'EDU_SSO_SECRET',
               'EDU_SSO_ORIGIN', 'EDU_SSO_ISSUER'}
    result = {}
    for line in raw.decode().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        lhs = line.split('=', 1)[0]
        if 'EDU_SSO_' not in lhs.upper():
            continue
        key, sep, value = line.partition('=')
        if not sep or key not in allowed or key in result or not re.fullmatch(r'[A-Za-z0-9_:/.-]+', value):
            raise ActivationError('ambiguous effective Edu authentication')
        result[key] = value
    if complete and (set(result) - {KEY} != allowed - {KEY}
            or result['EDU_SSO_ENABLED'] != 'true'
            or not re.fullmatch(r'[1-9][0-9]*', result['EDU_SSO_OWNER_ID'])
            or len(result['EDU_SSO_SECRET']) < 32
            or result['EDU_SSO_ORIGIN'] != 'https://edu.executor.life'
            or result['EDU_SSO_ISSUER'] != 'https://health.executor.life'):
        raise ActivationError('existing Edu authentication is not enabled as expected')
    return result


def configure(owner, viewer):
    if type(owner) is not int or type(viewer) is not int or min(owner, viewer) <= 0 or owner == viewer:
        raise ActivationError('distinct positive identities required')
    NEW.clear()
    NEW[KEY] = str(viewer)


def check_owner_binding(raw, owner):
    lines = [line for line in raw.decode().splitlines()
             if line.strip() and not line.lstrip().startswith('#')
             and 'EDU_SSO_OWNER_ID' in line.split('=', 1)[0].upper()]
    if lines != [f'EDU_SSO_OWNER_ID={owner}']:
        raise ActivationError('existing Edu owner differs')


def advance(journal, actions, save):
    names = [name for name, _ in actions]
    done = journal.get('done')
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
    if Path(__file__).absolute() != source / 'scripts/edu_viewer_activation.py':
        raise ActivationError('canonical operator required')
    # This reviewed helper supplies the existing bounded metadata, CAS, fsync,
    # subprocess, health and source verification primitives; no Edu action runs.
    path = source / 'scripts/trusted_edu_login.py'
    for item in [*reversed(path.parents), path]:
        info = item.lstat()
        if item.is_symlink() or info.st_uid != 0 or info.st_mode & 0o022:
            raise ActivationError('unsafe canonical helper')
    spec = importlib.util.spec_from_file_location('viewer_io', path)
    io = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(io)
    io.secure(Path(__file__))
    def module(filename, name):
        entry = source / 'scripts' / filename
        io.secure(entry)
        spec = importlib.util.spec_from_file_location(name, entry)
        value = importlib.util.module_from_spec(spec)
        sys.modules[name] = value
        spec.loader.exec_module(value)
        return value
    helper = module('trusted_review_reset.py', 'viewer_reviewed')
    checked, bootstrap, server = helper.load_reviewed(publisher)
    if checked != source:
        raise ActivationError('reviewed source differs')
    gate = module('trusted_release_gate.py', 'viewer_gate')
    return source, io, helper, bootstrap, server, gate


def service(io, name, *, allow_stopped=False):
    properties = ('User', 'ActiveState', 'MainPID', 'EnvironmentFiles',
                  'Environment', 'PassEnvironment', 'UnsetEnvironment')
    props = {}
    output = io.run('/usr/bin/systemctl', 'show', name, '--property=' + ','.join(properties))
    for line in output.splitlines():
        key, sep, value = line.partition('=')
        if not sep or key not in properties or (key in props and key != 'EnvironmentFiles'):
            raise ActivationError('ambiguous service property readback')
        # systemctl emits one EnvironmentFiles row per configured source.
        # Preserve order; the exact comparison below rejects duplicates/extras.
        props[key] = props[key] + ' ' + value if key in props else value
    if set(props) != set(properties):
        raise ActivationError('incomplete service property readback')
    expected = '/opt/health-app/backend/.env (ignore_errors=no) /var/lib/reva-health-evidence-runtime/enabled.env (ignore_errors=yes) /var/lib/reva-vision-model/model.env (ignore_errors=no)'
    if (props.get('User') != 'health-app' or props.get('EnvironmentFiles') != expected
            or props.get('PassEnvironment') or props.get('UnsetEnvironment')):
        raise ActivationError('service configuration source or identity differs')
    for assignment in shlex.split(props.get('Environment', '')):
        if 'EDU_SSO_' in assignment.split('=', 1)[0].upper():
            raise ActivationError('unit overrides viewer policy')
    for path in (Path('/var/lib/reva-health-evidence-runtime/enabled.env'), Path('/var/lib/reva-vision-model/model.env')):
        if path.name == 'enabled.env' and not os.path.lexists(path):
            io.secure(path.parent, directory=True)
        elif authentication_settings(io.read(path), complete=False):
            raise ActivationError('later environment source overrides viewer policy')
    pid = int(props.get('MainPID', '0'))
    if allow_stopped and pid == 0 and props.get('ActiveState') in ('inactive', 'failed'):
        return {}
    if pid <= 1 or props.get('ActiveState') != 'active':
        raise ActivationError('active service required')
    raw = Path(f'/proc/{pid}/environ').read_bytes()
    entries = [entry.split(b'=', 1) for entry in raw.split(b'\0') if b'=' in entry]
    result = {}
    for key, value in entries:
        if key.decode().upper() == KEY:
            if key.decode() != KEY or key.decode() in result:
                raise ActivationError('ambiguous running viewer policy')
            result[key.decode()] = value.decode()
    validate_policy(result)
    effective = authentication_settings(raw.replace(b'\0', b'\n'))
    expected = authentication_settings(io.read(ENV_FILE))
    previous = {key: value for key, value in expected.items() if key != KEY}
    if effective != expected and not (allow_stopped and expected.get(KEY) == NEW[KEY] and effective == previous):
        raise ActivationError('effective Edu authentication differs from base configuration')
    # Reacquire PID to reject a process replacement during the readback.
    if io.run('/usr/bin/systemctl', 'show', name, '--property=MainPID', '--value') != str(pid):
        raise ActivationError('service changed during readback')
    return result


def validate_journal(journal, binding):
    keys = {'publisher_sha', 'production_sha', 'policy', 'before', 'after', 'done', 'pending', 'state', 'owner_id', 'viewer_id'}
    if (not isinstance(journal, dict) or set(journal) != keys
            or any(journal.get(key) != value for key, value in binding.items())
            or any(re.fullmatch('[a-f0-9]{64}', str(journal.get(key))) is None for key in ('before', 'after'))
            or journal['before'] == journal['after']
            or journal['state'] not in ('ACTIVATING', 'NEEDS_OPERATOR', 'CONFIGURATION_SUCCEEDED')):
        raise ActivationError('unknown activation binding or journal')
    done, pending = journal['done'], journal['pending']
    if (not isinstance(done, list) or done != PHASES[:len(done)] or len(done) > len(PHASES)
            or pending not in (None, PHASES[len(done)] if len(done) < len(PHASES) else None)
            or (journal['state'] == 'CONFIGURATION_SUCCEEDED' and (done != PHASES or pending is not None))):
        raise ActivationError('unknown activation journal phase')


def execute(args):
    configure(args.owner_id, args.viewer_id)
    source, io, helper, bootstrap, server, gate = load(args.publisher_sha)
    binding = dict(publisher_sha=args.publisher_sha, production_sha=args.publisher_sha,
                   policy='edu-viewer-v1', owner_id=args.owner_id, viewer_id=args.viewer_id)
    def preflight():
        gate.verify_release(args.publisher_sha, args.publisher_sha)
        helper._revision_proof(args.publisher_sha, source, bootstrap)
        if bootstrap._read_json(STATE / args.publisher_sha / 'completed.json') != {'sha': args.publisher_sha, 'state': 'SUCCEEDED'}:
            raise ActivationError('exact installed backend success receipt required')
        policy = server.validate_policy(bootstrap._read_json(bootstrap.CONFIG / 'authorized-release.json'), now=time.time())
        expected = digest((source / 'scripts/trusted_release_server.py').read_bytes())
        if (policy['sha'] != args.publisher_sha or policy['executor_sha256'] != expected
                or digest(io.read(bootstrap.INSTALLED)) != expected):
            raise ActivationError('installed authorization differs')
        helper._validate_venv(server)
        io.owner_database(args.owner_id)
        io.owner_database(args.viewer_id)
        server.assert_frontend_rebuild_history()
        server.assert_ota_history()
    preflight()
    lock = STATE / 'launcher.lock'
    io.secure(lock)
    with lock.open('r+b') as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        preflight()
        raw = io.read(ENV_FILE)
        # Retain the existing root:health-app 0640 production-env contract.
        if server.read_production_env().encode() != raw:
            raise ActivationError('production configuration changed during preflight')
        server.validate_live_deployment_config(raw.decode())
        authentication_settings(raw)
        check_owner_binding(raw, args.owner_id)
        current = selected(raw)
        validate_policy(current)
        if not ROOT.exists():
            if args.resume or LEASE.exists() or current != OLD:
                raise ActivationError('original invitation policy and no operation required')
            if any(service(io, name) != OLD for name in SERVICES):
                raise ActivationError('running policy differs before activation')
            replacement = patch_env(raw)
            if not args.apply:
                return dict(state='READY', **binding)
            ROOT.mkdir(mode=0o700)
            io.sync(ROOT.parent)
            journal = dict(binding, before=digest(raw), after=digest(replacement),
                           done=[], pending=None, state='ACTIVATING')
            io.atomic(ROOT / 'journal.json', json.dumps(journal, sort_keys=True).encode())
            LEASE.mkdir(mode=0o700)
            for key, value in {'token': secrets.token_hex(32), 'label': 'edu-viewer',
                               'stage': str(ROOT), 'started_at': str(int(time.time()))}.items():
                io.atomic(LEASE / key, (value + '\n').encode())
            io.sync(LEASE.parent)
        else:
            io.secure(ROOT, directory=True)
            journal = server._json(io.read(ROOT / 'journal.json'))
            validate_journal(journal, binding)
            if journal['state'] == 'CONFIGURATION_SUCCEEDED' and not LEASE.exists():
                if (digest(raw) != journal['after'] or current != NEW
                        or any(service(io, name) != NEW for name in SERVICES)):
                    raise ActivationError('completed configuration no longer matches')
                return dict(state='CONFIGURATION_SUCCEEDED', edu_mapping='separate', real_login='not_verified', **binding)
            if not args.resume or not args.apply:
                raise ActivationError('explicit resume of original activation required')
        io.secure(LEASE, directory=True)
        if io.read(LEASE / 'label') != b'edu-viewer\n' or io.read(LEASE / 'stage') != (str(ROOT) + '\n').encode():
            raise ActivationError('activation lease differs')
        lease_identity, lease_token = io.identity(LEASE.lstat()), io.read(LEASE / 'token')
        def check_lease():
            if io.identity(LEASE.lstat()) != lease_identity or io.read(LEASE / 'token') != lease_token:
                raise ActivationError('activation lease changed')
        def save(value):
            check_lease()
            io.atomic(ROOT / 'journal.json', json.dumps(value, sort_keys=True).encode())
        def write_env():
            current_raw = io.read(ENV_FILE)
            if digest(current_raw) == journal['after'] and selected(current_raw) == NEW:
                return
            if digest(current_raw) != journal['before'] or selected(current_raw) != OLD:
                raise ActivationError('configuration differs from original intent')
            replacement = patch_env(current_raw)
            if digest(replacement) != journal['after']:
                raise ActivationError('replacement differs from original intent')
            io.atomic(ENV_FILE, replacement, journal['before'])
        def restart(name):
            if digest(io.read(ENV_FILE)) != journal['after']:
                raise ActivationError('configuration changed before restart')
            if service(io, name, allow_stopped=True) != NEW:
                io.run('/usr/bin/systemctl', 'restart', name)
            if service(io, name) != NEW:
                raise ActivationError('running policy differs after restart')
        def verify():
            if digest(io.read(ENV_FILE)) != journal['after']:
                raise ActivationError('configuration changed after activation')
            for name in SERVICES:
                if service(io, name) != NEW:
                    raise ActivationError('running policy differs at final readback')
            io.wait_ready('health')
            helper._revision_proof(args.publisher_sha, source, bootstrap)
        try:
            advance(journal, [('write', write_env),
                *[(name, lambda name=name: restart(name)) for name in SERVICES], ('verify', verify)], save)
            # Recheck even when resuming after verify was persisted.
            verify()
            journal['state'] = 'CONFIGURATION_SUCCEEDED'
            save(journal)
            check_lease()
            if {p.name for p in LEASE.iterdir()} != {'token', 'label', 'stage', 'started_at'}:
                raise ActivationError('lease inventory changed')
            for item in LEASE.iterdir():
                item.unlink()
            LEASE.rmdir()
            io.sync(LEASE.parent)
            return dict(state='CONFIGURATION_SUCCEEDED', edu_mapping='separate', real_login='not_verified', **binding)
        except BaseException:
            journal['state'] = 'NEEDS_OPERATOR'
            save(journal)
            raise


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--publisher-sha', required=True)
    parser.add_argument('--owner-id', type=int, required=True)
    parser.add_argument('--viewer-id', type=int, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    try:
        if (not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode
                or os.geteuid() != 0 or sys.executable != '/usr/bin/python3.12'
                or 'SSH_ORIGINAL_COMMAND' in os.environ
                or re.fullmatch('[a-f0-9]{40}', args.publisher_sha) is None):
            raise ActivationError('isolated root and exact binding required')
        os.umask(0o077)
        os.environ.clear()
        os.environ.update(ENV)
        print(json.dumps(execute(args), sort_keys=True))
        return 0
    except Exception:
        print('Registration activation rejected; inspect protected operation state', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
