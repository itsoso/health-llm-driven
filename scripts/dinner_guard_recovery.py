"""One-shot service-only recovery for the fixed 2026-10-23 dinner guard failure.

Never deploys, retires, clears a lease, changes configuration or creates backups.
The canonical recovery source requires its own exact green CI revision.
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
import subprocess
import sys

FAILED = 'ae49cf1fc53c567b305c2a9f6cfff5c3257e7309'
PRODUCTION = 'f42bb4c6d1c962453a6eadd1318ca6b663174b80'
STATE = Path('/var/lib/reva-release')
LIVE = Path('/opt/health-app')
LEASE = Path('/run/lock/health-app-release')
LEASE_NS = 1792718504427748929
LOG_PIN = '798e31464702c1ac39dc98790cf6374b500b88e2a144e5a65aaadf4aa688c2a8'
TERMINAL_PIN = '1081c9f232505c3e95fe5bcd8a245ec9de2cdab20986b4a983adff2b30821ae4'
COMPLETED_PIN = '8f92a6ab19f796a0b3ebb90284192a2e932f305a5ddb8ab471fee17ef0276dfe'
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C',
       'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
       'GIT_CONFIG_SYSTEM': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1',
       'GIT_OPTIONAL_LOCKS': '0', 'GIT_TERMINAL_PROMPT': '0'}
FIELDS = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_ctime_ns', 'st_mtime_ns')
# Populated from the fixed, independent read-only incident observation.
FILE_PINS = {'/etc/systemd/system/celery-beat.service': '88a365c82d13840a23b38f214a9cad73f8195964efd69bac34552532d2874e55',
 '/etc/systemd/system/celery-beat.service.d/80-reva-health-evidence-runtime.conf': 'ddd36c082173d9cfd41cf04fcc226f1f09ed65e20a281a8b9db2f6fcc1b33df6',
 '/etc/systemd/system/celery-beat.service.d/90-runtime-state.conf': '9fcb53e7e0107750ae56bb95bd7718fd3bae9deb531a4e896e05a87e028ade00',
 '/etc/systemd/system/celery-beat.service.d/security-network.conf': 'ab8e275de385f3622c44f50beff226686e608cb1ecffe54f11d5051832336964',
 '/etc/systemd/system/celery-beat.service.d/zzzz-reva-vision-model.conf': 'ed75be4ac5d2dbc9d90baa2baa9677cdd793a173abb893386577573543fc7f6c',
 '/etc/systemd/system/celery-worker.service': '2d73bf0cfa5fc128ec9859bb8fff69d6e218f6eb111091338d9881f27ab88d10',
 '/etc/systemd/system/celery-worker.service.d/80-reva-health-evidence-runtime.conf': 'ddd36c082173d9cfd41cf04fcc226f1f09ed65e20a281a8b9db2f6fcc1b33df6',
 '/etc/systemd/system/celery-worker.service.d/90-runtime-state.conf': 'ed467a43ebc1ef1fd6f768233970d0f391a8ea7f2c31a38a5e22d8cf07d5e006',
 '/etc/systemd/system/celery-worker.service.d/security-network.conf': 'ab8e275de385f3622c44f50beff226686e608cb1ecffe54f11d5051832336964',
 '/etc/systemd/system/celery-worker.service.d/zzzz-reva-vision-model.conf': 'ed75be4ac5d2dbc9d90baa2baa9677cdd793a173abb893386577573543fc7f6c',
 '/etc/systemd/system/health-backend.service': 'd7a4e1930573ee70ad5728b399b5c7a88dc61a2c4592804616efe6fce1b19d56',
 '/etc/systemd/system/health-backend.service.d/80-reva-health-evidence-runtime.conf': 'ddd36c082173d9cfd41cf04fcc226f1f09ed65e20a281a8b9db2f6fcc1b33df6',
 '/etc/systemd/system/health-backend.service.d/90-runtime-state.conf': '996bc38bc9077b3ce078ccec6464ee9eb9155d49c098695fc49aeb1ba806fb02',
 '/etc/systemd/system/health-backend.service.d/security-network.conf': 'ab8e275de385f3622c44f50beff226686e608cb1ecffe54f11d5051832336964',
 '/etc/systemd/system/health-backend.service.d/zzzz-reva-vision-model.conf': 'ed75be4ac5d2dbc9d90baa2baa9677cdd793a173abb893386577573543fc7f6c',
 '/etc/systemd/system/health-backend.socket': '8dc93d766722e7c54c7a545a2647b3bb8015b29c93d72df28dfadeaf2c9fc932',
 '/opt/health-app/backend/.env': '2feb3232df2d106d658bf69004cc7276b2362b5e53d28e1cb86149c20a8c732c',
 '/opt/health-app/backend/pi-runtime/install.sh': 'ac9f3d0e4ad916d78fdacd7ddd83093c5314576b2759369589bbcd8dbe6c1722',
 '/opt/health-app/backend/pi-runtime/node_modules/.package-lock.json': '0de1df28714c88f049a06a9b00d916d092a892ee5b62aeae0fc3fad2d35cdca1',
 '/opt/health-app/backend/pi-runtime/package-lock.json': 'e80af8d1291d2b5cac3635f5c0c2be1409f774f0128ad74f54693ea3e1c13a10',
 '/opt/health-app/backend/requirements.lock': '1dff2a6d77a296c0dc26b42f7c40e290f3e027a8e138a9e2f64c73f654c82fc5',
 '/var/lib/reva-laya-release/install.json': 'cc984d7362af332b2f34294250afcf914c924d71bb8cb0e332661e1f1890779a'}
LEASE_PINS = {'label': '0f75c32c9b3e6ff855f241b4ff350de08b910a3d585369e5cafb940b33477f0c',
 'stage': '52451581fbbeb3373a6cc2d9bd83dc35ce652b59ec36597848dee69619c249b6',
 'started_at': '2b451b70d299eed5a6e834b7095af9737c8096cd7ba704301af487d3de3ac9a5',
 'token': '1f84f5444ab64e80a69b9641485b89123675053b44d342ebf5db1ea24f3d55bf'}
UNIT_CONFIG_PINS = {'celery-beat.service': '70a2c544ec74aa7218795a186446b921ba49f7e81d9187b9abfe14d2a23e900f',
 'celery-worker.service': '4a7a7e312541b3506acbe699d6748367139dbf92bb241fb1652c02ad27118163',
 'health-backend.service': '5aaf964ff5df7e42ff0ecc1c9ebb125201dfda05e1379189379f26a1ec32b6e9',
 'health-backend.socket': '30b035fcd5dbd1c194dd10817ea8aaed08b53e799b58e6547f8aeaa088aa17ac'}


class RecoveryError(RuntimeError):
    pass


def need(value):
    if not value:
        raise RecoveryError('fixed dinner recovery proof rejected')


def secure(path, directory=False, *, lease_parent=False):
    info = path.lstat()
    if lease_parent:
        need(path == Path('/run/lock') and directory and info.st_uid == info.st_gid == 0
             and stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o1777)
        return info
    need(info.st_uid == 0 and not info.st_mode & 0o022)
    need(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
    return info


def identity(path, *, pin=None, before_lease=False):
    path = Path(path)
    for parent in reversed(path.parents):
        secure(parent, True, lease_parent=(parent == Path('/run/lock') and path.parent == LEASE))
    before = secure(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(16_000_001)
        after = os.fstat(stream.fileno())
    named = secure(path)
    need(len(raw) <= 16_000_000 and all(getattr(before, k) == getattr(opened, k) == getattr(after, k) == getattr(named, k) for k in FIELDS))
    digest = hashlib.sha256(raw).hexdigest()
    need(pin is None or digest == pin)
    need(not before_lease or max(before.st_ctime_ns, before.st_mtime_ns) < LEASE_NS)
    return {**{k: getattr(before, k) for k in FIELDS}, 'sha256': digest}, raw


def run(args):
    result = subprocess.run(args, env=ENV, check=True, capture_output=True, timeout=30)
    need(len(result.stdout) <= 1_000_000)
    return result.stdout


def validate_log(raw):
    need(hashlib.sha256(raw).hexdigest() == LOG_PIN)
    need(raw.count(b'phase=remote_guard_started') == 1 and raw.count(b'phase=remote_pi_install_started') == 1)
    need(raw.count(b'pi-runtime/install.sh: No such file or directory') == 1)
    for marker in (b'phase=remote_writers_stopped', b'phase=remote_checkout_completed',
                   b'phase=remote_pi_install_completed', b'phase=remote_dependencies_completed',
                   b'command=prepare-code', b'command=install', b'command=restore', b'command=commit'):
        need(marker not in raw)


def dependency_metadata(root):
    """No imports or package execution; reject any post-lease non-bytecode change."""
    root = Path(root)
    secure(root, True)
    entries, directories = [], []
    def walk_error(_error):
        raise RecoveryError('dependency inventory unavailable') from None
    for parent, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        dirs[:] = sorted(d for d in dirs if d != '__pycache__')
        for name in dirs:
            path = Path(parent) / name
            info = path.lstat()
            need(stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode))
            need(max(info.st_ctime_ns, info.st_mtime_ns) < LEASE_NS)
            target = os.readlink(path) if stat.S_ISLNK(info.st_mode) else None
            directories.append((str(path.relative_to(root)), target, *(getattr(info, k) for k in FIELDS)))
            need(len(directories) <= 100000)
        for name in sorted(files):
            if name.endswith(('.pyc', '.pyo')):
                continue
            path = Path(parent) / name
            info = path.lstat()
            need(stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode))
            need(max(info.st_ctime_ns, info.st_mtime_ns) < LEASE_NS)
            entries.append((str(path.relative_to(root)), *(getattr(info, k) for k in FIELDS)))
            need(len(entries) <= 100000)
    expected = {'/opt/health-app/backend/venv': 11935,
                '/opt/health-app/backend/pi-runtime/node_modules': 11799}
    need(entries and (str(root) not in expected or len(entries) == expected[str(root)]))
    return {'count': len(entries), 'directory_count': len(directories),
            'sha256': hashlib.sha256(json.dumps([entries, directories]).encode()).hexdigest()}



def stopped_unit_allowed(unit, fields, pids):
    need(not pids and fields['MainPID'] in ('0', ''))
    if unit == 'celery-worker.service' and fields['ActiveState'] == 'failed':
        need(fields['SubState'] == 'failed' and fields['Result'] == 'timeout')
    else:
        need(fields['ActiveState'] == 'inactive' and fields['SubState'] == 'dead')


class DinnerProof:
    failed_sha = FAILED
    production_sha = PRODUCTION

    def __init__(self, source, bootstrap, server, token, check):
        module = load(source / 'scripts/contained_recovery_proof.py', 'dinner_base_proof')
        self.base = module.RecoveryProof(source, bootstrap, server, FAILED, PRODUCTION, token)
        self.bootstrap, self.check, self.token = bootstrap, check, token
        self.initial_lease = self.lease_snapshot()

    def lease_snapshot(self):
        secure(LEASE, True)
        need({p.name for p in LEASE.iterdir()} == set(LEASE_PINS))
        result = {name: identity(LEASE / name, pin=pin)[0] for name, pin in LEASE_PINS.items()}
        need(result['started_at']['st_ctime_ns'] == LEASE_NS)
        need(identity(LEASE / 'token')[1] == (self.token + '\n').encode())
        return result

    def unit_configuration(self):
        result = {}
        for unit, expected in UNIT_CONFIG_PINS.items():
            raw = run(['/usr/bin/systemctl', 'show', unit,
                '--property=FragmentPath,DropInPaths,ExecStart,EnvironmentFiles,WorkingDirectory,User,Group,Requires,After,NeedDaemonReload'])
            need(hashlib.sha256(raw).hexdigest() == expected)
            values = dict(line.split('=', 1) for line in raw.decode().splitlines() if '=' in line)
            need(values['NeedDaemonReload'] == 'no')
            paths = [values['FragmentPath'], *values['DropInPaths'].split()]
            need(set(paths) == {p for p in FILE_PINS if p == values['FragmentPath'] or p.startswith('/etc/systemd/system/' + unit + '.d/')})
            result[unit] = {'effective_sha256': expected,
                           'files': {p: identity(p, pin=FILE_PINS[p], before_lease=True)[0] for p in paths}}
        return result

    def snapshot(self):
        self.check()
        need(self.lease_snapshot() == self.initial_lease)
        old = self.bootstrap.canonical_source(PRODUCTION)
        self.base.reset._revision_proof(PRODUCTION, old, self.bootstrap)
        need(run(['/usr/bin/git', '-C', str(LIVE), 'rev-parse', 'HEAD']).decode().strip() == PRODUCTION)
        run(['/usr/bin/git', '-C', str(LIVE), 'diff', '--quiet', 'HEAD', '--'])
        log, raw = identity(STATE / FAILED / 'deployment.log', pin=LOG_PIN)
        validate_log(raw)
        completed, raw = identity(STATE / FAILED / 'completed.json', pin=COMPLETED_PIN)
        need(json.loads(raw) == {'sha': FAILED, 'state': 'NEEDS_OPERATOR'})
        runtime = Path('/var/lib/health-app/release-state')
        need({p.name for p in runtime.iterdir()} == {'runtime-state-terminal.json'})
        terminal, raw = identity(runtime / 'runtime-state-terminal.json', pin=TERMINAL_PIN)
        data = json.loads(raw)
        need(data['phase'] == 'COMMITTED' and data['terminal_sha'] == PRODUCTION)
        for path in ('/var/lib/reva-health-evidence-runtime/enabled.env',
                     '/run/reva-health-evidence-activation',
                     '/opt/health-app/backend/.env.reva-release.tmp'):
            need(not os.path.lexists(path))
        for unit in ('health-backend.service', 'celery-worker.service', 'celery-beat.service'):
            need(not os.path.lexists(Path('/run/systemd/system') / (unit + '.d') / '90-reva-health-evidence-activation.conf'))
        files = {p: identity(p, pin=pin, before_lease=True)[0] for p, pin in FILE_PINS.items()}
        units = self.unit_configuration()
        dependencies = {p: dependency_metadata(p) for p in
                        ('/opt/health-app/backend/venv', '/opt/health-app/backend/pi-runtime/node_modules')}
        self.check()
        need(self.lease_snapshot() == self.initial_lease)
        return {'lease': self.initial_lease, 'log': log, 'completed': completed,
                'terminal': terminal, 'files': files, 'units': units, 'dependencies': dependencies}

    def stopped(self):
        self.check()
        need(self.lease_snapshot() == self.initial_lease)
        self.base._no_jobs()
        for unit in (
                'health-backend.socket', 'health-backend.service', 'celery-worker.service', 'celery-beat.service'):
            fields = {name: self.base.systemd.show(unit, name) for name in
                      ('ActiveState', 'SubState', 'MainPID', 'Result')}
            stopped_unit_allowed(unit, fields, self.base._pids(unit))
        self.base._no_jobs()
        self.check()

    def running_snapshot(self):
        self.check()
        need(self.lease_snapshot() == self.initial_lease)
        result = self.base.running_services_snapshot()
        self.check()
        return result


def load(path, name):
    _, raw = identity(path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--evidence-sha256')
    parser.add_argument('--github-token-stdin', action='store_true', required=True)
    args = parser.parse_args()
    need(os.geteuid() == 0 and sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode)
    need(not sys.flags.optimize and re.fullmatch('[a-f0-9]{40}', args.sha) and args.sha not in (FAILED, PRODUCTION))
    need(args.evidence_sha256 is None or re.fullmatch('[a-f0-9]{64}', args.evidence_sha256))
    source = STATE / 'bootstrap' / args.sha / 'source'
    need(Path(__file__).absolute() == source / 'scripts/dinner_guard_recovery.py')
    os.umask(0o077)
    core = load(source / 'scripts/recover_contained_services.py', 'dinner_recovery_core')
    checked, bootstrap, server = core._context(args.sha, verify_ci=False)
    need(checked == source)
    raw = sys.stdin.buffer.read(4097)
    need(re.fullmatch(rb'[A-Za-z0-9_.-]{1,4096}', raw))
    subprocess.run(['/usr/bin/python3.12', '-I', '-S', '-B',
        str(source / 'scripts/trusted_release_gate.py'), '--token-stdin',
        '--sha', args.sha, '--workflow-sha', args.sha], input=raw, env=ENV,
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    del raw
    # The fixed original lease is read locally only after the exact CI gate.
    _, raw = identity(LEASE / 'token', pin=LEASE_PINS['token'])
    need(re.fullmatch(rb'[A-Za-z0-9._:-]{1,255}\n', raw))
    token = raw[:-1].decode('ascii')
    del raw
    launcher = STATE / 'launcher.lock'
    secure(launcher)
    fd = os.open(launcher, os.O_RDWR | os.O_NOFOLLOW)
    build = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build = bootstrap._acquire_existing_build_lock(FAILED)
        def check():
            bootstrap._assert_original_lock(launcher, fd)
            core._check_original_build_lock(bootstrap, FAILED, build)
        check()
        bootstrap._recovery_process_proof()
        proof = DinnerProof(source, bootstrap, server, token, check)
        parent = STATE / 'contained-service-recoveries'
        if os.path.lexists(parent):
            secure(parent, True)
            need(stat.S_IMODE(parent.stat().st_mode) == 0o700)
        elif args.evidence_sha256:
            parent.mkdir(mode=0o700)
            core._sync(STATE)
        result = core.recover_services(proof, parent / FAILED, args.sha, args.evidence_sha256)
        check()
        print(json.dumps(result, sort_keys=True))
    finally:
        if build is not None:
            os.close(build)
        os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        print('dinner recovery blocked; preserve original lease and all evidence', file=sys.stderr)
        sys.exit(1)
