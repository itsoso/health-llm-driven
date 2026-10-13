"""Reviewed operator publication of a new frontend tree, preserving backend revision.

Runs only from canonical current-main staging. Installs artifacts rather than
tracked source/package files; hardened systemd launches Next directly. Unknown
outcomes retain the business lease and immutable audit; never retry automatically.
"""
from types import SimpleNamespace
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import pwd
import stat
import ssl
import subprocess
import sys
import time
import urllib.request

STATE = Path('/var/lib/reva-release')
PRODUCTION = Path('/opt/health-app')
BUILDS = Path('/var/lib/reva-frontend-builds')
LEASE = Path('/var/lock/health-app-release')
RUNTIME = {'User': 'health-web', 'Group': 'health-web',
           'WorkingDirectory': '/opt/health-app/frontend',
           'FragmentPath': '/etc/systemd/system/health-frontend.service',
           'DropInPaths': '', 'Restart': 'on-failure', 'RestartUSec': '5s', 'ReadWritePaths': '/opt/health-app/frontend/.next/cache', 'ProtectSystem': 'strict', 'NoNewPrivileges': 'yes',
           'ExecStart': '/usr/bin/node /opt/health-app/frontend/node_modules/next/dist/bin/next start -H 127.0.0.1 -p 30001'}

class PublishError(Exception):
    """Sanitized error; private command output remains private."""


def validate_binding(publisher, production, expected_tree, actual_tree, live, backend):
    for value in (publisher, production, expected_tree, actual_tree, live):
        if re.fullmatch('[0-9a-f]{40}', value) is None:
            raise PublishError('invalid exact revision')
    if (expected_tree != actual_tree or live != production
            or backend != {'sha': production, 'state': 'SUCCEEDED'}):
        raise PublishError('frontend or preserved backend proof differs')


def receipt(publisher, production, operation, tree, state, digest):
    return dict(kind='frontend-publication', publisher_sha=publisher,
                production_sha=production, operation_id=operation,
                frontend_tree=tree, state=state, artifact_digest=digest)


def validate_runtime(values):
    if any(values.get(key) != value for key, value in RUNTIME.items()):
        raise PublishError('hardened frontend runtime differs')


def load_reviewed(publisher):
    # The old rebuild's entry check is deliberately not reused or weakened.
    source = STATE / 'bootstrap' / publisher / 'source'
    entry = source / 'scripts/trusted_frontend_publish.py'
    import importlib.util
    spec = importlib.util.spec_from_file_location('publication_rebuild', entry.with_name('trusted_frontend_rebuild.py'))
    # Secure every component before executing any imported bytes.
    for path in (entry, entry.with_name('trusted_frontend_rebuild.py')):
        for item in [*reversed(path.parents), path]:
            info = item.lstat()
            expected = stat.S_ISREG if item == path else stat.S_ISDIR
            if info.st_uid != 0 or info.st_mode & 0o022 or not expected(info.st_mode) or (item == path and info.st_nlink != 1):
                raise PublishError('unsafe canonical publisher')
    if Path(__file__).absolute() != entry:
        raise PublishError('canonical publisher entry required')
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    helper = build.module_at(entry.with_name('trusted_review_reset.py'), 'publication_helpers', build.secure_entry)
    checked_source, bootstrap, server = helper.load_reviewed(publisher)
    if checked_source != source:
        raise PublishError('canonical source differs')
    gate = build.module_at(entry.with_name('trusted_release_gate.py'), 'publication_gate', build.secure_entry)
    return source, helper, bootstrap, server, gate, build


def runtime(build):
    fields = ','.join([*RUNTIME, 'ActiveState', 'SubState', 'MainPID', 'Environment', 'NRestarts', 'ExecMainStartTimestampMonotonic'])
    values = dict(line.split('=', 1) for line in build.run(['/usr/bin/systemctl', 'show', 'health-frontend', '--property='+fields]).splitlines())
    raw = values['ExecStart']
    # systemctl encodes process status in braces; bind only its executable/argv.
    match = re.fullmatch(r'\{ path=/usr/bin/node ; argv\[\]=([^;{}]+) ; ignore_errors=no ; start_time=\[[^;{}]*\] ; stop_time=\[[^;{}]*\] ; pid=[0-9]+ ; code=(?:\(null\)|exited) ; status=[0-9]+/[0-9]+ \}', raw)
    if not match:
        raise PublishError('frontend launcher is not a single direct node command')
    values['ExecStart'] = match.group(1).strip()
    validate_runtime(values)
    if values['ActiveState'] != 'active' or values['SubState'] != 'running' or re.fullmatch(r'[1-9][0-9]{0,19}', values.get('MainPID','')) is None:
        raise PublishError('frontend is not active')
    if (re.fullmatch(r'(?:0|[1-9][0-9]{0,19})', values.get('NRestarts','')) is None
            or re.fullmatch(r'[1-9][0-9]{0,19}', values.get('ExecMainStartTimestampMonotonic','')) is None):
        raise PublishError('frontend restart identity is invalid')
    if values['Environment'] != 'NODE_ENV=production BACKEND_URL=http://127.0.0.1:8000':
        raise PublishError('frontend runtime environment differs')
    return values


def stable_runtime(build):
    """A historical restart counter is valid only if the current process is stable."""
    first=runtime(build)
    time.sleep(6)  # exceed the bound fixed RestartSec=5s recovery window
    if runtime(build)!=first:
        raise PublishError('frontend process or restart counter changed')
    return first


def configuration(build):
    environment, fingerprints = {}, {}
    for name in ('.env', '.env.production', '.env.local', '.env.production.local'):
        path = PRODUCTION / 'frontend' / name
        if os.path.lexists(path):
            fingerprint, data = build.data_fingerprint(path)
            values=build.public_build_env(data.decode())
            if any(key in environment and environment[key] != value for key,value in values.items()):
                raise PublishError('frontend endpoint sources conflict')
            environment.update(values)
            fingerprints[name] = fingerprint
    if environment.get('BACKEND_URL', 'http://127.0.0.1:8000') not in ('http://127.0.0.1:8000', 'http://localhost:8000'):
        raise PublishError('frontend build/runtime backend endpoints differ')
    environment['BACKEND_URL'] = 'http://127.0.0.1:8000'
    return environment, fingerprints


def inspect(args, source, helper, bootstrap, server, gate, build):
    gate.verify_release(args.publisher_sha, args.publisher_sha)
    gate._latest(gate._get_json, args.production_sha)
    helper._revision_proof(args.production_sha, source, bootstrap)
    tree = build.git(source, 'rev-parse', 'HEAD:frontend')
    # Only compiled application artifacts switch. Runtime configuration/public
    # assets remain tracked at the preserved production revision.
    runtime_inputs = ('frontend/public', 'frontend/next.config.js', 'frontend/next.config.mjs', 'frontend/next.config.ts')
    if build.git(source, 'diff', '--name-only', args.production_sha, args.publisher_sha, '--', *runtime_inputs):
        raise PublishError('runtime source inputs require a separately reviewed publication')
    old_package = json.loads(build.git(PRODUCTION, 'show', args.production_sha+':frontend/package.json'))
    new_package = json.loads((source/'frontend/package.json').read_text())
    if old_package.get('type') != new_package.get('type'):
        raise PublishError('runtime package module type changed')
    validate_binding(args.publisher_sha, args.production_sha, args.frontend_tree, tree,
                     build.git(PRODUCTION, 'rev-parse', 'HEAD'),
                     bootstrap._read_json(STATE / args.production_sha / 'completed.json'))
    server.assert_frontend_rebuild_history(STATE)
    for name in ('.next','node_modules'):
        server._frontend_publication_backup_digest(PRODUCTION/'frontend'/name,live=True)
    prepared = bool(getattr(args, 'prepared_artifact', False))
    if any(os.path.lexists(path) for path in (LEASE, STATE/'frontend-publications'/args.operation_id)) or (not prepared and os.path.lexists(BUILDS/args.operation_id)):
        raise PublishError('existing operation or lease; retry forbidden')
    environment, fingerprints = configuration(build)
    process = stable_runtime(build)
    # Runtime package scripts must not execute candidate source or lifecycle hooks.
    package = json.loads((source/'frontend/package.json').read_text())
    if package['scripts']['build'] != 'node scripts/braces-depth-guard.cjs --root . --apply && next build':
        raise PublishError('reviewed frontend build command differs')
    plan = dict(publisher_sha=args.publisher_sha, production_sha=args.production_sha,
                operation_id=args.operation_id, frontend_tree=tree,
                snapshot=build.snapshot(server), frontend_env=fingerprints,
                frontend_process=process, public_build_env=environment,
                restore_preswitch_availability=bool(getattr(args,'restore_preswitch_availability',False)),
                unit_fingerprint=build.data_fingerprint(Path(RUNTIME['FragmentPath']))[0],
                toolchain=dict(node=build.run(['/usr/bin/node','--version']).strip(),
                               npm=build.run(['/usr/bin/npm','--version']).strip()))
    if prepared:
        artifact = load_artifact(source, build)
        expected = artifact.binding(source, args.publisher_sha, tree, args.operation_id, environment, build)
        plan['prepared_artifact'] = artifact.verify(expected, SimpleNamespace(bundle_digest=bundle_digest), build, server)
    return plan


def load_artifact(source, build):
    return build.module_at(source/'scripts/trusted_frontend_artifact.py', 'publication_artifact', build.secure_entry)


def assert_preserved(plan, source, helper, bootstrap, server, build):
    helper._revision_proof(plan['production_sha'], source, bootstrap)
    if build.git(PRODUCTION, 'rev-parse', 'HEAD') != plan['production_sha'] or build.snapshot(server) != plan['snapshot'] or configuration(build)[1] != plan['frontend_env']:
        raise PublishError('preserved backend/configuration changed')
    if build.data_fingerprint(Path(RUNTIME['FragmentPath']))[0] != plan['unit_fingerprint']:
        raise PublishError('frontend unit bytes changed')


def assert_unchanged(plan, source, helper, bootstrap, server, build, *, restarted=False):
    assert_preserved(plan,source,helper,bootstrap,server,build)
    current = runtime(build)
    expected = dict(plan['frontend_process'])
    if restarted:
        for key in ('MainPID','ExecMainStartTimestampMonotonic','NRestarts'):
            current.pop(key); expected.pop(key)
    if current != expected:
        raise PublishError('frontend runtime changed')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def verify_pages():
    _verify_pages(include_connection=True)


def verify_availability_pages():
    # The preserved version may legitimately lack /connect/health.
    _verify_pages(include_connection=False)


def _verify_pages(*, include_connection):
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    defaults=ssl.get_default_verify_paths()
    cafile=defaults.openssl_cafile if os.path.isfile(defaults.openssl_cafile) else None
    capath=defaults.openssl_capath if os.path.isdir(defaults.openssl_capath) else None
    if not cafile and not capath: raise PublishError('system TLS trust unavailable')
    context.load_verify_locations(cafile=cafile,capath=capath)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=context))
    for host in ('http://127.0.0.1:30001', 'https://health.executor.life'):
        routes=[('/privacy','可选足迹与分享')]
        if include_connection: routes.append(('/connect/health','小巴健康 · 数据连接'))
        for path, marker in routes:
            success = False
            for _ in range(10):
                try:
                    with opener.open(urllib.request.Request(host+path, headers={'Cache-Control':'no-cache'}), timeout=10) as response:
                        raw=response.read(2_000_001)
                        success=response.status == 200 and response.geturl() == host+path and len(raw)<=2_000_000 and marker in raw.decode()
                except (OSError, UnicodeError):
                    success=False
                if success: break
                time.sleep(2)
            if not success: raise PublishError('frontend public/internal page readback failed')


def publication_artifact_digest(root, build):
    """Bind immutable Next output, with an explicit bounded mutable cache."""
    owner = pwd.getpwnam('health-web')
    cache = root / 'cache'
    if not cache.is_dir() or cache.is_symlink():
        raise PublishError('Next cache boundary differs')
    pending=[cache]; count=0
    while pending:
        path=pending.pop(); count+=1
        if count>150000: raise PublishError('cache inventory exceeds bound')
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            for child in path.iterdir():
                if count+len(pending)>=150000: raise PublishError('cache inventory exceeds bound')
                pending.append(child)
        if (not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode))
                or info.st_uid != owner.pw_uid or info.st_gid != owner.pw_gid
                or info.st_mode & 0o022 or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)):
            raise PublishError('Next cache metadata differs')
    # Contents may change at runtime; immutable child inventories remain bound.
    value = {'mode': stat.S_IMODE(root.lstat().st_mode),
             'cache_owner': [owner.pw_uid, owner.pw_gid],
             'children': {p.name: build.artifact_digest(p) for p in sorted(root.iterdir()) if p.name != 'cache'}}
    return build.evidence_digest(value)


def bundle_digest(frontend, build):
    return hashlib.sha256((publication_artifact_digest(frontend / '.next', build)
                           + build.artifact_digest(frontend / 'node_modules')).encode()).hexdigest()


def prepare_cache(frontend):
    owner = pwd.getpwnam('health-web')
    cache = frontend / '.next/cache'
    cache.mkdir(mode=0o755, exist_ok=True)
    pending=[cache]; count=0
    while pending:
        path=pending.pop(); count+=1
        if count>150000: raise PublishError('cache inventory exceeds bound')
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            for child in path.iterdir():
                if count+len(pending)>=150000: raise PublishError('cache inventory exceeds bound')
                pending.append(child)
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise PublishError('unsafe Next cache')
        os.chown(path, owner.pw_uid, owner.pw_gid, follow_symlinks=False)
        path.chmod(0o755 if path.is_dir() else 0o644)


def build_command(build, operation, stage):
    command=build.build_command(operation,stage)
    expected='npm ci --ignore-scripts --no-audit --no-fund\nnpm run build'
    if command[-1]!=expected: raise PublishError('sandbox build command changed')
    # npm run defaults execute prebuild/postbuild even when install hooks were
    # disabled. Run the explicitly reviewed build only, including braces guard.
    command[-1]=expected.replace('npm run build','npm run --ignore-scripts build')
    return command


STOP_FIELDS='ActiveState,SubState,MainPID,ControlPID,Result,ExecMainCode,ExecMainStatus'


def validate_stopped(values):
    common=dict(MainPID='0',ControlPID='0')
    normal=[dict(**common,ActiveState='inactive',SubState='dead',Result='success',ExecMainCode=code,ExecMainStatus=status)
            for code,status in (('0','0'),('1','0'),('2','15'))]
    terminated=dict(**common,ActiveState='failed',SubState='failed',Result='exit-code',ExecMainCode='1',ExecMainStatus='143')
    if values not in [*normal,terminated]:
        raise PublishError('frontend stop outcome is not proved fully stopped')


def stopped_runtime(build):
    values=dict(line.split('=',1) for line in build.run(['/usr/bin/systemctl','show','health-frontend','--property='+STOP_FIELDS]).splitlines())
    validate_stopped(values)
    return values


def execute(plan, source, helper, bootstrap, server, build, check_locks):
    """Frozen: the legacy publisher creates rollback copies."""
    raise PublishError("no-backup policy freezes legacy frontend publication; evidence preserved")


def main():
    print("no-backup policy freezes legacy frontend publication/rebuild", file=sys.stderr)
    return 1

if __name__=='__main__':
    sys.exit(main())
