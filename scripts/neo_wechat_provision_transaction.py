"""Internal one-shot provisioning writer; no CLI, owner-input adapter or dispatcher.

The canonical caller must establish trusted code, exact release admission, locks,
an immutable dormant receipt, and directory path lineage before invoking this
function. ``guard`` must recheck those facts on every call. Descriptor identities
and caller-supplied hashes alone do not establish that authority. ``audit_root_fd``
must refer to a SEPARATE lifecycle root, never the immutable dormant-install audit.
No current production entry calls this module or accepts this new audit schema.

Real credentials must come from the separately approved owner-operated surface.
Tests override root identity solely for synthetic temporary directories. Inputs,
bundle bytes and exception contexts must never be logged by callers. Python does
not guarantee memory zeroization. No failure cleans up, retries, or resumes; an
existing provision-v1 namespace blocks even an alternate operation identifier.
Completion-file presence alone is not a success receipt: its fsync or the final
guard can fail after bytes become visible. A future consumer must preserve the
caller's original lease and apply a separately reviewed reconciliation protocol;
this module's on-disk records never authorize activation by themselves.
"""
import base64
import hashlib
import json
import os
import re
import stat

from scripts.neo_wechat_provisioning import _Bundle, validate_config


NAMESPACE = 'provision-v1'
# Write config last. The writer never starts either systemd unit.
FILENAMES = ('encryption_key', 'admin_password_hash', 'slack_webhook', 'config.json')


class TransactionError(RuntimeError):
    """Only fixed, secret-free failure states escape this API."""


def _require(value):
    if not value:
        raise ValueError('invalid transaction evidence')


def _identity(info):
    return (info.st_dev, info.st_ino)


def _directory(fd, identity, uid, gid, mode):
    _require(type(fd) is int and fd >= 0)
    _require(type(identity) is tuple and len(identity) == 2
             and all(type(item) is int and item >= 0 for item in identity))
    info = os.fstat(fd)
    _require(stat.S_ISDIR(info.st_mode) and _identity(info) == identity
             and info.st_uid == uid and info.st_gid == gid
             and stat.S_IMODE(info.st_mode) == mode)


def _metadata(info):
    return {key: getattr(info, 'st_' + key) for key in
            ('dev', 'ino', 'uid', 'gid', 'mode', 'nlink', 'size', 'mtime_ns', 'ctime_ns')}


def _snapshot(bundle):
    _require(type(bundle) is _Bundle)
    _require(set(bundle.filenames) == set(FILENAMES) and len(bundle.filenames) == 4)
    payload = {name: bundle.content(name) for name in FILENAMES}
    _require(all(type(raw) is bytes and 0 < len(raw) <= 8192 for raw in payload.values()))
    config = validate_config(json.loads(payload['config.json']))
    canonical = (json.dumps(config, sort_keys=True, separators=(',', ':')) + '\n').encode()
    _require(payload['config.json'] == canonical)  # also rejects duplicate keys
    key_raw = payload['encryption_key']
    _require(len(key_raw) == 45 and key_raw.endswith(b'\n'))
    key = base64.b64decode(key_raw[:-1], validate=True)
    _require(len(key) == 32 and len(set(key)) >= 2 and base64.b64encode(key) == key_raw[:-1])
    password_hash = payload['admin_password_hash']
    _require(password_hash.endswith(b'\n'))
    parts = password_hash[:-1].split(b':')
    _require(len(parts) == 3 and parts[0] == b'scrypt-v1')
    for encoded, length in zip(parts[1:], (16, 32)):
        decoded = base64.b64decode(encoded, validate=True)
        _require(len(decoded) == length and base64.b64encode(decoded) == encoded)
    _require(re.fullmatch(rb'https://hooks\.slack\.com/services/T6TNPEFLY/[A-Za-z0-9]+/[A-Za-z0-9_-]+\n',
                         payload['slack_webhook']) is not None)
    return payload


def _new_directory(parent, name, uid, gid):
    os.mkdir(name, mode=0o700, dir_fd=parent)
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                 dir_fd=parent)
    try:
        os.fchown(fd, uid, gid)
        os.fchmod(fd, 0o700)
        _directory(fd, _identity(os.fstat(fd)), uid, gid, 0o700)
        os.fsync(fd)
        os.fsync(parent)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _new_file(parent, name, raw, uid, gid, mode):
    # O_EXCL protects all existing objects, including symlinks and hardlinks.
    fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600, dir_fd=parent)
    try:
        os.fchown(fd, uid, gid)
        position = 0
        while position < len(raw):
            written = os.write(fd, raw[position:])
            _require(written > 0)
            position += written
        os.fchmod(fd, mode)
        os.lseek(fd, 0, os.SEEK_SET)
        readback = bytearray()
        while len(readback) <= len(raw):
            chunk = os.read(fd, len(raw) + 1 - len(readback))
            if not chunk:
                break
            readback.extend(chunk)
        _require(readback == raw)
        info = os.fstat(fd)
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                 and info.st_uid == uid and info.st_gid == gid
                 and stat.S_IMODE(info.st_mode) == mode and info.st_size == len(raw))
        _require(_metadata(os.stat(name, dir_fd=parent, follow_symlinks=False)) == _metadata(info))
        os.fsync(fd)
        os.fsync(parent)
        return _metadata(info)
    finally:
        os.close(fd)


def provision(*, config_fd, audit_root_fd, config_identity, audit_identity, bundle,
              operation_id, dormant_receipt_sha256, publisher_sha, bridge_gid, guard,
              owner_uid=0, audit_gid=0):
    """Persist an already-prepared bundle to trusted directory descriptors once.

    Success means PROVISIONED_DORMANT only. It grants no activation, binding,
    OAuth, Slack or Health authority. Any exception after the namespace claim is
    an uncertain outcome; preserve all files and seek reviewed reconciliation.
    Missing/partial credentials are not replaced. Permission or identity errors
    are not repaired. The caller owns and must retain its original locks/lease.
    """
    claimed = False
    namespace_fd = operation_fd = None
    created = {}
    try:
        for value in (owner_uid, audit_gid, bridge_gid):
            _require(type(value) is int and 0 <= value < 2 ** 32)
        for value, length in ((operation_id, 32), (dormant_receipt_sha256, 64), (publisher_sha, 40)):
            _require(type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value))
        _require(callable(guard))
        payload = _snapshot(bundle)

        def check():
            guard()
            _directory(config_fd, config_identity, owner_uid, bridge_gid, 0o710)
            _directory(audit_root_fd, audit_identity, owner_uid, audit_gid, 0o700)
            _require(config_identity != audit_identity)
            _require(set(os.listdir(config_fd)) == set(created))
            for name, expected in created.items():
                _require(_metadata(os.stat(name, dir_fd=config_fd, follow_symlinks=False)) == expected)

        check()
        _require(NAMESPACE not in os.listdir(audit_root_fd))
        # Mark uncertain before the first syscall that can mutate host state.
        claimed = True
        namespace_fd = _new_directory(audit_root_fd, NAMESPACE, owner_uid, audit_gid)
        check()
        operation_fd = _new_directory(namespace_fd, operation_id, owner_uid, audit_gid)
        namespace_identity = _identity(os.fstat(namespace_fd))
        operation_identity = _identity(os.fstat(operation_fd))
        previous = dormant_receipt_sha256
        sequence = 0
        audit_files = {}

        def record(phase, *, filename=None, metadata=None):
            nonlocal previous, sequence
            check()
            _directory(namespace_fd, namespace_identity, owner_uid, audit_gid, 0o700)
            _directory(operation_fd, operation_identity, owner_uid, audit_gid, 0o700)
            _require(_identity(os.stat(NAMESPACE, dir_fd=audit_root_fd, follow_symlinks=False)) == namespace_identity)
            _require(set(os.listdir(namespace_fd)) == {operation_id})
            _require(_identity(os.stat(operation_id, dir_fd=namespace_fd, follow_symlinks=False)) == operation_identity)
            _require(set(os.listdir(operation_fd)) == set(audit_files))
            for name, expected in audit_files.items():
                _require(_metadata(os.stat(name, dir_fd=operation_fd, follow_symlinks=False)) == expected)
            row = dict(version=1, kind='provision', phase=phase, sequence=sequence,
                       operation_id=operation_id, dormant_receipt_sha256=dormant_receipt_sha256,
                       publisher_sha=publisher_sha, previous_record_sha256=previous)
            if filename is not None:
                row['filename'] = filename
            if metadata is not None:
                row['file_identity'] = metadata
            if phase == 'completed':
                row.update(state='PROVISIONED_DORMANT', activation_authorized=False)
            raw = json.dumps(row, sort_keys=True, separators=(',', ':')).encode() + b'\n'
            name = f'{sequence:03d}-{phase}.json'
            audit_files[name] = _new_file(operation_fd, name, raw, owner_uid, audit_gid, 0o600)
            previous = hashlib.sha256(raw).hexdigest()  # metadata records only; never credential digests
            sequence += 1
            return row

        record('intent')
        for name in FILENAMES:
            record('intent', filename=name)
            check()
            created[name] = _new_file(config_fd, name, payload[name], owner_uid,
                bridge_gid if name == 'config.json' else audit_gid,
                0o640 if name == 'config.json' else 0o600)
            record('verified', filename=name, metadata=created[name])
        result = record('completed')
        check()
        os.close(operation_fd)
        operation_fd = None
        os.close(namespace_fd)
        namespace_fd = None
        return result
    except BaseException:
        # No compensating mutations, failed-record rewrite, secret-valued errors,
        # lease release, fallback, or automatic recovery after uncertain writes.
        raise TransactionError('provisioning_outcome_uncertain' if claimed
                               else 'provisioning_precondition_failed') from None
    finally:
        close_failed = False
        for fd in (operation_fd, namespace_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    close_failed = True
        if close_failed:
            raise TransactionError('provisioning_outcome_uncertain') from None
