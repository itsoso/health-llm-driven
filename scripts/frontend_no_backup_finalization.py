"""Close one installed no-backup publication after a CSR readback false negative.

Never reruns publication, rebuilds, switches artifacts, or restarts services.
Original failure evidence stays immutable. Any partial finalization blocks.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import subprocess
from types import ModuleType
import time

STATE = Path('/var/lib/reva-release')
LEASE = Path('/run/lock/health-app-release')


class FinalizationError(Exception):
    """Static diagnostic without credentials or private process output."""


def load(sha):
    source = STATE / 'bootstrap' / sha / 'source'
    if Path(__file__).absolute() != source / 'scripts/frontend_no_backup_finalization.py':
        raise FinalizationError('canonical finalizer required')
    for path in (Path(__file__), source / 'scripts/trusted_frontend_publish.py'):
        for item in (*reversed(path.parents), path):
            info = item.lstat()
            if (info.st_uid != 0 or info.st_mode & 0o022
                    or not (stat.S_ISDIR(info.st_mode) if item != path else stat.S_ISREG(info.st_mode))
                    or (item == path and info.st_nlink != 1)):
                raise FinalizationError('unsafe canonical finalizer source')
    entry = source / 'scripts/trusted_frontend_artifact.py'
    for item in (*reversed(entry.parents), entry):
        info = item.lstat()
        if (info.st_uid != 0 or info.st_mode & 0o022
                or not (stat.S_ISREG(info.st_mode) if item == entry else stat.S_ISDIR(info.st_mode))
                or (item == entry and info.st_nlink != 1)):
            raise FinalizationError('unsafe canonical loader')
    raw = entry.read_bytes()
    environment = dict(PATH='/usr/bin:/bin', HOME='/root', LC_ALL='C', GIT_CONFIG_NOSYSTEM='1',
                       GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null', GIT_NO_REPLACE_OBJECTS='1')
    canonical = subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
                                '-C', str(source), 'show', sha + ':scripts/trusted_frontend_artifact.py'],
                               env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=30, check=True).stdout
    if raw != canonical:
        raise FinalizationError('canonical loader bytes differ')
    artifact = ModuleType('finalization_artifact')
    artifact.__file__ = str(entry)
    exec(compile(raw, str(entry), 'exec', dont_inherit=True), artifact.__dict__)
    publisher = artifact.canonical_module('finalization_publisher', source / 'scripts/trusted_frontend_publish.py', source, sha)
    checked, helper, bootstrap, server, gate, build = publisher.load_reviewed(sha)
    if checked != source:
        raise FinalizationError('canonical source differs')
    build.secure_entry(Path(__file__))
    return source, publisher, helper, bootstrap, server, gate, build


def secure_lease_path(server, path, *, directory=False):
    for item in (*reversed(path.parents), path):
        info = item.lstat()
        if item == Path('/run/lock') and info.st_uid == 0 and stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o1777:
            continue
        server.validate_metadata(info, directory=item != path or directory, private=item == path and not directory)


def lease_file_evidence(server, path):
    secure_lease_path(server, path)
    before = path.lstat()
    if before.st_size > 4096:
        raise FinalizationError('lease value exceeds bound')
    raw = path.read_bytes()
    after = path.lstat()
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if any(getattr(before, name) != getattr(after, name) for name in fields):
        raise FinalizationError('lease changed while reading')
    return {'sha256': hashlib.sha256(raw).hexdigest(), **{name: getattr(after, name) for name in fields}}


def lease_evidence(server, operation):
    secure_lease_path(server, LEASE, directory=True)
    info = LEASE.lstat()
    names = {'token', 'label', 'stage', 'started_at'}
    if stat.S_IMODE(info.st_mode) != 0o700 or {p.name for p in LEASE.iterdir()} != names:
        raise FinalizationError('original lease inventory differs')
    files = {name: lease_file_evidence(server, LEASE / name) for name in names}
    values = {name: (LEASE / name).read_bytes() for name in names}
    if any(hashlib.sha256(values[name]).hexdigest() != files[name]['sha256'] for name in names):
        raise FinalizationError('lease changed while reading values')
    token = values['token'].rstrip(b'\n')
    if (re.fullmatch(rb'[a-f0-9]{64}', token) is None
            or values['token'] != token + b'\n'
            or values['label'] != b'frontend-publication\n'
            or values['stage'] != (str(operation) + '\n').encode()
            or re.fullmatch(rb'[0-9]+\n', values['started_at']) is None):
        raise FinalizationError('original lease binding differs')
    return {'directory': {'dev': info.st_dev, 'ino': info.st_ino},
            'files': files}


def inspect(sha, context):
    source, publisher, helper, bootstrap, server, gate, build = context
    binding = server.NO_BACKUP_FINALIZATION_BINDING
    operation = STATE / 'frontend-publications' / binding['operation_id']
    original = server.no_backup_finalization_original(STATE, binding['operation_id'])
    server.assert_frontend_rebuild_history(STATE, pending_no_backup_finalization=binding['operation_id'])
    server.assert_ota_history()
    bootstrap._recovery_process_proof()
    policy = bootstrap._read_json(bootstrap.CONFIG / 'authorized-release.json')
    old_source = bootstrap.canonical_source(binding['publisher_sha'])
    old_digest = hashlib.sha256((old_source / 'scripts/trusted_release_server.py').read_bytes()).hexdigest()
    bootstrap.secure(bootstrap.INSTALLED, private=True)
    if (policy.get('sha') != binding['publisher_sha'] or policy.get('executor_sha256') != old_digest
            or hashlib.sha256(bootstrap.INSTALLED.read_bytes()).hexdigest() != old_digest):
        raise FinalizationError('original installed authorization differs')
    server.validate_policy(policy, now=time.time())
    lease = lease_evidence(server, operation)
    before = server._json(server._read_private(operation / 'before.json'))
    stage = publisher.BUILDS / binding['operation_id'] / 'frontend'
    if any(os.path.lexists(stage / name) for name in ('.next', 'node_modules')):
        raise FinalizationError('candidate was not fully installed')
    if bootstrap._read_json(STATE / binding['production_sha'] / 'completed.json') != {'sha': binding['production_sha'], 'state': 'SUCCEEDED'}:
        raise FinalizationError('preserved backend success missing')
    publisher.assert_unchanged(before, source, helper, bootstrap, server, build, restarted=True)
    if publisher.bundle_digest(publisher.PRODUCTION / 'frontend', build) != binding['artifact_digest']:
        raise FinalizationError('installed artifact differs')
    process = publisher.stable_runtime(build)
    publisher.verify_pages()
    if publisher.runtime(build) != process:
        raise FinalizationError('frontend changed during readback')
    publisher.assert_preserved(before, source, helper, bootstrap, server, build)
    if publisher.bundle_digest(publisher.PRODUCTION / 'frontend', build) != binding['artifact_digest']:
        raise FinalizationError('installed artifact changed after readback')
    if publisher.runtime(build) != process:
        raise FinalizationError('frontend changed after artifact verification')
    if (server.no_backup_finalization_original(STATE, binding['operation_id']) != original
            or lease_evidence(server, operation) != lease):
        raise FinalizationError('original evidence changed')
    return {'schema_version': 1, 'profile': 'csr-login-readback-v1', 'finalizer_sha': sha,
            'original': original, 'lease': lease, 'process': process}


def finalize(plan, inspect_again, server, bootstrap, check_locks, verify_live):
    if inspect_again() != plan:
        raise FinalizationError('finalization evidence changed before intent')
    check_locks()
    operation_id = plan['original']['binding']['operation_id']
    root = STATE / 'frontend-publication-finalizations'
    if not root.exists():
        root.mkdir(mode=0o700)
        server._sync_directory(root.parent)
    server.secure_path(root, directory=True)
    if stat.S_IMODE(root.lstat().st_mode) != 0o700:
        raise FinalizationError('unsafe finalization root')
    audit = root / operation_id
    audit.mkdir(mode=0o700)
    server._sync_directory(root)
    def write(name, value):
        raw = json.dumps(value, sort_keys=True).encode()
        bootstrap._write(audit / name, raw)
        return hashlib.sha256(raw).hexdigest()
    intent_hash = write('intent.json', plan)
    verify_live()
    operation = STATE / 'frontend-publications' / operation_id
    if (server.no_backup_finalization_original(STATE, operation_id) != plan['original']
            or lease_evidence(server, operation) != plan['lease']):
        raise FinalizationError('original evidence changed after intent')
    check_locks()
    verified_hash = write('verified.json', {'state': 'LIVE_VERIFIED', 'intent_sha256': intent_hash})
    # All four original files must remain bound immediately before removal.
    if lease_evidence(server, operation) != plan['lease']:
        raise FinalizationError('lease changed before release')
    for name in sorted(plan['lease']['files']):
        check_locks()
        info = LEASE.lstat()
        if {'dev': info.st_dev, 'ino': info.st_ino} != plan['lease']['directory']:
            raise FinalizationError('lease directory changed during release')
        if lease_file_evidence(server, LEASE / name) != plan['lease']['files'][name]:
            raise FinalizationError('lease file changed during release')
        (LEASE / name).unlink()
    info = LEASE.lstat()
    if {'dev': info.st_dev, 'ino': info.st_ino} != plan['lease']['directory']:
        raise FinalizationError('lease directory changed before removal')
    LEASE.rmdir()
    server._sync_directory(LEASE.parent)
    complete = {'state': 'FINALIZED_NO_BACKUP_PUBLICATION', **plan['original']['binding'],
                'finalizer_sha': plan['finalizer_sha'], 'intent_sha256': intent_hash,
                'verified_sha256': verified_hash}
    check_locks()
    committing = {'state': 'FINALIZATION_PENDING', 'intent_sha256': intent_hash}
    try:
        write('committing.json', committing)
        write('completed.json', complete)
        (audit / 'committing.json').unlink()
        server._sync_directory(audit)
    except BaseException:
        # Keep a visible blocker even when completed bytes preceded fsync failure.
        if not os.path.lexists(audit / 'committing.json'):
            write('committing.json', committing)
        raise
    return server.no_backup_finalization_completion(STATE, operation_id)


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--finalizer-sha', required=True)
    parser.add_argument('--evidence-sha256')
    args = parser.parse_args()
    try:
        if (os.geteuid() != 0 or sys.executable != '/usr/bin/python3.12' or not sys.flags.isolated
                or not sys.flags.no_site or not sys.flags.dont_write_bytecode
                or re.fullmatch('[a-f0-9]{40}', args.finalizer_sha) is None
                or (args.evidence_sha256 is not None and re.fullmatch('[a-f0-9]{64}', args.evidence_sha256) is None)):
            raise FinalizationError('isolated root and exact identity required')
        os.umask(0o077)
        context = load(args.finalizer_sha)
        source, publisher, helper, bootstrap, server, gate, build = context
        gate.verify_release(args.finalizer_sha, args.finalizer_sha)
        gate._latest(gate._get_json, server.NO_BACKUP_FINALIZATION_BINDING['publisher_sha'])
        gate._latest(gate._get_json, server.NO_BACKUP_FINALIZATION_BINDING['production_sha'])
        server.secure_path(STATE / 'launcher.lock', private=True)
        with (STATE / 'launcher.lock').open('r+b') as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            build_fd = bootstrap._acquire_existing_build_lock(server.NO_BACKUP_FINALIZATION_BINDING['production_sha'])
            def check_locks():
                helper._assert_lock(server, STATE / 'launcher.lock', stream.fileno())
                if build_fd is None and os.path.lexists(STATE / server.NO_BACKUP_FINALIZATION_BINDING['production_sha'] / 'build.lock'):
                    raise FinalizationError('original build lock appeared')
                if build_fd is not None:
                    helper._assert_lock(server, STATE / server.NO_BACKUP_FINALIZATION_BINDING['production_sha'] / 'build.lock', build_fd)
            def inspect_locked():
                check_locks()
                result = inspect(args.finalizer_sha, context)
                check_locks()
                return result
            try:
                plan = inspect_locked()
                digest = build.evidence_digest(plan)
                if args.evidence_sha256 is None:
                    print(json.dumps({'state': 'FINALIZATION_PREFLIGHT', 'evidence_sha256': digest}))
                elif digest != args.evidence_sha256:
                    raise FinalizationError('preflight evidence changed')
                else:
                    def verify_live():
                        before = server._json(server._read_private(STATE / 'frontend-publications' / plan['original']['binding']['operation_id'] / 'before.json'))
                        publisher.assert_preserved(before, source, helper, bootstrap, server, build)
                        if publisher.bundle_digest(publisher.PRODUCTION / 'frontend', build) != plan['original']['binding']['artifact_digest']:
                            raise FinalizationError('installed artifact changed before release')
                        if publisher.runtime(build) != plan['process']:
                            raise FinalizationError('frontend changed before release')
                    print(json.dumps(finalize(plan, inspect_locked, server, bootstrap, check_locks, verify_live)))
            finally:
                if build_fd is not None:
                    os.close(build_fd)
        return 0
    except Exception:
        print('No-backup finalization blocked; original evidence retained; no retry', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
