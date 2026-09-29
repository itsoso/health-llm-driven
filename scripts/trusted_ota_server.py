"""Canonical root-only OTA transaction. Never publishes or retries vendor writes.

claim persists one opportunity and holds the business lease. finish independently
checks public Expo bytes then atomically archives that exact lease. recover is a
separate local operator, valid after authorization expiry, for the SAME receipt.
"""
import argparse
from contextlib import contextmanager
import fcntl
from email.parser import BytesParser
from email import policy as email_policy
import importlib.util
import json
import os
import re
import ssl
import hashlib
import stat
import sys
import urllib.request
from pathlib import Path

STATE = Path('/var/lib/reva-release')


def load(source, sha, filename):
    # The bootstrap itself is root controlled and byte-checked before importing.
    import subprocess
    file = source / 'scripts' / filename
    for path in [*reversed(file.parents), file]:
        info = path.lstat()
        kind = stat.S_ISREG if path == file else stat.S_ISDIR
        if info.st_uid != 0 or info.st_mode & 0o022 or not kind(info.st_mode):
            raise ValueError('unsafe canonical code')
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_SYSTEM': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1'}
    expected = subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-C', str(source), 'show', sha + ':scripts/' + filename], env=env, capture_output=True, check=True, timeout=30).stdout
    if file.read_bytes() != expected or (source / 'scripts/__pycache__').exists():
        raise ValueError('canonical code changed')
    spec = importlib.util.spec_from_file_location(filename.removesuffix('.py'), file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write(server, path, value):
    server._write_private(path, json.dumps(value, sort_keys=True).encode())


def read(server, path):
    return server._json(server._read_private(path))


def validate_input(contract, sha, value):
    if (not isinstance(value, dict) or set(value) != {'sha', 'project', 'runtime', 'platform', 'channel', 'artifact', 'branch_id', 'branch_name'}
            or value['sha'] != sha or value['project'] != contract.PROJECT or value['runtime'] != contract.RUNTIME
            or value['platform'] != 'ios' or value['channel'] != 'production'
            or value['branch_name'] != 'production' or not isinstance(value['branch_id'], str)
            or re.fullmatch(contract.UUID, value['branch_id']) is None):
        raise ValueError('OTA claim binding differs')
    contract.validate_proof(value['artifact'])


def manifest(contract):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError('manifest redirect forbidden')
    defaults = ssl.get_default_verify_paths()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    cafile = defaults.openssl_cafile if os.path.isfile(defaults.openssl_cafile) else None
    capath = defaults.openssl_capath if os.path.isdir(defaults.openssl_capath) else None
    if not cafile and not capath:
        raise ValueError('system TLS trust unavailable')
    context.load_verify_locations(cafile=cafile, capath=capath)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(context=context))
    request = urllib.request.Request('https://u.expo.dev/' + contract.PROJECT, headers={
        'expo-platform': 'ios', 'expo-runtime-version': contract.RUNTIME, 'expo-channel-name': 'production',
        'expo-protocol-version': '1', 'Accept': 'multipart/mixed', 'Cache-Control': 'no-cache',
    })
    with opener.open(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError('manifest unavailable')
        raw = response.read(2000001)
        return parse_manifest(contract, response.headers.get('Content-Type', ''), raw)


def parse_manifest(contract, content_type, raw):
    if len(raw) > 2000000 or "\r" in content_type or "\n" in content_type:
        raise ValueError('invalid manifest envelope')
    message = BytesParser(policy=email_policy.default).parsebytes(
        ('Content-Type: ' + content_type + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + raw)
    if message.get_content_type() != 'multipart/mixed' or not message.is_multipart() or message.defects:
        raise ValueError('invalid multipart manifest')
    parts = list(message.iter_parts())
    manifests = [part for part in parts if part.get_param('name', header='content-disposition') == 'manifest']
    if len(manifests) != 1 or len(parts) > 3 or any(part.defects or part.is_multipart() for part in parts):
        raise ValueError('ambiguous manifest parts')
    part = manifests[0]
    if part.get_content_type() not in ('application/json', 'application/expo+json'):
        raise ValueError('unexpected manifest media type')
    return json.loads(part.get_payload(decode=True), object_pairs_hook=contract.unique)


def archive_lease(server, operation, lease):
    """Copy durable evidence, then rename the original within /run/lock."""
    durable = operation / 'released-lease'
    retired = server.BUSINESS_LEASE.with_name(server.BUSINESS_LEASE.name + '.ota-' + operation.name)
    if os.path.lexists(retired):
        original = retired
    else:
        original = server.BUSINESS_LEASE
        server._assert_testflight_lease(lease, STATE / operation.name)
    # The fixed /run/lock sticky parent is separately checked by the shared protocol.
    server._testflight_lease_parent()
    info = original.lstat()
    server.validate_metadata(info, directory=True)
    identity = [info.st_dev, info.st_ino]
    expected = {'token': lease['token'], 'label': 'testflight-check',
                'stage': str(STATE / operation.name), 'started_at': lease['started_at']}
    if stat.S_IMODE(info.st_mode) != 0o700 or {p.name for p in original.iterdir()} != set(expected):
        raise ValueError('original OTA lease inventory changed')
    contents = {}
    for name, value in expected.items():
        path = original / name
        # Parent is the fixed root-owned sticky /run/lock exception, not a code path.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            metadata = os.fstat(stream.fileno())
            server.validate_metadata(metadata, private=True)
            contents[name] = stream.read(4097)
            if contents[name] != (value + '\n').encode():
                raise ValueError('original OTA lease content changed')
            if name == 'token':
                identity.extend((metadata.st_dev, metadata.st_ino))
    if identity != lease['identity']:
        raise ValueError('original OTA lease inode changed')
    durable.mkdir(mode=0o700, exist_ok=True)
    server.secure_path(durable, directory=True)
    if any(p.name not in expected for p in durable.iterdir()):
        raise ValueError('unknown durable lease evidence')
    for name, raw in contents.items():
        path = durable / name
        if os.path.lexists(path):
            if server._read_private(path) != raw:
                raise ValueError('durable lease evidence differs')
        else:
            server._write_private(path, raw)
    server._sync_directory(durable)
    server._sync_directory(operation)
    if original == server.BUSINESS_LEASE:
        server._assert_testflight_lease(lease, STATE / operation.name)
        if os.path.lexists(retired):
            raise ValueError('retired lease already exists')
        os.rename(original, retired)
        server._sync_directory(original.parent)
    server.validate_ota_archive(operation)


def claim(server, contract, policy, value):
    sha = policy['sha']
    validate_input(contract, sha, value)
    server.assert_ota_history()
    server._assert_deployment_window(policy)
    server.validate_loopback(policy)
    if server.read_status(sha, STATE / sha)['state'] != 'SUCCEEDED':
        raise ValueError('exact deployed backend required')
    root = STATE / 'ota'
    root.mkdir(mode=0o700, exist_ok=True)
    server.secure_path(root, directory=True)
    operation = root / sha
    if os.path.lexists(operation) or os.path.lexists(server.BUSINESS_LEASE):
        raise ValueError('OTA already claimed or business lease exists')
    # Consumption precedes lease initialization. Any partial state blocks, never retries.
    operation.mkdir(mode=0o700)
    server._sync_directory(root)
    write(server, operation / 'intent.json', value)
    lease = server._acquire_testflight_lease(STATE / sha)
    write(server, operation / 'lease.json', lease)
    proof = server.testflight_backend_proof(policy, lease=lease)
    if proof != {'sha': sha, 'production_sha': sha, 'state': 'COMPATIBLE'}:
        raise ValueError('production revision differs')
    server._assert_testflight_lease(lease, STATE / sha)
    write(server, operation / 'claimed.json', {'sha': sha, 'state': 'CLAIMED'})
    return {'sha': sha, 'state': 'CLAIMED'}


def finish(server, contract, sha, value):
    if (not isinstance(value, dict) or set(value) != {'sha', 'group_id', 'update_id'} or value['sha'] != sha
            or any(not isinstance(value[k], str) or re.fullmatch(contract.UUID, value[k]) is None for k in ('group_id', 'update_id'))):
        raise ValueError('invalid publication receipt')
    operation = STATE / 'ota' / sha
    server.secure_path(operation, directory=True)
    intent = read(server, operation / 'intent.json')
    validate_input(contract, sha, intent)
    if read(server, operation / 'claimed.json') != {'sha': sha, 'state': 'CLAIMED'}:
        raise ValueError('complete original claim required')
    receipt = operation / 'verified.json'
    terminal = operation / 'completed.json'
    if os.path.lexists(receipt):
        if read(server, receipt) != value:
            raise ValueError('different finish receipt forbidden')
    else:
        server._assert_testflight_lease(read(server, operation / 'lease.json'), STATE / sha)
        contract.validate_manifest(manifest(contract), value['update_id'], intent['artifact'])
        write(server, receipt, value)
    if not os.path.lexists(terminal):
        archive_lease(server, operation, read(server, operation / 'lease.json'))
    else:
        server.validate_ota_archive(operation)
    result = {'sha': sha, 'state': 'SUCCEEDED'}
    completed = {**result, 'intent_sha256': hashlib.sha256(server._read_private(operation / 'intent.json')).hexdigest(),
                 'receipt_sha256': hashlib.sha256(server._read_private(receipt)).hexdigest()}
    if os.path.lexists(terminal):
        if read(server, terminal) != completed:
            raise ValueError('invalid OTA terminal')
    else:
        write(server, terminal, completed)
    return result


@contextmanager
def transaction_locks(server, bootstrap, sha, *, create):
    """All OTA transitions serialize with rotation, backend, and native claims."""
    launcher = STATE / 'launcher.lock'
    build = STATE / sha / 'build.lock'
    server.secure_path(launcher, private=True)
    fd = os.open(launcher, os.O_RDWR | os.O_NOFOLLOW)
    build_fd = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build_fd = os.open(build, os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT if create else 0), 0o600)
        server.secure_path(build, private=True)
        fcntl.flock(build_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        bootstrap._assert_original_lock(launcher, fd)
        bootstrap._assert_original_lock(build, build_fd)
        yield
        bootstrap._assert_original_lock(launcher, fd)
        bootstrap._assert_original_lock(build, build_fd)
    finally:
        if build_fd is not None:
            os.close(build_fd)
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--action', choices=('claim', 'finish', 'recover'), required=True)
    args = parser.parse_args()
    try:
        if not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode or os.geteuid() != 0 or re.fullmatch(r'[0-9a-f]{40}', args.sha) is None:
            raise ValueError('isolated canonical root invocation required')
        os.umask(0o077)
        source = STATE / 'bootstrap' / args.sha / 'source'
        if Path(__file__).absolute() != source / 'scripts/trusted_ota_server.py':
            raise ValueError('canonical staging required')
        bootstrap = load(source, args.sha, 'bootstrap_trusted_release.py')
        checked_source, server = bootstrap.reviewed_source(args.sha)
        if source != checked_source:
            raise ValueError('wrong source')
        contract = load(source, args.sha, 'trusted_ota.py')
        value = contract.read_json(sys.stdin.buffer)
        with transaction_locks(server, bootstrap, args.sha, create=args.action == 'claim'):
            if args.action != 'recover':
                policy = server.validate_policy(read(server, server.POLICY), now=__import__('time').time())
                if policy['sha'] != args.sha:
                    raise ValueError('authorization changed')
            if args.action == 'claim':
                result = claim(server, contract, policy, value)
            else:
                result = finish(server, contract, args.sha, value)
    except Exception:
        print('OTA transaction failed; evidence retained; never retry publication', file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
