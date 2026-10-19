"""Explicit historical-target review maintenance; no release or rotation authority.

Only execute root-owned canonical bytes with system Python -I -S -B. Requires
user authorization for demo reset and independent review of this operator SHA.
Current main CI and the deployed target's historical CI are separate proofs.
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
import time

STATE = Path('/var/lib/reva-release')
PRODUCTION_ENV = Path('/opt/health-app/backend/.env')
EXCEPTIONS = frozenset({'scripts/trusted_review_maintenance.py',
                        'scripts/test_trusted_review_reset.py'})


class MaintenanceError(Exception):
    """Sanitized failure; never disclose credentials or underlying exceptions."""


def secure_import(path):
    for item in [*reversed(path.parents), path]:
        info = item.lstat()
        kind = stat.S_ISREG if item == path else stat.S_ISDIR
        if info.st_uid != 0 or info.st_mode & 0o022 or not kind(info.st_mode):
            raise MaintenanceError('unsafe canonical source')
        if item == path and info.st_nlink != 1:
            raise MaintenanceError('unsafe canonical source link count')


def import_reviewed(path, name):
    secure_import(path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def validate_ids(operator_sha, target_sha, operation_id):
    for value in (operator_sha, target_sha):
        if not isinstance(value, str) or re.fullmatch('[0-9a-f]{40}', value) is None:
            raise MaintenanceError('exact SHA required')
    if operator_sha == target_sha or re.fullmatch('[0-9a-f]{32}', operation_id) is None:
        raise MaintenanceError('distinct operator and target with exact operation required')


def execution_inventory(source):
    result = {}
    paths = [source / 'deploy.sh', source / 'scripts', *(source / 'scripts').rglob('*')]
    for path in paths:
        relative = path.relative_to(source).as_posix()
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            result[relative] = ('directory', stat.S_IMODE(info.st_mode))
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            if relative not in EXCEPTIONS:
                result[relative] = ('file', stat.S_IMODE(info.st_mode),
                                    hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            raise MaintenanceError('unsupported executable inventory')
    return result


def load_sources(operator_sha, target_sha):
    operator = STATE / 'bootstrap' / operator_sha / 'source'
    if Path(__file__).absolute() != operator / 'scripts/trusted_review_maintenance.py':
        raise MaintenanceError('canonical operator path required')
    secure_import(Path(__file__).absolute())
    bootstrap = import_reviewed(operator / 'scripts/bootstrap_trusted_release.py', 'maintenance_bootstrap')
    operator, unused_server = bootstrap.reviewed_source(operator_sha)
    target = bootstrap.canonical_source(target_sha)
    for source in (operator, target):
        for path in source.rglob('*'):
            bootstrap.secure(path)
            if path.name == '__pycache__' or path.suffix == '.pyc':
                raise MaintenanceError('cached canonical code forbidden')
    if execution_inventory(operator) != execution_inventory(target):
        raise MaintenanceError('maintenance executable closure changed')
    # Only target modules are used after source/closure verification. Never
    # import operator backend or put either backend on the outer search path.
    reset = import_reviewed(target / 'scripts/trusted_review_reset.py', 'maintenance_target_reset')
    reset.operator_context()
    source, target_bootstrap, server = reset.load_reviewed(target_sha)
    gate = import_reviewed(source / 'scripts/trusted_release_gate.py', 'maintenance_target_gate')
    return source, target_bootstrap, server, reset, gate


def attest_maintenance(gate, operator_sha, target_sha):
    # Original release gate is unchanged: the current operator must satisfy it.
    operator = gate.verify_release(operator_sha, operator_sha, observed_main=operator_sha)
    get = gate._get_json
    target = gate._receipt(gate._latest(get, target_sha), target_sha, target_sha)
    detail = gate._read(get, f"/actions/runs/{target['ci_run_id']}")
    if gate._receipt(detail, target_sha, target_sha) != target:
        raise MaintenanceError('target CI attempt changed')
    if gate._receipt(gate._latest(get, target_sha), target_sha, target_sha) != target:
        raise MaintenanceError('target CI history changed')
    if gate._main_sha(get) != operator_sha:
        raise MaintenanceError('operator main changed')
    return {'operator': operator, 'target': target}


def production_identity(server):
    before = PRODUCTION_ENV.lstat()
    raw = server.read_production_env()
    after = PRODUCTION_ENV.lstat()
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
                info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if identity(before) != identity(after):
        raise MaintenanceError('production configuration changed during read')
    return identity(after), hashlib.sha256(raw.encode()).hexdigest(), raw


def workspace_preflight(sha, source, bootstrap, server, reset):
    # Same checks as the original reset before its legacy env read. This entry
    # prepares that missing file explicitly, then invokes the original complete
    # validator. It never catches/ignores a failed original validation.
    if bootstrap.canonical_source(sha) != source:
        raise MaintenanceError('canonical target mismatch')
    policy = server.validate_policy(bootstrap._read_json(bootstrap.CONFIG / 'authorized-release.json'), now=time.time())
    server._assert_deployment_window(policy)
    digest = hashlib.sha256((source / 'scripts/trusted_release_server.py').read_bytes()).hexdigest()
    bootstrap.secure(bootstrap.INSTALLED)
    if policy['sha'] != sha or policy['executor_sha256'] != digest or hashlib.sha256(bootstrap.INSTALLED.read_bytes()).hexdigest() != digest:
        raise MaintenanceError('installed target authorization changed')
    workspace = STATE / sha
    reset._private_directory(server, workspace)
    for name, state in (('started.json', 'STARTED'), ('completed.json', 'SUCCEEDED')):
        if bootstrap._read_json(workspace / name) != {'sha': sha, 'state': state}:
            raise MaintenanceError('successful deployed target required')
    if os.path.lexists(bootstrap.BUSINESS_LEASE):
        raise MaintenanceError('business lease exists')
    reset._validate_production(sha, source, bootstrap, server)
    server.validate_loopback(policy)
    server.secure_path(Path(server.PYTHON))
    bindir = workspace / 'bin'
    reset._private_directory(server, bindir)
    reset._private_directory(server, workspace / 'home')
    if {path.name for path in bindir.iterdir()} != {'ssh', 'scp', 'python3'}:
        raise MaintenanceError('unexpected wrapper inventory')
    for command in ('ssh', 'scp', 'python3'):
        target = server.PYTHON if command == 'python3' else f'/usr/bin/{command}'
        args = '' if command == 'python3' else ' -F /etc/reva-release/loopback.conf'
        wrapper = bindir / command
        server.secure_path(wrapper)
        if stat.S_IMODE(wrapper.lstat().st_mode) != 0o700 or wrapper.read_bytes() != f'#!/bin/sh\nexec {target}{args} "$@"\n'.encode():
            raise MaintenanceError('wrapper differs from reviewed bytes')
    if os.path.lexists(workspace / 'deployment.env'):
        raise MaintenanceError('environment already exists; preparation cannot overwrite')
    server._assert_deployment_window(policy)
    return workspace


def run_maintenance(operator_sha, target_sha, operation_id):
    validate_ids(operator_sha, target_sha, operation_id)
    source, bootstrap, server, reset, gate = load_sources(operator_sha, target_sha)
    lock = STATE / 'launcher.lock'
    server.secure_path(lock, private=True)
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    try:
        reset._assert_lock(server, lock, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        reset._assert_lock(server, lock, fd)
        reset._assert_previous_resets(bootstrap, server)
        workspace = STATE / target_sha
        preparation = workspace / 'review-environment-preparation'
        if os.path.lexists(preparation):
            raise MaintenanceError('preparation already consumed; no retry')
        ci = attest_maintenance(gate, operator_sha, target_sha)
        workspace_preflight(target_sha, source, bootstrap, server, reset)
        identity, digest, raw = production_identity(server)
        lines = [line for line in raw.splitlines() if not line.startswith(('DEPLOY_SERVER=', 'DEPLOY_PATH='))]
        expected = ('\n'.join(lines) + '\nDEPLOY_SERVER=health\nDEPLOY_PATH=/opt/health-app\n').encode()
        root = workspace / 'review-resets'
        operation = root / operation_id
        if os.path.lexists(operation):
            raise MaintenanceError('reset operation already consumed')
        proof = {'operator_sha': operator_sha, 'target_sha': target_sha,
                 'operation_id': operation_id, 'production_identity': list(identity),
                 'production_sha256': digest, 'environment_sha256': hashlib.sha256(expected).hexdigest(), 'ci': ci}
        preparation.mkdir(mode=0o700)
        server._sync_directory(workspace)
        server._write_private(preparation / 'started.json', json.dumps({**proof, 'state': 'STARTED'}, sort_keys=True).encode())
        def same_environment():
            current_identity, current_digest, unused = production_identity(server)
            if (current_identity, current_digest) != (identity, digest):
                raise MaintenanceError('production configuration changed')
        try:
            same_environment()
            server._write_private(workspace / 'deployment.env', expected)
            same_environment()
            env = reset._validate_workspace(target_sha, source, bootstrap, server)
            if attest_maintenance(gate, operator_sha, target_sha) != ci:
                raise MaintenanceError('CI admission changed before reset')
            reset._assert_lock(server, lock, fd)
            same_environment()
            if not os.path.lexists(root):
                root.mkdir(mode=0o700)
            reset._private_directory(server, root)
            server._sync_directory(workspace)
            operation.mkdir(mode=0o700)
            reset._private_directory(server, operation)
            server._sync_directory(root)
            server._write_private(operation / 'started.json', json.dumps(reset._marker(target_sha, operation_id, 'STARTED'), sort_keys=True).encode())
            try:
                subprocess.run(['/bin/bash', str(source / 'deploy.sh'), '-R'], cwd=source, env=env,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=True, timeout=server.DEPLOY_TIMEOUT_SECONDS, start_new_session=True)
            except BaseException:
                server._write_private(operation / 'completed.json', json.dumps(reset._marker(target_sha, operation_id, 'NEEDS_OPERATOR'), sort_keys=True).encode())
                raise
            reset._assert_lock(server, lock, fd)
            same_environment()
            server._write_private(operation / 'completed.json', json.dumps(reset._marker(target_sha, operation_id, 'SUCCEEDED'), sort_keys=True).encode())
            result = {**proof, 'state': 'SUCCEEDED'}
            server._write_private(preparation / 'completed.json', json.dumps(result, sort_keys=True).encode())
            return result
        except BaseException:
            server._write_private(preparation / 'completed.json', json.dumps({**proof, 'state': 'NEEDS_OPERATOR'}, sort_keys=True).encode())
            raise
    finally:
        os.close(fd)


def main():
    try:
        if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode) or os.geteuid() != 0 or sys.executable not in ('/usr/bin/python3', '/usr/bin/python3.12') or 'SSH_ORIGINAL_COMMAND' in os.environ:
            raise MaintenanceError('isolated operator execution required')
        os.umask(0o077)
        os.environ.clear()
        os.environ.update(PATH='/usr/bin:/bin', HOME='/nonexistent', LANG='C.UTF-8')
        parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
        parser.add_argument('--operator-sha', required=True)
        parser.add_argument('--target-sha', required=True)
        parser.add_argument('--operation-id', required=True)
        args = parser.parse_args()
        print(json.dumps(run_maintenance(args.operator_sha, args.target_sha, args.operation_id), sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print('review maintenance failed; preserve original evidence, no retry', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
