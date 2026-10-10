"""Read only exact systemd credential permission forms from a read-only mount.

Linux POSIX ACL v2 exposes group mode bits as the ACL mask. A root-owned
0440 file is accepted only with the exact named-service-UID ACL below, never
because its group bits happen to be read-only. No credential values enter errors.
"""
from __future__ import annotations

import errno
import os
from pathlib import Path
import re
import stat
import struct

MAX_CREDENTIAL_BYTES = 65536


class CredentialError(ValueError):
    def __init__(self):
        super().__init__('unsafe_credential')


def _limits(uid, max_bytes):
    if (type(uid) is not int or not 0 < uid < 0xffffffff
            or type(max_bytes) is not int or not 1 <= max_bytes <= MAX_CREDENTIAL_BYTES):
        raise CredentialError()


def validate_credential_metadata(info, acl, uid, *, directory=False,
                                 default_acl=None, max_bytes=MAX_CREDENTIAL_BYTES):
    """Validate systemd's private-owner or exact root/named-UID ACL representation."""
    _limits(uid, max_bytes)
    try:
        mode = stat.S_IMODE(info.st_mode)
        correct_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if not correct_type or default_acl is not None:
            raise CredentialError()
        if not directory and (info.st_nlink != 1 or not 0 <= info.st_size <= max_bytes):
            raise CredentialError()
        permission = 5 if directory else 4
        entries = []
        if acl is None:
            if info.st_uid != uid or mode != permission << 6:
                raise CredentialError()
            model = 'service_owner_read_only'
        else:
            if not isinstance(acl, bytes) or len(acl) != 44 or struct.unpack_from('<I', acl)[0] != 2:
                raise CredentialError()
            entries = list(struct.iter_unpack('<HHI', acl[4:]))
            undefined = 0xffffffff
            expected = [(1, permission, undefined), (2, permission, uid), (4, 0, undefined),
                        (16, permission, undefined), (32, 0, undefined)]
            if (entries != expected or info.st_uid != 0
                    or mode != (permission << 6 | permission << 3)):
                raise CredentialError()
            model = 'root_owner_service_uid_read_acl'
        return {'mode': format(mode, '04o'), 'uid': info.st_uid, 'gid': info.st_gid,
                'acl': entries, 'access_model': model}
    except (AttributeError, TypeError, ValueError, struct.error):
        raise CredentialError() from None


def credential_xattr(fd, name):
    try:
        return os.getxattr(fd, name)
    except OSError as error:
        # ramfs may lack ACL support. Permission/I/O/other failures are not absence.
        if error.errno in (errno.ENODATA, errno.EOPNOTSUPP):
            return None
        raise CredentialError() from None
    except (AttributeError, TypeError, ValueError):
        raise CredentialError() from None


def credential_fd_metadata(fd, uid, *, directory=False, max_bytes=MAX_CREDENTIAL_BYTES):
    try:
        report = validate_credential_metadata(os.fstat(fd), credential_xattr(fd, 'system.posix_acl_access'),
            uid, directory=directory, default_acl=credential_xattr(fd, 'system.posix_acl_default'),
            max_bytes=max_bytes)
        # A file owner could otherwise chmod it back to writable. Inspect the
        # actual descriptor's mount inside the service namespace.
        if not os.fstatvfs(fd).f_flag & os.ST_RDONLY:
            raise CredentialError()
        report['mount_read_only'] = True
        return report
    except (OSError, AttributeError, TypeError, ValueError):
        raise CredentialError() from None


def _directory_fd(directory):
    path = Path(directory)
    if not path.is_absolute() or '..' in path.parts or len(path.parts) < 2:
        raise CredentialError()
    flags = os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    # Linux credential ancestors can be traverse-only (0711). O_PATH pins each
    # ancestor without requiring read permission; the credential directory itself
    # must be readable for exact metadata/xattr validation. Non-Linux fallback is
    # conservative and does not weaken the Linux production boundary.
    ancestor_flags = flags | getattr(os, 'O_PATH', os.O_RDONLY)
    current = os.open('/', ancestor_flags)
    try:
        # Do not allow a symlink at any ancestor, not just the final directory.
        for index, component in enumerate(path.parts[1:], start=1):
            child_flags = flags | os.O_RDONLY if index == len(path.parts)-1 else ancestor_flags
            child = os.open(component, child_flags, dir_fd=current)
            os.close(current)
            current = child
        return current
    except Exception:
        os.close(current)
        raise


def read_credential_with_metadata(directory, name, *, uid=None, max_bytes=MAX_CREDENTIAL_BYTES):
    """Return (bytes, safe metadata); pin directory and file with NOFOLLOW dirfds."""
    uid = os.geteuid() if uid is None else uid
    _limits(uid, max_bytes)
    if not isinstance(name, str) or re.fullmatch(r'[A-Za-z0-9_-]{1,128}', name) is None:
        raise CredentialError()
    dfd = fd = None
    try:
        dfd = _directory_fd(directory)
        directory_report = credential_fd_metadata(dfd, uid, directory=True, max_bytes=max_bytes)
        # NONBLOCK prevents a malicious FIFO from hanging before type validation.
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=dfd)
        file_report = credential_fd_metadata(fd, uid, max_bytes=max_bytes)
        data = bytearray()
        while len(data) <= max_bytes:
            block = os.read(fd, max_bytes + 1 - len(data))
            if not block:
                break
            data.extend(block)
        if len(data) > max_bytes:
            raise CredentialError()
        # Fail closed if metadata changed during the read, even in a test or
        # externally changed mount namespace. Never return partial oversized data.
        if (credential_fd_metadata(fd, uid, max_bytes=max_bytes) != file_report
                or os.fstat(fd).st_size != len(data)):
            raise CredentialError()
        return bytes(data), {'directory': directory_report, 'file': file_report}
    except (OSError, TypeError, ValueError):
        raise CredentialError() from None
    finally:
        if fd is not None:
            os.close(fd)
        if dfd is not None:
            os.close(dfd)


def read_credential(directory, name, *, uid=None, max_bytes=MAX_CREDENTIAL_BYTES):
    return read_credential_with_metadata(directory, name, uid=uid, max_bytes=max_bytes)[0]
