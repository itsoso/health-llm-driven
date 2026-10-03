"""One upload opportunity for retained build 274; never builds or submits review.

GitHub's fresh trusted runner owns vendor credentials and attests live evidence.
The server independently proves closure, deployed code and exclusive lease. This
does not defend against a compromised GitHub runner/root/vendor control plane.
Unknown vendor outcomes retain the claim and lease; only finish may be recovered.
"""
import argparse
from contextlib import contextmanager
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

STATE = Path('/var/lib/reva-release')
OLD_SHA = '514c8c28a87ad5761a6f66b284c19a69dff33e8f'
BUILD_ID = '63b61a31-058c-44e5-bb82-67727ca7d073'
PROJECT = '911ea84f-bc7e-4a12-90cf-33966b6f7398'
ASC_APP = '6763569720'
PROFILE = 'retained-testflight-274-v1'
UUID = r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}'
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'GIT_CONFIG_NOSYSTEM': '1',
       'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_SYSTEM': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1'}
# Exact operations-only changes since the original build, never arbitrary *.md/scripts.
ALLOWED = frozenset({
    '.github/workflows/ci.yml', '.github/workflows/trusted-release.yml',
    'backend/tests/test_harness_workflow_trace.py',
    'docs/dossiers/2026-10-03-local-change-integration.md', 'docs/governance/deploy.md',
    'plugins/reva-health-harness/scripts/harness_workflow_trace.py',
    'scripts/built_unuploaded_proof.py', 'scripts/contained_recovery_proof.py',
    'scripts/contained_release_retirement.py', 'scripts/harness_workflow_trace.py',
    'scripts/recover_contained_services.py', 'scripts/test_built_unuploaded_proof.py',
    'scripts/test_contained_recovery_proof.py', 'scripts/test_contained_release_retirement.py',
    'scripts/test_recover_contained_services.py', 'scripts/trusted_retained_testflight.py',
    'scripts/test_trusted_retained_testflight.py', 'scripts/trusted_release_server.py',
    'scripts/bootstrap_trusted_release.py', 'scripts/test_trusted_release_server.py',
    'scripts/test_bootstrap_trusted_release.py', 'scripts/test_trusted_release_workflow.py',
})
BUILD = {'id': BUILD_ID, 'gitCommitHash': OLD_SHA, 'status': 'FINISHED', 'platform': 'IOS',
         'distribution': 'STORE', 'buildProfile': 'production',
         'appIdentifier': 'life.executor.health', 'appVersion': '1.3.4',
         'appBuildVersion': '274', 'isForIosSimulator': False, 'app': {'id': PROJECT}}
# Fields are from pinned eas-cli SubmissionWithSubmittedBuildFragment, not CLI text.
QUERY = '''query($buildId: ID!) { builds { byId(buildId: $buildId) {
 id gitCommitHash status platform distribution buildProfile appIdentifier
 appVersion appBuildVersion isForIosSimulator app { id } submissions {
 id status platform app { id } iosConfig { ascAppIdentifier } submittedBuild { id }
 } } } }'''
CONTRACT = None
SOURCE = None


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate field')
        result[key] = value
    return result


def parsed(raw):
    if len(raw) > 1_000_000:
        raise ValueError('oversized evidence')
    return json.loads(raw, object_pairs_hook=unique)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def git(source, *args):
    return subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
                           '-C', str(source), *args], env=ENV, stdin=subprocess.DEVNULL,
                          capture_output=True, check=True, timeout=90).stdout


def load(source, sha, filename):
    path = source / 'scripts' / filename
    for item in [*reversed(path.parents), path]:
        info = item.lstat()
        kind = stat.S_ISREG if item == path else stat.S_ISDIR
        if info.st_uid != 0 or info.st_mode & 0o022 or not kind(info.st_mode):
            raise ValueError('unsafe canonical helper')
    if (os.path.lexists(path.parent / '__pycache__')
            or path.read_bytes() != git(source, 'show', sha + ':scripts/' + filename)):
        raise ValueError('canonical helper differs or has cached code')
    spec = importlib.util.spec_from_file_location('retained_' + filename[:-3], path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def initialize(source, sha):
    global SOURCE, CONTRACT
    SOURCE = source
    CONTRACT = load(source, sha, 'built_unuploaded_proof.py')


def validate_paths(paths):
    if any(path not in ALLOWED for path in paths):
        raise ValueError('retained artifact has runtime or unknown source delta')


def validate_before(value):
    CONTRACT.validate_history(value, OLD_SHA)


def validate_after(build):
    if (not isinstance(build, dict) or set(build) != set(BUILD) | {'submissions'}
            or any(build.get(k) != v for k, v in BUILD.items())
            or build.get('isForIosSimulator') is not False
            or not isinstance(build.get('submissions'), list) or len(build['submissions']) != 1):
        raise ValueError('exact retained artifact required')
    submission = build['submissions'][0]
    if (not isinstance(submission, dict)
            or set(submission) != {'id', 'status', 'platform', 'app', 'iosConfig', 'submittedBuild'}
            or not isinstance(submission['id'], str) or re.fullmatch(UUID, submission['id']) is None
            or submission != {'id': submission['id'], 'status': 'FINISHED', 'platform': 'IOS',
                              'app': {'id': PROJECT}, 'iosConfig': {'ascAppIdentifier': ASC_APP},
                              'submittedBuild': {'id': BUILD_ID}}):
        raise ValueError('exact finished submission required')


def validate_request(value, sha, *, after=False, fresh=True):
    keys = {'sha', 'profile', 'observed_at', 'after', 'claim_id'} if after else {'sha', 'profile', 'observed_at', 'before'}
    if (not isinstance(value, dict) or set(value) != keys or value['sha'] != sha
            or re.fullmatch(r'[0-9a-f]{40}', sha) is None or value['profile'] != PROFILE
            or type(value['observed_at']) is not int
            or (fresh and not -10 <= time.time() - value['observed_at'] <= 120)):
        raise ValueError('invalid or stale retained evidence')
    if after:
        if not isinstance(value['claim_id'], str) or re.fullmatch(r'[0-9a-f]{64}', value['claim_id']) is None:
            raise ValueError('invalid claim identity')
        validate_after(value['after'])
    else:
        validate_before(value['before'])


def operation():
    return STATE / 'retained-testflight' / BUILD_ID


def read(server, path):
    return parsed(server._read_private(path))


def write(server, path, value):
    server._write_private(path, json.dumps(value, sort_keys=True).encode())


def prove_original(server, bootstrap):
    history = bootstrap._retired_history()
    original = history.get(OLD_SHA)
    if not original or original['workspace'].get('state') != 'CLOSED_UNCHANGED_RELEASE':
        raise ValueError('original mixed release not closed and retired')
    closure = read(server, STATE / 'unchanged-release-closures' / OLD_SHA / 'intent.json')
    validate_before(closure['snapshot']['built_unuploaded'])
    if (read(server, STATE / OLD_SHA / 'build-started.json') != {'sha': OLD_SHA, 'state': 'STARTED'}
            or any(os.path.lexists(STATE / OLD_SHA / name) for name in ('native-started.json', 'testflight-base.json'))):
        raise ValueError('original build claim changed')
    # Store only hashes, never retirement secrets or archived health configuration.
    return {'retirement': digest(original), 'closure': digest(closure),
            'build_claim': digest(read(server, STATE / OLD_SHA / 'build-started.json'))}


def prove_backend(server, bootstrap, sha, lease):
    proof = server.testflight_backend_proof({'sha': sha}, lease=lease)
    if proof != {'sha': sha, 'production_sha': sha, 'state': 'COMPATIBLE'}:
        raise ValueError('publisher must already be deployed')
    def inventory(repo, revision):
        result = {}
        for row in git(repo, 'ls-tree', '-r', '-z', '--full-tree', revision).split(b'\0'):
            if row:
                metadata, path = row.split(b'\t', 1)
                result[path.decode('utf-8', errors='strict')] = metadata
        return result
    old_source = bootstrap.canonical_source(OLD_SHA)
    target, old = inventory(SOURCE, sha), inventory(old_source, OLD_SHA)
    validate_paths([path for path in target.keys() | old.keys() if target.get(path) != old.get(path)])
    return proof


def claim(server, bootstrap, policy, value):
    sha = policy['sha']
    validate_request(value, sha)
    server.assert_ota_history()
    server._assert_deployment_window(policy)
    server.validate_loopback(policy)
    if server.read_status(sha, STATE / sha)['state'] != 'SUCCEEDED':
        raise ValueError('successful exact backend required')
    root = operation().parent
    if os.path.lexists(operation()) or os.path.lexists(server.BUSINESS_LEASE):
        raise ValueError('retained artifact already consumed or business lease exists')
    original = prove_original(server, bootstrap)
    root.mkdir(mode=0o700, exist_ok=True)
    server.secure_path(root, directory=True)
    if stat.S_IMODE(root.stat().st_mode) != 0o700 or any(root.iterdir()):
        raise ValueError('unknown retained artifact audit')
    # Persist the name linking this global once-only registry into STATE before
    # granting any permission. Fsyncing the child alone cannot make a newly
    # created parent directory survive power loss. Also sync an existing empty
    # registry: its prior creation may have been interrupted before persistence.
    server._sync_directory(STATE)
    operation().mkdir(mode=0o700)
    server._sync_directory(root)
    # Consumption precedes lease initialization; partial state never grants retry.
    write(server, operation() / 'intent.json', {'request': value, 'original': original})
    lease = server._acquire_testflight_lease(STATE / sha)
    server._sync_business_lease_parent()
    write(server, operation() / 'lease.json', lease)
    prove_backend(server, bootstrap, sha, lease)
    if prove_original(server, bootstrap) != original:
        raise ValueError('original closure drift')
    server._assert_testflight_lease(lease, STATE / sha)
    result = {'sha': sha, 'state': 'CLAIMED', 'claim_id': secrets.token_hex(32)}
    write(server, operation() / 'claimed.json', result)
    return result


def validate_archive(server, op, sha):
    archive = op / 'released-lease'
    server.secure_path(archive, directory=True)
    lease = read(server, op / 'lease.json')
    if (not isinstance(lease, dict) or set(lease) != {'token', 'started_at', 'identity'}
            or not isinstance(lease['token'], str) or re.fullmatch(r'[0-9a-f]{64}', lease['token']) is None
            or not isinstance(lease['started_at'], str) or re.fullmatch(r'[0-9]{1,12}', lease['started_at']) is None
            or not isinstance(lease['identity'], list) or len(lease['identity']) != 4
            or any(type(n) is not int or n < 0 for n in lease['identity'])):
        raise ValueError('invalid retained lease')
    expected = {'token': lease['token'], 'started_at': lease['started_at'],
                'label': 'testflight-check', 'stage': str(STATE / sha)}
    if stat.S_IMODE(archive.stat().st_mode) != 0o700 or {p.name for p in archive.iterdir()} != set(expected):
        raise ValueError('retained lease archive differs')
    for key, val in expected.items():
        if server._read_private(archive / key) != (val + '\n').encode():
            raise ValueError('retained lease bytes differ')


def move_noreplace(source, destination):
    before = source.lstat()
    subprocess.run(['/usr/bin/mv', '--no-clobber', '-T', '--', str(source), str(destination)],
                   env=ENV, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=True, timeout=10)
    after = destination.lstat()
    if os.path.lexists(source) or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise ValueError('lease archive was not the same no-clobber move')


def archive_lease(server, sha, lease, *, release=True):
    op = operation()
    durable = op / 'released-lease'
    retired = server.BUSINESS_LEASE.with_name(server.BUSINESS_LEASE.name + '.retained-' + BUILD_ID)
    server._testflight_lease_parent()
    original = retired if os.path.lexists(retired) else server.BUSINESS_LEASE
    if original == server.BUSINESS_LEASE:
        server._assert_testflight_lease(lease, STATE / sha)
    info = original.lstat()
    server.validate_metadata(info, directory=True)
    expected = {'token': lease['token'], 'started_at': lease['started_at'],
                'label': 'testflight-check', 'stage': str(STATE / sha)}
    if stat.S_IMODE(info.st_mode) != 0o700 or {p.name for p in original.iterdir()} != set(expected):
        raise ValueError('original retained lease inventory differs')
    identity = [info.st_dev, info.st_ino]
    contents = {}
    for name, value in expected.items():
        with os.fdopen(os.open(original / name, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
            meta = os.fstat(stream.fileno())
            server.validate_metadata(meta, private=True)
            raw = stream.read(4097)
            if raw != (value + '\n').encode():
                raise ValueError('original retained lease bytes differ')
            if name == 'token':
                identity.extend((meta.st_dev, meta.st_ino))
            contents[name] = raw
    if identity != lease['identity']:
        raise ValueError('original retained lease inode differs')
    durable.mkdir(mode=0o700, exist_ok=True)
    server.secure_path(durable, directory=True)
    if any(path.name not in expected for path in durable.iterdir()):
        raise ValueError('unknown lease archive')
    for name, raw in contents.items():
        if os.path.lexists(durable / name):
            if server._read_private(durable / name) != raw:
                raise ValueError('partial archive differs')
        else:
            server._write_private(durable / name, raw)
    server._sync_directory(durable)
    server._sync_directory(op)
    if release and original == server.BUSINESS_LEASE:
        server._assert_testflight_lease(lease, STATE / sha)
        if os.path.lexists(retired):
            raise ValueError('retired lease appeared')
        move_noreplace(original, retired)
        server._sync_business_lease_parent()
    validate_archive(server, op, sha)


def finish(server, bootstrap, sha, value, *, recover=False):
    op = operation()
    server.secure_path(op, directory=True)
    names = {path.name for path in op.iterdir()}
    if (not {'intent.json', 'lease.json', 'claimed.json'} <= names
            or names - {'intent.json', 'lease.json', 'claimed.json', 'verified.json', 'completed.json', 'released-lease'}
            or ('released-lease' in names and 'verified.json' not in names)
            or ('completed.json' in names and 'released-lease' not in names)):
        raise ValueError('unknown retained transaction inventory')
    intent = read(server, op / 'intent.json')
    validate_request(intent['request'], sha, fresh=False)
    saved = read(server, op / 'claimed.json')
    if saved != {'sha': sha, 'state': 'CLAIMED', 'claim_id': value.get('claim_id')}:
        raise ValueError('claim identity differs')
    verified, terminal = op / 'verified.json', op / 'completed.json'
    validate_request(value, sha, after=True, fresh=not os.path.lexists(verified))
    if os.path.lexists(verified):
        if read(server, verified) != value:
            raise ValueError('different finish proof forbidden')
    else:
        if recover:
            raise ValueError('recovery requires previously persisted verified proof')
        lease = read(server, op / 'lease.json')
        server._assert_testflight_lease(lease, STATE / sha)
        prove_backend(server, bootstrap, sha, lease)
        if prove_original(server, bootstrap) != intent['original']:
            raise ValueError('original release evidence changed')
        write(server, verified, value)
    had_terminal = os.path.lexists(terminal)
    lease = read(server, op / 'lease.json')
    if not had_terminal:
        # UPLOADED proves vendor completion and durable lease evidence, not that
        # the process returned. Persist it BEFORE making the business lease free.
        # A crash before rename still blocks ordinary deploy.sh by the same lease;
        # after rename every global history observer already sees complete proof.
        archive_lease(server, sha, lease, release=False)
        write(server, terminal, {'sha': sha, 'state': 'UPLOADED',
                                'intent_sha256': digest(intent), 'verified_sha256': digest(value)})
    validate_history(server, op)
    retired = server.BUSINESS_LEASE.with_name(server.BUSINESS_LEASE.name + '.retained-' + BUILD_ID)
    if os.path.lexists(retired):
        archive_lease(server, sha, lease)
    elif not had_terminal:
        archive_lease(server, sha, lease)
    elif os.path.lexists(server.BUSINESS_LEASE):
        info = server.BUSINESS_LEASE.lstat()
        if [info.st_dev, info.st_ino] == lease['identity'][:2]:
            archive_lease(server, sha, lease)
        # A later publisher's lease is never released by completed replay. The
        # durable original archive remains sufficient across /run cleanup/reboot.
    return {'sha': sha, 'state': 'UPLOADED', 'build_id': BUILD_ID,
            'submission_id': value['after']['submissions'][0]['id']}


def validate_history(server, op):
    server.secure_path(op, directory=True)
    if (op.name != BUILD_ID or stat.S_IMODE(op.stat().st_mode) != 0o700
            or {p.name for p in op.iterdir()} != {'intent.json', 'lease.json', 'claimed.json',
                                               'verified.json', 'completed.json', 'released-lease'}):
        raise ValueError('unfinished retained artifact requires operator recovery')
    intent, verified = read(server, op / 'intent.json'), read(server, op / 'verified.json')
    if not isinstance(intent, dict) or set(intent) != {'request', 'original'}:
        raise ValueError('invalid retained intent')
    original = intent['original']
    if (not isinstance(original, dict) or set(original) != {'retirement', 'closure', 'build_claim'}
            or any(not isinstance(v, str) or re.fullmatch(r'[0-9a-f]{64}', v) is None for v in original.values())):
        raise ValueError('invalid original release proof')
    sha = intent['request']['sha']
    validate_request(intent['request'], sha, fresh=False)
    validate_request(verified, sha, after=True, fresh=False)
    if (read(server, op / 'claimed.json') != {'sha': sha, 'state': 'CLAIMED', 'claim_id': verified['claim_id']}
            or read(server, op / 'completed.json') != {'sha': sha, 'state': 'UPLOADED',
                'intent_sha256': digest(intent), 'verified_sha256': digest(verified)}):
        raise ValueError('retained completion differs')
    validate_archive(server, op, sha)


@contextmanager
def locks(server, bootstrap, sha, *, create):
    paths = [STATE / 'launcher.lock', STATE / OLD_SHA / 'build.lock', STATE / sha / 'build.lock']
    fds = []
    try:
        for index, path in enumerate(paths):
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT if create and index == 2 else 0), 0o600)
            fds.append(fd)
            server.secure_path(path, private=True)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            bootstrap._assert_original_lock(path, fd)
        yield
        for path, fd in zip(paths, fds):
            bootstrap._assert_original_lock(path, fd)
    finally:
        for fd in reversed(fds):
            os.close(fd)


def collect_before(source, github_token, expo_token):
    c = CONTRACT
    for path, expected in c.HASHES.items():
        if hashlib.sha256(git(source, 'show', OLD_SHA + ':' + path)).hexdigest() != expected:
            raise ValueError('original canonical source differs')
    headers = {'Authorization': 'Bearer ' + github_token, 'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28', 'Cache-Control': 'no-cache'}
    url = c.BASE + '/actions/runs/' + str(c.RUN['id'])
    run = parsed(c.read(url, headers))
    jobs = parsed(c.read(url + '/attempts/1/jobs?per_page=100', headers))
    log = c.read(c.BASE + '/actions/jobs/' + str(c.JOB_IDS['ios-build']) + '/logs', headers, log=True)
    build = collect_build(expo_token)
    proof = c.validate(run, jobs, build, log)
    validate_before(proof)
    if parsed(c.read(url, headers)) != run:
        raise ValueError('original workflow changed')
    return proof


def collect_build(expo_token):
    raw = CONTRACT.read(CONTRACT.EXPO, {'Authorization': 'Bearer ' + expo_token, 'Content-Type': 'application/json'},
                        payload=json.dumps({'query': QUERY, 'variables': {'buildId': BUILD_ID}}).encode())
    value = parsed(raw)
    if not isinstance(value, dict) or value.get('errors') or not value.get('data'):
        raise ValueError('vendor evidence unavailable')
    return value['data']['builds']['byId']


def runner(args):
    source = Path('/opt/reva-release/source')
    if Path(__file__).absolute() != source / 'scripts/trusted_retained_testflight.py':
        raise ValueError('fixed runner source required')
    initialize(source, args.sha)
    gate = load(source, args.sha, 'trusted_release_gate.py')
    gate.verify_release(args.sha, args.sha)
    github, expo = os.environ.get('GH_TOKEN', ''), os.environ.get('EXPO_TOKEN', '')
    if not github or not expo:
        raise ValueError('vendor authorization absent')
    def rpc(action, value):
        command = ['/usr/bin/ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
                   '-o', 'IdentityAgent=none', '-o', 'StrictHostKeyChecking=yes',
                   '-o', 'UserKnownHostsFile=' + args.known_hosts, '-o', 'GlobalKnownHostsFile=/dev/null',
                   '-o', 'ClearAllForwardings=yes', '-o', 'ConnectTimeout=15', '-i', args.key,
                   'root@39.98.206.178', action + ' ' + args.sha]
        return parsed(subprocess.run(command, input=json.dumps(value).encode(), env=ENV,
                                     capture_output=True, check=True, timeout=600).stdout)
    before = collect_before(source, github, expo)
    response = rpc('claim-retained-testflight', {'sha': args.sha, 'profile': PROFILE,
                    'observed_at': int(time.time()), 'before': before})
    if (not isinstance(response, dict) or set(response) != {'sha', 'state', 'claim_id'}
            or response['sha'] != args.sha or response['state'] != 'CLAIMED'
            or not isinstance(response['claim_id'], str) or re.fullmatch(r'[0-9a-f]{64}', response['claim_id']) is None):
        raise ValueError('claim response unknown; never repeat submit')
    print('Retained 274 upload claim consumed; no build will be created.', flush=True)
    # Check immediately before the ONLY vendor write. Any failure retains the claim.
    gate.verify_release(args.sha, args.sha)
    collect_before(source, github, expo)
    node = Path(args.node)
    if not node.is_absolute() or node.name != 'node':
        raise ValueError('fixed node toolchain required')
    env = {'PATH': str(node.parent) + ':/usr/bin:/bin', 'HOME': '/root', 'EXPO_TOKEN': expo, 'CI': '1'}
    subprocess.run([str(node), str(source / 'scripts/release-tools/node_modules/eas-cli/bin/run'),
                    'submit', '-p', 'ios', '--id', BUILD_ID, '--profile', 'production', '--non-interactive', '--wait'],
                   cwd=source / 'mobile', env=env, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=4200)
    after = collect_build(expo)
    validate_after(after)
    value = {'sha': args.sha, 'profile': PROFILE, 'observed_at': int(time.time()),
             'claim_id': response['claim_id'], 'after': after}
    result = rpc('finish-retained-testflight', value)
    if result != {'sha': args.sha, 'state': 'UPLOADED', 'build_id': BUILD_ID,
                  'submission_id': after['submissions'][0]['id']}:
        raise ValueError('upload finish unknown; preserve original claim')
    print(json.dumps(result, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--action', choices=('claim', 'finish', 'recover'))
    parser.add_argument('--runner', action='store_true')
    parser.add_argument('--key')
    parser.add_argument('--known-hosts')
    parser.add_argument('--node')
    args = parser.parse_args()
    try:
        if (not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode
                or os.geteuid() != 0 or re.fullmatch(r'[0-9a-f]{40}', args.sha) is None or args.sha == OLD_SHA):
            raise ValueError('isolated new canonical publisher required')
        os.umask(0o077)
        if args.runner:
            if args.action is not None or not all((args.key, args.known_hosts, args.node)):
                raise ValueError('invalid runner arguments')
            runner(args)
            return 0
        source = STATE / 'bootstrap' / args.sha / 'source'
        if args.action is None or any((args.key, args.known_hosts, args.node)) or Path(__file__).absolute() != source / 'scripts/trusted_retained_testflight.py':
            raise ValueError('canonical server staging required')
        initialize(source, args.sha)
        bootstrap = load(source, args.sha, 'bootstrap_trusted_release.py')
        checked, server = bootstrap.reviewed_source(args.sha)
        if checked != source:
            raise ValueError('canonical source mismatch')
        value = parsed(sys.stdin.buffer.read(1_000_001))
        with locks(server, bootstrap, args.sha, create=args.action == 'claim'):
            if args.action != 'recover':
                policy = server.validate_policy(read(server, server.POLICY), now=time.time())
                if policy['sha'] != args.sha:
                    raise ValueError('authorization differs')
                server.validate_loopback(policy)
            if args.action == 'claim':
                result = claim(server, bootstrap, policy, value)
            else:
                result = finish(server, bootstrap, args.sha, value, recover=args.action == 'recover')
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print('Retained TestFlight blocked; preserve evidence and never repeat vendor submission.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
