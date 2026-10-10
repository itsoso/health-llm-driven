"""Private encrypted snapshots with a lifetime process lease and durable publication."""
from __future__ import annotations

import copy
import fcntl
import json
import os
import secrets
import stat
import threading
from contextlib import contextmanager
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAX_BYTES = 16 * 1024 * 1024
_MAGIC = b'NEOWX1\x00'


class StoreError(RuntimeError):
    """A constant, non-sensitive failure code."""


def _private(fd, directory=False):
    info = os.fstat(fd)
    correct_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if (not correct_type or info.st_uid != os.geteuid() or info.st_mode & 0o077
            or (not directory and info.st_nlink != 1)):
        raise StoreError('store_permissions')


class Store:
    """path is an intentionally provisioned, owner-only directory, never auto-created.

    Every operation uses lock, including reads. Callers may hold that RLock across
    a transaction and an external action to serialize revocation with launch.
    A write error poisons this instance: uncertain persistence is never retried.
    """
    def __init__(self, path: Path, key: bytes, owner: str):
        if (not isinstance(key, bytes) or len(key) != 32 or not isinstance(owner, str)
                or not owner or len(owner.encode()) > 512):
            raise StoreError('store_configuration')
        self.path, self.owner = Path(path), owner
        self._pid = os.getpid()
        self.lock = threading.RLock()
        self._dirfd = self._lockfd = None
        self._closed = self._poisoned = self._in_transaction = False
        self._cipher = AESGCM(key)
        self._aad = json.dumps(['neo-wechat', 1, owner], separators=(',', ':')).encode()
        try:
            self._dirfd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            _private(self._dirfd, directory=True)
            self._lockfd = os.open('lease.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                                   0o600, dir_fd=self._dirfd)
            _private(self._lockfd)
            try:
                fcntl.flock(self._lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise StoreError('store_locked') from None
            # No state read is permitted before exclusive ownership succeeds.
            self._state = self._load()
        except Exception as exc:
            self.close()
            if isinstance(exc, StoreError):
                raise
            raise StoreError('store_invalid') from None

    def _validate(self, state):
        if (not isinstance(state, dict) or state.get('schema') != 1
                or state.get('owner') != self.owner
                or not isinstance(state.get('messages'), dict)
                or not isinstance(state.get('oauth'), dict)
                or not isinstance(state.get('audit'), list)):
            raise StoreError('store_invalid')

    def _load(self):
        try:
            fd = os.open('state.enc', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self._dirfd)
        except FileNotFoundError:
            return {'schema': 1, 'owner': self.owner, 'binding': None,
                    'messages': {}, 'oauth': {}, 'login': None, 'audit': []}
        with os.fdopen(fd, 'rb') as stream:
            _private(stream.fileno())
            if os.fstat(stream.fileno()).st_size > MAX_BYTES + 64:
                raise StoreError('store_capacity')
            data = stream.read(MAX_BYTES + 65)
        if len(data) < len(_MAGIC) + 28 or not data.startswith(_MAGIC):
            raise StoreError('store_invalid')
        try:
            raw = self._cipher.decrypt(data[len(_MAGIC):len(_MAGIC)+12],
                                       data[len(_MAGIC)+12:], self._aad)
            state = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            self._validate(state)
            return state
        except Exception:
            raise StoreError('store_invalid') from None

    def _available(self):
        if self._closed or self._poisoned or os.getpid() != self._pid:
            raise StoreError('store_unavailable')

    def read(self):
        with self.lock:
            self._available()
            return copy.deepcopy(self._state)

    @contextmanager
    def transaction(self):
        with self.lock:
            self._available()
            if self._in_transaction:
                raise StoreError('store_nested_transaction')
            self._in_transaction = True
            try:
                candidate = copy.deepcopy(self._state)
                yield candidate
                self._validate(candidate)
                try:
                    raw = json.dumps(candidate, ensure_ascii=False, allow_nan=False,
                                     separators=(',', ':')).encode()
                except (ValueError, TypeError, UnicodeError, RecursionError):
                    raise StoreError('store_invalid') from None
                if len(raw) > MAX_BYTES:
                    raise StoreError('store_capacity')
                self._persist(raw)
                self._state = copy.deepcopy(candidate)
            finally:
                self._in_transaction = False

    def _persist(self, raw):
        temporary = '.state-' + secrets.token_hex(16)
        fd = None
        try:
            # Refuse replacement of suspicious existing nodes, even though rename
            # itself would not follow them. Only the private directory is writable.
            try:
                existing = os.open('state.enc', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self._dirfd)
            except FileNotFoundError:
                existing = None
            if existing is not None:
                try:
                    _private(existing)
                finally:
                    os.close(existing)
            nonce = os.urandom(12)
            blob = _MAGIC + nonce + self._cipher.encrypt(nonce, raw, self._aad)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=self._dirfd)
            with os.fdopen(fd, 'wb') as stream:
                fd = None
                stream.write(blob)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(temporary, 'state.enc', src_dir_fd=self._dirfd, dst_dir_fd=self._dirfd)
            os.fsync(self._dirfd)
        except Exception:
            self._poisoned = True
            raise StoreError('store_uncertain') from None
        finally:
            if fd is not None:
                os.close(fd)
            try:
                os.unlink(temporary, dir_fd=self._dirfd)
            except FileNotFoundError:
                pass  # Successful rename already removed the temporary name.

    def close(self):
        with self.lock:
            self._closed = True
            if self._lockfd is not None:
                os.close(self._lockfd)
                self._lockfd = None
            if self._dirfd is not None:
                os.close(self._dirfd)
                self._dirfd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
