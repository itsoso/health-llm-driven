"""Publish a prepared Web artifact without retaining replaced application bytes.

Legacy publication/recovery remains frozen. Unknown outcomes retain the lease;
there is no rollback promise or automatic continuation after destructive intent.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
from types import ModuleType

OWNER = 0
POLICY = 'no-backup-v1'
STATE = Path('/var/lib/reva-release')
MOUNTINFO = Path('/proc/self/mountinfo')


class PublicationError(Exception):
    """Fixed diagnostics; command output and configuration remain private."""


def identity(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != OWNER or info.st_mode & 0o022:
        raise PublicationError('unsafe artifact directory')
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode


def mount_points():
    """Read the kernel mount inventory, including same-device bind mounts."""
    try:
        with MOUNTINFO.open('rb') as stream:
            raw = stream.read(4 * 1024 * 1024 + 1)
        if not raw or len(raw) > 4 * 1024 * 1024:
            raise ValueError('mount inventory size')
        points, identifiers = [], set()
        escapes = {'040': ' ', '011': '\t', '012': '\n', '134': '\\'}
        for line in raw.decode('utf-8', errors='strict').splitlines():
            fields, separator, suffix = line.partition(' - ')
            fields = fields.split(' ')
            if (not separator or len(fields) < 6 or len(suffix.split(' ')) != 3
                    or any(not field for field in fields + suffix.split(' '))
                    or not all(re.fullmatch(r'[0-9]+', value) for value in fields[:2])
                    or not re.fullmatch(r'[0-9]+:[0-9]+', fields[2])
                    or fields[0] in identifiers):
                raise ValueError('mount inventory format')
            identifiers.add(fields[0])
            value = fields[4]
            if not re.fullmatch(r'(?:[^\\\x00-\x20]|\\(?:040|011|012|134))*', value):
                raise ValueError('mount path encoding')
            value = re.sub(r'\\(040|011|012|134)', lambda match: escapes[match[1]], value)
            path = Path(value)
            if not path.is_absolute() or '..' in path.parts or str(path) != value:
                raise ValueError('mount path format')
            points.append(path)
        if not points:
            raise ValueError('empty mount inventory')
        return points
    except (OSError, UnicodeError, ValueError) as error:
        raise PublicationError('mount inventory unavailable or malformed') from error


def assert_no_mounts(root):
    if any(point == root or point.is_relative_to(root) for point in mount_points()):
        raise PublicationError('artifact contains a mount boundary')


def check_removal_tree(root, parent_identity):
    """Do not let a fixed-name recursive deletion cross a mount boundary."""
    root_identity = identity(root)
    assert_no_mounts(root)
    if root_identity[0] != parent_identity[0]:
        raise PublicationError('artifact filesystem differs')
    pending = [root]
    count = 0
    while pending:
        path = pending.pop()
        info = path.lstat()
        count += 1
        if count > 150000 or info.st_dev != parent_identity[0] or path.is_mount():
            raise PublicationError('artifact mount or inventory boundary differs')
        if stat.S_ISDIR(info.st_mode):
            pending.extend(path.iterdir())
        elif not (stat.S_ISLNK(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise PublicationError('unsupported old artifact object')
    if identity(root) != root_identity:
        raise PublicationError('artifact root changed')
    return root_identity


def remove_live(frontend, name, parent_identity, root_identity):
    if name not in ('.next', 'node_modules') or not shutil.rmtree.avoids_symlink_attacks:
        raise PublicationError('safe fixed artifact deletion unavailable')
    if identity(frontend) != parent_identity:
        raise PublicationError('artifact parent changed')
    if check_removal_tree(frontend / name, parent_identity) != root_identity:
        raise PublicationError('artifact root changed before removal')
    fd = os.open(frontend, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode) != parent_identity:
            raise PublicationError('artifact parent changed before removal')
        current = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if (current.st_dev, current.st_ino, current.st_uid, current.st_gid, current.st_mode) != root_identity:
            raise PublicationError('artifact root changed at deletion boundary')
        assert_no_mounts(frontend / name)
        shutil.rmtree(name, dir_fd=fd)
        os.fsync(fd)
    finally:
        os.close(fd)


def assert_stopped(publisher, build):
    if build.run(['/usr/bin/systemctl', 'show', 'health-frontend', '--property=KillMode', '--value']).strip() != 'control-group':
        raise PublicationError('frontend process containment differs')
    publisher.stopped_runtime(build)
    group = Path('/sys/fs/cgroup/system.slice/health-frontend.service')
    if os.path.lexists(group):
        if group.is_symlink() or not group.is_dir():
            raise PublicationError('frontend cgroup differs')
        for path in group.rglob('cgroup.procs'):
            if path.read_text().strip():
                raise PublicationError('frontend descendants remain')


def assert_installed_consumer(plan, source, bootstrap, server):
    policy = bootstrap._read_json(bootstrap.CONFIG / 'authorized-release.json')
    server.validate_policy(policy, now=int(time.time()))
    expected = hashlib.sha256((source / 'scripts/trusted_release_server.py').read_bytes()).hexdigest()
    server.secure_path(bootstrap.INSTALLED)
    if (policy['sha'] != plan['publisher_sha'] or policy['executor_sha256'] != expected
            or hashlib.sha256(bootstrap.INSTALLED.read_bytes()).hexdigest() != expected):
        raise PublicationError('installed history consumer or authorization differs')


def execute(plan, source, helper, bootstrap, server, build, publisher, check_locks):
    if (plan.get('publication_policy') != POLICY or 'prepared_artifact' not in plan
            or not shutil.rmtree.avoids_symlink_attacks):
        raise PublicationError('no-backup policy and prepared artifact required')
    assert_installed_consumer(plan, source, bootstrap, server)
    frontend = publisher.PRODUCTION / 'frontend'
    parent_identity = identity(frontend)
    stage = publisher.BUILDS / plan['operation_id'] / 'frontend'
    old_roots = {name: check_removal_tree(frontend / name, parent_identity) for name in ('.next', 'node_modules')}
    for name in old_roots:
        if identity(stage / name)[0] != parent_identity[0]:
            raise PublicationError('candidate filesystem differs')
    check_locks()
    root = publisher.STATE / 'frontend-publications'
    root.mkdir(mode=0o700, exist_ok=True)
    server.secure_path(root, directory=True)
    audit = root / plan['operation_id']
    audit.mkdir(mode=0o700)
    server._sync_directory(root)
    def receipt(state, digest):
        return {**publisher.receipt(*(plan[k] for k in ('publisher_sha', 'production_sha', 'operation_id', 'frontend_tree')), state, digest),
                'publication_policy': POLICY}
    def record(name, state, digest):
        build.write_json(server, audit / name, receipt(state, digest))
    record('intent.json', 'FRONTEND_STARTED', None)
    build.write_json(server, audit / 'before.json', plan)
    publisher.LEASE.mkdir(mode=0o700)
    token = secrets.token_hex(32)
    for name, value in dict(token=token, label='frontend-publication', stage=str(audit), started_at=str(int(time.time()))).items():
        server._write_private(publisher.LEASE / name, (value + '\n').encode())
    server._sync_business_lease_parent()
    lease_identity = helper._lease_identity(str(publisher.LEASE), token, bootstrap, server)
    def bound():
        check_locks()
        if helper._lease_identity(str(publisher.LEASE), token, bootstrap, server) != lease_identity:
            raise PublicationError('business lease changed')
    try:
        artifact = publisher.load_artifact(source, build)
        digest = artifact.consume(plan, source, publisher, build, server, audit)
        bound()
        publisher.assert_unchanged(plan, source, helper, bootstrap, server, build)
        assert_installed_consumer(plan, source, bootstrap, server)
        if identity(frontend) != parent_identity:
            raise PublicationError('artifact parent changed before stop')
        # Validate both roots before stopping; any partial replacement still
        # keeps the original lease and cannot enter another publication.
        for name, expected in old_roots.items():
            if check_removal_tree(frontend / name, parent_identity) != expected:
                raise PublicationError('artifact changed before stop')
        record('install-started.json', 'FRONTEND_INSTALLING', digest)
        build.run(['/usr/bin/systemctl', 'stop', 'health-frontend'])
        assert_stopped(publisher, build)
        for name in old_roots:
            bound()
            assert_stopped(publisher, build)
            remove_live(frontend, name, parent_identity, old_roots[name])
            (stage / name).rename(frontend / name)
            server._sync_directory(frontend)
            server._sync_directory(stage)
        if publisher.bundle_digest(frontend, build) != digest:
            raise PublicationError('installed artifact differs before start')
        bound()
        publisher.assert_preserved(plan, source, helper, bootstrap, server, build)
        build.run(['/usr/bin/systemctl', 'start', 'health-frontend'])
        process = publisher.stable_runtime(build)
        publisher.verify_pages()
        if publisher.runtime(build) != process:
            raise PublicationError('frontend changed during verification')
        publisher.assert_unchanged(plan, source, helper, bootstrap, server, build, restarted=True)
        if publisher.bundle_digest(frontend, build) != digest:
            raise PublicationError('published artifact differs')
        bound()
        record('verified.json', 'FRONTEND_VERIFIED', digest)
        complete = receipt('FRONTEND_SUCCEEDED', digest)
        complete['proof_sha256'] = {name: hashlib.sha256((audit / name).read_bytes()).hexdigest()
                                    for name in ('before.json', 'build.log', 'install-started.json', 'verified.json')}
        complete['backups_digest'] = {}
        build.write_json(server, audit / 'completed.json', complete)
        bound()
        for name in ('token', 'label', 'stage', 'started_at'):
            (publisher.LEASE / name).unlink()
        publisher.LEASE.rmdir()
        server._sync_business_lease_parent()
        return complete
    except BaseException:
        if not (audit / 'failed.json').exists():
            record('failed.json', 'FRONTEND_NEEDS_OPERATOR', None)
        raise PublicationError('publication stopped; evidence and lease retained; no retry') from None


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    for name in ('publisher-sha', 'production-sha', 'frontend-tree', 'operation-id'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--evidence-sha256')
    args = parser.parse_args()
    try:
        if (not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode
                or os.geteuid() != 0 or sys.executable != '/usr/bin/python3.12'):
            raise PublicationError('isolated system Python root required')
        import re
        for name, size in (('publisher_sha', 40), ('production_sha', 40), ('frontend_tree', 40), ('operation_id', 32), ('evidence_sha256', 64)):
            value = getattr(args, name)
            if value is not None and re.fullmatch('[0-9a-f]{%d}' % size, value) is None:
                raise PublicationError('invalid exact binding')
        source = STATE / 'bootstrap' / args.publisher_sha / 'source'
        entry = source / 'scripts/trusted_frontend_no_backup.py'
        if Path(__file__).absolute() != entry:
            raise PublicationError('canonical entry required')
        artifact_path = entry.with_name('trusted_frontend_artifact.py')
        for path in (*reversed(entry.parents), entry, artifact_path):
            info = path.lstat()
            if info.st_uid != 0 or info.st_mode & 0o022 or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise PublicationError('unsafe canonical source')
        raw = artifact_path.read_bytes()
        canonical = subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
                                    '-C', str(source), 'show', args.publisher_sha + ':scripts/trusted_frontend_artifact.py'],
                                   env={'PATH': '/usr/bin:/bin', 'HOME': '/root', 'GIT_CONFIG_NOSYSTEM': '1',
                                        'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_SYSTEM': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1'},
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=True)
        if raw != canonical.stdout:
            raise PublicationError('canonical artifact helper differs')
        artifact = ModuleType('no_backup_artifact')
        artifact.__file__ = str(artifact_path)
        exec(compile(raw, str(artifact_path), 'exec', dont_inherit=True), artifact.__dict__)
        publisher = artifact.canonical_module('no_backup_publisher', entry.with_name('trusted_frontend_publish.py'), source, args.publisher_sha)
        checked, helper, bootstrap, server, gate, build = publisher.load_reviewed(args.publisher_sha)
        if checked != source:
            raise PublicationError('canonical source differs')
        os.umask(0o077)
        args.prepared_artifact = True
        lock = STATE / 'launcher.lock'
        server.secure_path(lock, private=True)
        with lock.open('r+b') as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            build_fd = bootstrap._acquire_existing_build_lock(args.production_sha)
            def check_locks():
                helper._assert_lock(server, lock, stream.fileno())
                if build_fd is None:
                    if os.path.lexists(STATE / args.production_sha / 'build.lock'):
                        raise PublicationError('build lock appeared')
                else:
                    helper._assert_lock(server, STATE / args.production_sha / 'build.lock', build_fd)
            try:
                check_locks()
                plan = publisher.inspect(args, source, helper, bootstrap, server, gate, build)
                plan['publication_policy'] = POLICY
                assert_installed_consumer(plan, source, bootstrap, server)
                if build.run(['/usr/bin/systemctl', 'show', 'health-frontend', '--property=KillMode', '--value']).strip() != 'control-group':
                    raise PublicationError('frontend process containment differs')
                digest = build.evidence_digest(plan)
                if args.evidence_sha256 is None:
                    print(json.dumps(dict(state='FRONTEND_PUBLICATION_PREFLIGHT', publication_policy=POLICY,
                                          publisher_sha=args.publisher_sha, production_sha=args.production_sha,
                                          operation_id=args.operation_id, evidence_sha256=digest)))
                else:
                    if digest != args.evidence_sha256:
                        raise PublicationError('preflight evidence changed')
                    print(json.dumps(execute(plan, source, helper, bootstrap, server, build, publisher, check_locks), sort_keys=True))
            finally:
                if build_fd is not None:
                    os.close(build_fd)
        return 0
    except Exception:
        print('no-backup frontend publication blocked or failed; inspect private evidence; no retry', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
