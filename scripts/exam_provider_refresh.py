"""Fixed-incident credential receipt; never release authorization or CI bypass.

The client invokes the byte-pinned existing local GitHub App provider. Only its
SSH transport changes. The provider itself proves App, installation, repository
and exact minted scopes; the receiver additionally verifies live token reads.
"""
import argparse
import base64
import tempfile
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
import types
import urllib.request

APP = 5376682
INSTALLATION = 172918270
REPO = 'itsoso/health-llm-driven'
PERMISSIONS = {'actions': 'read', 'contents': 'read', 'metadata': 'read'}
PROVIDER_HASH = '3d3d5c7fed2c28bd106543a6c2c7fa58b5e3feb7620f03c7605d2d0d1b6cb399'
PUBLIC_KEY_HASH = '0d65ace3355fd51fe1f8f798c6f493e7f095f438c3c4249616f07edec79ecc04'
FAILED = 'a8cd1e7635eb697c0f0bc528382c98b3602893c3'
OLD = '83876750fcbb404255b7439482688fee82a490d4'
ROOT = Path('/var/lib/reva-release')
CREDENTIAL = Path('/etc/reva-github-api/credential.json')
PROVIDER_STATE = Path('/var/lib/reva-github-api')


class RefreshBlocked(RuntimeError):
    pass


def validate(value):
    if (not isinstance(value, dict) or set(value) != {'repository', 'token', 'expires_at', 'app_id',
            'installation_id', 'permissions', 'provider_sha256'} or value['repository'] != REPO
            or value['app_id'] != APP or value['installation_id'] != INSTALLATION
            or value['permissions'] != PERMISSIONS or value['provider_sha256'] != PROVIDER_HASH
            or type(value['expires_at']) is not int or not time.time() + 300 < value['expires_at'] < time.time() + 3700
            or not isinstance(value['token'], str) or re.fullmatch(r'ghs_[A-Za-z0-9_.-]{20,4096}', value['token']) is None):
        raise RefreshBlocked('exact provider and scoped installation credential required')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RefreshBlocked('redirect refused')


def api(path, token):
    request = urllib.request.Request('https://api.github.com' + path, headers={
        'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'Reva-incident-provider'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=25) as response:
        raw = response.read(2000001)
    if len(raw) > 2000000:
        raise RefreshBlocked('oversized API response')
    return json.loads(raw)


def verify_token(value, request=api):
    validate(value)
    inventory = request('/installation/repositories', value['token'])
    if (inventory.get('total_count') != 1
            or [item.get('full_name') for item in inventory.get('repositories', [])] != [REPO]):
        raise RefreshBlocked('live repository inventory differs')
    repo = request('/repos/' + REPO, value['token'])
    permissions = repo.get('permissions', {})
    if (repo.get('full_name') != REPO
            or any(permissions.get(key, False) is not False for key in ('push', 'admin', 'maintain', 'triage'))):
        raise RefreshBlocked('live repository permission projection differs')
    content = request('/repos/' + REPO + '/contents/AGENTS.md?ref=main', value['token'])
    if content.get('type') != 'file' or content.get('path') != 'AGENTS.md':
        raise RefreshBlocked('live Contents read authority unavailable')
    runs = request('/repos/' + REPO + '/actions/runs?per_page=1', value['token'])
    if not isinstance(runs.get('workflow_runs'), list):
        raise RefreshBlocked('live Actions read authority unavailable')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def signed_bytes(value, sha):
    return json.dumps({'receiver_sha': sha, 'credential': value}, sort_keys=True, separators=(',', ':')).encode()


def verify_envelope(envelope, sha, public_key):
    if (not isinstance(envelope, dict) or set(envelope) != {'receiver_sha', 'credential', 'signature'}
            or envelope['receiver_sha'] != sha
            or hashlib.sha256(public_key.read_bytes()).hexdigest() != PUBLIC_KEY_HASH):
        raise RefreshBlocked('signed provider envelope binding differs')
    validate(envelope['credential'])
    try:
        signature = base64.b64decode(envelope['signature'], validate=True)
    except (ValueError, TypeError):
        raise RefreshBlocked('provider signature malformed') from None
    if len(signature) not in (256, 384, 512):
        raise RefreshBlocked('provider signature size differs')
    with tempfile.TemporaryFile() as stream:
        stream.write(signature)
        stream.flush()
        stream.seek(0)
        subprocess.run(['/usr/bin/openssl', 'dgst', '-sha256', '-verify', str(public_key),
                        '-signature', '/dev/fd/' + str(stream.fileno())],
                       input=signed_bytes(envelope['credential'], sha), pass_fds=(stream.fileno(),),
                       env={'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C'},
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=15)
    return envelope['credential']


def receive(sha):
    if (os.geteuid() != 0 or sys.platform != 'linux' or sys.executable != '/usr/bin/python3.12'
            or not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode)
            or 'SSH_ORIGINAL_COMMAND' in os.environ or re.fullmatch('[a-f0-9]{40}', sha or '') is None
            or sha in (FAILED, OLD)):
        raise RefreshBlocked('isolated canonical root receiver required')
    source = ROOT / 'bootstrap' / sha / 'source'
    entry = source / 'scripts/exam_provider_refresh.py'
    if Path(__file__).absolute() != entry:
        raise RefreshBlocked('canonical receiver required')
    for path in [*reversed(entry.parents), entry, entry.with_name('bootstrap_trusted_release.py')]:
        info = path.lstat()
        if (info.st_uid or info.st_gid or info.st_mode & 0o022
                or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))
                or stat.S_ISREG(info.st_mode) and info.st_nlink != 1):
            raise RefreshBlocked('unsafe canonical receiver metadata')
    if os.path.lexists(entry.parent / '__pycache__'):
        raise RefreshBlocked('cached receiver code forbidden')
    os.umask(0o077)
    b = load(entry.with_name('bootstrap_trusted_release.py'), 'exam_provider_bootstrap')
    if b.canonical_source(sha) != source:
        raise RefreshBlocked('canonical source differs')
    # No CI call here: this only restores the existing CI reader credential.
    # All later recovery operations still execute their independent exact-SHA CI gate.
    h = load(entry.with_name('exam_attempts_release.py'), 'exam_provider_files')
    service = load(entry.with_name('recover_contained_services.py'), 'exam_provider_services')
    pmod = load(entry.with_name('contained_recovery_proof.py'), 'exam_provider_proof')
    server = load(entry.with_name('trusted_release_server.py'), 'exam_provider_server')
    locks, build_fd = [], None
    try:
        launcher = ROOT / 'launcher.lock'
        b.secure(launcher, private=True)
        fd = os.open(launcher, os.O_RDWR | os.O_NOFOLLOW)
        locks.append(fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build_fd = b._acquire_existing_build_lock(FAILED)
        lock = PROVIDER_STATE / 'provider-refresh.lock'
        b.secure(lock, private=True)
        provider_fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
        locks.append(provider_fd)
        fcntl.flock(provider_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Fixed root-owned lease, never caller-selected or removed.
        token_raw = h.protected_read(h.LEASE / 'token', private=True)
        if re.fullmatch(rb'[A-Za-z0-9._:-]{1,255}\n', token_raw) is None:
            raise RefreshBlocked('original lease token malformed')
        proof = pmod.RecoveryProof(source, b, server, FAILED, OLD, token_raw[:-1].decode())
        proof._original_lease = proof._lease_snapshot()
        failed_source = b.canonical_source(FAILED)
        workspace = proof._workspace(failed_source)
        def check():
            b._assert_original_lock(launcher, fd)
            b._assert_original_lock(lock, provider_fd)
            service._check_original_build_lock(b, FAILED, build_fd)
            b._recovery_process_proof()
            proof._assert_original_lease()
            if proof._workspace(failed_source) != workspace:
                raise RefreshBlocked('original failed workspace changed')
            b._recovery_production_proof(FAILED, source)
            proof.stopped()
        check()
        raw = sys.stdin.buffer.read(8193)
        if not 0 < len(raw) <= 8192:
            raise RefreshBlocked('credential payload bound exceeded')
        key = entry.with_name('exam-provider-app-public.pem')
        b.secure(key)
        value = verify_envelope(json.loads(raw), sha, key)
        verify_token(value)
        for parent in reversed(CREDENTIAL.parents):
            b.secure(parent)
        old = h.protected_read(CREDENTIAL, private=True)
        old_value = json.loads(old)
        if (set(old_value) != {'repository', 'token', 'expires_at'} or old_value['repository'] != REPO
                or not isinstance(old_value['token'], str) or not old_value['token'].startswith('ghs_')):
            raise RefreshBlocked('existing provider credential differs')
        identity = b._recovery_file_identity(CREDENTIAL)
        replacement = json.dumps({key: value[key] for key in ('repository', 'token', 'expires_at')}, sort_keys=True).encode()
        parent = PROVIDER_STATE / 'refresh'
        b.secure(parent)
        audit = parent / ('exam-' + sha)
        if os.path.lexists(audit):
            raise RefreshBlocked('refresh attempt already consumed; inspect original audit')
        check()
        audit.mkdir(mode=0o700)
        h.sync_directory(parent)
        intent = {'state': 'REFRESH_INTENT', 'publisher_sha': sha, 'failed_sha': FAILED,
                  'repository': REPO, 'app_id': APP, 'installation_id': INSTALLATION,
                  'permissions': PERMISSIONS, 'provider_sha256': PROVIDER_HASH,
                  'before_sha256': hashlib.sha256(old).hexdigest(),
                  'after_sha256': hashlib.sha256(replacement).hexdigest(),
                  'expires_at': value['expires_at'], 'lease': proof._original_lease,
                  'workspace': workspace}
        h.write_once(audit / 'intent.json', intent)
        temporary = CREDENTIAL.with_name('credential.exam-' + sha + '.tmp')
        out = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(out, 'wb') as stream:
            stream.write(replacement)
            stream.flush()
            os.fsync(stream.fileno())
        check()
        if b._recovery_file_identity(CREDENTIAL) != identity or h.protected_read(CREDENTIAL, private=True) != old:
            raise RefreshBlocked('credential changed before atomic replace')
        os.replace(temporary, CREDENTIAL)
        h.sync_directory(CREDENTIAL.parent)
        check()
        if h.protected_read(CREDENTIAL, private=True) != replacement:
            raise RefreshBlocked('credential readback differs')
        h.write_once(audit / 'completed.json', dict(intent, state='CREDENTIAL_REFRESHED'))
        print(json.dumps({'state': 'CREDENTIAL_REFRESHED', 'expires_at': value['expires_at'], 'audit': str(audit)}))
    finally:
        if build_fd is not None:
            os.close(build_fd)
        for fd in reversed(locks):
            os.close(fd)


def client(sha):
    if re.fullmatch('[a-f0-9]{40}', sha or '') is None:
        raise RefreshBlocked('exact canonical receiver SHA required')
    path = Path.home() / '.config/reva-release/refresh-github.py'
    info = path.lstat()
    raw = path.read_bytes()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022
            or info.st_nlink != 1 or hashlib.sha256(raw).hexdigest() != PROVIDER_HASH):
        raise RefreshBlocked('existing original provider bytes or ownership differ')
    provider = types.ModuleType('existing_exam_provider')
    provider.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), provider.__dict__)
    original_api, original_run = provider.api, subprocess.run
    minted = {}
    def checked_api(route, token, body=None):
        if (route == '/app/installations/172918270/access_tokens'
                and body != {'repositories': ['health-llm-driven'], 'permissions': PERMISSIONS}):
            raise RefreshBlocked('provider issuance scope changed')
        result = original_api(route, token, body)
        if route == '/app/installations/172918270/access_tokens':
            minted.update(result)
        return result
    def transport(command, *args, **kwargs):
        if isinstance(command, list) and command[:2] == ['ssh', 'health-prod']:
            value = json.loads(kwargs['input'])
            if (value['token'] != minted.get('token') or minted.get('permissions') != PERMISSIONS
                    or [item['full_name'] for item in minted.get('repositories', [])] != [REPO]):
                raise RefreshBlocked('provider issuance receipt differs')
            value.update(app_id=APP, installation_id=INSTALLATION, permissions=PERMISSIONS,
                         provider_sha256=PROVIDER_HASH)
            validate(value)
            signature = original_run(['openssl', 'dgst', '-sha256', '-sign', str(provider.KEY)],
                input=signed_bytes(value, sha), capture_output=True, check=True).stdout
            kwargs['input'] = json.dumps({'receiver_sha': sha, 'credential': value,
                'signature': base64.b64encode(signature).decode()}).encode()
            remote = '/usr/bin/python3.12 -I -S -B /var/lib/reva-release/bootstrap/' + sha + '/source/scripts/exam_provider_refresh.py receive --sha ' + sha
            command = ['ssh', '-o', 'UserKnownHostsFile=' + str(Path.home() / '.ssh/known_hosts'),
                       '-o', 'StrictHostKeyChecking=yes', 'root@39.98.206.178', remote]
        return original_run(command, *args, **kwargs)
    provider.api = checked_api
    provider.subprocess.run = transport
    try:
        provider.main()
    finally:
        provider.subprocess.run = original_run


def main():
    try:
        parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
        parser.add_argument('mode', choices=('client', 'receive'))
        parser.add_argument('--sha', required=True)
        args = parser.parse_args()
        (client if args.mode == 'client' else receive)(args.sha)
        return 0
    except BaseException:
        print('EXAM_PROVIDER_REFRESH_BLOCKED: preserve original lease and protected provider audit', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
