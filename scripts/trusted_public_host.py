"""Canonical operator entry for post-deploy host containment; no release credentials."""
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
import sys
import time

STATE = Path('/var/lib/reva-release')
LEASE = Path('/var/lock/health-app-release')


def secure(path):
    for item in [*reversed(path.parents), path]:
        info = item.lstat()
        kind = stat.S_ISREG if item == path else stat.S_ISDIR
        if info.st_uid != 0 or info.st_mode & 0o022 or not kind(info.st_mode):
            raise RuntimeError('untrusted canonical entry')
        if item == path and info.st_nlink != 1:
            raise RuntimeError('linked canonical entry')


def module(path, name):
    secure(path)
    if os.path.lexists(path.parent / "__pycache__"):
        raise RuntimeError("cached code forbidden before module execution")
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def load_reviewed(sha):
    source = STATE / 'bootstrap' / sha / 'source'
    entry = source / 'scripts/trusted_public_host.py'
    if Path(__file__).absolute() != entry:
        raise RuntimeError('canonical operator staging required')
    secure(entry)
    helper = module(entry.with_name('trusted_review_reset.py'), 'host_revision_helpers')
    reviewed, bootstrap, server = helper.load_reviewed(sha)
    if reviewed != source:
        raise RuntimeError('canonical source mismatch')
    gate = module(entry.with_name('trusted_release_gate.py'), 'host_release_gate')
    guard = module(entry.with_name('harden_public_host.py'), 'host_hardening')
    return source, helper, bootstrap, server, gate, guard


def require_backend_receipt(sha, value):
    if value != {'sha': sha, 'state': 'SUCCEEDED'}:
        raise RuntimeError('exact backend success receipt required')


def verify_runtime(guard, *, check_network=True):
    required = {'AUTH_PHONE_SELF_REGISTRATION_ENABLED': 'false',
                'REGISTRATION_INVITATION_ENFORCEMENT_ENABLED': 'true',
                'REGISTRATION_INVITATION_ROLLOUT_ENABLED': 'true'}
    for name in ('health-backend', 'celery-worker', 'celery-beat'):
        values = dict(line.split('=', 1) for line in guard.run('/usr/bin/systemctl', 'show', name,
            '-p', 'User,ActiveState,MainPID,NoNewPrivileges,ProtectSystem,ProtectHome,MemoryMax,CPUQuotaPerSecUSec,InaccessiblePaths').splitlines())
        if (values.get('User') != 'health-app' or values.get('ActiveState') != 'active'
                or values.get('NoNewPrivileges') != 'yes' or values.get('ProtectSystem') != 'strict'
                or values.get('ProtectHome') not in ('yes', 'true')
                or values.get('MemoryMax') in (None, 'infinity')
                or '/mnt' not in [item.lstrip('-+') for item in values.get('InaccessiblePaths', '').split()]):
            raise RuntimeError('backend sandbox readback failed')
        pid = int(values['MainPID'])
        env = dict(item.split(b'=', 1) for item in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0') if b'=' in item)
        if any(env.get(key.encode(), b'').decode().lower() != value for key, value in required.items()):
            raise RuntimeError('running admission policy differs')
    if check_network:
        guard.network_guard()


def verify_frontend_artifacts(sha, source, bootstrap, server):
    frontend = module(source / "scripts/trusted_frontend_rebuild.py", "host_frontend_proof")
    server.assert_frontend_rebuild_history(STATE)
    root = STATE / "frontend-rebuilds"
    server.secure_path(root, directory=True)
    tree = frontend.git(source, "rev-parse", "HEAD:frontend")
    matches = []
    for operation in root.iterdir():
        server.secure_path(operation, directory=True)
        # The history gate already validates the durable closure of a failed
        # preinstall attempt; such attempts intentionally have no completion.
        if os.path.lexists(operation / "failed.json"):
            continue
        value = bootstrap._read_json(operation / "completed.json")
        if value.get("publisher_sha") == sha and value.get("production_sha") == sha:
            matches.append((operation, value))
    if len(matches) != 1:
        raise RuntimeError("exactly one final revision frontend receipt required")
    operation, completed = matches[0]
    operation_id = operation.name
    if re.fullmatch(r"[a-f0-9]{32}", operation_id) is None:
        raise RuntimeError("invalid frontend operation identity")
    digest = hashlib.sha256("".join(frontend.artifact_digest(frontend.PRODUCTION / "frontend" / name)
                                    for name in (".next", "node_modules")).encode()).hexdigest()
    expected = frontend.receipt(sha, sha, operation_id, tree, "FRONTEND_SUCCEEDED", digest)
    if completed != expected:
        raise RuntimeError("running frontend artifacts differ from final revision receipt")
    for filename, state in (("verified.json", "FRONTEND_VERIFIED"), ("install-started.json", "FRONTEND_INSTALLING")):
        if bootstrap._read_json(operation / filename) != frontend.receipt(sha, sha, operation_id, tree, state, digest):
            raise RuntimeError("frontend installation evidence differs")
    return {"operation_id": operation_id, "frontend_tree": tree, "artifact_digest": digest}


def execute(sha):
    source, helper, bootstrap, server, gate, guard = load_reviewed(sha)
    gate.verify_release(sha, sha)
    lock = STATE / 'launcher.lock'
    server.secure_path(lock, private=True)
    with lock.open('r+b') as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        helper._assert_lock(server, lock, stream.fileno())
        helper._revision_proof(sha, source, bootstrap)
        require_backend_receipt(sha, bootstrap._read_json(STATE / sha / 'completed.json'))
        verify_runtime(guard, check_network=False)
        artifact_proof = verify_frontend_artifacts(sha, source, bootstrap, server)
        if os.path.lexists(LEASE):
            raise RuntimeError('existing business lease')
        audit = STATE / sha / 'host-hardening'
        if os.path.lexists(audit):
            raise RuntimeError('existing hardening attempt; retry forbidden')
        audit.mkdir(mode=0o700)
        server._sync_directory(audit.parent)
        server._write_private(audit / 'frontend.json', json.dumps(artifact_proof).encode())
        server._write_private(audit / 'started.json', json.dumps({'sha': sha, 'state': 'STARTED'}).encode())
        LEASE.mkdir(mode=0o700)
        token = secrets.token_hex(32)
        for name, value in {'token': token, 'label': 'host-hardening', 'stage': str(audit), 'started_at': str(int(time.time()))}.items():
            server._write_private(LEASE / name, (value + '\n').encode())
        server._sync_directory(LEASE.parent)
        identity = helper._lease_identity(str(LEASE), token, bootstrap, server)
        try:
            guard.apply(sha)
            verify_runtime(guard)
            helper._revision_proof(sha, source, bootstrap)
            helper._assert_lock(server, lock, stream.fileno())
            if helper._lease_identity(str(LEASE), token, bootstrap, server) != identity:
                raise RuntimeError('business lease changed')
            server._write_private(audit / 'verified.json', json.dumps({'sha': sha, 'state': 'LOCAL_VERIFIED'}).encode())
            for name in ('token', 'label', 'stage', 'started_at'):
                (LEASE / name).unlink()
            LEASE.rmdir()
            server._sync_directory(LEASE.parent)
            result = {'sha': sha, 'state': 'LOCAL_VERIFIED', 'external_readback_required': True}
            server._write_private(audit / 'completed.json', json.dumps(result).encode())
            return result
        except BaseException:
            server._write_private(audit / 'failed.json', json.dumps({'sha': sha, 'state': 'NEEDS_OPERATOR'}).encode())
            raise


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--sha', required=True)
    args = parser.parse_args()
    try:
        if (not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode
                or os.geteuid() != 0 or sys.executable != '/usr/bin/python3.12'
                or re.fullmatch(r'[a-f0-9]{40}', args.sha) is None or 'SSH_ORIGINAL_COMMAND' in os.environ):
            raise RuntimeError('isolated root operator required')
        os.umask(0o077)
        os.environ.clear()
        os.environ.update(PATH='/usr/bin:/bin', HOME='/root', LC_ALL='C', GIT_CONFIG_NOSYSTEM='1',
                          GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null', GIT_NO_REPLACE_OBJECTS='1')
        print(json.dumps(execute(args.sha)))
        return 0
    except Exception:
        print('host hardening blocked or incomplete; inspect private evidence, no blind retry', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
