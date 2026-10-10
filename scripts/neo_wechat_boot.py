"""Fixed two-unit boot links; private primitive for the canonical host adapter.

This module grants no deployment authority. The adapter must supply a securely
opened /etc/systemd/system/multi-user.target.wants directory, pin its identity,
and authenticate original leases/receipts via guard. before_effect must confirm a
durable enable_boot/disable_boot intent covering the indicated fixed unit before
each filesystem mutation. Returned metadata must be durably bound into the exact
operation's verified evidence before it can authorize a future disable.

No subprocess, automatic retry, cleanup or target-unit modification occurs. An
uncertain partial operation preserves its links and evidence for reconciliation.
Synthetic tests provide their own temporary directory descriptor and identities.
"""
import os
import stat
import tempfile
from pathlib import Path


UNITS = ('neo-wechat.service', 'neo-wechat.socket')
TARGETS = {name: '/etc/systemd/system/' + name for name in UNITS}
_FIELDS = {'dev', 'ino', 'uid', 'gid', 'mode', 'nlink', 'ctime_ns', 'target'}
_TEST_SEAL = object()


class _SyntheticBootPermission:
    __slots__ = ('identity',)

    def __setattr__(self, name, value):
        raise BootError('boot_startup_authority_unavailable')

    def __init__(self, seal, identity):
        if seal is not _TEST_SEAL:
            raise BootError('boot_startup_authority_unavailable')
        object.__setattr__(self, 'identity', identity)


def startup_allowed():
    """No confirmed-closure issuer is approved: production startup stays blocked."""
    return False


def _synthetic_boot_permission_for_tests(directory):
    """Test-only permission tied to one real temporary directory inode."""
    path = Path(directory).resolve(strict=True)
    if not path.is_relative_to(Path(tempfile.gettempdir()).resolve()) or path == Path(tempfile.gettempdir()).resolve():
        raise BootError('boot_startup_authority_unavailable')
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise BootError('boot_startup_authority_unavailable')
    return _SyntheticBootPermission(_TEST_SEAL, (info.st_dev, info.st_ino))


class BootError(RuntimeError):
    """Constant errors never echo filesystem paths or host exceptions."""


def _require(value):
    if not value:
        raise ValueError('invalid boot evidence')


class BootLinks:
    def __init__(self, directory_fd, identity, *, guard, before_effect, owner_uid=0, owner_gid=0,
                 startup_permission=None):
        self.fd, self.identity = directory_fd, identity
        self.guard, self.before_effect = guard, before_effect
        self.uid, self.gid = owner_uid, owner_gid
        self.startup_permission = startup_permission

    def _check(self):
        _require(callable(self.guard) and self.guard() is None and callable(self.before_effect))
        _require(type(self.fd) is int and self.fd >= 0)
        _require(type(self.identity) is tuple and len(self.identity) == 2
                 and all(type(item) is int and item >= 0 for item in self.identity))
        _require(all(type(value) is int and 0 <= value < 2 ** 32 for value in (self.uid, self.gid)))
        info = os.fstat(self.fd)
        _require(stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == self.identity
                 and info.st_uid == self.uid and info.st_gid == self.gid
                 and stat.S_IMODE(info.st_mode) == 0o755)

    def _read(self, unit):
        try:
            before = os.stat(unit, dir_fd=self.fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        _require(stat.S_ISLNK(before.st_mode) and before.st_nlink == 1
                 and before.st_uid == self.uid and before.st_gid == self.gid)
        target = os.readlink(unit, dir_fd=self.fd)
        after = os.stat(unit, dir_fd=self.fd, follow_symlinks=False)
        _require(before == after and target == TARGETS[unit])
        return {**{name: getattr(after, 'st_' + name) for name in _FIELDS - {'target'}}, 'target': target}

    def _receipt(self, value):
        _require(type(value) is dict and set(value) == set(UNITS))
        for name in UNITS:
            row = value[name]
            _require(type(row) is dict and set(row) == _FIELDS and row['target'] == TARGETS[name])
            _require(all(type(item) is int and 0 <= item < 2 ** 64
                         for key, item in row.items() if key != 'target'))
            _require(stat.S_ISLNK(row['mode']) and row['nlink'] == 1
                     and row['uid'] == self.uid and row['gid'] == self.gid)

    def snapshot(self, expected=None):
        try:
            self._check()
            observed = {name: self._read(name) for name in UNITS}
            if expected is not None:
                self._receipt(expected)
                _require(observed == expected)
            self._check()
            return observed
        except BaseException:
            raise BootError('boot_links_precondition_failed') from None

    def enable(self):
        started = False
        try:
            # A callback returning None or a visible completion file cannot
            # authorize reboot startup. Only temp-directory tests have a issuer.
            _require(type(self.startup_permission) is _SyntheticBootPermission
                     and self.startup_permission.identity == self.identity)
            _require(self.snapshot() == dict.fromkeys(UNITS))
            created = {}
            for unit in UNITS:
                self._check()
                _require({name: self._read(name) for name in UNITS}
                         == {name: created.get(name) for name in UNITS})
                started = True
                _require(self.before_effect('enable_boot', unit) is None)
                self._check()
                os.symlink(TARGETS[unit], unit, dir_fd=self.fd)
                os.chown(unit, self.uid, self.gid, dir_fd=self.fd, follow_symlinks=False)
                os.fsync(self.fd)
                created[unit] = self._read(unit)
                _require(created[unit] is not None)
            return self.snapshot(created)
        except BaseException:
            raise BootError('boot_links_uncertain' if started else 'boot_links_precondition_failed') from None

    def disable(self, recorded):
        started = False
        try:
            self.snapshot(recorded)
            remaining = dict(recorded)
            for unit in UNITS:
                self._check()
                _require({name: self._read(name) for name in UNITS} == remaining)
                started = True
                _require(self.before_effect('disable_boot', unit) is None)
                self._check()
                _require(self._read(unit) == recorded[unit])
                os.unlink(unit, dir_fd=self.fd)
                os.fsync(self.fd)
                remaining[unit] = None
            _require(self.snapshot() == dict.fromkeys(UNITS))
        except BaseException:
            raise BootError('boot_links_uncertain' if started else 'boot_links_precondition_failed') from None
